"""Import the verified NC 2027 pilot from official PDFs and CMS county data.

Only this exact contract/PBP/segment is imported. No historical network is reused.
"""
import argparse
import csv
import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import urllib.request
import zipfile
from healthspring_data import parse_formulary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', required=True, type=Path)
    parser.add_argument('--landscape', required=True, type=Path)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parent
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    base = 'https://www.healthspring.com/static/docs/medicare/plans/2027/'
    documents = []
    texts = {}
    for kind, filename in [('benefits', 'sb-h7849-113-001.pdf'),
                           ('evidence', 'eoc-h7849-113-001.pdf'),
                           ('formulary', 'formulary-mapd.pdf'),
                           ('provider_directory', 'provider-pharmacy-directory-north-carolina-ppo.pdf')]:
        target = args.cache / filename
        if not target.exists():
            with urllib.request.urlopen(base + filename, timeout=40) as response:
                target.write_bytes(response.read())
        text_path = target.with_suffix('.txt')
        subprocess.run(['pdftotext', '-layout', str(target), str(text_path)], check=True)
        texts[kind] = text_path.read_text()
        if '2027' not in texts[kind][:1200]:
            raise ValueError('Document year mismatch: ' + filename)
        documents.append({'kind': kind, 'url': base + filename,
                          'page_url': 'https://shop.healthspringmedicare.com/28262/37119/plan/1TT7MDD1LZ?planYear=2027',
                          'retrieved_at': now, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    for kind in ['benefits', 'evidence', 'formulary']:
        if not re.search(r'H7849[-_]113[-_]001', texts[kind]):
            raise ValueError('Document does not identify the pilot plan: ' + kind)
    if 'HealthSpring True Choice (PPO)' not in texts['provider_directory'][:6000]:
        raise ValueError('Wrong provider directory')
    zipmap = json.loads((root / 'docs/data/zip-counties.json').read_text())
    county_codes = {(c['state'], c['name']): c['code'] for values in zipmap.values() for c in values}
    with zipfile.ZipFile(args.landscape) as archive:
        filename = next(n for n in archive.namelist() if n.endswith('.csv'))
        records = list(csv.DictReader(io.TextIOWrapper(archive.open(filename), encoding='utf-8-sig')))
    counties = sorted({r['County Name'] for r in records if r['Contract Year'] == '2027'
                       and r['State Territory Abbreviation'] == 'NC' and r['Contract ID'] == 'H7849'
                       and r['Plan ID'] == '113' and r['Segment ID'] == '1'})
    expected = {'Alexander', 'Anson', 'Cabarrus', 'Catawba', 'Cleveland', 'Gaston', 'Iredell',
                'Lincoln', 'Mecklenburg', 'Rowan', 'Union'}
    if set(counties) != expected or not all(name in texts['benefits'][:1500] for name in counties):
        raise ValueError('CMS and PDF service areas disagree')
    sb_url = base + 'sb-h7849-113-001.pdf'
    metrics = {}
    def metric(key, amount, period, marker, notes, pattern):
        text = texts['benefits']
        pos = text.find(marker)
        if pos < 0 or not re.search(pattern, re.sub(r'\s+', ' ', text[pos:pos + 1000])):
            raise ValueError('Benefit source changed: ' + key)
        metrics[key] = {'amount': amount, 'period': period, 'notes': notes,
                        'source_url': sb_url + '#page=' + str(text[:pos].count('\f') + 1),
                        'status': 'Source amount extracted'}
    metric('premium', 0, 'month', 'Monthly Plan Premium', 'Part B premium still applies.', r'\$0 per month')
    metric('moop', 7100, 'year', 'Maximum Out-of-Pocket',
           'In-network medical maximum; Part D and excluded services do not count. Combined in/out-of-network maximum is $10,100.', r'\$7,100')
    metric('dental', 800, 'year', 'Maximum Coverage Amount',
           '$800 shared yearly preventive/comprehensive allowance, in/out-of-network combined. Any US-licensed dentist; billing and reimbursement rules apply.', r'\$800 yearly allowance')
    metric('specialist', 45, 'visit', 'Specialists', 'In-network specialist copay. Read service-specific rules.', r'\$45 copay')
    metric('hospital', 2000, '7-day stay', 'Inpatient Hospital Coverage',
           'One modeled in-network seven-day admission: $400/day for days 1–5; $0/day for days 6–90.', r'\$400 copay per day for.{0,100}days 1-5\..{0,100}\$0 copay per day for days 6-90')
    metric('vision', 100, 'year', 'Routine Eyewear',
           '$100 yearly eyewear allowance, in/out-of-network combined, for one set. Read eligible-item rules.', r'\$100 yearly allowance')
    costs = {'tiers': {}, 'supply_days': 30, 'pharmacy_type': 'Preferred network retail pharmacy',
             'stage': 'Initial coverage', 'extra_help': 'Standard schedule without Extra Help',
             'conditions': 'Preferred network retail, 30-day supply, initial coverage. Standard retail Tier 1 is $10 and Tier 2 is $20; mail-order and longer supplies may differ. Exact pharmacy, coverage stage and Extra Help require confirmation.',
             'deductible_note': '$0 deductible for Tiers 1–2. $500 deductible for Tiers 3–5; full drug cost applies until the deductible is met.'}
    drug_page = texts['benefits'].split('\f')
    page_number, schedule = next((i + 1, page) for i, page in enumerate(drug_page) if 'Initial Coverage Stage' in page and 'Retail Pharmacy' in page)
    for tier, expected_cost in [('1', '$0'), ('2', '$8'), ('3', '20%'), ('4', '25%'), ('5', '28%')]:
        match = re.search(r'Tier ' + tier + r'\s+30-day\s+(\$\d+|\d+%)\s+(\$\d+|\d+%)\s+(\$\d+|\d+%)\s+(\$\d+|\d+%)', schedule)
        if not match or match[3] != expected_cost:
            raise ValueError('Retail tier schedule changed')
        costs['tiers'][tier] = {'type': 'copay' if expected_cost.startswith('$') else 'coinsurance',
                                'display': expected_cost + (' per prescription' if expected_cost.startswith('$') else ' of drug cost'),
                                'source_url': sb_url + '#page=' + str(page_number)}
    rows = parse_formulary(texts['formulary'])
    atorvastatin = next((r for r in rows if r['name'] == 'atorvastatin'), None)
    if len(rows) < 1500 or not atorvastatin or atorvastatin['tier'] != '1' or atorvastatin['restrictions'] != 'QL (30/30)':
        raise ValueError('Formulary extraction validation failed')
    if not re.search(r'Hearing Aids\s+Not covered', texts['benefits']):
        raise ValueError('Hearing benefit changed')
    plan = {'id': 'healthspring-H7849-113-001-2027', 'locator': 'H7849-113-001-2027',
            'cms_id': 'H7849-113-001', 'name': 'HealthSpring True Choice (PPO)', 'carrier': 'HealthSpring',
            'year': 2027, 'business': 'Medicare Advantage', 'state': 'NC', 'county_names': counties,
            'counties': [county_codes[('NC', name)] for name in counties], 'premium': '$0',
            'benefit_metrics': metrics, 'benefit_review_notes': {'otc': 'No OTC allowance verified in the checked plan sources; this is not a confirmed $0 benefit.', 'transportation': 'Annual free routine rides remain unverified. Ambulance and transplant travel benefits are separate.'}, 'benefit_unavailable': {'hearing': 'Not covered — routine hearing aids'},
            'special_needs': False, 'ma_only': False, 'drug_costs': costs, 'documents': documents,
            'network': [], 'directory_base_url': 'https://data.healthspring.healthlx.com:8003/',
            'network_mapping_status': '2027 network mapping unavailable; older-year records are not used.',
            'provider_search_url': 'https://www.healthspring.com/medicare/member-resources/provider-pharmacy-directories',
            'source_url': 'https://www.cms.gov/files/zip/cy2027-landscape-202609-1.zip',
            'verified_on': now[:10],
            'scope_note': 'HealthSpring is the former Cigna Medicare business. Pilot: this one 2027 NC plan only. Formulary entries may group strengths/forms; confirm the exact prescription in the source. OTC and routine transportation amounts are unverified. Live 2027 provider/facility coverage is not connected.'}
    output = {'plans': [plan], 'county_options': [{'code': county_codes[('NC', name)], 'name': name, 'state': 'NC'} for name in counties],
              'formularies': {base + 'formulary-mapd.pdf': {'rows': rows, 'retrieved_at': now}},
              'retrieved_at': now, 'availability_sha256': hashlib.sha256(args.landscape.read_bytes()).hexdigest()}
    (root / 'docs/data/healthspring.json').write_text(json.dumps(output, ensure_ascii=False, separators=(',', ':')) + '\n')
    print('Imported one plan,', len(counties), 'counties,', len(rows), 'formulary candidates. Atorvastatin:', atorvastatin)


if __name__ == '__main__':
    main()
