"""Download official 2027 NC shopping documents without member credentials.
PDFs and text stay in a maintainer cache, outside the public dashboard.
"""
import argparse
import urllib.request,urllib.parse,http.cookiejar,re,html,json,concurrent.futures,subprocess,hashlib
from pathlib import Path
parser=argparse.ArgumentParser(description='Retrieve source documents for the seven verified Wellcare NC 2027 MA plans.')
parser.add_argument('--cache',required=True)
args=parser.parse_args()
op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
s=op.open('https://wellcare.isf.io/',timeout=30).read().decode()
for values in [{'quote.Location.Zip':'28202','submit':'GO_TO_PLANS'},{'planYear':'2027'}]:
 a=re.search(r'<form action="([^"]+)"',s).group(1);values['__RequestVerificationToken']=re.search(r'name="__RequestVerificationToken" type="hidden" value="([^"]+)"',s).group(1)
 s=op.open('https://wellcare.isf.io'+a,data=urllib.parse.urlencode(values).encode(),timeout=30).read().decode()
links=re.findall(r'<a href="([^"]+)"[^>]*id="block\((\d+)\)-link"',s,re.S)
root=Path(args.cache);root.mkdir(exist_ok=True)
plans=[]
for path,pid in links:
 if pid not in ['4146','4111','4112','4113','4114','4144','4145']:continue
 t=op.open('https://wellcare.isf.io'+html.unescape(path),timeout=30).read().decode();(root/(pid+'.html')).write_text(t)
 text=re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]+>',' ',re.sub(r'<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>','',t,flags=re.S))))
 cms=re.search(r'Contract ID\s+(H\d{4}-\d{3})',text).group(1)
 urls=[html.unescape(x) for x in re.findall(r'href="([^"]+)"',t) if '.pdf' in x]
 selected=[u for u in urls if 'Comp_Form' in u or ('2027' in u and ('_SB_' in u or '_EOC_' in u))]
 plans.append({'cms_id':cms,'pid':pid,'documents':selected,'text':text})
 print(cms,selected)
urls=sorted(set(u for p in plans for u in p['documents']))
def download(u):
 name=hashlib.sha256(u.encode()).hexdigest();pdf=root/(name+'.pdf');txt=root/(name+'.txt')
 if not pdf.exists():pdf.write_bytes(urllib.request.urlopen(u,timeout=40).read())
 subprocess.run(['pdftotext','-layout',str(pdf),str(txt)],check=True,capture_output=True)
 return u,{'text_path':str(txt),'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()}
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:docs=dict(ex.map(download,urls))
(root/'manifest.json').write_text(json.dumps({'plans':plans,'documents':docs},indent=2))
if len(plans)!=7:raise ValueError('Expected seven NC plans; review changed shopping results before importing')
print('Downloaded',len(urls),'documents for',len(plans),'plans')
