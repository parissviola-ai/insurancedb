"""Plan-bound public PDF retrieval. Caches stay on this computer, outside Git."""
import hashlib
import io
import json
import logging
from pathlib import Path
import re
import threading
import time
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
import carrier_websites as carriers

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / '.local-cache' / 'plan-documents'
_slots = threading.BoundedSemaphore(2)
_locks = {}
_guard = threading.Lock()
DOC_TYPES = {'1':'enrollment','2':'evidence','3':'benefits','1027':'provider_directory',
             '6014':'changes','6002':'highlights','1043':'stars','2019':'prior_authorization',
             '2020':'step_therapy','2021':'formulary_deletions'}


def pdf_url(url):
    p = urlparse(url)
    valid = (p.scheme == 'https' and p.port in (None,443) and not p.username and not p.password and
             ((p.hostname == 'www.aetna.com' and p.path.startswith('/medicare/documents/')) or
              (p.hostname == 'www.aarpmedicareplans.com' and p.path.startswith(('/alphadog/','/online_documents/')))))
    if not valid:
        raise ValueError('Unexpected official document URL')
    return url


class PDFRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        pdf_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def normalize(text):
    return text.replace('\u2011','-').replace('\u2013','-').replace('\u2010','-').replace('\u00ad','')


def read_pdf(url, refresh=False):
    pdf_url(url)
    key = hashlib.sha256(url.encode()).hexdigest()
    with _guard:
        lock = _locks.setdefault(key,threading.Lock())
    with lock:
        CACHE.mkdir(parents=True,exist_ok=True)
        meta_path=CACHE/(key+'.json'); pdf_path=CACHE/(key+'.pdf'); text_path=CACHE/(key+'.txt')
        if not refresh and all(p.is_file() for p in (meta_path,pdf_path,text_path)) and time.time()-meta_path.stat().st_mtime<86400:
            meta=json.loads(meta_path.read_text())
            return text_path.read_text(),meta
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError('The PDF reader is missing. Reopen the updated Mac launcher to install its free components.')
        logging.getLogger('pypdf').setLevel(logging.ERROR)
        with build_opener(PDFRedirect()).open(Request(url,headers={'User-Agent':'FernAndMossPlanFinder/1.0','Accept':'application/pdf'}),timeout=35) as response:
            pdf_url(response.url); body=response.read(30_000_001)
        if len(body)>30_000_000 or not body.startswith(b'%PDF'):
            raise ValueError('Document was not a readable PDF within the download limit')
        reader=PdfReader(io.BytesIO(body))
        if reader.is_encrypted or len(reader.pages)>650:
            raise ValueError('Document is encrypted or exceeds the extraction limit')
        pages=[normalize(p.extract_text(extraction_mode='layout') or '') for p in reader.pages]
        if not pages or not any(p.strip() for p in pages):
            raise ValueError('Document has no readable text')
        text='\f'.join(pages)
        meta={'url':url,'retrieved_at':carriers.now(),'sha256':hashlib.sha256(body).hexdigest(),'pages':len(pages)}
        # Do not cache a partially downloaded/unextracted file as a success.
        pdf_path.write_bytes(body);text_path.write_text(text);meta_path.write_text(json.dumps(meta))
        return text,meta


def document_catalog(plan,loc):
    if plan['carrier']=='Aetna':
        invoke,source,_,_=carriers.aetna_session(loc)
        contract,pbp=plan['official_id'].split('-')[:2]
        raw=invoke('getPlanDocuments',{'ContractID':contract,'PBP':pbp,'PlanYear':str(loc['year']),'Brand':'aetna'}, {})
        docs=[]
        kinds={'SB':'benefits','EOC':'evidence','FORM':'formulary','STARS':'stars','MAP':'provider_directory'}
        for row in raw['result']['planDocs']:
            if row.get('PDFLanguage')!='English':continue
            kind=kinds.get(row.get('PDFLinkType'))
            if not kind:continue
            url=pdf_url(row['PDFLink'])
            if f"/{loc['year']}/" not in urlparse(url).path:continue
            docs.append({'kind':kind,'label':row['PDFName'],'url':url,'metadata_checked_at':carriers.now()})
        return docs
    source=plan['source_url'];html=carriers.read(source)
    match=re.search(r'\bplanInfo\s*:\s*',html)
    if not match:raise ValueError('UHC plan details format changed')
    info=json.JSONDecoder().raw_decode(html[match.end():])[0]
    expected=plan['official_id'].replace('-','')
    if info.get('planId')!=expected or str(info.get('planYear'))!=str(loc['year']):
        raise ValueError('UHC plan details returned a different plan or year')
    brand=info.get('brandId','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',brand):raise ValueError('UHC document brand mapping changed')
    contract,pbp,segment=plan['official_id'].split('-')
    base='https://www.aarpmedicareplans.com'
    url=f"{base}/pdfdoclog/asyncpdf/aarp/planpdf/{contract}/{pbp}/{segment}/GOVT/{brand}/{loc['year']}/{loc['state']}/{quote(loc['county_name'],safe='')}/v2"
    data=carriers.get_json(url)
    docs=[]
    for code,language_map in data['data']['docListMap'].items():
        row=language_map.get('en_us')
        if not row or str(row.get('year'))!=str(loc['year']):continue
        label=row.get('pdfDocumentType','')
        kind=DOC_TYPES.get(code)
        if not kind:
            low=(label+' '+row.get('name','')).lower()
            kind=('formulary_deletions' if 'deletion' in low else 'vendor_information' if 'vendor' in low else 'prior_authorization' if 'prior authorization' in low else 'step_therapy' if 'step therapy' in low else 'formulary' if ('formulary' in low or 'drug list' in low) and 'um' not in low else 'other')
        docs.append({'kind':kind,'label':label or row.get('name','Document'),'url':pdf_url(urljoin(base,row['link'])),
                     'source_date':row.get('lastModifiedDate'),'metadata_checked_at':carriers.now()})
    return docs


