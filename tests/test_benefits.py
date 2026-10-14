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

    def test_medical_costs_use_first_in_network_amount(self):
        text="Maximum Out-of- $6,150 $7,650\nPocket Responsibility\nSpecialist: $35 copay Specialist: $45 copay\nEyewear Up to $300 each year\nHearing Aids* $399 copay or $699 copay per aid\nInpatient Hospital Days 1 - 6 Days 1 - 6\nCoverage $385 copay per day $385 copay per day\nDay 7+ Day 7+\n$0 copay per day $0 copay per day"
        m=parse_benefits(text,'https://example.org/sb.pdf')
        self.assertEqual(m['moop']['amount'],6150)
        self.assertEqual(m['specialist']['amount'],35)
        self.assertEqual(m['vision']['amount'],300)
        self.assertEqual(m['hearing']['amount'],399)
        self.assertEqual(m['hospital']['amount'],2310)

    def test_hospital_unsupported_schedule_stays_unknown(self):
        m=parse_benefits('Inpatient Hospital Days 1 - 6 $385 copay per day Day 7+ 20% coinsurance','https://example.org/sb.pdf')
        self.assertNotIn('hospital',m)

    def test_transportation_not_covered_is_explicit_zero(self):
        m=parse_benefits('Transportation Not covered','https://example.org/sb.pdf')
        self.assertEqual(m['transportation']['amount'],0)
        self.assertNotIn('transportation',parse_benefits('Transportation rules not supplied','https://example.org/sb.pdf'))

    def test_free_one_way_rides_preserve_units(self):
        m=parse_benefits('Transportation $0 copay for 24 one-way trips per year','https://example.org/sb.pdf')
        self.assertEqual(m['transportation']['amount'],24)
        self.assertEqual(m['transportation']['period'],'one-way rides/year')
