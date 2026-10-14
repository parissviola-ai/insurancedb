"""Read-only Devoted public FHIR connector. Never infer service areas from provider ZIPs."""
import json
import re
import time
import threading
import service_data
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from datetime import datetime, timezone

BASE = 'https://fhir.devoted.com/fhir/'
_cache = {}
_lock = threading.Lock()


def get(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc != 'fhir.devoted.com' or not (parsed.path == '/fhir' or parsed.path.startswith('/fhir/')):
        raise ValueError('Unexpected FHIR URL')
    with _lock:
        cached = _cache.get(url)
    if cached and time.monotonic() - cached[0] < 300:
        return cached[1]
    with urlopen(Request(url, headers={'Accept':'application/fhir+json'}), timeout=20) as response:
        body = response.read(12_000_001)
    if len(body) > 12_000_000:
        raise ValueError('FHIR response too large')
    result = json.loads(body)
    if result.get('resourceType') == 'OperationOutcome':
        raise ValueError('FHIR search failed')
    with _lock:
        if len(_cache) > 500:
            _cache.clear()
        _cache[url] = (time.monotonic(), result)
    return result


def search(resource, params, pages=10):
    url = BASE + resource + '?' + urlencode(params)
    rows = []
    for _ in range(pages):
        bundle = get(url)
        if bundle.get('resourceType') != 'Bundle':
            raise ValueError('Expected FHIR search bundle')
        rows.extend(e['resource'] for e in bundle.get('entry',[])
                    if e.get('search',{}).get('mode') != 'outcome' and 'resource' in e)
        url = next((l['url'] for l in bundle.get('link',[]) if l['relation']=='next'),None)
        if not url:
            return rows, False
    return rows, True


def valid_year(resource, year):
    period = resource.get('period',{})
    return (period.get('start','') <= f'{year}-01-01' and
            period.get('end','') >= f'{year}-12-31' and bool(period.get('start')))


def provider_matches(term, networks, year, zip_code):
    words = term.split()
    query = {'_count':10}
    if re.fullmatch(r'\d{10}',term):
        query['identifier'] = 'http://hl7.org/fhir/sid/us-npi|' + term
    elif len(words) >= 2:
        query.update({'given':words[0], 'family':words[-1]})
    else:
        query['name'] = term
    people, truncated = search('Practitioner', query, pages=1)
    matches = []
    for person in people[:10]:
        roles, more = search('PractitionerRole',
                             {'practitioner':'Practitioner/'+person['id'],'_count':100}, pages=2)
        truncated = truncated or more
        for role in roles:
            linked = {e.get('valueReference',{}).get('reference') for e in role.get('extension',[])
                      if e.get('url','').endswith('/network-reference')}
            if not (linked & networks) or role.get('active') is not True or not valid_year(role,year):
                continue
            for ref in role.get('location',[]):
                location = get(BASE + ref['reference'])
                address = location.get('address',{})
                if address.get('state') != 'NC':
                    continue
                if zip_code and address.get('postalCode','')[:5] != zip_code:
                    continue
                name = person.get('name',[{}])[0]
                display = name.get('text') or ' '.join(name.get('given',[])+[name.get('family','')])
                matches.append({'name':display, 'detail':address.get('text') or ', '.join(
                    address.get('line',[])+[address.get('city',''),address.get('state',''),address.get('postalCode','')]),
                    'status':'restricted','restrictions':'Listed in this plan network for the displayed office and year. Confirm exact provider identity and participation before enrollment.',
                    'source_url':BASE+'PractitionerRole/'+role['id'],
                    'verified_on':role.get('meta',{}).get('lastUpdated','')[:10]})
                if len(matches)>=20:
                    return matches, True
    return matches, truncated


def lookup(params):
    if params.get('state','NC') != 'NC':
        return {'plans':[], 'notice':'Live Devoted integration currently supports North Carolina only.', 'truncated':False}
    year = int(params.get('year','2027'))
    zip_code = params.get('zip','')
    if not re.fullmatch(r'\d{5}',zip_code):
        raise ValueError('Enter a five-digit ZIP code')
    if params.get('business') not in ('',None,'Medicare Advantage') or params.get('carrier','').lower() not in ('','devoted','devoted health'):
        return {'plans':[], 'notice':'Live Devoted connector covers Medicare Advantage only.', 'truncated':False}
    counties, selected, locators, sync = service_data.area(zip_code,params.get('county',''),year)
    if not selected:
        return {'plans':[], 'counties':counties,'needs_county':len(counties)>1,'truncated':False,
                'notice':'Select your county to see plans.' if counties else 'This ZIP was not found in Devoted’s published NC lookup. No plan availability inferred.'}
    if not locators:
        return {'plans':[], 'counties':counties,'selected_county':selected['code'],'truncated':False,
                'notice':'Devoted’s published 2027 lookup lists no plans for '+selected['name']+' County.'}
    rows, truncated = search('InsurancePlan', {'name:contains':'NC','_count':100})
    output = []
    provider_cache = {}
    provider_terms = [t.strip() for t in params.get('provider','').splitlines() if t.strip()]
    drug_terms = [t.strip() for t in params.get('medication','').splitlines() if t.strip()]
    if len(provider_terms)>3 or len(drug_terms)>10:
        raise ValueError('Search up to 3 providers and 10 medications at a time')
    for p in rows:
        # Explicit state label in official plan name; not a ZIP service-area assertion.
        if not re.search(r'\bNC\b',p.get('name','')) or p.get('status')!='active' or not valid_year(p,year):
            continue
        identifiers = [i.get('value','') for i in p.get('identifier',[]) if i.get('system')=='http://cms.gov/medicare/ma-plan-id']
        locator = next((i+'-'+str(year) for i in identifiers if i+'-'+str(year) in locators),None)
        if not locator:
            continue
        docs,premium,excerpt,checks = service_data.documents(locator,drug_terms)
        networks = {n['reference'] for n in p.get('network',[]) if 'reference' in n}
        for term in provider_terms:
            key = (term,tuple(sorted(networks)))
            if key not in provider_cache:
                provider_cache[key] = provider_matches(term,networks,year,params.get('provider_zip',''))
            matches, more = provider_cache[key]
            truncated = truncated or more
            checks.append({'kind':'provider','query':term,'matches':matches})
        output.append({'id':p['id'],'carrier':'Devoted Health','name':p['name'],'year':year,'state':'NC',
                       'county':selected['name'],'zip':zip_code or 'not specified','business':'Medicare Advantage',
                       'premium':premium or 'unverified', 'benefits':excerpt or 'Read the official benefit documents below. Structured benefits are not yet extracted.',
                       'documents':docs, 'document_excerpt':bool(excerpt),
                       'source_url':BASE+'InsurancePlan/'+p['id'],
                       'verified_on':p.get('meta',{}).get('lastUpdated','')[:10], 'checks':checks})
    return {'plans':output,'counties':counties,'selected_county':selected['code'],'truncated':truncated,'notice':
            'Plans matched to Devoted’s published '+str(year)+' county service areas. Formulary text matches need review; they do not confirm drug coverage. Provider offices may be outside your home ZIP. Website snapshot retrieved '+sync['retrieved_at']}
