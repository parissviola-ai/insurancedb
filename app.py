"""Local plan lookup. No third-party dependencies or patient search storage."""
import argparse
import json
import sqlite3
import devoted
import service_data
import carrier_websites
import mimetypes
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'data' / 'plans.sqlite'
STATES = ['NC','SC','GA','FL','AL','TN','VA','KY','LA','TX','OH','PA','DE','MI','NY']
BUSINESSES = ['Medicare Advantage', 'Part D', 'Medigap', 'ACA']


def connect(path=DB):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def initialize(path=DB):
    with connect(path) as db:
        db.executescript((ROOT / 'schema.sql').read_text())



def search(params, path=DB):
    filters, values = [], []
    for key in ('state','zip','county','business','year','carrier'):
        if params.get(key):
            filters.append(f'{key} = ?')
            values.append(params[key])
    with connect(path) as db:
        plans = db.execute('SELECT * FROM plans WHERE ' + (' AND '.join(filters) or '1=1') +
                           ' ORDER BY carrier, name, county LIMIT 201', values).fetchall()
        result = []
        for row in plans[:200]:
            plan = dict(row)
            checks = []
            for kind in ('medication', 'provider'):
                # One medication/provider per line; every requested item is assessed separately.
                for term in params.get(kind, '').splitlines():
                    term = term.strip()
                    if not term:
                        continue
                    records = db.execute('SELECT * FROM coverage WHERE plan_id=? AND kind=?',
                                         (plan['id'],kind)).fetchall()
                    matches = [dict(r) for r in records if term.casefold() in
                               (r['name'] + ' ' + r['detail']).casefold()]
                    checks.append({'kind':kind,'query':term,'matches':matches})
            plan['checks'] = checks
            result.append(plan)
    return {'plans':result, 'truncated':len(plans)>200,
            'notice':'Only imported source records are shown. Missing coverage records are unverified.'}


def import_data(filename, path=DB):
    payload = json.loads(Path(filename).read_text())
    if not isinstance(payload.get('plans'), list):
        raise ValueError('Expected a plans array')
    with connect(path) as db:
        for item in payload['plans']:
            p = dict(item)
            records = p.pop('coverage', [])
            for key in ('id','carrier','name','year','state','county','zip','business','source_url','verified_on'):
                if key not in p or p[key] == '':
                    raise ValueError(f'Missing {key}')
            if p['state'] not in STATES or p['business'] not in BUSINESSES:
                raise ValueError('Unsupported state or line of business')
            if not isinstance(p['zip'], str) or len(p['zip']) != 5 or not p['zip'].isdigit():
                raise ValueError('ZIP must be a five-digit string')
            validate_source(p['source_url'], p['verified_on'])
            columns = ['id','carrier','name','year','state','county','zip','business','premium','benefits','source_url','verified_on']
            db.execute('INSERT INTO plans (' + ','.join(columns) + ') VALUES (' +
                       ','.join('?' for _ in columns) + ') ON CONFLICT(id) DO UPDATE SET ' +
                       ','.join(f'{c}=excluded.{c}' for c in columns[1:]),
                       [p.get(c,'') for c in columns])
            db.execute('DELETE FROM coverage WHERE plan_id=?', (p['id'],))
            for c in records:
                validate_source(c['source_url'], c['verified_on'])
                db.execute('''INSERT INTO coverage
                    (plan_id,kind,name,detail,status,restrictions,source_url,verified_on)
                    VALUES (?,?,?,?,?,?,?,?)''',
                    [p['id']] + [c.get(k,'') for k in
                    ('kind','name','detail','status','restrictions','source_url','verified_on')])


def validate_source(url, checked):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Source must be a public HTTPS URL without credentials')
    if date.fromisoformat(checked) > date.today():
        raise ValueError('Verification date cannot be in the future')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Do not log medication/provider queries.

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ('/api/plans', '/api/devoted', '/api/document', '/api/carrier-websites', '/api/carrier-locations'):
            params = {k:v[0] for k,v in parse_qs(parsed.query).items()}
            try:
                data = (carrier_websites.locations(params.get('zip', '')) if parsed.path == '/api/carrier-locations' else
                        carrier_websites.search(params) if parsed.path == '/api/carrier-websites' else
                        service_data.document_text(params.get('url','')) if parsed.path == '/api/document' else
                        devoted.lookup(params) if parsed.path == '/api/devoted' else search(params))
                self.respond(json.dumps(data).encode(), 'application/json')
            except carrier_websites.ShoppingError as error:
                self.respond(json.dumps({'error':error.message, 'status':error.status}).encode(), 'application/json', 503)
            except ValueError as error:
                self.respond(json.dumps({'error':str(error)}).encode(), 'application/json', 400)
            except Exception:
                self.respond(json.dumps({'error':'Lookup unavailable. No plan availability or coverage inferred; please retry.'}).encode(), 'application/json', 502)
        elif parsed.path.startswith('/dashboard/'):
            relative = parsed.path.removeprefix('/dashboard/') or 'index.html'
            target = (ROOT / 'docs' / relative).resolve()
            if not target.is_relative_to((ROOT / 'docs').resolve()) or not target.is_file():
                self.send_error(404)
                return
            self.respond(target.read_bytes(), mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
        elif parsed.path in ('/', '/app.js', '/style.css'):
            name = {'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[parsed.path]
            mime = {'/':'text/html','/app.js':'text/javascript','/style.css':'text/css'}[parsed.path]
            self.respond((ROOT / 'static' / name).read_bytes(), mime)
        else:
            self.send_error(404)

    def respond(self, body, mime, status=200):
        self.send_response(status)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--import-json')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    initialize()
    if args.import_json:
        import_data(args.import_json)
        print('Import complete')
    else:
        print(f'Plan lookup running on port {args.port}', flush=True)
        ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()