def verified_text(text,plan,kind):
    header=normalize(text[:14000]);year=str(plan['year'])
    if year not in header:raise ValueError('PDF plan year could not be verified')
    if kind=='formulary':return  # Explicit plan-bound carrier catalog supplies shared formulary linkage.
    identity=plan['official_id']
    compact=re.sub(r'[_\s]+','-',header)
    if identity not in compact:
        raise ValueError('PDF plan identity could not be verified')
    if kind=='benefits':
        identities=set(re.findall(r'[HSR]\d{4}-\d{3}(?:-\d{3})?',header[:4500].replace('_','-')))
        if len(identities)>1:
            raise ValueError('PDF covers multiple plan identities; automatic amount extraction withheld')
        name=re.sub(r'\s+[HSR]\d{4}-\d{3}(?:-\d{3})?$','',plan['name'])
        common={'aetna','medicare','aarp','from','uhc','hmo','ppo','pos','snp','plan','d','c'}
        tokens=[t for t in re.findall(r'[a-z0-9]+',name.lower()) if t not in common]
        cover=' '.join(re.findall(r'[a-z0-9]+',header[:4500].lower()))
        if any(not re.search(r'\b'+re.escape(t)+r'\b',cover) for t in tokens):
            raise ValueError('PDF cover name differs from the shopping plan; amounts withheld')


