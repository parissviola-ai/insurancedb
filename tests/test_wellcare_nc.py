import json
from pathlib import Path
import unittest
from wellcare_data import parse_formulary

DATA = Path(__file__).resolve().parents[1] / 'docs/data/wellcare.json'


class WellcareNCTests(unittest.TestCase):
    def test_wrapped_strengths_restrictions_and_combination(self):
        text = '''Drug Name                                       Drug Requirements/Limits
                                                Tier
LIPID LOWERING AGENTS
amlodipine-atorvastatin oral tablet 10-10 mg,
                                                 6   QL (30 EA per 30 days)
10-20 mg
atorvastatin oral tablet 10 mg, 20 mg, 40
                                                 6   QL (30 EA per 30 days)
mg, 80 mg
losartan oral tablet 100 mg                  6 QL (30 EA per 30 days)
You can find information on what the symbols mean
'''
        rows = parse_formulary(text)
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0]['name'].startswith('amlodipine-atorvastatin'))
        self.assertEqual(rows[1]['name'], 'atorvastatin oral tablet 10 mg, 20 mg, 40 mg, 80 mg')
        self.assertEqual(rows[1]['restrictions'], 'QL (30 EA per 30 days)')
        self.assertEqual(rows[1]['tier'], '6')
        self.assertEqual(rows[2]['name'], 'losartan oral tablet 100 mg')
        self.assertEqual(rows[2]['restrictions'], 'QL (30 EA per 30 days)')

    def test_nc_inventory_and_sources(self):
        j = json.loads(DATA.read_text())
        self.assertEqual(len(j['plans']), 7)
        self.assertEqual(len(j['county_options']), 74)
        self.assertEqual(len(j['formularies']), 4)
        simple = next(p for p in j['plans'] if p['locator'] == 'H1914-007-0-2027')
        self.assertEqual(len(simple['counties']), 70)
        self.assertNotIn('verified_zips', simple)
        self.assertEqual(simple['product_network_id'], '994892')
        self.assertEqual(simple['benefit_metrics']['otc']['amount'], 51)
        self.assertIn('shared', simple['benefit_metrics']['otc']['notes'].lower())
        self.assertEqual(simple['drug_costs']['tiers']['6']['display'], '$0 per prescription')
        self.assertEqual(sum(p['ma_only'] for p in j['plans']), 1)
        for p in j['plans']:
            self.assertEqual(p['state'], 'NC')
            self.assertTrue(any(d['kind'] == 'benefits' and '/2027/' in d['url'] for d in p['documents']))
            self.assertTrue(any(d['kind'] == 'evidence' and '/2027/' in d['url'] for d in p['documents']))
            self.assertEqual(p['network'], [])  # No inferred FHIR network participation.
            for d in p['documents']:
                if d['kind'] == 'formulary':
                    rows = j['formularies'][d['url']]['rows']
                    atorvastatin = next(r for r in rows if r['name'].startswith('atorvastatin oral'))
                    self.assertEqual(atorvastatin['tier'], '6')
                    self.assertIn('QL', atorvastatin['restrictions'])


if __name__ == '__main__':
    unittest.main()
