import unittest
from benefit_data import parse_benefits

class BenefitTests(unittest.TestCase):
    def test_missing_does_not_become_zero(self):
        self.assertEqual(parse_benefits('No identifiable benefit amounts','https://example.org/sb.pdf'),{})

    def test_explicit_amounts_periods_and_page_citations(self):
        text='2027\fMonthly Premium $0\nDental Allowance\nYou have a $3,000 yearly allowance. 50% reimbursement\fOver-the-Counter Items (OTC) $50 per quarter'
        metrics=parse_benefits(text,'https://example.org/sb.pdf')
        self.assertEqual(metrics['premium']['amount'],0)
        self.assertEqual(metrics['dental']['amount'],3000)
        self.assertIn('50%',metrics['dental']['notes'])
        self.assertEqual(metrics['otc']['amount'],50)
        self.assertEqual(metrics['otc']['period'],'quarter')
        self.assertTrue(metrics['otc']['source_url'].endswith('#page=3'))

    def test_conditional_food_is_not_otc(self):
        metrics=parse_benefits('Food & Home Card $346 per month for qualifying members','https://example.org/sb.pdf')
        self.assertNotIn('otc',metrics)
