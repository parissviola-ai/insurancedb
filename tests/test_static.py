import json
import unittest
from pathlib import Path

DATA=Path(__file__).resolve().parents[1]/'docs'/'data'
class StaticDataTests(unittest.TestCase):
    def test_service_area_examples(self):
        plans=json.loads((DATA/'plans.json').read_text())['plans']
        counties=json.loads((DATA/'zip-counties.json').read_text())
        self.assertEqual(len(plans),37)
        for zip_code,count in [('28202',12),('28697',12),('27601',0)]:
            self.assertEqual(len(counties[zip_code]),1)
            code=counties[zip_code][0]['code']
            self.assertEqual(sum(code in p['counties'] for p in plans),count)
        self.assertEqual(len(counties['27344']),3)

    def test_document_and_drug_links(self):
        plans=json.loads((DATA/'plans.json').read_text())['plans']
        drugs=json.loads((DATA/'formularies.json').read_text())
        for plan in plans:
            self.assertTrue(any(d['kind']=='benefits' for d in plan['documents']))
            for doc in plan['documents']:
                self.assertTrue(doc['url'].startswith('https://assets.devoted.com/'))
                if doc['kind']=='formulary':self.assertIn(doc['url'],drugs)
        self.assertTrue(any('atorvastatin' in row['name'].lower() for f in drugs.values() for row in f['rows']))
        self.assertTrue(all(row['page']>0 for f in drugs.values() for row in f['rows']))
