import json
from pathlib import Path
import unittest
from healthspring_data import parse_formulary


class HealthSpringTests(unittest.TestCase):
    def test_two_columns_wrapped_drugs_and_restrictions(self):
        header = '  Drug Name                  Drug Tier Requirements/         Drug Name                   Drug Tier Requirements/'
        left = lambda name, tier='', restriction='': '  ' + name.ljust(29) + tier.ljust(6) + restriction
        right = lambda name, tier='', restriction='': name.ljust(30) + tier.ljust(6) + restriction
        line = lambda a, b: a.ljust(61) + b
        text = header + '\nLimits\n' + '\n'.join([
            line(left('amlodipine-atorvastatin', '1'), right('NEXLETOL', '3', 'PA; QL')),
            line(left('atorvastatin', '1', 'QL (30/30)'), right('', '', '(30/30)')),
            line(left('fluconazole in nacl', '4', 'PA'), right('lovastatin oral tablet 20', '1', 'QL (60/30)')),
            line(left('(iso-osm) intravenous'), right('mg, 40 mg')),
            line(left('piggyback 200 mg/100'), right('')),
            line(left('ml, 400 mg/200 ml'), right('')),
            'CAPITALIZED = BRAND NAME DRUG',
        ])
        rows = parse_formulary(text)
        self.assertEqual([r['name'] for r in rows], ['amlodipine-atorvastatin', 'atorvastatin',
                         'fluconazole in nacl (iso-osm) intravenous piggyback 200 mg/100 ml, 400 mg/200 ml',
                         'NEXLETOL', 'lovastatin oral tablet 20 mg, 40 mg'])
        self.assertEqual(rows[1]['restrictions'], 'QL (30/30)')
        self.assertEqual(rows[3]['restrictions'], 'PA; QL (30/30)')

    def test_imported_sources_and_year_safety(self):
        data = json.loads((Path(__file__).resolve().parents[1] / 'docs/data/healthspring.json').read_text())
        self.assertEqual(len(data['plans']), 1)
        plan = data['plans'][0]
        self.assertEqual(plan['cms_id'], 'H7849-113-001')
        self.assertEqual(len(plan['counties']), 11)
        self.assertEqual(plan['network'], [])
        self.assertEqual(plan['benefit_metrics']['hospital']['amount'], 2000)
        self.assertEqual(plan['benefit_metrics']['dental']['amount'], 800)
        self.assertNotIn('otc', plan['benefit_metrics'])
        self.assertNotIn('transportation', plan['benefit_metrics'])
        self.assertNotIn('hearing', plan['benefit_metrics'])
        self.assertEqual(plan['drug_costs']['tiers']['1']['display'], '$0 per prescription')
        self.assertEqual(plan['drug_costs']['tiers']['2']['display'], '$8 per prescription')
        self.assertIn('Standard retail Tier 1 is $10', plan['drug_costs']['conditions'])
        self.assertEqual(len(plan['documents']), 4)
        for doc in plan['documents']:
            self.assertIn('/2027/', doc['url'])
            self.assertEqual(len(doc['sha256']), 64)
        rows = next(iter(data['formularies'].values()))['rows']
        atorvastatin = next(r for r in rows if r['name'] == 'atorvastatin')
        self.assertEqual(atorvastatin['tier'], '1')
        self.assertEqual(atorvastatin['restrictions'], 'QL (30/30)')
        self.assertEqual(atorvastatin['page'], 53)

    def test_nc_document_library_does_not_mix_segments_or_pdp(self):
        data = json.loads((Path(__file__).resolve().parents[1] / 'docs/data/healthspring-documents.json').read_text())
        documents = data['documents']
        self.assertEqual(len(documents), 14)
        self.assertEqual(sum(d['business'] == 'Medicare Advantage' for d in documents), 13)
        preferred = next(d for d in documents if d['cms_id'] == 'H9725-009-001')
        self.assertIn('Mecklenburg', preferred['counties'])
        other_segment = next(d for d in documents if d['cms_id'] == 'H9725-009-004')
        self.assertNotIn('Mecklenburg', other_segment['counties'])
        assurance = next(d for d in documents if d['business'] == 'Part D')
        self.assertIn('Assurance Rx', assurance['name'])
        self.assertIsNone(assurance['cms_id'])
        self.assertTrue(all('/2027/' in d['url'] and len(d['sha256']) == 64 for d in documents))


if __name__ == '__main__':
    unittest.main()
