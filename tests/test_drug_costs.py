import unittest
from drug_costs import parse_drug_costs

class DrugCostTests(unittest.TestCase):
    def test_retail_column_not_mail_order(self):
        text='2027\fPharmacy (Part D) Deductible $650 for Tiers 3-5\nInitial Coverage Stage\n30-Day Supply Network 100-Day Supply Network\nRetail Pharmacy Mail Order\nTier 1: Preferred Generic $0 per prescription $0 per prescription\nTier 2: Generic $2 per prescription $5 per prescription\nTier 3: Preferred Brand 25% of the total cost 25% of the total cost\nCatastrophic Coverage'
        result=parse_drug_costs(text,'https://example.org/sb.pdf')
        self.assertEqual(result['tiers']['2']['display'],'$2 per prescription')
        self.assertEqual(result['tiers']['3']['type'],'coinsurance')
        self.assertEqual(result['tiers']['3']['display'],'25% of the total cost')
        self.assertEqual(result['supply_days'],30)
        self.assertIn('$650 for Tiers 3-5',result['deductible_note'])
        self.assertTrue(result['tiers']['1']['source_url'].endswith('#page=2'))

    def test_unsupported_supply_or_pharmacy_header_is_not_priced(self):
        text='Initial Coverage Stage\n90-Day Supply Preferred Pharmacy\nTier 1: Generic $0 per prescription\nCatastrophic Coverage'
        self.assertEqual(parse_drug_costs(text,'https://example.org'),{})

    def test_ma_only_no_drug_schedule(self):
        self.assertEqual(parse_drug_costs('No included Part D','https://example.org'),{})
