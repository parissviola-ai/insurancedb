"""Extract the explicit 30-day network-retail initial-coverage tier column."""
import re


def parse_drug_costs(text,url):
    start=text.find('Initial Coverage Stage')
    if start<0:return {}
    end=text.find('Catastrophic Coverage',start)
    if end<0:return {}
    section=text[start:end]
    flat=re.sub(r'\s+',' ',section)
    if '30-Day Supply Network 100-Day Supply Network Retail Pharmacy Mail Order' not in flat:
        return {}
    tiers={}
    for match in re.finditer(r'^\s*Tier ([1-5]):[^\n]*?(\$[\d,.]+ per prescription|[\d.]+% of the total cost)',section,re.M):
        tier=match.group(1);raw=match.group(2)
        page=text[:start+match.start()].count('\f')+1
        tiers[tier]={'type':'copay' if raw.startswith('$') else 'coinsurance',
                     'display':raw,'source_url':url+'#page='+str(page)}
    if not tiers:return {}
    # Preserve deductible conditions; never infer deductible completion.
    before=text[max(0,start-1100):start]
    marker=before.rfind('Pharmacy (Part D)')
    deductible=re.sub(r'\s+',' ',before[marker:]).strip() if marker>=0 else 'Deductible rules need review in the plan documents.'
    deductible_amount=re.search(r'\$([\d,]+)\s+for Tiers\s+([1-5](?:\s*[-–]\s*[1-5])?)',deductible)
    if deductible_amount:
        deductible='Part D deductible: $'+deductible_amount.group(1)+' for Tiers '+deductible_amount.group(2)+'. Extra Help may change the deductible.'
    return {'tiers':tiers,'supply_days':30,'pharmacy_type':'Network retail pharmacy',
            'stage':'Initial coverage','extra_help':'Standard schedule without Extra Help',
            'deductible_note':deductible,
            'conditions':'Assumes exact drug is covered and any applicable deductible is satisfied. Pharmacy participation and actual price are not verified. Extra Help, insulin, vaccine, and coverage-stage rules may change your cost.'}
