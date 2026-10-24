"""Concurrent, anonymous public carrier shopping. No portal credentials or sessions."""
import json
import math
import re
import threading
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, unquote, urlparse
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

AETNA_SOURCE = 'https://www.aetna.com/medicare/compare-plans-enroll.html'
HS_API = 'https://api.marketing.aws.zilverton.com/drx/v2'
DEVOTED_SOURCE = 'https://www.devoted.com/page-data/find-a-plan/page-data.json'
CARRIERS = {
    'Highmark': 'https://medicare.highmark.com/view-plans',
    'Aetna': AETNA_SOURCE,
    'Devoted Health': 'https://www.devoted.com/find-a-plan/',
    'HealthSpring': 'https://shop.healthspringmedicare.com/',
    'UnitedHealthcare / AARP': 'https://www.aarpmedicareplans.com/',
    'Molina': 'https://molina1.destinationrx.com/PC/2027/Shopping/PlanList',
    'CareFirst': 'https://www.carefirst.com/medicare/',
    'Cigna': 'https://www.cigna.com/medicare/',
    'Excellus BlueCross BlueShield': 'https://www.excellusbcbs.com/plans/medicare-advantage',
    'Medico': 'https://www.wellabe.com/products/medicare-supplement',
    'Guarantee Trust Life': 'https://gtlic.com/medicare-supplement-insurance/',
    'Highmark Wholecare': 'https://www.highmark.com/wholecare/medicare/enrollment',
}
HOSTS = {'api.marketing.aws.zilverton.com', 'www.devoted.com', 'enrollmedicare.aetna.com', 'www.aarpmedicareplans.com', 'www.wellabe.com', 'wellabe.com', 'gtlic.com', 'www.gtlic.com', 'www.carefirst.com'}
# A small global cap prevents overlapping searches from creating unbounded work.
_slots = threading.BoundedSemaphore(3)


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class ShoppingError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


class PublicRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.username or parsed.password:
        raise ShoppingError('response_changed', 'Shopping site redirected to an unexpected destination.')


def client():
    return build_opener(PublicRedirects(), HTTPCookieProcessor(CookieJar()))


def read(url, payload=None, form=False, opener=None):
    validate_url(url)
    headers = {'Accept': 'application/json', 'User-Agent': 'FernAndMossPlanFinder/1.0'}
    body = None
    if payload is not None:
        body = (urlencode(payload) if form else json.dumps(payload)).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    with (opener or client()).open(Request(url, data=body, headers=headers), timeout=22) as response:
        validate_url(response.url)
        content = response.read(20_000_001)
    if len(content) > 20_000_000:
        raise ShoppingError('response_changed', 'Shopping response exceeded its expected size.')
    return content.decode('utf-8')


def get_json(url, **kwargs):
    return json.loads(read(url, **kwargs))


def locations(zip_code):
    import app
    if not re.fullmatch(r'[0-9]{5}', zip_code):
        raise ValueError('Enter a five-digit ZIP code.')
    rows = get_json(HS_API + '/counties/' + zip_code)
    if not isinstance(rows, list):
        raise ShoppingError('response_changed', 'ZIP lookup returned an unexpected response.')
    counties = []
    for row in rows:
        if not all(isinstance(row.get(k), str) for k in ('CountyFIPS', 'CountyName', 'State')):
            raise ShoppingError('response_changed', 'ZIP lookup fields changed.')
        if not re.fullmatch(r'[0-9]{5}', row['CountyFIPS']):
            raise ShoppingError('response_changed', 'ZIP lookup county code changed.')
        if row['State'] in app.STATES:
            counties.append({'code': row['CountyFIPS'], 'name': row['CountyName'], 'state': row['State']})
    return {'zip': zip_code, 'counties': counties, 'states': app.STATES,
            'source_url': HS_API + '/counties/' + zip_code, 'checked_at': now(),
            'notice': 'Select your county.' if counties else 'No county in the configured states was resolved. Plan availability has not been determined.'}


