"""Conservative extraction of explicitly stated Summary of Benefits amounts."""
import re


def parse_benefits(text, url):
    result={}
    def add(key,match,notes,period,amount_override=None):
        if not match:return
        amount=float(match.group(1).replace(',','')) if amount_override is None else amount_override
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
    add('moop',re.search(r'Maximum Out[^$]{0,120}\$([\d,]+)',text),
        'In-network yearly medical maximum. Part D and excluded supplemental benefits do not count.','year')
    add('specialist',re.search(r'Specialist:\s*\$([\d,]+) copay',text),
        'In-network specialist office visit copay. Other services may have separate charges.','visit')
    add('vision',re.search(r'Eyewear\s+Up to \$([\d,]+) each year',text),
        'Eyeglasses/contact allowance. Designated vendor, network, or reimbursement rules may apply.','year')
    hearing=re.search(r'Hearing Aids[^$]{0,30}\$([\d,]+) copay or \$([\d,]+) copay per aid',text)
    add('hearing',hearing,
        ('Advanced hearing aid copay; Premium option costs $'+hearing.group(2)+' per aid. Participating vendor required; optional features may cost extra.') if hearing else '', 'aid')
    start=text.find('Inpatient Hospital')
    if start>=0:
        segment=text[start:start+700]
        stay=re.search(r'\$([\d,]+) copay per stay',segment)
        days=re.search(r'Days 1\s*-\s*(\d+)',segment)
        daily=re.search(r'\$([\d,]+) copay per day',segment)
        # The initial in-network amount must precede any daily out-of-network schedule.
        if stay and (not days or stay.start()<days.start()):
            full=re.search(r'Inpatient Hospital[\s\S]{0,140}?\$([\d,]+) copay per stay',text)
            add('hospital',full,'In-network cost for one modeled 7-day admission, using the stated per-stay copay. Authorization and benefit-period rules apply.','7-day stay')
        elif days and daily:
            n=int(days.group(1))
            if re.search(r'Day '+str(n+1)+r'\+[^$]{0,100}\$0 copay per day',segment):
                full=re.search(r'Inpatient Hospital[\s\S]{0,200}?\$([\d,]+) copay per day',text)
                cost=float(daily.group(1).replace(',',''))*min(n,7)
                add('hospital',full,'Modeled in-network 7-day admission: $'+daily.group(1)+' per day for days 1–'+str(n)+', then $0. Actual cost depends on stay length; authorization and benefit-period rules apply.','7-day stay',cost)
    transport=re.search(r'Transportation\s+Not covered',text)
    if transport:
        add('transportation',transport,'Plan transportation benefit is listed as not covered. Other transportation programs may have separate eligibility.','one-way rides/year',0)
    else:
        rides=re.search(r'Transportation[\s\S]{0,250}?\b(\d+) one-way (?:trips|rides)[\s\S]{0,80}?(?:per year|each year)',text,re.I)
        if rides and re.search(r'\$0 copay',rides.group(0)):
            add('transportation',rides,'Covered one-way rides per year. Round trips use two rides. Check destination, mileage, vendor, and advance-booking rules.','one-way rides/year')
    return result
