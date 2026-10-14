"""Lookup locally imported official website mappings and document text."""
import re


def area(zip_code, county, year):
    import app
    if year != 2027:
        raise ValueError('Official website/document import currently covers 2027 only')
    with app.connect() as db:
        sync = db.execute('SELECT * FROM devoted_sync WHERE id=1').fetchone()
        if not sync:
            raise ValueError('Official plan documents need syncing. Run python3 sync_devoted.py.')
        counties = [dict(r) for r in db.execute(
            'SELECT county_code AS code, county_name AS name FROM devoted_zip_counties WHERE zip=? ORDER BY county_name', (zip_code,))]
        selected = next((c for c in counties if county in (c['code'],c['name'])),None) if county else (counties[0] if len(counties)==1 else None)
        if county and not selected:
            raise ValueError('Select a county associated with this ZIP code')
        locators = {r['locator'] for r in db.execute('SELECT locator FROM devoted_service_areas WHERE county_code=?',
                                                   (selected['code'],))} if selected else set()
    return counties,selected,locators,dict(sync)


def documents(locator, terms):
    import app
    with app.connect() as db:
        rows = db.execute('''SELECT l.kind,l.page_url,d.* FROM devoted_document_links l
            JOIN devoted_documents d ON d.url=l.url WHERE l.locator=? ORDER BY l.kind''',(locator,)).fetchall()
    docs = []
    premium = ''
    benefit_excerpt = ''
    drug_checks = []
    for r in rows:
        text = r['text']
        docs.append({'kind':r['kind'],'url':r['url'],'page_url':r['page_url'],
                     'retrieved_at':r['retrieved_at'],'sha256':r['sha256']})
        if r['kind']=='benefits':
            match = re.search(r'Monthly Premium\s+(\$[\d,.]+)',text)
            premium = match.group(1) if match else ''
            marker = text.find('Monthly Premium, Deductible, and Limits')
            if marker>=0:
                benefit_excerpt=text[marker:marker+1200].strip()
        if r['kind']=='formulary':
            for term in terms:
                matches = []
                for number,page in enumerate(text.split('\f'),1):
                    lines = page.splitlines()
                    for i,line in enumerate(lines):
                        if term.casefold() in line.casefold():
                            matches.append({'name':term,'detail':'Document text match · PDF page '+str(number),
                             'status':'unverified','restrictions':'\n'.join(lines[max(0,i-1):i+3]).strip() +
                             '\nText match only. Confirm strength/form, tier, restrictions, and legend in the official formulary.',
                             'source_url':r['url']+'#page='+str(number),'verified_on':r['retrieved_at'][:10]})
                            if len(matches)>=5:break
                    if len(matches)>=5:break
                drug_checks.append({'kind':'medication','query':term,'matches':matches})
    # Every term remains present even for plans with no formulary (e.g. MA-only).
    for term in terms:
        if not any(c['query']==term for c in drug_checks):
            drug_checks.append({'kind':'medication','query':term,'matches':[]})
    return docs,premium,benefit_excerpt,drug_checks


def document_text(url):
    import app
    with app.connect() as db:
        row = db.execute('SELECT text,retrieved_at FROM devoted_documents WHERE url=?',(url,)).fetchone()
    if not row:
        raise ValueError('Document not found in official import')
    return dict(row)