def plan(carrier, identity, name, loc, source, business='Medicare Advantage', premium=None, special_needs=False):
    if not identity or not name:
        raise ShoppingError('response_changed', 'A plan is missing its official identity or name.')
    record = {'id': carrier + ':' + identity + ':' + str(loc['year']), 'official_id': identity,
            'carrier': carrier, 'name': name, **loc, 'business': business,
            'source_url': source, 'checked_at': now(), 'premium': premium,
            'special_needs': special_needs,
            'notice': 'Public shopping listing. Confirm eligibility and complete plan conditions. Provider and medication coverage not checked.'}
    if carrier == 'HealthSpring':
        base = f"https://shop.healthspringmedicare.com/{loc['zip']}/{loc['county']}"
        record['review_sources'] = {'medication': base + f"/prescriptions?planYear={loc['year']}",
                                    'pharmacy': base + f"/pharmacy?planYear={loc['year']}"}
    return record


def shopping_benefits(record, medical_maximum=None):
    """Only explicit comparable scalar fields, retaining their shopping source."""
    metrics = {}
    if record['business'] == 'Medicare Advantage' and type(medical_maximum) in (int, float) and math.isfinite(medical_maximum) and medical_maximum >= 0:
        metrics['moop'] = {'amount': medical_maximum, 'period': 'year',
                           'notes': 'In-network annual medical maximum from public shopping. Part D and excluded services are separate; confirm source conditions.',
                           'source_url': record['source_url']}
    record['shopping_metrics'] = metrics
    return record


def devoted_plans(loc):
    data = get_json(DEVOTED_SOURCE)['result']['data']
    areas = data['site']['siteMetadata']['ssaCountiesForMarketablePbps']
    # Devoted uses SSA codes. Never pass the shared FIPS code into this lookup.
    counties = [c for c in areas if c['state_abbreviation'] == loc['state']
                and c['display_name'].casefold() == loc['county_name'].casefold()
                and any(z['zip_code'] == loc['zip'] for z in c['zip_codes'])]
    if not counties:
        raise ShoppingError('location_unresolved', 'Devoted’s public mapping did not resolve this ZIP and county. No availability inferred.')
    codes = {c['code'] for c in counties}
    all_plans = data['allPbps']['nodes']
    if not all_plans or not any(str(p.get('year')) == str(loc['year']) for p in all_plans):
        raise ShoppingError('year_unavailable', 'The requested plan year is not present in Devoted’s public shopping data.')
    output = []
    for p in all_plans:
        if str(p['year']) != str(loc['year']) or not any(a['county_code'] in codes for a in p['service_areas']):
            continue
        locator = p['record_locator']
        output.append(plan('Devoted Health', locator.rsplit('-', 1)[0], p['name'], loc,
                           'https://www.devoted.com/plan-documents/benefit-and-coverage-details/' + locator + '/',
                           special_needs='SNP' in p.get('plan', {}).get('ma_variant', '')))
    return output


def healthspring_plans(loc):
    opener = client()
    session = get_json(HS_API + '/session', payload={}, opener=opener)
    if not isinstance(session, list) or not session or not session[0].get('SessionID'):
        raise ShoppingError('response_changed', 'HealthSpring’s anonymous shopping session could not be created.')
    session_id = session[0]['SessionID']
    if not re.fullmatch(r'[A-Za-z0-9_-]+', session_id):
        raise ShoppingError('response_changed', 'HealthSpring’s session format changed.')
    url = HS_API + '/session/' + session_id + '/plans?' + urlencode(
        {'zip': loc['zip'], 'fips': loc['county'], 'year': loc['year'], 'language': 'en'})
    data = get_json(url, opener=opener)
    if not isinstance(data.get('MedicarePlans'), list):
        raise ShoppingError('response_changed', 'HealthSpring’s shopping response changed.')
    output = []
    for p in data['MedicarePlans']:
        if str(p['PlanYear']) != str(loc['year']):
            raise ShoppingError('year_mismatch', 'HealthSpring returned a different plan year. Results withheld.')
        identity = p['ContractID'] + '-' + p['PlanID'] + '-' + p['SegmentID']
        if not re.fullmatch(r'[A-Za-z0-9]+', p['ID']):
            raise ShoppingError('response_changed', 'HealthSpring’s plan identity format changed.')
        source = f"https://shop.healthspringmedicare.com/{loc['zip']}/{loc['county']}/plan/{p['ID']}?planYear={loc['year']}"
        # Annual plan premium is the explicit combined premium, not estimated drug spend.
        annual = p.get('AnnualPlanPremium')
        premium = round(annual / 12, 2) if isinstance(annual, (int, float)) and annual >= 0 else None
        business = 'Part D' if p.get('PlanSubType') == 'PDP' or p['ContractID'].startswith('S') else 'Medicare Advantage'
        output.append(plan('HealthSpring', identity, p['PlanName'], loc, source, business, premium,
                           bool(p.get('PlanSNPCategories'))))
        if isinstance(p.get('HasDrugCoverage'), bool):
            output[-1]['has_drug_coverage'] = p['HasDrugCoverage']
        shopping_benefits(output[-1], p.get('MaximumOutOfPocketCost'))
    return output


