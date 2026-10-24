import json
import threading
import unittest
from unittest.mock import patch
import carrier_websites as c

LOC = dict(zip='28202', county='37119', county_name='Mecklenburg', state='NC', year=2027)
GEO = {'counties': [{'code': '37119', 'name': 'Mecklenburg', 'state': 'NC'}], 'notice': 'Select county'}


class CarrierWebsiteTests(unittest.TestCase):
    def test_configured_states_and_ambiguous_zip(self):
        import app
        with patch.object(c, 'get_json', return_value=[{'CountyFIPS':'37119','CountyName':'Mecklenburg','State':'NC'},
                                                      {'CountyFIPS':'06001','CountyName':'Alameda','State':'CA'}]):
            result = c.locations('28202')
        self.assertEqual(result['states'], app.STATES)
        self.assertEqual(len(result['counties']), 1)
        with patch.object(c, 'locations', return_value={'counties':GEO['counties'] + [{'code':'37001','name':'Alamance','state':'NC'}]}):
            self.assertTrue(c.search({'zip':'28202'})['needs_county'])

    def test_invalid_zip_year_state_or_mismatched_county(self):
        for params in [{'zip':'2820'}, {'zip':'２８２０２'}, {'zip':'28202','year':'2025'}, {'zip':'28202','state':'CA'}]:
            with self.subTest(params=params), self.assertRaises(ValueError):c.search(params)
        with patch.object(c, 'locations', return_value=GEO), self.assertRaises(ValueError):
            c.search({'zip':'28202','county':'34590'})  # SSA is not FIPS.

    def test_runs_in_parallel_and_keeps_partial_results(self):
        barrier = threading.Barrier(3, timeout=2)
        def good(loc):
            barrier.wait()
            self.assertEqual(loc, LOC)
            self.assertNotIn('medication', loc)
            return [c.plan('Aetna', 'H1234-001', 'Fixture plan', loc, c.AETNA_SOURCE, premium=0)]
        def failed(loc):
            barrier.wait()
            raise TimeoutError()
        with patch.object(c, 'locations', return_value=GEO), patch.dict(c.CONNECTORS, {'Aetna':good,'Devoted Health':failed,'HealthSpring':failed}, clear=True):
            result = c.search({'zip':'28202','year':'2027','medication':'never-send','provider':'never-send'})
        self.assertEqual(len(result['plans']), 1)
        self.assertEqual(result['plans'][0]['premium'], 0)
        self.assertEqual(len(result['carriers']), 12)
        self.assertFalse(result['complete'])
        statuses = {r['carrier']:r for r in result['carriers']}
        self.assertIsNotNone(statuses['Aetna']['checked_at'])
        self.assertIsNone(statuses['Devoted Health']['checked_at'])
        self.assertEqual(statuses['Cigna']['status'], 'included_under_healthspring')

    def test_aetna_wrong_year_and_changed_response_are_not_no_plans(self):
        html='/s/sfsites/l/%7B%22mode%22%3A%22PROD%22%2C%22fwuid%22%3A%22x%22%2C%22app%22%3A%22x%22%2C%22loaded%22%3A%7B%7D%7D'
        payload={'status':True,'result':{'IpResult':[{'PlanYear':'2026'}]}}
        response={'actions':[{'state':'SUCCESS','returnValue':{'returnValue':json.dumps(payload)}}]}
        with patch.object(c, 'read', return_value=html), patch.object(c, 'get_json', return_value=response), self.assertRaises(c.ShoppingError) as caught:
            c.aetna_plans(LOC)
        self.assertEqual(caught.exception.status,'year_mismatch')
        with patch.object(c, 'read', return_value='<html>Sign in</html>'), self.assertRaises(c.ShoppingError):c.aetna_plans(LOC)

    def test_devoted_uses_ssa_mapping_and_exact_county_and_year(self):
        data={'result':{'data':{'site':{'siteMetadata':{'ssaCountiesForMarketablePbps':[
            {'state_abbreviation':'NC','display_name':'Mecklenburg','code':'34590','zip_codes':[{'zip_code':'28202'}]}]}},
            'allPbps':{'nodes':[
                {'year':'2027','name':'Fixture current','record_locator':'H1234-001-000-2027','service_areas':[{'county_code':'34590'}]},
                {'year':'2026','name':'Fixture old','record_locator':'H1234-001-000-2026','service_areas':[{'county_code':'34590'}]},
                {'year':'2027','name':'Fixture other','record_locator':'H1234-002-000-2027','service_areas':[{'county_code':'37119'}]}]}}}}
        with patch.object(c, 'get_json', return_value=data):
            result=c.devoted_plans(LOC)
            self.assertEqual([p['name'] for p in result],['Fixture current'])
            with self.assertRaises(c.ShoppingError):c.devoted_plans({**LOC,'county_name':'Wrong county'})

    def test_healthspring_zero_premium_and_no_session_exposure(self):
        responses=[[{'SessionID':'anonymous-session'}],{'MedicarePlans':[{
            'ID':'p1','ContractID':'H1234','PlanID':'001','SegmentID':'000','PlanYear':'2027',
            'PlanName':'Fixture','AnnualPlanPremium':0,'PlanSubType':'PPO','PlanSNPCategories':[]}]}]
        with patch.object(c, 'get_json', side_effect=responses):
            plans=c.healthspring_plans(LOC)
        self.assertEqual(plans[0]['premium'],0)
        self.assertNotIn('anonymous-session',json.dumps(plans))

    def test_sources_cannot_redirect_to_arbitrary_hosts(self):
        for url in ['http://www.devoted.com/x','https://example.com/','https://user:password@www.devoted.com/']:
            with self.assertRaises(c.ShoppingError):c.validate_url(url)

    def test_http_dispatch_and_dashboard_assets_without_socket(self):
        import app
        from unittest.mock import Mock
        with patch.object(c, 'search', return_value={'plans':[], 'complete':False}):
            for path in ['/dashboard/', '/dashboard/carrier-websites.js', '/api/carrier-websites?zip=28202']:
                handler = object.__new__(app.Handler)
                handler.path = path
                handler.respond = Mock()
                handler.do_GET()
                self.assertTrue(handler.respond.call_args.args[0])
        handler.path = '/dashboard/../../app.py'
        handler.send_error = Mock()
        handler.do_GET()
        handler.send_error.assert_called_once_with(404)

    def test_healthspring_s_contract_is_drug_only_even_without_pdp_subtype(self):
        payload={'MedicarePlans':[{'PlanYear':2027,'ContractID':'S5715','PlanID':'024','SegmentID':'000','ID':'fixture','PlanName':'Assurance Rx (PDP)','PlanSubType':'RX','AnnualPlanPremium':486,'MaximumOutOfPocketCost':0}]}
        with patch.object(c,'get_json',side_effect=[[{'SessionID':'fixture'}],payload]):
            record=c.healthspring_plans(LOC)[0]
        self.assertEqual(record['business'],'Part D')
        self.assertNotIn('moop',record.get('shopping_metrics',{}))

    def test_healthspring_exact_shopping_benefits_and_document_binding(self):
        record=c.plan('HealthSpring','H9725-009-003','Preferred',LOC,'https://shop.healthspringmedicare.com/28202/37119/plan/fixture')
        c.shopping_benefits(record,4450)
        raw={'PlanDataFields':[
            {'Name':'Over-the-Counter Items (In Network)','Type':'In Network','Description':'$20.00 every 3 months.'},
            {'Name':'Doctor Specialty Visit (In Network)','Type':'In Network','Description':'$20 copay per visit.'},
            {'Name':'Inpatient Hospital Care (In Network)','Type':'In Network','Description':'$290 copay per day for days 1-5.<br>$0 copay per day for days 6-90.','Range':[{'RangeMin':1,'RangeMax':5,'Amount':290,'AmountType':1},{'RangeMin':6,'RangeMax':90,'Amount':0,'AmountType':1}]},
            {'Name':'Dental (included with plan) (In Network)','Type':'In Network','Description':'Comprehensive dental included.'},
            {'Name':'Dental Services (In Network)','Type':'In Network','Description':'$0 copay.'},
            {'Name':'Other','Type':'In Network','Description':None}],
            'Documents':[{'Types':[{'Name':'SUMMARY_OF_BENEFITS'}],'Name':'Summary of Benefits','Url':'https://www.healthspring.com/static/docs/medicare/plans/2027/sb-h9725-009-003.pdf'},
                         {'Types':[{'Name':'SUMMARY_OF_BENEFITS'}],'Url':'https://www.healthspring.com/static/docs/medicare/plans/2027/sb-h9725-009-001.pdf'}]}
        c.healthspring_benefits(record,raw)
        self.assertEqual({k:v['amount'] for k,v in record['shopping_metrics'].items()},{'moop':4450,'otc':20,'specialist':20,'hospital':1450})
        self.assertNotIn('dental',record['shopping_metrics'])
        self.assertEqual(len(record['documents']),1)
        self.assertIn('annual dollar allowance',record['benefit_review_notes']['dental'])
        raw['PlanDataFields'][0]['Description']='$200 every 3 months for qualifying members.'
        raw['PlanDataFields'][2]['Range'][1]['RangeMin']=5
        record['shopping_metrics']={}
        c.healthspring_benefits(record,raw)
        self.assertNotIn('otc',record['shopping_metrics'])
        self.assertNotIn('hospital',record['shopping_metrics'])

    def test_healthspring_snp_flag_uses_type_or_explicit_name(self):
        row={'ID':'fixture','ContractID':'H1234','PlanID':'001','SegmentID':'000','PlanYear':'2027','PlanName':'TotalCare (HMO D-SNP)','AnnualPlanPremium':0,'PlanSubType':'HMO','PlanSNPCategories':[],'SNPType':1}
        with patch.object(c,'get_json',side_effect=[[{'SessionID':'fixture'}],{'MedicarePlans':[row]}]):
            self.assertTrue(c.healthspring_plans(LOC)[0]['special_needs'])

    def test_drx_detail_adapter_is_conservative_about_quarterly_benefits(self):
        r=c.plan('Highmark Wholecare','H1234-001-000','Fixture',LOC,'https://example.com')
        c.shopping_benefits(r,1000)
        raw={'drugDeductible':700,'planDataFields':[
            {'name':'Over-the-Counter Items (In Network)','type':'In Network','description':'In-Network: $0 copay; Maximum plan benefit coverage of $35 every 3 month.'},
            {'name':'Doctor Specialty Visit (In Network)','type':'In Network','description':'In-Network: $25 copay per visit'},
            {'name':'Inpatient Hospital Care (In Network)','type':'In Network','description':'In-Network: $225 copay per day for days 1-5, $0 copay per day for days 6-90.'}]}
        c.drx_benefits(r,raw)
        self.assertEqual(r['shopping_metrics']['otc']['amount'],35)
        self.assertEqual(r['shopping_metrics']['specialist']['amount'],25)
        self.assertEqual(r['shopping_metrics']['hospital']['amount'],1125)
        self.assertIn('$700',r['drug_details'][0]['description'])
        raw['planDataFields'][0]['description']='In-Network: $35 per month for qualifying members.'
        c.shopping_benefits(r);c.drx_benefits(r,raw)
        self.assertNotIn('otc',r['shopping_metrics'])

    def test_pdp_details_keep_medical_metrics_empty_and_pharmacy_conditions_explicit(self):
        r=c.plan('HealthSpring','S5715-029-000','Assurance',LOC,'https://example.com',business='Part D')
        c.shopping_benefits(r,0)
        c.healthspring_benefits(r,{'DrugDeductible':700,'FormularyExternalID':'27061','FormularyTiers':[{'TierDescription':'Tier 3','CopayPrices':[{'Cost':0.22,'CostType':2,'DaysOfSupply':30,'DefaultBenefit':True,'IsMailOrder':False,'IsPreferredPharmacy':True}]}]})
        self.assertEqual(r['shopping_metrics'],{})
        self.assertEqual(r['formulary_id'],'27061')
        self.assertIn('22% coinsurance',r['drug_details'][1]['description'])
        self.assertIn('preferred retail',r['drug_details'][1]['description'])
        self.assertIn('Not an exact prescription quote',r['drug_details'][1]['description'])

    def test_uhc_shopping_uses_explicit_network_rows_only(self):
        r=c.plan('UnitedHealthcare / AARP','H1234-001-000','Fixture',LOC,'https://example.com')
        raw={'planBenefit':[{'benefitName':'Out-of-pocket maximum','networkTypes':[{'networkType':'OON','benefitDescription':'$14,800 when using in and out-of-network providers'},{'networkType':'INN','benefitDescription':'$9,500'}]}],
             'medicalBenefit':[{'benefitName':'PCP and Specialist','networkTypes':[{'networkType':'OON','benefitDescription':'$0 PCP and $90 specialist visits'},{'networkType':'INN','benefitDescription':'$0 PCP and $45 specialist visits'}]}]}
        c.uhc_shopping_benefits(r,raw)
        self.assertEqual(r['shopping_metrics']['moop']['amount'],9500)
        self.assertEqual(r['shopping_metrics']['specialist']['amount'],45)
        r['business']='Part D';c.uhc_shopping_benefits(r,raw)
        self.assertEqual(r['shopping_metrics'],{})

    def test_aetna_official_source_opens_selected_plan(self):
        from urllib.parse import urlparse,parse_qs
        from unittest.mock import Mock
        invoke=Mock(return_value={'status':True,'result':{'IpResult':[{'PlanID':'H5521-348','Name':'Signature Giveback','Family':'MAPD','PlanYear':'2027','DTCValue':'Display'}]}})
        source='https://enrollmedicare.aetna.com/s/shop?PlanYear=2027&ZipCode=28202&CountyFIPS=37119&step=PlanList'
        with patch.object(c,'aetna_session',return_value=(invoke,source,{},'2027-01-02')):
            row=c.aetna_plans(LOC)[0]
        query=parse_qs(urlparse(row['source_url']).query)
        self.assertEqual(query['PlanID'],['H5521-348-2027'])
        self.assertEqual(query['ZipCode'],['28202'])
        self.assertEqual(query['CountyFIPS'],['37119'])

    def test_successful_carrier_search_seeds_document_validation_snapshot(self):
        import app
        from unittest.mock import Mock
        plan=c.plan('Aetna','H5521-348','Fixture',LOC,'https://enrollmedicare.aetna.com')
        data={'location':LOC,'plans':[plan],'carriers':[]}
        handler=object.__new__(app.Handler);handler.path='/api/carrier-websites?zip=28202';handler.respond=Mock()
        with patch.object(c,'search',return_value=data),patch.object(app.plan_documents,'remember_search') as remember:
            handler.do_GET()
        remember.assert_called_once_with(LOC,[plan])
        self.assertEqual(handler.respond.call_args.args[1],'application/json')

    def test_uhc_exact_location_year_and_zero_premium(self):
        values={'selectedCounty':{'zipCode':'28202','stateCode':'NC','fipsStateCode':'37','fipsCountyCode':'119'},
                'maPlansCount':1,'pdpPlansCount':0,'pdpPlans':[],
                'maPlans':[{'planYear':'2027','contractNumber':'H1234','pbpNumber':'001','segmentId':'000','planId':'H1234001000','planName':'Fixture UHC','monthlyPremium':'0','planType':'MAPD'}]}
        def html():return '\n'.join(k+': '+json.dumps(v)+',' for k,v in values.items())
        with patch.object(c, 'read', side_effect=lambda *a,**kw:html()):
            self.assertEqual(c.uhc_plans(LOC)[0]['premium'],0)
            values['selectedCounty']['fipsCountyCode']='001'
            with self.assertRaises(c.ShoppingError) as caught:c.uhc_plans(LOC)
            self.assertEqual(caught.exception.status,'county_mismatch')

    def test_highmark_and_wholecare_split_exact_records(self):
        def record(contract, name):return {'contractId':contract,'planId':'001','segmentId':'000','planYear':2027,
                'planName':name,'carrierName':name,'annualPlanPremium':0,'planTypeAbbreviation':'MAPD'}
        payload={'source_url':'https://highmark1.destinationrx.com/PC/2027/Shopping/Home',
                 'plans':[record('H5932','Highmark Wholecare Fixture'),record('H1234','HIGHMARK Fixture')]}
        for carrier, expected in [('Highmark','H1234-001-000'),('Highmark Wholecare','H5932-001-000')]:
            plans=c.drx_plans(carrier,LOC,payload)
            self.assertEqual([p['official_id'] for p in plans],[expected])
        payload['plans'][0]['planYear']=2026
        with self.assertRaises(c.ShoppingError):c.drx_plans('Highmark Wholecare',LOC,payload)

    def test_quote_page_check_is_never_successful_plan_check(self):
        with patch.object(c, 'read', return_value='Medicare Supplement Insurance'):
            result=c.carrier_result('Guarantee Trust Life',LOC)
        self.assertEqual(result['status'],'quote_required')
        self.assertIsNone(result['checked_at'])
        self.assertIsNotNone(result['source_checked_at'])
        self.assertEqual(result['plans'],[])

    def test_shopping_benefit_fields_and_healthspring_review_links(self):
        record=c.plan('HealthSpring','H1234-001-000','Fixture',LOC,'https://shop.healthspringmedicare.com/')
        self.assertIn('/28202/37119/prescriptions?planYear=2027',record['review_sources']['medication'])
        self.assertIn('/pharmacy?planYear=2027',record['review_sources']['pharmacy'])
        self.assertEqual(c.shopping_benefits(record,0)['shopping_metrics']['moop']['amount'],0)
        for value in (None,False,-1,float('inf')):
            self.assertEqual(c.shopping_benefits(dict(record),value)['shopping_metrics'],{})
        pdp={**record,'business':'Part D'}
        self.assertEqual(c.shopping_benefits(pdp,500)['shopping_metrics'],{})

    def test_aetna_prices_require_exact_product_and_year(self):
        def record(identity):return c.plan('Aetna',identity,'Fixture',LOC,c.AETNA_SOURCE)
        good={'CalculatedPriceData':{'PlanID':'H1234-001','productKey':'exact-product',
              'ProductAttributeMapping__ContractPBPPlanYear':'H1234-001-2027','productFamily':'MA',
              'PlanPremiumMA':0,'ProductAttributeMapping__IN_MOOP':'$7,150'}}
        plan=record('H1234-001')
        c.apply_aetna_prices([plan],[good],{'H1234-001':'exact-product'},2027)
        self.assertEqual(plan['premium'],0)
        self.assertEqual(plan['shopping_metrics']['moop']['amount'],7150)
        for change in [{'productKey':'other-product'}, {'ProductAttributeMapping__ContractPBPPlanYear':'H1234-001-2026'}]:
            with self.subTest(change=change):
                plan=record('H1234-001')
                c.apply_aetna_prices([plan],[{'CalculatedPriceData':{**good['CalculatedPriceData'],**change}}],{'H1234-001':'exact-product'},2027)
                self.assertIsNone(plan['premium'])
        plan=record('H1234-001')
        c.apply_aetna_prices([plan],[good,good],{'H1234-001':'exact-product'},2027)
        self.assertIsNone(plan['premium'])
