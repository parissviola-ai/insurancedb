"""Build the three-plan 2027 Excellus document integration from official PDFs and CMS.

Run: python import_excellus.py --cache /tmp/excellus-cache
All downloads use certificate-verified HTTPS. No candidate information is processed.
"""
import argparse,csv,hashlib,io,json,re,subprocess,urllib.request,zipfile
from pathlib import Path
from datetime import datetime,timezone
import fitz
ROOT=Path(__file__).resolve().parent
BASE='https://www.excellusbcbs.com/documents/d/global/'
FORM='https://fm.formularynavigator.com/FBO/251/Excellus_5T_DP_odd.pdf'
DIRECTORY=BASE+'exc-mdm-medicare-blue-024-205-206-208-029-030-032-cnyu-1-odd'
CMS='https://www.cms.gov/files/zip/cy2027-landscape-202609-1.zip'
def build(cache):
 cache.mkdir(parents=True,exist_ok=True)
 def get(url,key):
  p=cache/key
  if not p.exists():p.write_bytes(urllib.request.urlopen(url,timeout=90).read())
  return p
 def pdf(url,key):
  p=get(url,key+'.pdf');d=fitz.open(p);assert '2027' in ''.join(x.get_text() for x in list(d)[:3]),key
  return p,d
 docs={}
 for key,url in [('formulary',FORM),('directory',DIRECTORY)]+[(f'sb{n}',BASE+'exc-mdm-mdp-summary-of-benefits-'+('028-029' if n in ['028','029'] else '030-031')+'-odd') for n in ['028','029','030']]+[(f'eoc{n}',BASE+'exc-mdm-mdp-evidence-of-coverage-'+n+'-odd') for n in ['028','029','030']]:docs[key]=(*pdf(url,key),url)
 z=zipfile.ZipFile(get(CMS,'cms.zip'));land=list(csv.DictReader(io.TextIOWrapper(z.open(next(n for n in z.namelist() if n.endswith('.csv'))),encoding='utf-8-sig')))
 zipmap=json.loads((ROOT/'docs/data/zip-counties.json').read_text());counties={c['name']:c for cs in zipmap.values() for c in cs if c['state']=='NY'}
 plans=[]
 for n,premium,moop,specialist,hospital,vision in [('028',14,9850,55,2450,0),('029',85.30,8500,40,2000,200),('030',125.30,7500,30,1750,200)]:
  rows=[r for r in land if r['Contract ID']=='H3351' and r['Plan ID']==n and r['Contract Year']=='2027' and r['State Territory Abbreviation']=='NY'];assert len(rows)==13 and {r['Segment ID'] for r in rows}=={'0'}
  for r in rows:counties.setdefault(r['County Name'],{'name':r['County Name'],'state':'NY','code':'NY:'+r['County Name'].lower()})
  assert all(abs(float(r['Monthly Consolidated Premium (Part C + D)'].strip().replace('$','').replace(',',''))-premium)<.01 for r in rows)
  sb=docs['sb'+n][2];eoc=docs['eoc'+n][2];assert 'H3351-'+n in docs['sb'+n][1][0].get_text()
  metrics={}
  for k,a,period,notes,page in [('premium',premium,'month','Part B premium still applies. Optional dental costs an additional $35/month.',3),('moop',moop,'year','In-network medical maximum; excludes Part D and premiums.',3),('specialist',specialist,'visit','In-network specialist visit; service-specific rules apply.',4),('hospital',hospital,'7-day stay','Modeled in-network seven-day admission: daily copay on days 1–5; days 6+ fully covered.',3),('vision',vision,'year','Eyewear not covered.' if not vision else '$200 yearly eyewear allowance; eligible items and network conditions apply.',7),('hearing',499,'aid','Advanced TruHearing option; per hearing aid, not a cash allowance. Confirm fitting and network rules.',6),('transportation',0,'year','Routine transportation explicitly not covered; ambulance is a separate medical benefit.',9)]:
   metrics[k]={'amount':a,'period':period,'notes':notes,'source_url':sb+'#page='+str(page),'status':'Source amount extracted'}
  plan={'id':'excellus-H3351-'+n+'-000-2027','locator':'H3351-'+n+'-000-2027','cms_id':'H3351-'+n+'-000','name':rows[0]['Plan Name'],'carrier':'Excellus','year':2027,'business':'Medicare Advantage','state':'NY','county_names':sorted({r['County Name'] for r in rows}),'counties':sorted({counties[r['County Name']]['code'] for r in rows}),'premium':f'${premium:,.2f}','benefit_metrics':metrics,'benefit_review_notes':{'dental':'Included preventive dental services, not a verified dollar allowance. Optional comprehensive dental: up to $1,000/year for an additional $35/month; not included in the base premium.','otc':'No OTC allowance verified; do not interpret missing information as $0.'},'special_needs':False,'ma_only':False,'network':[],'provider_search_url':'https://medicare.excellusbcbs.com/find-a-doctor','source_url':CMS,'verified_on':'2026-10-14','scope_note':'Document-based 2027 comparison. Medication entries are candidate matches. Provider/facility results are dated PDF listings, not live network verification. Optional dental costs extra.','documents':[]}
  costs={'028':['$5','$15','20%','25%','25%'],'029':['$4','$15','20%','25%','25%'],'030':['$0','$5','20%','30%','29%']}[n]
  plan['drug_costs']={'tiers':{str(i+1):{'type':'coinsurance' if '%' in v else 'copay','display':v+(' of drug cost' if '%' in v else ' per prescription'),'source_url':sb+'#page='+str(10+i//2)} for i,v in enumerate(costs)},'supply_days':30,'pharmacy_type':'Preferred network retail pharmacy','stage':'Initial coverage','conditions':'Preferred network retail, 30-day supply, initial coverage, without Extra Help. Standard pharmacies and longer supplies differ. Insulin has special cost-sharing rules; verify the prescription and pharmacy.','deductible_note':'$325 deductible for Tiers 3–5; $0 for Tiers 1–2.' if n=='030' else '$700 deductible for Tiers 2–5; $0 for Tier 1. Full applicable drug cost applies until the deductible is met.'}
  for kind,key in [('benefits','sb'+n),('evidence','eoc'+n),('formulary','formulary'),('provider_directory','directory')]:
   p,_,url=docs[key];plan['documents'].append({'kind':kind,'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
  plans.append(plan)
 # Layout text retains the three table columns and wrapped drug names/restrictions.
 p=docs['formulary'][0];txt=subprocess.check_output(['pdftotext','-layout',str(p),'-'],text=True);drugs=[]
 for page,text in enumerate(txt.split('\f'),1):
  if 'DRUG NAME' not in text or 'DRUG TIER' not in text:continue
  pending=[];last=None
  for line in text.splitlines()[1:]:
   if 'You can find information' in line or re.match(r'^\s*\d+\s*$',line):continue
   m=re.match(r'^(.*?)\s{2,}([1-5])(?:\s{2,}(.*))?\s*$',line)
   if m:
    name=' '.join(pending+[m[1].strip()]).strip();pending=[]
    if not name:continue
    last={'name':name,'tier':m[2],'restrictions':(m[3] or '').strip(),'page':page};drugs.append(last)
   elif line.strip():
    # Only non-column text ending with a comma is a wrapped drug name.
    if last and re.match(r'^\s{60,}\S',line):last['restrictions']+=' '+line.strip()
    elif re.match(r'^\s*(?:\d|\d+\s*mg)',line) and last:last['name']+=' '+line.strip()
    elif line.rstrip().endswith(','):pending.append(line.strip())
    else:pending=[]
 assert len(drugs)>1000 and any(r['name']=='atorvastatin' and r['tier']=='1' for r in drugs)
 # Conservative blocks: require an explicit name, street, ZIP and phone in the same block.
 d=docs['directory'][1];offices=[]
 for pi,page in enumerate(d):
  header=page.get_text(clip=fitz.Rect(0,0,612,42)).strip()
  if not header.startswith('NY') or any(s in header for s in ['Pharmacy','Index:']):continue
  person_section=any(s in header for s in ['Primary Care','Providers by Specialty','Dentistry','HIV Trained'])
  facility_section=any(s in header for s in ['Hospitals','Skilled Nursing','Specialty Centers','Medical Suppliers','Urgent Care','Ambulatory'])
  if not person_section and not facility_section:continue
  for b in page.get_text('blocks'):
   lines=[s.strip() for s in b[4].splitlines() if s.strip()]; ai=next((i for i,s in enumerate(lines) if re.match(r'^\d+[A-Za-z\d-]*\s+\S',s)),None)
   if ai is None or ai==0:continue
   phone=next((s for s in lines if s.startswith('Phone:')),'');end=next((i for i in range(ai,len(lines)) if re.search(r'\b\d{5}(?:-\d{4})?\b',lines[i]) and ('NY' in ' '.join(lines[ai:i+1]))),None)
   if not phone or end is None:continue
   name=' '.join(lines[:ai]);person=bool(re.match(r"^[A-Za-z'’ .-]+,\s+[A-Za-z].*,\s*(?:MD|DO|NP|PA|DDS|DMD|OD|PT|LCSW|PHD)",name,re.I))
   if person:name=re.split(r'\s+(?:Gender:|Group affiliations:|Board Certifications:|Languages Spoken:|Hospital Affiliations:)',name)[0].strip()
   if person_section and not person:continue
   if facility_section and (person or ':' in name):continue
   office=' '.join(lines[ai:end+1]);key=hashlib.sha256((name+office).encode()).hexdigest()[:20]
   offices.append({'name':name,'kind':'provider' if person else 'facility','office':office,'phone':phone.replace('Phone:','').strip(),'npi':'','page':pi+1,'locationId':key,'restrictions':'Dated directory listing. Confirm exact office, service, new-patient availability and current participation.'})
 offices=list({(r['kind'],r['name'],r['office']):r for r in offices}.values());assert len(offices)>500 and any(r['kind']=='facility' for r in offices)
 out=ROOT/'docs/data';(out/'excellus.json').write_text(json.dumps({'plans':plans,'county_options':[counties[n] for n in plans[0]['county_names']],'formularies':{FORM:{'rows':drugs,'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}}},ensure_ascii=False,separators=(',',':'))+'\n')
 (out/'excellus-providers.json').write_text(json.dumps({'rows':offices,'year':2027,'directory_date':'2026-09-13','url':DIRECTORY,'source_sha256':hashlib.sha256(docs['directory'][0].read_bytes()).hexdigest(),'plan_ids':[p['cms_id'] for p in plans]},ensure_ascii=False,separators=(',',':'))+'\n')
 print('Plans',len(plans),'drug candidates',len(drugs),'offices',len(offices),'facilities',sum(r['kind']=='facility' for r in offices))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--cache',type=Path,default=Path('/tmp/excellus-cache'));build(a.parse_args().cache)