def apply_aetna_prices(plans, rows, products, year):
    candidates = {}
    for row in rows:
        value = row.get('CalculatedPriceData', {})
        identity = value.get('PlanID')
        if identity not in products or value.get('productKey') != products[identity]:
            continue
        if value.get('ProductAttributeMapping__ContractPBPPlanYear') != f'{identity}-{year}':
            continue
        candidates.setdefault(identity, []).append(value)
    for record in plans:
        values = candidates.get(record['official_id'], [])
        if len(values) != 1:
            record['benefit_notice'] = 'No unique Aetna price record was verified. Missing amounts remain unverified.'
            continue
        value = values[0]
        premium = value.get('PlanPremiumMA' if value.get('productFamily') == 'MA' else 'PlanPremiumNoExtra')
        if type(premium) in (int, float) and math.isfinite(premium) and premium >= 0:
            record['premium'] = premium
            record['premium_notes'] = 'Monthly plan premium before Extra Help adjustments. Part B and other costs still apply.'
        raw_maximum = value.get('ProductAttributeMapping__IN_MOOP', '')
        match = re.fullmatch(r'\$([0-9][0-9,]*(?:\.[0-9]{1,2})?)', str(raw_maximum).strip())
        record['checked_at'] = now()
        shopping_benefits(record, float(match[1].replace(',', '')) if match else None)


def aetna_session(loc):
    opener = client()
    base = 'https://enrollmedicare.aetna.com'
    page = '/s/shop?' + urlencode({'PlanYear': loc['year'], 'ZipCode': loc['zip'], 'CountyFIPS': loc['county'], 'step': 'PlanList'})
    html = read(base + page, opener=opener)
    match = next((m for m in re.finditer(r'/s/sfsites/l/(%7B[^"<>]+)', html) if 'fwuid' in m[1]), None)
    if not match:
        raise ShoppingError('response_changed', 'Aetna’s public shopping configuration changed or requires an interactive browser.')
    config = json.JSONDecoder().raw_decode(unquote(match[1]))[0]
    context = {k: config[k] for k in ('mode', 'fwuid', 'app', 'loaded')}
    context.update(dn=[], globals={}, uad=True)
    # Same anonymous static-data request made by Browse plans. This does not
    # make personal eligibility, enrollment date or medication assumptions.
    effective = str(loc['year']) + '-01-02'
    inputs = {'prospect.brand': 'aetna', 'prospect.modName': 'DTC', 'prospect.remainingMonths': 12,
              'prospect.state': loc['state'], 'prospect.fips': loc['county'],
              'prospect.estimatedPharmacyCostList': None, 'prospect.pharmacyNetworkStatusList': None,
              'prospect.pharmacyNetworkStatusList2': None, 'prospect.pharmacyNetworkStatusList3': None,
              'prospect.providerPlans': None, 'prospect.isMailOrderPharmacy': False,
              'prospect.isStaticDataRequest': True, 'prospect.isDynamicDataRequest': False,
              'prospect.extraHelpForPresDrugs': '', 'prospect.socialSecPerExtraHelp': ''}
    def invoke(method, input_data, options):
        action = {'id': '1;a', 'descriptor': 'aura://ApexActionController/ACTION$execute', 'callingDescriptor': 'UNKNOWN',
                  'params': {'namespace': '', 'classname': 'GenericInvokeController', 'method': 'invokeApex',
                             'params': {'sClassName': 'CommunityUserController', 'sMethodName': method,
                                        'input': json.dumps(input_data), 'options': json.dumps(options)},
                             'cacheable': False, 'isContinuation': False}}
        data = get_json(base + '/s/sfsites/aura?r=1&aura.ApexAction.execute=1',
                        payload={'message': json.dumps({'actions': [action]}), 'aura.context': json.dumps(context),
                                 'aura.pageURI': page, 'aura.token': 'null'}, form=True, opener=opener)
        result = data['actions'][0]
        if result.get('state') != 'SUCCESS':
            raise ShoppingError('unavailable', 'Aetna’s public shopping request failed. No plan availability inferred.')
        value = json.loads(result['returnValue']['returnValue'])
        if value.get('status') is not True:
            raise ShoppingError('response_changed', 'Aetna’s public shopping response changed.')
        return value
    return invoke, base + page, inputs, effective


