"""Conservative extraction of explicitly stated Summary of Benefits amounts."""
import re


def parse_benefits(text, url):
    result={}
    def add(key,match,notes,period):
        if not match:return
        amount=float(match.group(1).replace(',',''))
        page=text[:match.start()].count('\f')+1
        result[key]={'amount':amount,'period':period,'notes':notes,
                     'source_url':url+'#page='+str(page),'status':'Source amount extracted'}
    add('premium',re.search(r'Monthly Premium\s+\$([\d,]+(?:\.\d{2})?)',text),
        'Monthly plan premium only. Part B premium and other costs still apply.','month')
    dental=re.search(r'Dental Allowance\s+You have a \$([\d,]+) yearly allowance',text)
    if dental:
        context=text[dental.start():dental.start()+1400]
        notes='Reimbursement benefit; pay first and request reimbursement. Covered dental codes and exclusions apply.'
        if '50% reimbursement' in context:
            notes+=' Comprehensive dental reimbursed at 50%; preventive at 100%, subject to allowance.'
        add('dental',dental,notes,'year')
    else:
        dental=re.search(r'Dental Services[^\n]*\n\s*Devoted Health will pay as much as \$([\d,]+) per year',text)
        add('dental',dental,'Participating dental provider required. Covered service codes and exclusions apply.','year')
    otc=re.search(r'Over-the-Counter[\s\S]{0,110}?\$([\d,]+) per quarter',text)
    add('otc',otc,'Eligible items only. Quarterly allowance; annual comparison assumes four quarters, not rollover.','quarter')
    return result
