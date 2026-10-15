"""Build separate dated PDF suggestion indexes for official target-state directories."""
import concurrent.futures
import datetime
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import urllib.request
import argparse
from fetch_healthspring_documents import STATES
from import_healthspring_providers import extract


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path,required=True);args=p.parse_args();args.cache.mkdir(exist_ok=True,parents=True)
    root=Path(__file__).resolve().parent;out=root/'docs/data/healthspring-directories';out.mkdir(exist_ok=True)
    source='https://www.healthspring.com/medicare/member-resources/provider-pharmacy-directories'
    markup=html.unescape(urllib.request.urlopen(source,timeout=30).read().decode())
    names={name:code for code,name in STATES.items()};names['Virgina']='VA'
    rs=[{k:v[1] for k,v in json.loads(raw).items()} for raw in re.findall(r'\{"Year":\[0,2027\][^{}]*\}',markup)]
    by_path={}
    for r in rs:
        if r['State'] in names:
            by_path.setdefault(r['PDF_URL'],set()).add(names[r['State']])
    previous_path=root/'docs/data/healthspring-directory-index.json'
    previous={d['id']:d for d in json.loads(previous_path.read_text())['directories']} if previous_path.exists() else {}
    def process(pair):
        path,states=pair;key=path.split('/')[-1][:-4];target=args.cache/(key+'.pdf');url='https://www.healthspring.com'+path
        meta={'id':key,'url':url,'states':sorted(states),'year':2027,'name':key.replace('provider-pharmacy-directory-','').replace('-',' ').title(),'plan_ids':[]}
        try:
            if not re.fullmatch(r'/static/docs/medicare/plans/2027/provider-pharmacy-directory-[a-z-]+\.pdf',path):raise ValueError('Unexpected directory URL')
            if not target.exists():
                try:content=urllib.request.urlopen(url,timeout=60).read()
                except urllib.error.HTTPError as e:
                    if e.code not in [502,503,504]:raise
                    content=urllib.request.urlopen(url,timeout=60).read()
                target.write_bytes(content)
            cached=previous.get(key)
            if cached and cached.get('status')=='Indexed' and cached.get('sha256')==hashlib.sha256(target.read_bytes()).hexdigest() and (out/(key+'.json')).exists():
                return cached
            text=subprocess.check_output(['pdftotext','-f','1','-l','6','-layout',str(target),'-']).decode()
            if '2027' not in text[:2000]:raise ValueError('Directory year not confirmed')
            flat=re.sub(r'\s+',' ',text).replace('o f','of')
            date=re.search(r'current as of ([A-Z][a-z]+ \d{1,2}, \d{4})',flat,re.I)
            date=datetime.datetime.strptime(date[1],'%B %d, %Y').date().isoformat() if date else None
            rows,skipped=extract(target)
            if not rows:raise ValueError('No reliably extracted office records')
            if key=='provider-pharmacy-directory-north-carolina-ppo':
                pilot=json.loads((root/'docs/data/healthspring.json').read_text())['plans'][0]
                expected=next(d['sha256'] for d in pilot['documents'] if d['kind']=='provider_directory')
                if hashlib.sha256(target.read_bytes()).hexdigest()==expected:meta['plan_ids']=['H7849-113-001']
            compact=[{k:r[k] for k in ['kind','name','npi','office','phone','page','locationId','restrictions']} for r in rows]
            meta.update(directory_date=date,row_count=len(rows),providers=sum(r['kind']=='provider' for r in rows),facilities=sum(r['kind']=='facility' for r in rows),skipped_blocks=skipped,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),status='Indexed',index_file='./data/healthspring-directories/'+key+'.json')
            (out/(key+'.json')).write_text(json.dumps({'rows':compact},ensure_ascii=False,separators=(',',':'))+'\n')
            print('Indexed',key,len(rows),flush=True)
        except Exception as e:meta.update(status='Needs review',error=str(e));print('ERROR',key,str(e),flush=True)
        return meta
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:directories=list(pool.map(process,sorted(by_path.items())))
    manifest={'year':2027,'source_url':source,'states':list(STATES),'directories':directories,'scope_note':'Partial PDF extraction for suggestions, not live network verification. Regional sources remain separate. Only the NC PPO pilot has a verified comparison-plan attachment; other plan mappings require review.'}
    (root/'docs/data/healthspring-directory-index.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('SUMMARY',len(directories),'directories',sum(d['status']=='Indexed' for d in directories),'indexed')


if __name__=='__main__':main()