def aetna_plans(loc):
    invoke, source, inputs, effective = aetna_session(loc)
    result = invoke('getEligibleProd', {'PlanYear': str(loc['year']), 'effectiveDate': effective, 'userInputs': inputs},
                    {'effectiveDate': effective, 'filters': '', 'includeFilterAttrValues': True})
    if result.get('status') is not True or not isinstance(result.get('result', {}).get('IpResult'), list):
        raise ShoppingError('response_changed', 'Aetna’s public plan-list format changed.')
    output = []
    for p in result['result']['IpResult']:
        if str(p['PlanYear']) != str(loc['year']):
            raise ShoppingError('year_mismatch', 'Aetna returned a different plan year. Results withheld.')
        if p.get('DTCValue') != 'Display':
            continue
        if p.get('Family') not in ('MA', 'MAPD', 'PDP'):
            raise ShoppingError('response_changed', 'Aetna returned an unrecognized product type.')
        output.append(plan('Aetna', p['PlanID'], p['Name'], loc, source,
                           'Part D' if p['Family'] == 'PDP' else 'Medicare Advantage',
                           special_needs='SNP' in p.get('SubType', '')))
        output[-1]['has_drug_coverage'] = p['Family'] != 'MA'
    products = {p['PlanID']: p['Id'] for p in result['result']['IpResult']
                if p.get('DTCValue') == 'Display' and re.fullmatch(r'[A-Za-z0-9]{15,18}', p.get('Id', ''))}
    if output:
        try:
            if len(products) != len(output):
                raise ShoppingError('response_changed', 'Aetna product identities could not be linked to prices.')
            prices = invoke('getProduct2Data', {'effectiveDate': effective, 'userInputs': inputs},
                            {'effectiveDate': effective, 'evalOptionalCoverageRelationship': False, 'mergeList': True,
                             'omitEligibility': True, 'rootPricingOnly': True, 'ruleAttributeSetValue': False,
                             'validateCoverageSelection': False, 'products': list(products.values())})
            apply_aetna_prices(output, prices['result']['records'], products, loc['year'])
        except Exception:
            for record in output:
                record['benefit_notice'] = 'Aetna pricing details could not be retrieved. Missing amounts remain unverified.'

    return output


