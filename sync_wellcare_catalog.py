"""Join official CMS 2027 county availability to captured Wellcare directory options.
No credentials or provider records are persisted. Network candidates require review.
"""
import argparse
import csv
import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

STATES = 'NC SC GA FL AL TN VA KY LA TX OH PA DE MI NY'.split()
SOURCE = 'https://www.cms.gov/files/zip/cy2027-landscape-202609-1.zip'


def normalize(value):
    return re.sub(r'\s+', ' ', value.strip()).casefold()


def build(landscape, options):
    captured = json.loads(Path(options).read_text())
    states = captured['states'] if isinstance(captured, dict) else captured
    if any(row.get('error') for row in states):
        raise ValueError('Directory snapshot contains failed state requests')
    if set(row['state'] for row in states) != set(STATES):
        raise ValueError('Directory snapshot must include all 15 states')
    products = {row['state']: row['products'] for row in states}
    plans = {}
    with zipfile.ZipFile(landscape) as archive:
        csv_name = next(name for name in archive.namelist() if name.endswith('.csv'))
        with io.TextIOWrapper(archive.open(csv_name), encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                state = row['State Territory Abbreviation']
                if row['Contract Year'] != '2027' or state not in STATES:
                    continue
                if row['Parent Organization Name'] != 'Centene Corporation':
                    continue
                if not any('wellcare' in row[key].casefold() for key in ['Plan Name', 'Organization Marketing Name']):
                    continue
                key = (state, row['Contract Plan Segment ID'])
                if key not in plans:
                    name, contract = row['Plan Name'], row['Contract ID']
                    expected = normalize(name + (' - ' + contract if row['Contract Category Type'] != 'PDP' else ''))
                    matches = [p for p in products[state] if normalize(p['name']) == expected]
                    plans[key] = {
                        'state': state, 'year': 2027, 'contract': contract,
                        'pbp': row['Plan ID'], 'segment': row['Segment ID'],
                        'cms_id': '-'.join([contract, row['Plan ID'], row['Segment ID']]),
                        'name': name, 'category': row['Contract Category Type'],
                        'plan_type': row['Plan Type'], 'sanctioned': row['Sanctioned Plan'],
                        'counties': [], 'network_candidates': matches,
                        'network_status': 'Unique name/contract candidate — verify plan selection' if len(matches) == 1 else 'Ambiguous — review' if matches else 'No exact directory candidate',
                        'source_url': SOURCE,
                    }
                if row['County Name'] not in plans[key]['counties']:
                    plans[key]['counties'].append(row['County Name'])
    result = list(plans.values())
    for plan in result:
        plan['counties'].sort()
    return {
        'retrieved_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'cms_source_url': SOURCE,
        'cms_archive_sha256': hashlib.sha256(Path(landscape).read_bytes()).hexdigest(),
        'directory_retrieved_at': captured.get('retrieved_at') if isinstance(captured, dict) else None,
        'limitations': 'County names, not county FIPS. Exact name/contract matches are candidates, not verified CMS-to-network mappings. PDP All Counties is state-level. Supplemental benefits and provider participation are not inferred.',
        'plans': result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--landscape', required=True)
    parser.add_argument('--network-options', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = build(args.landscape, args.network_options)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'wellcare-2027-catalog.json').write_text(json.dumps(result, indent=2) + '\n')
    with (out / 'wellcare-2027-service-areas.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['State', 'Year', 'CMS plan ID', 'Plan name', 'Category', 'County', 'Candidate product networks', 'Match status', 'CMS source'])
        for plan in result['plans']:
            for county in plan['counties']:
                writer.writerow([plan['state'], plan['year'], plan['cms_id'], plan['name'], plan['category'], county, '; '.join(p['id'] for p in plan['network_candidates']), plan['network_status'], SOURCE])
    print(f"Exported {len(result['plans'])} state/plan/segment records")


if __name__ == '__main__':
    main()
