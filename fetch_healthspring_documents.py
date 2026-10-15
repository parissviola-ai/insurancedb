"""Collect official 2027 NC EOCs and validate MA segment/county links against CMS."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--landscape', type=Path, required=True)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    source = 'https://www.healthspring.com/medicare/member-resources/eoc'
    with urllib.request.urlopen(source, timeout=30) as response:
        markup = html.unescape(response.read().decode())
    rows = [{k: v[1] for k, v in json.loads(raw).items()} for raw in re.findall(
        r'\{"Year":\[0,2027\],"State":\[0,"North Carolina"\][^{}]*\}', markup)]
    if not rows:
        raise ValueError('Official NC EOC catalog could not be parsed')
    with zipfile.ZipFile(args.landscape) as archive:
        filename = next(n for n in archive.namelist() if n.endswith('.csv'))
        cms = list(csv.DictReader(io.TextIOWrapper(archive.open(filename), encoding='utf-8-sig')))

    def fetch(row):
        path = row['PDF_URL']
        if not re.fullmatch(r'/static/docs/medicare/plans/2027/eoc-[a-z0-9-]+\.pdf', path):
            raise ValueError('Unexpected document path')
        url = 'https://www.healthspring.com' + path
        pdf = args.cache / path.split('/')[-1]
        if not pdf.exists():
            with urllib.request.urlopen(url, timeout=40) as response:
                pdf.write_bytes(response.read())
        text_file = pdf.with_suffix('.txt')
        subprocess.run(['pdftotext', '-layout', str(pdf), str(text_file)], check=True)
        text = text_file.read_text()
        name = row['Plan_Name'].replace(' 2027 EOC', '')
        if '2027' not in text[:1500] or name not in re.sub(r'\s+', ' ', text[:1800]):
            raise ValueError('Wrong document year or plan: ' + path)
        result = {'year': 2027, 'state': 'NC', 'name': name, 'kind': 'evidence', 'url': url,
                  'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(), 'bytes': pdf.stat().st_size,
                  'retrieved_at': datetime.datetime.fromtimestamp(pdf.stat().st_mtime, datetime.timezone.utc).isoformat()}
        match = re.search(r'eoc-([hr]\d{4})-(\d{3})-(\d{3})\.pdf', path)
        if match:
            contract, pbp, segment = match.groups()
            identifier = contract.upper() + '-' + pbp + '-' + segment
            # Zero-segment covers often print only contract/PBP in their document code.
            printed = re.escape(contract) + r'[-_]' + pbp + (r'(?:[-_]000)?\b' if segment == '000' else r'[-_]' + segment)
            if not re.search(printed, text, re.I):
                raise ValueError('Wrong printed plan code: ' + identifier)
            records = [c for c in cms if c['Contract Year'] == '2027'
                       and c['State Territory Abbreviation'] == 'NC' and c['Contract ID'] == contract.upper()
                       and c['Plan ID'] == pbp and int(c['Segment ID']) == int(segment)]
            counties = sorted({c['County Name'] for c in records})
            if counties != sorted(c.strip() for c in row['Counties'].split(',')):
                raise ValueError('CMS/catalog county disagreement: ' + identifier)
            result.update(cms_id=identifier, counties=counties, business='Medicare Advantage',
                          cms_match='CMS 2027 contract/PBP/segment and county list match')
        else:
            result.update(business='Part D', cms_id=None, counties=None,
                          cms_match='Shared statewide PDP document; exact regional CMS plan linkage requires review')
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        documents = list(pool.map(fetch, rows))
    output = {'source_url': source + '#2027', 'state': 'NC', 'year': 2027, 'documents': documents,
              'scope_note': 'Coverage-document library. Only True Choice H7849-113-001 is imported into plan comparison. Other EOCs require benefit/formulary integration and 2027 network confirmation.'}
    target = Path(__file__).resolve().parent / 'docs/data/healthspring-documents.json'
    target.write_text(json.dumps(output, indent=2) + '\n')
    print('Verified', len(documents), 'official EOCs;', sum(d['business'] == 'Medicare Advantage' for d in documents), 'exact MA segment/county matches.')


if __name__ == '__main__':
    main()