def uhc_plans(loc):
    base = 'https://www.aarpmedicareplans.com'
    source = f"{base}/health-plans/plan-summary/{loc['zip']}/{loc['county'][2:]}/{loc['year']}"
    html = read(source)
    def field(key):
        match = re.search(r'\b' + re.escape(key) + r'\s*:\s*', html)
        if not match:
            raise ShoppingError('response_changed', 'UnitedHealthcare’s public shopping format changed.')
        return json.JSONDecoder().raw_decode(html[match.end():])[0]
    county = field('selectedCounty')
    if county.get('zipCode') != loc['zip'] or county.get('stateCode') != loc['state'] or county.get('fipsStateCode', '') + county.get('fipsCountyCode', '') != loc['county']:
        raise ShoppingError('county_mismatch', 'UnitedHealthcare returned a different location. Results withheld.')
    output = []
    for key, count_key in [('maPlans', 'maPlansCount'), ('pdpPlans', 'pdpPlansCount')]:
        rows = field(key)
        if not isinstance(rows, list) or len(rows) != field(count_key):
            raise ShoppingError('incomplete', 'UnitedHealthcare returned an incomplete public shopping list.')
        for p in rows:
            if str(p['planYear']) != str(loc['year']):
                raise ShoppingError('year_mismatch', 'UnitedHealthcare returned a different plan year. Results withheld.')
            identity = p['contractNumber'] + '-' + p['pbpNumber'] + '-' + p['segmentId']
            raw = p.get('monthlyPremium')
            premium = float(raw) if isinstance(raw, (int, float, str)) and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', str(raw)) else None
            detail = f"{base}/health-plans/details.html/{loc['zip']}/{loc['county'][2:]}/{p['planId']}/{loc['year']}"
            output.append(plan('UnitedHealthcare / AARP', identity, p['planName'], loc, detail,
                               'Part D' if p['planType'] == 'PDP' else 'Medicare Advantage', premium, bool(p.get('snpType'))))
            output[-1]['review_sources'] = {'medication': source + ('#PDP' if p['planType'] == 'PDP' else '#MA'),
                'provider': 'https://findcare.guest.uhc.com/guest-plan-selection/browse?deeplink=eyJsYW5ndWFnZSI6ImVuLVVTIiwibG9iIjoiTVIifQ==',
                'pharmacy': 'https://www.aarpmedicareplans.com/health-plans/aarp-pharmacy.html#/Pharmacy-Search-English'}
            if p['planType'] in ('MA', 'MAPD', 'PDP'):
                output[-1]['has_drug_coverage'] = p['planType'] != 'MA'
    return output


def drx_response(site_carrier, loc):
    run = subprocess.run(['node', str(Path(__file__).with_name('public-shopping.cjs'))],
                         input=json.dumps({'carrier': site_carrier, **loc}), text=True,
                         capture_output=True, timeout=85)
    try:
        result = json.loads(run.stdout)
    except (ValueError, TypeError):
        raise ShoppingError('unavailable', 'Public shopping browser is not installed or unavailable.')
    if result.get('error'):
        raise ShoppingError(result['error'], result.get('message', 'Public shopping unavailable.'))
    if not isinstance(result.get('plans'), list):
        raise ShoppingError('response_changed', 'Public shopping result format changed.')
    return result


def drx_plans(carrier, loc, result=None):
    site_carrier = carrier if carrier in ('Molina', 'Excellus BlueCross BlueShield') else 'Highmark'
    if result is None:
        result = drx_response(site_carrier, loc)
    output = []
    for p in result['plans']:
        if str(p['planYear']) != str(loc['year']):
            raise ShoppingError('year_mismatch', 'The public site returned a different plan year. Results withheld.')
        is_wholecare = 'wholecare' in p['carrierName'].casefold() or p['contractId'] == 'H5932'
        actual = site_carrier if site_carrier in ('Molina', 'Excellus BlueCross BlueShield') else 'Highmark Wholecare' if is_wholecare else 'Highmark'
        if actual != carrier:
            continue
        if actual == 'Highmark' and 'highmark' not in p['carrierName'].casefold():
            raise ShoppingError('response_changed', 'An unexpected carrier appeared in Highmark shopping results.')
        if actual == 'Molina' and 'molina' not in p['carrierName'].casefold():
            raise ShoppingError('response_changed', 'An unexpected carrier appeared in Molina shopping results.')
        if actual == 'Excellus BlueCross BlueShield' and 'excellus' not in p['carrierName'].casefold():
            raise ShoppingError('response_changed', 'An unexpected carrier appeared in Excellus shopping results.')
        identity = p['contractId'] + '-' + p['planId'] + '-' + p['segmentId']
        annual = p.get('annualPlanPremium')
        premium = round(annual / 12, 2) if isinstance(annual, (int, float)) and annual >= 0 else None
        business = 'Part D' if p.get('planTypeAbbreviation') == 'PDP' else 'Medicare Advantage'
        output.append(plan(actual, identity, p['planName'], loc, result['source_url'], business, premium,
                           bool(p.get('planSNPCategories')) or 'SNP' in p['planName']))
        if isinstance(p.get('hasDrugCoverage'), bool):
            output[-1]['has_drug_coverage'] = p['hasDrugCoverage']
        shopping_benefits(output[-1], p.get('maximumOutOfPocketCost'))
    return output


