"""Collect target-state 2027 formularies; link MA segments using printed applicability IDs."""
import argparse
import concurrent.futures
import csv
import csv
import datetime
import hashlib
import io
import html
import json
from pathlib import Path
import re
import subprocess
import urllib.request
import zipfile
from fetch_healthspring_documents import STATES, catalog_rows, cms_key
from healthspring_data import parse_formulary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--landscape', type=Path, required=True)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    source = 'https://www.healthspring.com/medicare/member-resources/drug-list-formulary'
    with urllib.request.urlopen(source, timeout=30) as response:
        markup = response.read().decode()
        entries = catalog_rows(markup, list(STATES))
    if not entries:
        raise ValueError('No target-state formulary entries parsed')
    root = Path(__file__).resolve().parent
    eocs = json.loads((root / 'docs/data/healthspring-documents.json').read_text())
    for eoc in eocs['documents']:
        if eoc['business'] != 'Part D':
            continue
        filename = {'HealthSpring Assurance Rx (PDP)': 'formulary-assurance.pdf',
                    'HealthSpring Extra Rx (PDP)': 'formulary-extra.pdf'}.get(eoc['name'])
        if not filename:
            continue
        path = '/static/docs/medicare/plans/2027/' + filename
        if path not in html.unescape(markup):
            raise ValueError('PDP formulary link not found on official page')
        entries.append({'state_code': eoc['state'], 'Plan_Name': eoc['name'] + ' 2027 Drug List', 'PDF_URL': path})
    def download(path):
        if not re.fullmatch(r'/static/docs/medicare/plans/2027/formulary-[a-z0-9-]+\.pdf', path):
            raise ValueError('Unexpected formulary path')
        pdf = args.cache / path.split('/')[-1]
        url = 'https://www.healthspring.com' + path
        if not pdf.exists():
            with urllib.request.urlopen(url, timeout=40) as response:
                pdf.write_bytes(response.read())
        txt = pdf.with_suffix('.txt')
        subprocess.run(['pdftotext', '-layout', str(pdf), str(txt)], check=True)
        text = txt.read_text()
        if '2027' not in text[:1800]:
            raise ValueError('Formulary year mismatch')
        ids = sorted(set(re.findall(r'\b[HRS]\d{4}-\d{3}-\d{3}\b', text)))
        rows = parse_formulary(text)
        if len(rows) < 500:
            raise ValueError('Insufficient formulary candidates: ' + path)
        return url, {'url': url, 'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
                     'retrieved_at': datetime.datetime.fromtimestamp(pdf.stat().st_mtime, datetime.timezone.utc).isoformat(),
                     'bytes': pdf.stat().st_size, 'applicable_cms_ids': ids, 'rows': rows,
                     'formulary_id': next(iter(re.findall(r'Submission ID\s+(\d+)', text)), None)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        documents = dict(pool.map(download, sorted({row['PDF_URL'] for row in entries})))
    with zipfile.ZipFile(args.landscape) as archive:
        name = next(n for n in archive.namelist() if n.endswith('.csv'))
        cms = list(csv.DictReader(io.TextIOWrapper(archive.open(name), encoding='utf-8-sig')))
    indexed = {}
    for row in cms:
        if row['Contract Year'] == '2027' and row['State Territory Abbreviation'] in STATES:
            indexed.setdefault(cms_key(row), row)
    root = Path(__file__).resolve().parent
    eocs = json.loads((root / 'docs/data/healthspring-documents.json').read_text())
    links = {}
    for eoc in eocs['documents']:
        if eoc['business'] != 'Medicare Advantage' or not eoc['cms_id']:
            continue
        key = eoc['state'] + ':' + eoc['cms_id']
        record = indexed.get((eoc['state'], eoc['cms_id']))
        if record and record['Part D Coverage Indicator'] == 'No':
            links[key] = {'status': 'No included Part D', 'urls': []}
            continue
        source_options = [r for r in entries if r['state_code'] == eoc['state']
                          and r['Plan_Name'].replace(' 2027 Drug List', '') == eoc['name']]
        urls = sorted({'https://www.healthspring.com' + r['PDF_URL'] for r in source_options})
        verified = [u for u in urls if eoc['cms_id'] in documents[u]['applicable_cms_ids']]
        links[key] = {'status': 'Exact 2027 CMS segment listed in formulary' if len(verified) == 1 else 'Needs review',
                      'urls': verified if len(verified) == 1 else [], 'source_candidate_urls': urls}
    output = {'year': 2027, 'states': list(STATES), 'source_url': source + '#2027',
              'source_entries': [{'state': r['state_code'], 'name': r['Plan_Name'].replace(' 2027 Drug List', ''),
                                  'url': 'https://www.healthspring.com' + r['PDF_URL']} for r in entries],
              'documents': documents, 'plan_links': links,
              'scope_note': 'Formulary text yields candidates, not confirmed exact-prescription coverage. Plan links require explicit printed CMS segment applicability and matching state/plan name. Costs and provider networks are separate.'}
    (root / 'docs/data/healthspring-formularies.json').write_text(json.dumps(output, ensure_ascii=False, separators=(',', ':')) + '\n')
    with (root / 'docs/data/healthspring-ma-segments.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['State', 'Year', 'CMS plan/segment', 'Plan name', 'CMS counties', 'EOC URL', 'Document status', 'Source notes', 'Formulary status', 'Formulary URLs'])
        for eoc in eocs['documents']:
            if eoc['business'] == 'Medicare Advantage':
                mapping = links.get(eoc['state'] + ':' + str(eoc['cms_id']), {})
                writer.writerow([eoc['state'], 2027, eoc['cms_id'], eoc['name'], '; '.join(eoc['counties'] or []), eoc['url'], eoc['verification_status'], '; '.join(eoc.get('source_notes', []) + eoc['issues']), mapping.get('status', 'Unverified'), '; '.join(mapping.get('urls', []))])
    print('Unique formularies', len(documents), 'source state/plan entries', len(entries),
          'candidate rows', sum(len(d['rows']) for d in documents.values()))
    from collections import Counter
    print('MA links', dict(Counter(v['status'] for v in links.values())))
    for k, v in links.items():
        if v['status'] == 'Needs review': print('REVIEW', k, v['source_candidate_urls'])


if __name__ == '__main__':
    main()
