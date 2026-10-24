import unittest
from unittest.mock import patch
import plan_documents as docs

PLAN={'carrier':'UnitedHealthcare / AARP','official_id':'H1234-001-000','name':'AARP Medicare Advantage from UHC NC-15 (HMO-POS)','year':2027,'state':'NC','source_url':'https://www.aarpmedicareplans.com/health-plans/details.html/28613/035/H1234001000/2027'}


class PlanDocumentTests(unittest.TestCase):
    def test_document_urls_are_restricted(self):
        docs.pdf_url('https://www.aarpmedicareplans.com/alphadog/fixture')
        docs.pdf_url('https://www.aetna.com/medicare/documents/individual/2027/fixture.pdf')
        for url in ['http://www.aarpmedicareplans.com/alphadog/x','https://example.com/x.pdf','https://www.aetna.com/account','https://user:pass@www.aetna.com/medicare/documents/x','https://www.aetna.com:8000/medicare/documents/x']:
            with self.subTest(url=url),self.assertRaises(ValueError):docs.pdf_url(url)

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
