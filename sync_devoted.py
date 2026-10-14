"""Refresh official NC service areas and plan document text; no patient data."""
import concurrent.futures
import hashlib
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen
import app

SITE = 'https://www.devoted.com'
FINDER = SITE + '/page-data/find-a-plan/page-data.json'


def fetch(url):
    u = urlparse(url)
    if u.scheme != 'https' or u.hostname not in ('www.devoted.com','assets.devoted.com'):
        raise ValueError('Unexpected source host')
    with urlopen(url, timeout=35) as r:
        body = r.read(25_000_001)
    if len(body)>25_000_000:
        raise ValueError('Source exceeds size limit')
    return body


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for key, value in attrs:
                if key == 'href' and value.startswith('https://assets.devoted.com/'):
                    self.links.add(value)


def plan_links(plan):
    url = SITE + '/plan-documents/benefit-and-coverage-details/' + plan['record_locator'] + '/'
    parser = Links()
    parser.feed(fetch(url).decode())
    links = []
    for link in parser.links:
        if '/2027/' not in link or not link.lower().endswith('.pdf'):
            continue
        kind = ('benefits' if '-SB-' in link else 'evidence' if '-EOC-' in link
                else 'formulary' if '/formulary/' in link else None)
        if kind:
            links.append((kind,link))
    if not any(k=='benefits' for k,_ in links):
        raise ValueError('Missing Summary of Benefits for '+plan['record_locator'])
    return plan['record_locator'],url,links


def extract(url):
    content = fetch(url)
    if not content.startswith(b'%PDF'):
        raise ValueError('Expected PDF')
    with tempfile.TemporaryDirectory() as temp:
        pdf = Path(temp)/'source.pdf'
        pdf.write_bytes(content)
        text = subprocess.run(['pdftotext','-layout',str(pdf),'-'],
                              check=True,capture_output=True,timeout=60).stdout.decode()
    if not text.strip() or '2027' not in text[:4000]:
        raise ValueError('Missing readable 2027 document text')
    return url,text,hashlib.sha256(content).hexdigest()


def sync(path=app.DB, refresh=False):
    app.initialize(path)
    source = json.loads(fetch(FINDER))['result']['data']
    counties = [c for c in source['site']['siteMetadata']['ssaCountiesForMarketablePbps'] if c['state_abbreviation'] in app.STATES]
    county_states={c['code']:c['state_abbreviation'] for c in counties}
    plans=[]
    for p in source['allPbps']['nodes']:
        states={county_states[a['county_code']] for a in p['service_areas'] if a['county_code'] in county_states}
        if p['year']=='2027' and states:
            if len(states)!=1:raise ValueError('Ambiguous plan state')
            plans.append({**p,'state':states.pop()})
    with app.connect(path) as db:
        existing=list(db.execute('SELECT * FROM devoted_documents'))
        cached={} if refresh else {r['url']:(r['url'],r['text'],r['sha256']) for r in existing}
        cached_dates={} if refresh else {r['url']:r['retrieved_at'] for r in existing}
    if not plans or not counties:
        raise ValueError('Website service-area data missing')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        links = list(pool.map(plan_links,plans))
        urls = sorted({url for _,_,items in links for kind,url in items if kind!='evidence'})
        fresh=list(pool.map(extract,[u for u in urls if u not in cached]))
        documents=[cached[u] for u in urls if u in cached]+fresh
    checked = datetime.now(timezone.utc).isoformat(timespec='seconds')
    with app.connect(path) as db:
        db.executescript('CREATE TABLE IF NOT EXISTS devoted_county_states (code TEXT PRIMARY KEY,state TEXT NOT NULL); CREATE TABLE IF NOT EXISTS devoted_catalog (locator TEXT PRIMARY KEY,state TEXT NOT NULL,name TEXT NOT NULL);')
        db.execute('DELETE FROM devoted_county_states')
        db.execute('DELETE FROM devoted_catalog')
        db.executemany('INSERT INTO devoted_county_states VALUES (?,?)',county_states.items())
        db.executemany('INSERT INTO devoted_catalog VALUES (?,?,?)',[(p['record_locator'],p['state'],p['name']) for p in plans])
        db.execute('DELETE FROM devoted_zip_counties')
        db.execute('DELETE FROM devoted_service_areas')
        db.execute('DELETE FROM devoted_documents')
        db.execute('DELETE FROM devoted_document_links')
        for county in counties:
            db.executemany('INSERT INTO devoted_zip_counties VALUES (?,?,?)',
                           [(z['zip_code'],county['code'],county['display_name']) for z in county['zip_codes']])
        for p in plans:
            db.executemany('INSERT INTO devoted_service_areas VALUES (?,?,?)',
                           [(p['record_locator'],a['county_code'],p['name']) for a in p['service_areas']])
        for url,text,digest in documents:
            db.execute('INSERT INTO devoted_documents VALUES (?,?,?,?,?)',(url,text,digest,cached_dates.get(url,checked),2027))
        for locator,page,items in links:
            db.executemany('INSERT INTO devoted_document_links VALUES (?,?,?,?)',
                           [(locator,kind,url,page) for kind,url in items])
        db.execute('INSERT OR REPLACE INTO devoted_sync VALUES (1,?,?,?)',
                   (checked,source['site']['siteMetadata']['lastBuildTime'],FINDER))
    print(f'Synced {len(plans)} plans, {len(counties)} target-state counties, {len(documents)} distinct documents.',flush=True)


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--refresh',action='store_true',help='Redownload existing document URLs')
    sync(refresh=parser.parse_args().refresh)