def medico_plans(loc):
    opener = client()
    base = 'https://www.wellabe.com'
    # Use the public site's own ZIP selection, in a fresh anonymous cookie jar.
    read(base + '/products/medicare-supplement', opener=opener)
    result = read(base + '/Home/SetSessionVariable', payload={'zipCode': loc['zip']}, form=True, opener=opener)
    if result.strip().strip('"') != 'Successful Submission':
        raise ShoppingError('location_unresolved', 'Medico/Wellabe’s public ZIP selection could not be verified.')
    html = read(base + '/products/medicare-supplement', opener=opener)
    if 'Speak to an agent' not in html or 'Request a call' not in html:
        raise ShoppingError('response_changed', 'Medico/Wellabe’s public quote flow changed. No availability inferred.')
    error = ShoppingError('quote_required', 'Medico/Wellabe accepted the ZIP, but this public page directs shoppers to an agent for a quote. No year-specific plan list or premium was verified.')
    error.source_checked_at = now()
    raise error


def gtl_plans(loc):
    html = read(CARRIERS['Guarantee Trust Life'])
    if 'Medicare Supplement Insurance' not in html:
        raise ShoppingError('response_changed', 'Guarantee Trust Life’s public product page changed.')
    # This is a product/agent page, not a verified ZIP-and-year results API.
    error = ShoppingError('quote_required', 'Guarantee Trust Life’s public supplement product page was reached. ZIP-and-year plan retrieval is not available through the reviewed page; an agent quote requires follow-up. No plan availability or premium inferred.')
    error.source_checked_at = now()
    raise error


def carefirst_plans(loc):
    source = 'https://www.carefirst.com/medicare-options/compare-medicare-plans/medicare-advantage-plans.html'
    html = read(source)
    if '<title>404 Page</title>' in html or 'we cannot locate this content' in html:
        error = ShoppingError('site_unavailable', 'CareFirst’s public Medicare shopping entry leads to a missing-page screen. No plans or absence of plans could be verified.')
        error.source_checked_at = now()
        raise error
    raise ShoppingError('response_changed', 'CareFirst’s public shopping entry needs revalidation before ZIP-specific results can be shown.')


CONNECTORS = {'Medico': medico_plans, 'Guarantee Trust Life': gtl_plans, 'CareFirst': carefirst_plans, 'UnitedHealthcare / AARP': uhc_plans, 'Aetna': aetna_plans, 'Devoted Health': devoted_plans, 'HealthSpring': healthspring_plans,
              'Highmark': lambda loc: drx_plans('Highmark', loc),
              'Highmark Wholecare': lambda loc: drx_plans('Highmark Wholecare', loc),
              'Molina': lambda loc: drx_plans('Molina', loc),
              'Excellus BlueCross BlueShield': lambda loc: drx_plans('Excellus BlueCross BlueShield', loc)}


