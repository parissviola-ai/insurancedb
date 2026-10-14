import json
import tempfile
import unittest
from pathlib import Path
import app

class LookupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'test.sqlite'
        app.initialize(self.db)

    def test_empty_database_never_claims_coverage(self):
        self.assertEqual(app.search({'zip':'27601'}, self.db)['plans'], [])

    def test_lookup_scope_and_missing_coverage(self):
        # Synthetic fixtures exist only inside this temporary test database.
        with app.connect(self.db) as db:
            db.execute('''INSERT INTO plans
                (id,carrier,name,year,state,county,zip,business,source_url)
                VALUES ('test','Test','Test',2027,'NC','Wake','27601','Medicare Advantage','https://example.org')''')
            db.execute('''INSERT INTO coverage(plan_id,kind,name,detail,status,source_url)
                VALUES ('test','medication','Test drug','10 mg tablet','restricted','https://example.org')''')
        result = app.search({'zip':'27601','year':'2027','medication':'Test drug\nMissing drug'},self.db)['plans']
        self.assertEqual(result[0]['checks'][0]['matches'][0]['status'],'restricted')
        self.assertEqual(result[0]['checks'][1]['matches'],[])
        self.assertEqual(app.search({'zip':'10001'},self.db)['plans'],[])
        self.assertEqual(app.search({'carrier':"' OR 1=1 --"},self.db)['plans'],[])

    def test_import_failure_rolls_back(self):
        fixture = Path(self.temp.name) / 'bad.json'
        fixture.write_text(json.dumps({'plans':[{'id':'missing-required-fields'}]}))
        with self.assertRaises(ValueError):
            app.import_data(fixture,self.db)
        self.assertEqual(app.search({},self.db)['plans'],[])

if __name__ == '__main__':
    unittest.main()
