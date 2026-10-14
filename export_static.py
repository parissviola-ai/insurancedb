"""Export factual lookup data and source links for the static dashboard."""
import json
import re
from pathlib import Path
import app
import devoted
import service_data
from benefit_data import parse_benefits

OUT=Path(__file__).resolve().parent/'docs'/'data'


def export():
    OUT.mkdir(parents=True,exist_ok=True)
    rows,truncated=devoted.search('InsurancePlan',{'name:contains':'NC','_count':100})
    if truncated:raise ValueError('Incomplete plan API export')
    with app.connect() as db:
        sync=db.execute('SELECT * FROM devoted_sync WHERE id=1').fetchone()
        if not sync:raise ValueError('Run sync_devoted.py first')
        areas={}
        for r in db.execute('SELECT * FROM devoted_service_areas'):
            areas.setdefault(r['locator'],[]).append(r['county_code'])
        counties={}
        for r in db.execute('SELECT * FROM devoted_zip_counties'):
            counties.setdefault(r['zip'],[]).append({'code':r['county_code'],'name':r['county_name']})
        drugs={}
        for r in db.execute("SELECT * FROM devoted_documents WHERE url LIKE '%/formulary/%'"):
            # Export factual table rows only, not entire copyrighted documents.
            records=[]
            for page_number,page in enumerate(r['text'].split('\f'),1):
                if not ('DRUG NAME' in page.upper() and 'REQUIREMENTS' in page.upper() and 'TIER' in page.upper()):continue
                for line in page.splitlines():
                    m=re.match(r'^\s*(\S.*?)\s{2,}([1-5])(?:\s{2,}(.*))?\s*$',line)
                    if m:
                        records.append({'name':m[1].strip(),'tier':m[2],
                                        'restrictions':(m[3] or '').strip(),'page':page_number})
            if not records:raise ValueError('No drug table rows extracted from '+r['url'])
            drugs[r['url']]={'rows':records,'retrieved_at':r['retrieved_at']}
        plans=[]
        for p in rows:
            if p.get('status')!='active' or not devoted.valid_year(p,2027):continue
            ids=[i.get('value','')+'-2027' for i in p.get('identifier',[]) if i.get('system')=='http://cms.gov/medicare/ma-plan-id']
            locator=next((i for i in ids if i in areas),None)
            if not locator:continue
            docs,premium,_,_=service_data.documents(locator,[])
            sb=db.execute("SELECT d.text,d.url FROM devoted_document_links l JOIN devoted_documents d ON d.url=l.url WHERE l.locator=? AND l.kind='benefits'",(locator,)).fetchone()
            metrics=parse_benefits(sb['text'],sb['url']) if sb else {}
            plans.append({'id':p['id'],'locator':locator,'name':p['name'],'carrier':'Devoted Health',
                'year':2027,'business':'Medicare Advantage','state':'NC','counties':areas[locator],
                'premium':premium or 'unverified','benefit_metrics':metrics,
                'special_needs':bool(re.search(r'C-SNP|D-SNP',p['name'])),
                'ma_only':'MA ONLY' in p['name'], 'documents':docs,'network':p.get('network',[]),
                'source_url':devoted.BASE+'InsurancePlan/'+p['id'],
                'verified_on':p.get('meta',{}).get('lastUpdated','')[:10]})
        if len(plans)!=len(areas):raise ValueError('Some service-area plans lack API records')
        payloads={'plans.json':{'plans':plans,'snapshot':dict(sync)},'zip-counties.json':counties,'formularies.json':drugs}
        for name,value in payloads.items():
            (OUT/name).write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n')
    print(f'Exported {len(plans)} plans, {len(counties)} ZIPs, and {sum(len(d["rows"]) for d in drugs.values())} formulary candidate rows.')

if __name__=='__main__':export()