def carrier_result(name, loc, connectors=None):
    result = {'carrier': name, 'source_url': CARRIERS[name], 'attempted_at': now(), 'checked_at': None, 'plans': []}
    if name == 'Cigna':
        return {**result, 'status': 'included_under_healthspring',
                'message': 'Former Cigna Medicare plans are searched under HealthSpring. Separate Cigna commercial shopping is not connected.'}
    connector = (CONNECTORS if connectors is None else connectors).get(name)
    if connector is None:
        return {**result, 'status': 'integration_pending', 'message': 'Public shopping connector not yet validated. Plan availability has not been checked.'}
    try:
        plans = connector(loc)
        # Deduplicate within a carrier by exact official identity and year.
        plans = list({p['id']: p for p in plans}.values())
        return {**result, 'status': 'success', 'checked_at': now(), 'plans': plans,
                'message': f'{len(plans)} public shopping plans returned for the selected location and year.'}
    except ShoppingError as e:
        return {**result, 'status': e.status, 'message': e.message, 'source_checked_at': getattr(e, 'source_checked_at', None)}
    except HTTPError as e:
        if name == 'CareFirst' and e.code == 404:
            return {**result, 'status': 'site_unavailable', 'source_checked_at': now(),
                    'message': 'CareFirst’s public Medicare shopping entry returned a missing-page response. Plan availability remains unverified.'}
        status = 'sign_in_required' if e.code == 401 else 'access_blocked' if e.code == 403 else 'unavailable'
        return {**result, 'status': status, 'message': 'Public shopping request could not be completed. Plan availability remains unverified.'}
    except (TimeoutError, URLError, subprocess.TimeoutExpired):
        return {**result, 'status': 'unavailable', 'message': 'Public shopping site timed out or could not be reached. Plan availability remains unverified.'}
    except Exception:
        return {**result, 'status': 'response_changed', 'message': 'Public shopping response could not be verified. Plan availability remains unverified.'}


def search(params):
    import app
    zip_code = params.get('zip', '').strip()
    county = params.get('county', '').strip()
    year = str(params.get('year', '2027'))
    if not re.fullmatch(r'[0-9]{5}', zip_code):
        raise ValueError('Enter a five-digit ZIP code.')
    if year not in ('2026', '2027'):
        raise ValueError('Select a supported plan year.')
    if params.get('state') and params['state'] not in app.STATES:
        raise ValueError('Select one of the configured states.')
    if not _slots.acquire(blocking=False):
        raise ShoppingError('busy', 'Carrier searches are busy. Please retry shortly.')
    try:
        geo = locations(zip_code)
        counties = [c for c in geo['counties'] if not params.get('state') or c['state'] == params['state']]
        selected = next((c for c in counties if c['code'] == county), None)
        if not county and params.get('county_name'):
            matches = [c for c in counties if c['name'].casefold() == params['county_name'].casefold()]
            if len(matches) == 1:
                selected = matches[0]
        if not county and len(counties) == 1:
            selected = counties[0]
        if county and not selected:
            raise ValueError('Select a county associated with this ZIP. County codes must come from the carrier website ZIP lookup.')
        if selected is None:
            return {'plans': [], 'carriers': [], 'counties': counties, 'needs_county': bool(counties), 'complete': False,
                    'notice': 'Select your county to search all carrier websites.' if counties else geo['notice']}
        loc = {'zip': zip_code, 'county': selected['code'], 'county_name': selected['name'], 'state': selected['state'], 'year': int(year)}
        with ThreadPoolExecutor(max_workers=6) as pool:
            connectors = CONNECTORS.copy()
            if 'Highmark' in connectors and 'Highmark Wholecare' in connectors:
                shared = pool.submit(drx_response, 'Highmark', loc)
                for name in ('Highmark', 'Highmark Wholecare'):
                    connectors[name] = lambda location, name=name: drx_plans(name, location, shared.result())
            results = list(pool.map(lambda name: carrier_result(name, loc, connectors), CARRIERS))
        plans = [p for r in results for p in r['plans']]
        business = params.get('business', '')
        if business:
            plans = [p for p in plans if p['business'] == business]
        return {'location': loc, 'plans': plans, 'carriers': [{k:v for k,v in r.items() if k != 'plans'} | {'plan_count': len(r['plans'])} for r in results],
                'counties': counties, 'selected_county': selected['code'],
                'complete': all(r['status'] in ('success', 'included_under_healthspring') for r in results),
                'notice': 'Medicare Advantage and Part D results from verified public shopping responses. Medigap and supplemental quotes are not included. Review each carrier status. Premiums exclude Part B and other costs. Selected medications and providers are checked separately using connected exact-plan formularies and directories; other coverage remains unverified.'}
    finally:
        _slots.release()
