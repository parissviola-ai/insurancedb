import unittest
from unittest.mock import patch
import devoted

class DevotedTests(unittest.TestCase):
    def test_year_requires_explicit_period(self):
        self.assertFalse(devoted.valid_year({},2027))
        self.assertFalse(devoted.valid_year({'period':{'start':'2026-01-01','end':'2026-12-31'}},2027))
        self.assertTrue(devoted.valid_year({'period':{'start':'2027-01-01','end':'2027-12-31'}},2027))

    def test_rejects_foreign_pagination_url(self):
        with self.assertRaises(ValueError):
            devoted.get('https://example.org/fhir/Practitioner')

    def test_wrong_network_never_matches_provider(self):
        role={'id':'role','active':True,'period':{'start':'2027-01-01','end':'2027-12-31'},
              'extension':[{'url':'https://example.org/network-reference','valueReference':{'reference':'Organization/other'}}]}
        with patch('devoted.search',side_effect=[([{'id':'person'}],False),([role],False)]), patch('devoted.get') as get:
            matches,_=devoted.provider_matches('Test',{'Organization/selected'},2027,'27601')
        self.assertEqual(matches,[])
        get.assert_not_called()