def parse_benefits(text,url):
    """Extract only explicit periods/units; retain incomparable benefits as notes."""
    metrics={};notes={};unavailable={}
    def add(key,match,period,description,override=None):
        if not match:return
        amount=float(match.group(1).replace(',','')) if override is None else override
        metrics[key]={'amount':amount,'period':period,'notes':description,'source_url':url+'#page='+str(text[:match.start()].count('\f')+1)}
    amount=r'([0-9][0-9,]*(?:\.[0-9]{1,2})?)'
    # EOC explicitly distinguishes the network maximum from the combined maximum.
    moop=re.search(r'(?:Your\s+)?in-network maximum out-of-pocket amount\s*\(MOOP\)\s+is\s+\$'+amount,text,re.I)
    if not moop:
        # SB table columns must establish network-first order. Never use a
        # combined or out-of-network amount as the network-only maximum.
        for match in re.finditer(r'Maximum out-of-pocket amount\s*\(does\s*\$'+amount,text,re.I):
            before=text[max(0,match.start()-1500):match.start()]
            columns=list(re.finditer(r'In-network[ \t]+Out-of-network',before,re.I))
            after=text[match.end():match.end()+450]
            network_only=re.search(r'received from\s+network providers',after,re.I) and not re.search(r'out-of-network|combined|any provider',before[-250:]+after,re.I)
            if (columns or network_only) and re.search(r'each\s+year',after,re.I):
                moop=match;break
    add('moop',moop,'year','In-network annual medical maximum. Part D, premiums and excluded services are separate; confirm source conditions.')
    add('dental',re.search(r'Annual dental maximum:\s*\$'+amount,text,re.I),
        'year','Annual dental maximum/allowance. Comprehensive services may require coinsurance; network, exclusions and frequency rules apply.')
    # Aetna annual allowances need benefit-specific context, not the first allowance in the PDF.
    for key,anchor,noun in [('dental','Dental services','comprehensive'),('vision','Vision services','eyewear')]:
        start=text.find(anchor)
        if start>=0:
            segment=text[start:start+2300]
            found=re.search(r'annual benefit amount\s*\(allowance\)\s*of\s*\$'+amount+r'[\s\S]{0,160}?'+noun,segment,re.I)
            if found:
                full=re.search(re.escape(found.group(0)),text)
                add(key,full,'year',('Covered comprehensive dental services; preventive/comprehensive cost shares and benefit limits apply.' if key=='dental' else 'Annual prescription eyewear allowance; designated network/vendor and reimbursement rules apply.'),float(found.group(1).replace(',','')))
    if 'dental' in metrics:
        start=text.find('Annual dental maximum:')
        if start<0:start=text.find('Dental services')
        context=text[start:start+2200] if start>=0 else ''
        shares=list(dict.fromkeys(re.findall(r'\b[0-9]+%(?:\s*-\s*[0-9]+%)?(?=\s+coinsurance)',context)))
        if shares:metrics['dental']['notes']+=' Dental source lists '+', '.join(shares)+' coinsurance; check which services it applies to.'
    # A generic annual allowance must not become a dental amount merely because it occurs first.
    if 'dental' in metrics and 'Annual dental maximum:' not in text and 'Dental services' not in text:metrics.pop('dental',None)
    add('otc',re.search(r'(?:OTC credit|Over-the-counter)[^$]{0,100}\$'+amount+r'\s+credit\s+(?:every|per)\s+quarter',text,re.I),
        'quarter','Eligible OTC products only. Quarterly allowance; annual equivalent assumes four quarters, without rollover.')
    add('specialist',re.search(r'Specialists?(?:[\d,]+)?\s+\$'+amount+r'\s+copay',text,re.I),'visit','In-network specialist visit copay; separate services and authorization rules may apply.')
    eyewear=re.search(r'Routine eyewear\s+\$'+amount+r'\s+allowance every\s+(\d+)(?:\s+No coverage)?\s+years',text,re.I)
    if eyewear:
        n=int(eyewear.group(2));notes['vision']=f'${eyewear.group(1)} eyewear allowance every {n} years. Network and purchase rules apply.'
        if n!=1:unavailable['vision']=f'Every {n} years — not an annual allowance';metrics.pop('vision',None)
        else:add('vision',eyewear,'year',notes['vision'])
    hearing=re.search(r'Hearing aids\s*(?:\d)?\s+\$'+amount+r'\s+allowance',text,re.I)
    if not hearing:hearing=re.search(r'Hearing aids[\s\S]{0,100}?annual benefit amount\s*\(allowance\)\s*of\s*\$'+amount,text,re.I)
    if hearing:
        unavailable['hearing']='Hearing allowance — not an Advanced hearing-aid copay'
        notes['hearing']='$'+hearing.group(1)+' allowance; confirm per-ear/pair, vendor, frequency and device conditions in the PDF.'
    start=text.find('Inpatient hospital')
    if start>=0:
        segment=text[start:start+1300]
        daily=re.search(r'\$'+amount+r'\s+(?:copay\s+)?per day',segment,re.I)
        days=re.search(r'\b1\s*-\s*(\d+)',segment)
        zero=re.search(r'\$0\s+(?:copay\s+)?per day[^\d]{0,15}(\d+)[\s\S]{0,100}?(?:beyond|90)',segment,re.I)
        if daily and days and zero and int(zero.group(1))==int(days.group(1))+1:
            n=int(days.group(1));page=text[:start+daily.start()].count('\f')+1
            metrics['hospital']={'amount':float(daily.group(1).replace(',',''))*min(n,7),'period':'7-day stay',
                'notes':f'Modeled in-network 7-day stay: ${daily.group(1)} per day for days 1-{n}, then $0. Authorization and benefit-period rules apply.',
                'source_url':url+'#page='+str(page)}
    transport=re.search(r'(?:Non-emergency transportation|Routine transportation|Transportation)\s+Not covered',text,re.I)
    if transport:
        metrics['transportation']={'amount':0,'period':'one-way rides/year','notes':'Routine plan transportation is explicitly listed as not covered. Ambulance benefits are separate.', 'source_url':url+'#page='+str(text[:transport.start()].count('\f')+1)}
    return metrics,notes,unavailable


