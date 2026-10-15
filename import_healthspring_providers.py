"""Extract conservative office candidates from the verified 2027 NC PPO directory."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import fitz


def extract(pdf_path):
    doc = fitz.open(pdf_path)
    rows = []; names = {}; skipped = 0
    for page_index, page in enumerate(doc):
        blocks = page.get_text('blocks')
        header = ' '.join(b[4] for b in blocks if b[1] < 46).upper()
        if 'PROVIDER' not in header or 'PHARMACY' in header:
            continue
        hospital = 'HOSPITALS' in header
        for block in blocks:
            text = block[4]
            lines = [s.strip() for s in text.splitlines() if s.strip()]
            city = next((i for i, s in enumerate(lines) if re.search(r', NC \d{5}', s)), None)
            phone = next((re.search(r'\(\d{3}\) \d{3}-\d{4}', s).group() for s in lines if re.search(r'\(\d{3}\) \d{3}-\d{4}', s)), '')
            if city is None or not phone:
                continue
            address = next((i for i, s in enumerate(lines[:city]) if re.match(r'^\d+\s+\S', s)), None)
            if address is None or address == 0:
                skipped += 1; continue
            npi = next(iter(re.findall(r'NPI:\s*(\d{10})', text)), '')
            first = lines[0]
            organization = bool(re.search(r'\b(?:LLC|PLLC|INC|MEDICAL|HEALTH|HOSPITAL|ASSOCIATES|CLINIC)\b', first, re.I))
            person = not organization and bool(re.match(r"^[A-Za-z'’ .-]+,\s+[A-Za-z]", first)) and not hospital
            if person:
                name = re.sub(r'[«éë]+|\s+[PxY]+$', '', first).strip()
                if npi: names[npi] = name
                kind = 'provider'
            elif npi in names:
                name = names[npi]; kind = 'provider'
            elif hospital:
                name = ' '.join(lines[:address]); kind = 'facility'
                # Printed hospital listings commonly repeat their organization name.
                words = name.split()
                if len(words) % 2 == 0 and words[:len(words)//2] == words[len(words)//2:]:
                    name = ' '.join(words[:len(words)//2])
            else:
                skipped += 1; continue
            office = ', '.join([' '.join(lines[address:city]), lines[city]])
            key = hashlib.sha256((kind + name + office).encode()).hexdigest()[:20]
            rows.append({'kind': kind, 'name': name, 'npi': npi, 'office': office, 'phone': phone,
                         'specialty': 'Hospital' if hospital else 'PDF provider listing',
                         'locationId': key, 'personId': npi or key, 'page': page_index + 1,
                         'directory_pdf': True, 'source_url': 'https://www.healthspring.com/static/docs/medicare/plans/2027/provider-pharmacy-directory-north-carolina-ppo.pdf#page=' + str(page_index + 1),
                         'directory_date': '2026-09-23', 'plan_ids': ['H7849-113-001'],
                         'restrictions': 'Not accepting new patients per PDF.' if 'Does not accept new patients' in text else 'Confirm office and current availability.'})
    unique = {(r['kind'], r['name'], r['office']): r for r in rows}
    return list(unique.values()), skipped


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pdf',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parent
    plan=json.loads((root/'docs/data/healthspring.json').read_text())['plans'][0]
    expected=next(d['sha256'] for d in plan['documents'] if d['kind']=='provider_directory')
    if hashlib.sha256(args.pdf.read_bytes()).hexdigest()!=expected:
        raise ValueError('Directory does not match the verified 2027 PPO source')
    rows, skipped=extract(args.pdf)
    if len(rows)<1000 or not any(r['kind']=='facility' for r in rows):raise ValueError('Insufficient extraction')
    compact=[{k:r[k] for k in ['kind','name','npi','office','phone','page','locationId','restrictions']} for r in rows]
    output={'source_url':'https://www.healthspring.com/static/docs/medicare/plans/2027/provider-pharmacy-directory-north-carolina-ppo.pdf','plan_ids':['H7849-113-001'],'state':'NC','year':2027,'directory_date':'2026-09-23','source_sha256':hashlib.sha256(args.pdf.read_bytes()).hexdigest(),
            'rows':compact,'skipped_blocks':skipped,'scope_note':'Conservative NC PPO PDF candidates for True Choice; incomplete extraction. Suggestions are dated listings, not live network verification. Other states and HMO directories are not indexed.'}
    (Path(__file__).resolve().parent/'docs/data/healthspring-providers.json').write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n')
    print('Provider/facility candidates',len(rows),'skipped',skipped)


if __name__=='__main__':main()
