"""Conservative extraction of Wellcare table candidates and NC source schedules."""
import html
import re


def table_rows(markup):
    rows = []
    for tr in re.findall(r'<tr\b.*?</tr>', markup, re.S):
        cells = [re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', ' ', cell))).strip()
                 for cell in re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>', tr, re.S)]
        if cells:
            rows.append(cells)
    return rows


def parse_formulary(text):
    rows = []
    for page_number, page in enumerate(text.split('\f'), 1):
        if not ('Drug Name' in page and 'Tier' in page and 'Requirements' in page):
            continue
        current = None
        def save():
            if current and current.get('tier') and current['name']:
                current['name'] = re.sub(r'(\d)-\s+(\d)', r'\1-\2', current['name'])
                rows.append(dict(current))
        for line in page.splitlines()[2:]:
            if line.strip().startswith('You can find information'):
                break
            match = re.match(r'^(.*?)\s{2,}([1-6])\^?(?:\s+(.*))?\s*$', line)
            if match:
                left, tier, restriction = match.group(1).strip(), match.group(2), (match.group(3) or '').strip()
            else:
                left = line.strip() if len(line) - len(line.lstrip()) < 40 else ''
                tier, restriction = None, ''
                # Lines entirely to the right are wrapped restriction text.
                if not left and current and line.strip() and not line.strip().isdigit():
                    current['restrictions'] = (current['restrictions'] + ' ' + line.strip()).strip()
                    continue
            if not left and not tier:
                continue
            if left and left.isupper() and not tier and not re.search(r'\d|ORAL|INJECTION|TABLET|CAPSULE|TOPICAL|OPHTHALMIC|SOLUTION|SUSPENSION|NASAL|INHALATION', left):
                save(); current = None
                continue
            continuation = bool(re.match(r'^(?:X\s*\d|[\d.,/()%]|mg\b|mcg\b|ml\b|gram\b|unit\b|for\b|release\b|reconstitution\b|suspension\b|solution\b|tablet\b|capsule\b|piggyback\b|extended\b|delayed\b|disintegrating\b)', left, re.I))
            if left and current and current.get('tier') and not continuation:
                save(); current = None
            if current is None:
                current = {'name': '', 'tier': '', 'restrictions': '', 'page': page_number}
            if left:
                current['name'] = (current['name'] + ' ' + left).strip()
            if tier:
                if current['tier']:
                    save(); current = {'name': left, 'tier': '', 'restrictions': '', 'page': page_number}
                current['tier'] = tier
                current['restrictions'] = restriction
        save()
    return rows


def parse_schedule(markup, text, url):
    rows = table_rows(markup)
    lookup = {r[0]: r[1] for r in rows if len(r) >= 2}
    metrics = {}
    def add(key, amount, period, notes, marker):
        start = text.find(marker)
        if start < 0:
            return
        # Require the numeric fact in the PDF's relevant section as well as the website table.
        section = text[start:start + 8000]
        number = re.escape(f'{amount:g}')
        if not re.search(number, section.replace(',', '')):
            return
        metrics[key] = {'amount': amount, 'period': period, 'notes': notes,
                        'source_url': url + '#page=' + str(text[:start].count('\f') + 1), 'status': 'Source amount extracted'}
    flat = re.sub(r'\s+', ' ', text)
    premium = re.search(r'Monthly Plan Premium[^$]{0,140}\$([\d,]+)', flat)
    if premium:
        add('premium', float(premium[1].replace(',', '')), 'month', 'Part B premium and other costs still apply.', 'Monthly Plan Premium')
    moop = re.search(r'(?:Maximum Out-of-Pocket|Maximum Out.of.Pocket|Maximum Out of Pocket)[^$]{0,400}\$([\d,]+)', flat, re.I)
    if moop:
        marker = next((x for x in ['Maximum Out-of-Pocket', 'Maximum Out of Pocket'] if x in text), None)
        if marker:
            add('moop', float(moop[1].replace(',', '')), 'year', 'In-network medical maximum; Part D and excluded services do not count.', marker)
    for key, category, pattern, period, marker in [
        ('dental', 'Dental Services', r'comprehensive services up to \$([\d,]+)', 'year', 'Dental Services'),
        ('vision', 'Vision Services', r'up to \$([\d,]+)', 'year', 'Vision Services'),
        ('specialist', 'Doctor Specialty Visit', r'^\$([\d,]+)\.', 'visit', 'Specialists'),
    ]:
        value = lookup.get(category, '')
        match = re.search(pattern, value, re.I)
        if match:
            add(key, float(match[1].replace(',', '')), period, 'In-network source schedule. ' + value, marker)
    transport = lookup.get('Transportation', '')
    if transport.lower().startswith('not covered'):
        metrics['transportation'] = {'amount': 0, 'period': 'one-way rides/year', 'notes': 'Non-emergency transportation is not covered.', 'source_url': url, 'status': 'Source amount extracted'}
    else:
        match = re.search(r'\$0 for (\d+) one-way trips every year', transport)
        if match:
            add('transportation', float(match[1]), 'one-way rides/year', 'In-network non-emergency medical rides; booking, destination and eligibility rules apply.', 'Transportation Services')
    otc = lookup.get('Over-the-Counter Items', '')
    match = re.search(r'OTC allowance of \$([\d,]+) every month', otc)
    if match:
        monthly = float(match[1].replace(',', ''))
        start = text.find('Wellcare Spendables')
        if start >= 0 and str(int(monthly)) in text[start:start + 6000].replace(',', ''):
            metrics['otc'] = {'amount': monthly * 3, 'period': 'quarter', 'notes': f'${monthly:g} monthly (${monthly*12:g} yearly equivalent). Spendables may be shared with dental, vision, hearing or other eligible items; not separate allowances. Conditions and eligibility apply. ' + otc,
                              'source_url': url + '#page=' + str(text[:start].count('\f') + 1), 'status': 'Source amount extracted'}
    elif otc.lower().startswith('not covered'):
        metrics['otc'] = {'amount': 0, 'period': 'quarter', 'notes': 'OTC benefit is not covered.', 'source_url': url, 'status': 'Source amount extracted'}
    hospital = lookup.get('Inpatient Hospital Care', '')
    match = re.search(r'\$([\d,]+) co-pay per day for days 1-(\d+) and a \$0 co-pay per day for days (\d+)-90', hospital)
    if match and int(match[3]) == int(match[2]) + 1:
        amount = float(match[1].replace(',', '')) * min(int(match[2]), 7)
        add('hospital', amount / min(int(match[2]), 7), 'day', 'verification only', 'Inpatient Hospital Coverage')
        if 'hospital' in metrics:
            metrics['hospital'].update(amount=amount, period='7-day stay', notes='One modeled in-network 7-day admission. ' + hospital)
    tiers = {}
    for row in rows:
        match = re.match(r'Tier ([1-6])\b', row[0])
        if match and len(row) >= 2 and re.fullmatch(r'\$[\d.]+|[\d.]+%', row[1]):
            raw = row[1]
            tiers[match[1]] = {'type': 'copay' if raw.startswith('$') else 'coinsurance', 'display': raw + (' per prescription' if raw.startswith('$') else ' of drug cost'), 'source_url': url}
    costs = {'tiers': tiers, 'supply_days': 30, 'pharmacy_type': 'Preferred network retail pharmacy', 'stage': 'Initial coverage', 'extra_help': 'Standard schedule without Extra Help',
             'conditions': 'Preferred network retail 30-day supply. Standard retail and mail-order amounts may differ. Exact drug, pharmacy, deductible, Extra Help and coverage stage require confirmation.',
             'deductible_note': 'Check the official Part D deductible rules; Tier 6 is not subject to the standard deductible.'} if tiers else {}
    return metrics, costs
