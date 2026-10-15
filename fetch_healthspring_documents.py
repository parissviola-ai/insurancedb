"""Collect official 2027 EOCs for target states and cross-check MA segments with CMS."""
import argparse
import concurrent.futures
import csv
import datetime
import hashlib
import html
import io
import json
from pathlib import Path
import re
import subprocess
import urllib.request
import zipfile

STATES = {'NC': 'North Carolina', 'SC': 'South Carolina', 'GA': 'Georgia', 'FL': 'Florida',
          'AL': 'Alabama', 'TN': 'Tennessee', 'VA': 'Virginia', 'KY': 'Kentucky',
          'LA': 'Louisiana', 'TX': 'Texas', 'OH': 'Ohio', 'PA': 'Pennsylvania',
          'DE': 'Delaware', 'MI': 'Michigan', 'NY': 'New York'}


def catalog_rows(markup, states):
    names = {STATES[code]: code for code in states}
    rows = [{k: v[1] for k, v in json.loads(raw).items()} for raw in re.findall(
        r'\{"Year":\[0,2027\][^{}]*\}', html.unescape(markup))]
    return [dict(row, state_code=names[row['State']]) for row in rows if row['State'] in names]


def cms_key(row):
    return row['State Territory Abbreviation'], f"{row['Contract ID']}-{int(row['Plan ID']):03d}-{int(row['Segment ID']):03d}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--landscape', type=Path, required=True)
    parser.add_argument('--states', nargs='+', choices=list(STATES), default=list(STATES))
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    source = 'https://www.healthspring.com/medicare/member-resources/eoc'
    with urllib.request.urlopen(source, timeout=30) as response:
        rows = catalog_rows(response.read().decode(), args.states)
    if not rows:
        raise ValueError('Official EOC catalog could not be parsed')
    with zipfile.ZipFile(args.landscape) as archive:
        filename = next(n for n in archive.namelist() if n.endswith('.csv'))
        cms = list(csv.DictReader(io.TextIOWrapper(archive.open(filename), encoding='utf-8-sig')))
    indexed = {}
    for record in cms:
        if record['Contract Year'] == '2027' and record['State Territory Abbreviation'] in args.states:
            indexed.setdefault(cms_key(record), []).append(record)

    def download(path):
        try:
            if not re.fullmatch(r'/static/docs/medicare/plans/2027/eoc-[a-z0-9-]+\.pdf', path):
                raise ValueError('Unexpected document path')
            url = 'https://www.healthspring.com' + path
            pdf = args.cache / path.split('/')[-1]
            if not pdf.exists():
                with urllib.request.urlopen(url, timeout=40) as response:
                    pdf.write_bytes(response.read())
            text_file = pdf.with_suffix('.txt')
            subprocess.run(['pdftotext', '-layout', str(pdf), str(text_file)], check=True)
            return path, {'text': text_file.read_text(), 'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
                          'bytes': pdf.stat().st_size, 'retrieved_at': datetime.datetime.fromtimestamp(pdf.stat().st_mtime, datetime.timezone.utc).isoformat()}
        except Exception as error:
            return path, {'error': str(error)}

    paths = sorted({r['PDF_URL'] for r in rows})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        downloads = dict(pool.map(download, paths))
    documents = []
    for row in rows:
        path, state = row['PDF_URL'], row['state_code']
        downloaded = downloads[path]
        name = row['Plan_Name'].replace(' 2027 EOC', '')
        result = {'year': 2027, 'state': state, 'name': name, 'kind': 'evidence',
                  'url': 'https://www.healthspring.com' + path,
                  **{k: v for k, v in downloaded.items() if k != 'text'}}
        issues = []
        source_notes = []
        text = downloaded.get('text', '')
        if downloaded.get('error'):
            issues.append('Download/text extraction failed: ' + downloaded['error'])
        elif '2027' not in text[:1500] or name not in re.sub(r'\s+', ' ', text[:1800]):
            issues.append('Printed year or plan name requires review')
        match = re.search(r'eoc-([hr]\d{4})-(\d{3})-(\d{3})\.pdf', path)
        if match:
            contract, pbp, segment = match.groups()
            identifier = contract.upper() + '-' + pbp + '-' + segment
            printed = re.escape(contract) + r'[-_]' + pbp + (r'(?:[-_]000)?\b' if segment == '000' else r'[-_]' + segment)
            if text and not re.search(printed, text, re.I):
                issues.append('Printed contract/PBP/segment requires review')
            records = indexed.get((state, identifier), [])
            counties = sorted({c['County Name'] for c in records})
            source_counties = sorted(c.strip() for c in row.get('Counties', '').split(',') if c.strip())
            if not records:
                issues.append('No exact CMS 2027 state/contract/PBP/segment record')
            elif counties != source_counties:
                printed_area = re.search(r'Our service area includes these counties in [^:]+:\s*(.+?)(?:\.\s|\nIf you move)', text, re.S)
                printed_counties = sorted(c.strip() for c in re.sub(r'\s+', ' ', printed_area[1]).split(',')) if printed_area else []
                if printed_counties == counties:
                    source_notes.append('EOC-page county metadata differs; printed EOC service area and CMS agree. Use the CMS/PDF county list.')
                else:
                    issues.append('CMS and EOC-page county lists differ')
            result.update(cms_id=identifier, counties=counties, source_counties=source_counties,
                          business='Medicare Advantage', cms_match='Requires review' if issues else 'CMS 2027 contract/PBP/segment and county list match')
        else:
            business = 'Part D' if '(PDP)' in name else 'Medicare Advantage'
            if business != 'Part D':
                issues.append('MA document path has no identifiable contract/PBP/segment')
            result.update(business=business, cms_id=None, counties=None,
                          cms_match='Shared statewide PDP document; regional CMS plan linkage requires review')
        result['source_notes'] = source_notes
        result.update(verification_status='Needs review' if issues else 'Verified', issues=issues)
        documents.append(result)

    covered = {(d['state'], d['cms_id']) for d in documents if d['cms_id'] and d['verification_status'] == 'Verified'}
    missing = []
    for key, records in sorted(indexed.items()):
        r = records[0]
        is_healthspring = 'healthspring' in (r['Plan Name'] + ' ' + r['Organization Marketing Name']).lower()
        if is_healthspring and r['Contract Category Type'] in ['MA', 'MA-PD', 'SNP'] and key not in covered:
            missing.append({'state': key[0], 'cms_id': key[1], 'name': r['Plan Name'],
                            'counties': sorted({c['County Name'] for c in records}),
                            'reason': 'No verified matching EOC in the collected catalog'})
    summaries = []
    for state in args.states:
        docs = [d for d in documents if d['state'] == state]
        ma = [d for d in docs if d['business'] == 'Medicare Advantage']
        summaries.append({'state': state, 'ma_segments': len(ma),
                          'verified_ma_segments': sum(d['verification_status'] == 'Verified' for d in ma),
                          'pdp_documents': sum(d['business'] == 'Part D' for d in docs),
                          'needs_review': sum(d['verification_status'] != 'Verified' for d in docs),
                          'cms_ma_without_verified_eoc': sum(m['state'] == state for m in missing)})
    output = {'source_url': source + '#2027', 'states': args.states, 'year': 2027,
              'cms_source_url': 'https://www.cms.gov/files/zip/cy2027-landscape-202609-1.zip',
              'cms_archive_sha256': hashlib.sha256(args.landscape.read_bytes()).hexdigest(),
              'documents': documents, 'state_summary': summaries, 'missing_eocs': missing,
              'unique_pdf_count': len(downloads),
              'scope_note': 'Official source-document library across target states, not additional ranked results. Only the NC True Choice pilot has benefits/formulary integration. Source discrepancies stay flagged. Provider-network confirmation is separate.'}
    target = Path(__file__).resolve().parent / 'docs/data/healthspring-documents.json'
    target.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(summaries, indent=2))
    print('Documents', len(documents), 'unique PDFs', len(downloads), 'CMS MA gaps', len(missing))
    for d in documents:
        if d['issues']:
            print('REVIEW', d['state'], d['cms_id'], d['issues'])


if __name__ == '__main__':
    main()
