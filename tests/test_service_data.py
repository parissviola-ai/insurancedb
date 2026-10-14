import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
import service_data
import devoted

class ServiceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/'test.sqlite';app.initialize(self.db)
        real_connect=app.connect
        self.patch=patch('app.connect',side_effect=lambda:real_connect(self.db));self.patch.start();self.addCleanup(self.patch.stop)
        with app.connect() as db:
            db.execute("INSERT INTO devoted_sync VALUES (1,'2026-10-14','2026-10-14','https://www.devoted.com')")
            db.executemany('INSERT INTO devoted_zip_counties VALUES (?,?,?)',[('12345','A','County A'),('12345','B','County B'),('23456','C','County C')])
            db.execute("INSERT INTO devoted_service_areas VALUES ('TEST-2027','A','Test NC')")
            db.execute("INSERT INTO devoted_documents VALUES ('https://assets.devoted.com/test.pdf','2027 Formulary\fTest drug 10mg Tier 2 PA','hash','2026-10-14',2027)")
            db.execute("INSERT INTO devoted_document_links VALUES ('TEST-2027','formulary','https://assets.devoted.com/test.pdf','https://www.devoted.com')")

    def test_cross_county_requires_selection(self):
        cs,selected,locators,_=service_data.area('12345','',2027)
        self.assertEqual(len(cs),2);self.assertIsNone(selected);self.assertEqual(locators,set())
        self.assertEqual(service_data.area('12345','A',2027)[2],{'TEST-2027'})
        self.assertEqual(service_data.area('12345','B',2027)[2],set())

    def test_wrong_county_and_year_rejected(self):
        with self.assertRaises(ValueError):service_data.area('12345','C',2027)
        with self.assertRaises(ValueError):service_data.area('12345','A',2026)

    def test_no_service_plans_never_falls_back_to_state(self):
        with patch('devoted.search') as search:
            self.assertEqual(devoted.lookup({'zip':'23456','year':'2027'})['plans'],[])
            search.assert_not_called()

    def test_formulary_matches_are_unverified_and_page_cited(self):
        _,_,_,checks=service_data.documents('TEST-2027',['Test drug','Missing drug'])
        match=checks[0]['matches'][0]
        self.assertEqual(match['status'],'unverified')
        self.assertTrue(match['source_url'].endswith('#page=2'))
        self.assertEqual(checks[1]['matches'],[])
