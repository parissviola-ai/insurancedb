import unittest
from unittest.mock import patch
import plan_documents as docs

PLAN={'carrier':'UnitedHealthcare / AARP','official_id':'H1234-001-000','name':'AARP Medicare Advantage from UHC NC-15 (HMO-POS)','year':2027,'state':'NC','source_url':'https://www.aarpmedicareplans.com/health-plans/details.html/28613/035/H1234001000/2027'}


class PlanDocumentTests(unittest.TestCase):
    def test_document_urls_are_restricted(self):
        docs.pdf_url('https://www.aarpmedicareplans.com/alphadog/fixture')
        docs.pdf_url('https://www.aetna.com/medicare/documents/individual/2027/fixture.pdf')
        docs.pdf_url('https://www.healthspring.com/static/docs/medicare/plans/2027/sb-h9725-009-003.pdf')
        for url in ['http://www.aarpmedicareplans.com/alphadog/x','https://example.com/x.pdf','https://www.aetna.com/account','https://user:pass@www.aetna.com/medicare/documents/x','https://www.aetna.com:8000/medicare/documents/x']:
            with self.subTest(url=url),self.assertRaises(ValueError):docs.pdf_url(url)

    def test_healthspring_full_segment_catalog_required_for_short_pdf_cover(self):
        plan={**PLAN,'carrier':'HealthSpring','official_id':'H9725-009-003','name':'HealthSpring Preferred (HMO)'}
        text='Summary of Benefits 2027 HealthSpring Preferred (HMO) H9725_009'
        url='https://www.healthspring.com/static/docs/medicare/plans/2027/sb-h9725-009-003.pdf'
        docs.verified_text(text,plan,'benefits',url)
        for wrong in [None,url.replace('009-003','009-001'),url.replace('/2027/','/2026/')]:
            with self.assertRaises(ValueError):docs.verified_text(text,plan,'benefits',wrong)
        with self.assertRaises(ValueError):docs.verified_text(text.replace('Preferred','Courage'),plan,'benefits',url)

    def test_healthspring_dental_and_otc_are_allowances_not_copays(self):
        text=('Dental Allowance $0 for preventive and comprehensive dental services.\n'
              'Maximum Coverage Amount $1,450 yearly allowance for preventive and\ncomprehensive dental services.\n'
              'Over-the-Counter (OTC) Allowance Get an allowance each quarter to help\n'
              '$45 allowance each quarter for eligible OTC items.')
        metrics,_,_=docs.parse_benefits(text,'https://example.com/sb.pdf')
        self.assertEqual(metrics['dental']['amount'],1450)
        self.assertEqual(metrics['otc']['amount'],45)
        self.assertNotEqual(metrics['dental']['amount'],0)
        metrics,_,_=docs.parse_benefits('Maximum Coverage Amount $2,000 yearly allowance for hearing aids.','https://example.com/sb.pdf')
        self.assertNotIn('dental',metrics)

    def test_shared_silverscript_source_only_supplies_uniform_drug_wording(self):
        plan={**PLAN,'carrier':'Aetna','official_id':'S5601-016','name':'SilverScript Choice (PDP) S5601-016','business':'Part D'}
        url='https://www.aetna.com/medicare/documents/individual/2027/sb/en/Y0001_S5601_SB_2027_M.pdf'
        text='2027 Summary of Benefits SilverScript Choice (PDP)\nAnnual deductible                  $700\nNorth Carolina $143.50 $0 $7 23% 34% 25%'
        docs.verified_text(text,plan,'benefits',url)
        details=docs.parse_drug_details(text,url,'2026-10-24')
        self.assertIn('$700',details[0]['description'])
        self.assertNotIn('$143.50',details[0]['description'])
        with self.assertRaises(ValueError):docs.verified_text(text,{**plan,'name':'SilverScript Another (PDP)'},'benefits',url)
        with self.assertRaises(ValueError):docs.verified_text(text,plan,'benefits',url.replace('S5601','S9999'))

    def test_drug_deductible_preserves_tier_exemptions(self):
        text='Annual Prescription Drug Deductible$0 per year for Tier 1 and Tier 2; $300 for Tier 3, Tier 4\n and Tier 5 Part D prescription drugs.\n\nWhat is coinsurance?'
        rows=docs.parse_drug_details(text,'https://example.com/sb.pdf','2026-10-24')
        self.assertIn('$300',rows[0]['description'])
        self.assertIn('Tier 1 and Tier 2',rows[0]['description'])
        self.assertNotIn('What is',rows[0]['description'])

    def test_identity_year_and_cover_name(self):
        text='Summary of Benefits 2027\nH1234-001-000\nAARP Medicare Advantage from UHC NC-15 (HMO-POS)'
        docs.verified_text(text,PLAN,'benefits')
        for wrong in [text.replace('2027','2026'),text.replace('H1234-001-000','H1234-002-000'),text.replace('NC-15','NC-99')]:
            with self.assertRaises(ValueError):docs.verified_text(wrong,PLAN,'benefits')
        docs.verified_text('Shared formulary for 2027',PLAN,'formulary')
        with self.assertRaises(ValueError):docs.verified_text('Shared formulary 2026',PLAN,'formulary')

    def test_benefit_units_do_not_turn_allowances_into_copays(self):
        text=('Annual dental maximum: $1,500\n\fOTC credit $25 credit every quarter\n'
              'Routine eyewear $150 allowance every 2 No coverage years\n'
              'Hearing aids2 $700 allowance for 2 hearing aids every year\n'
              'Specialists1,2 $35 copay\n')
        metrics,notes,unavailable=docs.parse_benefits(text,'https://example.com/fixture.pdf')
        self.assertEqual(metrics['dental']['amount'],1500)
        self.assertEqual(metrics['otc']['amount'],25)
        self.assertEqual(metrics['specialist']['amount'],35)
        self.assertNotIn('vision',metrics)
        self.assertNotIn('hearing',metrics)
        self.assertIn('2 years',unavailable['vision'])
        self.assertIn('not an Advanced',unavailable['hearing'])
        self.assertIn('#page=2',metrics['otc']['source_url'])

    def test_allowance_is_scoped_to_dental_or_vision(self):
        text=('Hearing aids You get an annual benefit amount (allowance) of $1,250 per ear.\n'
              'Dental services You get an annual benefit amount (allowance) of $1,500 for covered comprehensive services.\n'
              'Vision services You get an annual benefit amount (allowance) of $100 for covered prescription eyewear.')
        metrics,_,_=docs.parse_benefits(text,'https://example.com/x.pdf')
        self.assertEqual(metrics['dental']['amount'],1500)
        self.assertEqual(metrics['vision']['amount'],100)
        metrics,_,_=docs.parse_benefits('Hearing aids annual benefit amount (allowance) of $1,250 per ear.','https://example.com/x.pdf')
        self.assertNotIn('dental',metrics)

    def test_medical_maximum_requires_explicit_network_context(self):
        text=('In-network    Out-of-network\nMonthly plan premium $53\n'
              'Maximum out-of-pocket amount (does $4,450    $6,700\n'
              'not include prescription drugs) This is the most you pay each year.')
        metrics,_,_=docs.parse_benefits(text,'https://example.com/sb.pdf')
        self.assertEqual(metrics['moop']['amount'],4450)
        metrics,_,_=docs.parse_benefits(text.replace('In-network    Out-of-network','Out-of-network    In-network'),'https://example.com/sb.pdf')
        self.assertNotIn('moop',metrics)
        metrics,_,_=docs.parse_benefits('Maximum out-of-pocket amount (does $8,900\nnot include prescription drugs) Most you pay each year for services received from\nnetwork providers.','https://example.com/hmo.pdf')
        self.assertEqual(metrics['moop']['amount'],8900)
        text='Your combined maximum out-of-pocket amount is $6,700. Your in-network maximum out-of-pocket amount (MOOP) is $4,450.'
        metrics,_,_=docs.parse_benefits(text,'https://example.com/eoc.pdf')
        self.assertEqual(metrics['moop']['amount'],4450)

    def test_aetna_service_allowance_and_quarterly_wallet_layouts(self):
        text=('Summary\fDental services\nBenefit Your in-network costs Your out-of-network costs\n'
              'Dental services $0 copay for covered services 50% coinsurance\n'
              'You get an annual benefit amount (allowance) of $2,000 for covered\n'
              'services. You are responsible for costs over this amount.\n'
              'Vision services annual benefit amount (allowance) of $100 for eyewear.\n'
              'CVS Over-the-Counter You get a $50 quarterly benefit amount (allowance) on the Aetna\n'
              '(OTC) Wallet Medicare Extra Benefits Card.')
        metrics,_,_=docs.parse_benefits(text,'https://example.com/sb.pdf')
        self.assertEqual(metrics['dental']['amount'],2000)
        self.assertEqual(metrics['otc']['amount'],50)
        self.assertEqual(metrics['otc']['period'],'quarter')
        self.assertTrue(metrics['dental']['source_url'].endswith('#page=2'))
        text='CVS Over-the-Counter (OTC) Wallet with a $25 quarterly benefit amount (allowance).'
        self.assertEqual(docs.parse_benefits(text,'https://example.com/eoc.pdf')[0]['otc']['amount'],25)
        text='Over-the-counter (OTC) creditQuarterly credit is $50 Not Covered'
        self.assertEqual(docs.parse_benefits(text,'https://example.com/eoc.pdf')[0]['otc']['amount'],50)

    def test_optional_dental_is_not_an_included_allowance(self):
        text=('Dental services $0 copay for preventive services.\n'
              'This plan does not include comprehensive services. You can purchase coverage for an additional premium.\n'
              'Optional Supplemental Benefits\nDental services You get an annual benefit amount (allowance) of $1,500 for covered services.')
        metrics,notes,unavailable=docs.parse_benefits(text,'https://example.com/sb.pdf')
        self.assertNotIn('dental',metrics)
        self.assertIn('costs extra',unavailable['dental'])
        text='Dental services through the Platinum Dental Rider. Optional supplemental benefits Platinum Dental Rider premium Additional $54 per month'
        metrics,_,unavailable=docs.parse_benefits(text,'https://example.com/sb.pdf')
        self.assertNotIn('dental',metrics)
        self.assertIn('Optional paid',unavailable['dental'])

    def test_conditional_or_combined_wallet_does_not_rank_as_otc_only(self):
        for condition in ['For qualifying members only.','This wallet also covers food and utilities.']:
            text='OTC credit $100 credit every quarter. '+condition
            metrics,notes,unavailable=docs.parse_benefits(text,'https://example.com/sb.pdf')
            self.assertNotIn('otc',metrics)
            self.assertIn('$100 / quarter',unavailable['otc'])
            self.assertIn('eligibility',notes['otc'])
        text='CVS Over-the-Counter (OTC) Wallet with a $25 monthly benefit amount (allowance).'
        self.assertNotIn('otc',docs.parse_benefits(text,'https://example.com/sb.pdf')[0])

    def test_formulary_rows_keep_wraps_and_page_numbers(self):
        text=('C1  Fixture drug (Oral Suspension     G   2   QL\n   Reconstituted)\n\f'
              'C1  Another fixture (Oral Tablet)     B   4   PA\n')
        rows=docs.formulary_rows(text,'UnitedHealthcare / AARP')
        self.assertEqual(rows[0]['name'],'Fixture drug (Oral Suspension Reconstituted)')
        self.assertEqual(rows[0]['tier'],'2')
        self.assertEqual(rows[1]['restrictions'],'PA')
        self.assertEqual(rows[1]['page'],2)
        text='     fixture/clavulanate   2   MO\n     suspension 600mg/5ml\nPENICILLINS\n'
        rows=docs.formulary_rows(text,'Aetna')
        self.assertEqual(rows[0]['name'],'fixture/clavulanate suspension 600mg/5ml')
        self.assertNotIn('PENICILLINS',rows[0]['name'])

    def test_wrong_county_or_unavailable_plan_stops_before_documents(self):
        geo={'counties':[{'code':'37035','name':'Catawba','state':'NC'}]}
        valid={'carrier':'UnitedHealthcare / AARP','plan_id':'H1234-001-000','zip':'28613','county':'37035','year':'2027'}
        with patch.object(docs.carriers,'locations',return_value=geo),patch.object(docs.carriers,'uhc_plans',return_value=[]),patch.object(docs,'document_catalog') as catalog:
            with self.assertRaises(ValueError):docs.lookup(valid)
            with self.assertRaises(ValueError):docs.lookup({**valid,'county':'37119'})
            catalog.assert_not_called()

    def test_evidence_otc_fallback_and_conflicts(self):
        params={'carrier':PLAN['carrier'],'plan_id':PLAN['official_id'],'zip':'28613','county':'37035','year':'2027'}
        catalog=[{'kind':'benefits','label':'SB','url':'https://www.aarpmedicareplans.com/alphadog/sb'},
                 {'kind':'evidence','label':'EOC','url':'https://www.aarpmedicareplans.com/alphadog/eoc'}]
        cover='Summary 2027 H1234-001-000 AARP Medicare Advantage from UHC NC-15 (HMO-POS)\n'
        geo={'counties':[{'code':'37035','name':'Catawba','state':'NC'}]}
        metadata={'retrieved_at':'2026-10-24','sha256':'fixture','pages':1}
        with patch.object(docs.carriers,'locations',return_value=geo),patch.object(docs.carriers,'uhc_plans',return_value=[PLAN]),patch.object(docs,'document_catalog',side_effect=lambda *a:[dict(d) for d in catalog]):
            with patch.object(docs,'read_pdf',side_effect=[(cover,metadata),(cover+'Over-the-counter (OTC) creditQuarterly credit is $50',metadata)]):
                result=docs.lookup(params)
                self.assertEqual(result['benefit_metrics']['otc']['amount'],50)
                self.assertIn('/eoc#page=1',result['benefit_metrics']['otc']['source_url'])
            with patch.object(docs,'read_pdf',side_effect=[(cover+'OTC credit $25 credit every quarter',metadata),(cover+'Over-the-counter (OTC) creditQuarterly credit is $50',metadata)]):
                result=docs.lookup(params)
                self.assertNotIn('otc',result['benefit_metrics'])
                self.assertIn('Conflicting',result['benefit_unavailable']['otc'])

    def test_conflicting_pdf_amounts_withheld_and_mismatched_cover_stops_companions(self):
        params={'carrier':PLAN['carrier'],'plan_id':PLAN['official_id'],'zip':'28613','county':'37035','year':'2027'}
        catalog=[{'kind':'benefits','label':'SB','url':'https://www.aarpmedicareplans.com/alphadog/sb'},
                 {'kind':'evidence','label':'EOC','url':'https://www.aarpmedicareplans.com/alphadog/eoc'}]
        cover='Summary 2027 H1234-001-000 AARP Medicare Advantage from UHC NC-15 (HMO-POS)\n'
        geo={'counties':[{'code':'37035','name':'Catawba','state':'NC'}]}
        metadata={'retrieved_at':'2026-10-24','sha256':'fixture','pages':1}
        with patch.object(docs.carriers,'locations',return_value=geo),patch.object(docs.carriers,'uhc_plans',return_value=[PLAN]),patch.object(docs,'document_catalog',side_effect=lambda *a:[dict(d) for d in catalog]):
            with patch.object(docs,'read_pdf',side_effect=[(cover+'Annual dental maximum: $1,000',metadata),(cover+'Annual dental maximum: $2,000',metadata)]):
                result=docs.lookup(params)
                self.assertNotIn('dental',result['benefit_metrics'])
                self.assertIn('Conflicting',result['benefit_unavailable']['dental'])
            with patch.object(docs,'read_pdf',return_value=(cover.replace('NC-15','NC-99'),metadata)) as read:
                result=docs.lookup(params)
                self.assertEqual(read.call_count,1)
                self.assertFalse(result['documents'][0]['identity_verified'])
                self.assertTrue(result['issues'])