def formulary_rows(text,carrier):
    rows=[]
    for page_number,page in enumerate(text.split('\f'),1):
        last=None
        for line in page.splitlines():
            columns=re.split(r'\s{2,}',line.strip())
            if columns and columns[0]=='C1':columns=columns[1:]
            candidate=None
            if carrier=='UnitedHealthcare / AARP' and len(columns)>=3 and columns[1] in ('B','G') and re.fullmatch(r'[1-9]',columns[2]):
                candidate=(re.sub(r'^C1\s+','',columns[0]),columns[2],' '.join(columns[3:]))
            elif carrier=='Aetna' and len(columns)>=2 and re.fullmatch(r'[1-9]',columns[1]):
                flags=' '.join(columns[2:])
                if re.fullmatch(r'[A-Z0-9 ;,/()-]*',flags):candidate=(columns[0],columns[1],flags)
            if candidate and re.search(r'[A-Za-z]',candidate[0]) and not re.search(r'\.{3}|Drug Name|Drug Tier|Requirements|Page ',candidate[0],re.I):
                last={'name':candidate[0].strip(),'tier':candidate[1],'restrictions':candidate[2].strip(),'page':page_number}
                rows.append(last)
            elif last and line.strip() and not re.match(r'^\s*\d+\s*$',line):
                continuation=line.strip()
                if (carrier=='Aetna' and line.startswith(' ') and len(continuation)<100 and not continuation.isupper() and not re.search(r'\bDrug|Tier|Requirements|Index|COVERED|Formulary\b',continuation)) or (carrier=='UnitedHealthcare / AARP' and last['name'].count('(')>last['name'].count(')')):
                    last['name']+=' '+continuation
                else:last=None
    # Tables are intentionally partial. Name candidates never assert exact drug equivalence.
    return list({(r['name'],r['tier'],r['restrictions'],r['page']):r for r in rows}.values())


def lookup(params):
    name=params.get('carrier');identity=params.get('plan_id','');year=str(params.get('year','2027'));zip_code=params.get('zip','');county=params.get('county','')
    if name not in ('Aetna','UnitedHealthcare / AARP') or year not in ('2026','2027') or not re.fullmatch(r'[HSR]\d{4}-\d{3}(?:-\d{3})?',identity):
        raise ValueError('Choose a supported carrier, exact plan ID and year')
    if not _slots.acquire(blocking=False):raise carriers.ShoppingError('busy','PDF downloads are busy. Retry shortly.')
    try:
        geo=carriers.locations(zip_code)
        selected=next((c for c in geo['counties'] if c['code']==county),None)
        if not selected:raise ValueError('ZIP/county relationship could not be verified')
        loc={'zip':zip_code,'county':county,'county_name':selected['name'],'state':selected['state'],'year':int(year)}
        plans=(carriers.aetna_plans(loc) if name=='Aetna' else carriers.uhc_plans(loc))
        plan=next((p for p in plans if p['official_id']==identity),None)
        if not plan:raise ValueError('This exact plan was not returned for the selected location and year')
        docs=document_catalog(plan,loc)
        if not docs:raise ValueError('No plan-specific documents were returned by the carrier.')
        result={**loc,'carrier':name,'official_id':identity,'documents':docs,'benefit_metrics':{},'benefit_review_notes':{},'benefit_unavailable':{},'formularies':{},'issues':[],'review_sources':dict(plan.get('review_sources',{}))}
        directory=next((d for d in docs if d['kind']=='provider_directory'),None)
        if directory:result['review_sources']['provider']=directory['url']
        for kind in ('benefits','evidence','formulary'):
            doc=next((d for d in docs if d['kind']==kind),None)
            if not doc:continue
            try:
                text,metadata=read_pdf(doc['url'],params.get('refresh')=='1')
                doc.update(metadata);verified_text(text,plan,kind);doc['identity_verified']=True
                if kind=='formulary':
                    result['formularies'][doc['url']]={**metadata,'rows':formulary_rows(text,name),'partial':True}
                else:
                    metrics,notes,unavailable=parse_benefits(text,doc['url'])
                    if kind=='evidence':
                        metrics={k:v for k,v in metrics.items() if k in ('dental','moop')}
                        notes={k:v for k,v in notes.items() if k in ('dental','moop')}
                        unavailable={k:v for k,v in unavailable.items() if k in ('dental','moop')}
                    for key in list(metrics):
                        previous=result['benefit_metrics'].get(key)
                        if previous and previous['amount']!=metrics[key]['amount']:
                            result['benefit_metrics'].pop(key,None);metrics.pop(key,None)
                            unavailable[key]='Conflicting PDF amounts — review sources'
                            result['issues'].append('Benefit amounts differ between official PDFs for '+key+'. Amount withheld.')
                    for metric in metrics.values():metric['source_retrieved_at']=metadata['retrieved_at'];metric['origin']='Official plan PDF'
                    result['benefit_metrics'].update(metrics);result['benefit_review_notes'].update(notes);result['benefit_unavailable'].update(unavailable)
            except Exception as error:
                doc['identity_verified']=False
                result['issues'].append(doc['label']+': '+(str(error) if isinstance(error,(ValueError,RuntimeError)) else 'Download or extraction unavailable.'))
                if kind=='benefits':break  # A mismatched SB must not attach a different plan's companion files.
        return result
    finally:_slots.release()
