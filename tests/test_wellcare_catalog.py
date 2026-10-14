import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from sync_wellcare_catalog import build, STATES


class WellcareCatalogTests(unittest.TestCase):
    def test_segment_and_state_isolation_and_ambiguous_networks(self):
        header = ['Contract Year', 'State Territory Abbreviation', 'Parent Organization Name', 'Plan Name', 'Organization Marketing Name', 'Contract Plan Segment ID', 'Contract ID', 'Contract Category Type', 'Plan ID', 'Segment ID', 'Plan Type', 'Sanctioned Plan', 'County Name']
        import csv
        import io
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(header)
        for state, segment, county in [('NC', '0', 'Wake'), ('NC', '1', 'Mecklenburg'), ('SC', '0', 'York')]:
            writer.writerow(['2027', state, 'Centene Corporation', 'Wellcare Simple Open (PPO)', 'Wellcare', 'H1914_007_' + segment, 'H1914', 'MA-PD', '007', segment, 'PPO', 'No', county])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with zipfile.ZipFile(root / 'cms.zip', 'w') as archive:
                archive.writestr('landscape.csv', stream.getvalue())
            options = [{'state': state, 'products': []} for state in STATES]
            options[0]['products'] = [{'id': '994892', 'name': 'Wellcare Simple Open (PPO) - H1914'}]
            options[1]['products'] = [{'id': str(i), 'name': 'Wellcare Simple Open (PPO) - H1914'} for i in [1, 2]]
            (root / 'options.json').write_text(json.dumps(options))
            result = build(root / 'cms.zip', root / 'options.json')['plans']
            self.assertEqual(len(result), 3)
            nc = [p for p in result if p['state'] == 'NC']
            self.assertEqual({p['segment'] for p in nc}, {'0', '1'})
            self.assertEqual({p['network_candidates'][0]['id'] for p in nc}, {'994892'})
            sc = next(p for p in result if p['state'] == 'SC')
            self.assertEqual(sc['network_status'], 'Ambiguous — review')
            self.assertEqual(sc['counties'], ['York'])


if __name__ == '__main__':
    unittest.main()
