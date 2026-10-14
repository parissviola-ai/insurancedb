"""Prepare factual Wellcare NC data; preserves source provenance and missing values."""
import argparse
import json,datetime,re
from pathlib import Path
from wellcare_data import parse_formulary,parse_schedule
parser=argparse.ArgumentParser(description='Import official Wellcare NC documents using CMS county availability and directory candidates.')
parser.add_argument('--source-manifest',required=True)
parser.add_argument('--catalog',required=True)
args=parser.parse_args()
source_root=Path(args.source_manifest).parent
root=Path(__file__).resolve().parent;m=json.load(open(args.source_manifest));catalog=json.load(open(args.catalog));now=datetime.datetime.now(datetime.timezone.utc).isoformat()
zipmap=json.load(open(root/'docs/data/zip-counties.json'));county_codes={(c['state'],c['name'].lower()):c['code'] for values in zipmap.values() for c in values}
plans=[];formularies={}
for item in m['plans']:
 p=next(p for p in catalog['plans'] if p['cms_id']==item['cms_id']+'-0');sb=next(u for u in item['documents'] if '_SB_' in u);text=Path(m['documents'][sb]['text_path']).read_text();markup=(source_root/(item['pid']+'.html')).read_text()
 if '2027' not in text[:800] or item['cms_id'].replace('-','_') not in text[:1500]:raise ValueError('Wrong plan/year PDF')
 metrics,costs=parse_schedule(markup,text,sb)
 docs=[]
 for u in item['documents']:
  kind='formulary' if 'Comp_Form' in u else 'benefits' if '_SB_' in u else 'evidence'
  docs.append({'kind':kind,'url':u,'page_url':'https://wellcare.isf.io/','retrieved_at':now,'sha256':m['documents'][u]['sha256']})
  if kind=='formulary' and u not in formularies:
   rows=parse_formulary(Path(m['documents'][u]['text_path']).read_text())
   if len(rows)<500:raise ValueError('Insufficient formulary extraction')
   formularies[u]={'rows':rows,'retrieved_at':now}
 network=p['network_candidates'][0];codes=[];missing=[]
 for county in p['counties']:
  code=county_codes.get(('NC',county.lower()))
  if code:codes.append(code)
  else:missing.append(county)
 for county in missing:codes.append('NC:'+county.lower())
 plans.append({'id':'wellcare-'+p['cms_id']+'-2027','locator':p['cms_id']+'-2027','name':p['name'],'carrier':'Wellcare','year':2027,'business':'Medicare Advantage','state':'NC','counties':codes,'county_names':p['counties'],'premium':'$'+str(int(metrics['premium']['amount'])) if 'premium' in metrics else 'unverified','benefit_metrics':metrics,'special_needs':p['category']=='SNP','ma_only':p['category']=='MA','drug_costs':costs,'documents':docs,'network':[],'product_network_id':network['id'],'network_mapping_status':'CMS state/contract/name matches official directory selection; office participation still requires confirmation.','provider_search_url':'https://my.wellcare.com/x/findaprovider/medicare/en/nc/search/'+network['id']+'?selectedEnrollmentYear=2027','source_url':p['source_url'],'verified_on':now[:10],'scope_note':'2027 NC county availability from CMS. Formulary text extraction yields candidate matches; exact strengths and restrictions require source review. Wellcare provider searches open the official directory; automated coverage checks are not connected.'})
 print(p['cms_id'],'counties',len(codes),'metrics',list(metrics),'drugs',sum(len(formularies[d['url']]['rows']) for d in docs if d['kind']=='formulary'))
out={'county_options':sorted([{'code':county_codes.get(('NC',name.lower()),'NC:'+name.lower()),'name':name,'state':'NC'} for name in set(c for p in plans for c in p['county_names'])],key=lambda c:c['name']),'plans':plans,'formularies':formularies,'retrieved_at':now,'availability_source_url':catalog['cms_source_url'],'availability_sha256':catalog['cms_archive_sha256']}
(root/'docs/data/wellcare.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':'))+'\n')
print('FORMULARIES',[(u.split('/')[-1],len(f['rows'])) for u,f in formularies.items()])
for u,f in formularies.items():print('ATOVA',u.split('/')[-1],[r for r in f['rows'] if r['name'].startswith('atorvastatin oral')][:2])
