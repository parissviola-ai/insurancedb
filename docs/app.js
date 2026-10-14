import {providers} from './provider.js';
const form=document.querySelector('#search'); const results=document.querySelector('#results');
const state=document.querySelector('#state');state.append(new Option('North Carolina','NC'));
const business=form.elements.business;business.replaceChildren(new Option('Medicare Advantage','Medicare Advantage'));
form.elements.carrier.value='Devoted Health';form.elements.carrier.readOnly=true;
const county=form.elements.county;
function el(tag,text,cls) {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function link(parent,label,url) {if(!/^https:\/\//.test(url))return;const n=el('a',label);n.href=url;n.target='_blank';n.rel='noopener noreferrer';parent.append(n);}
let dataPromise;let request;
async function data() {
  if(!dataPromise) dataPromise=Promise.all(['plans','zip-counties','formularies'].map(async name=> {
    const r=await fetch('./data/'+name+'.json');if(!r.ok)throw new Error('Prepared plan data could not be loaded. Please retry.');return r.json();
  })).catch(e=>{dataPromise=null;throw e;});
  return dataPromise;
}
function terms(value) {return value.split('\n').map(s=>s.trim()).filter(Boolean);}
function drugMatches(plan,term,formularies) {
  const hits=[];
  for(const doc of plan.documents.filter(d=>d.kind==='formulary')) {
    const rows=formularies[doc.url]?.rows || [];
    for(const row of rows.filter(r=>r.name.toLowerCase().includes(term.toLowerCase())).slice(0,5)) hits.push({
      name:row.name,detail:`Tier ${row.tier} · PDF page ${row.page}`,status:'Review required',
      restrictions:row.restrictions || '',
      source_url:doc.url+'#page='+row.page});
  }
  return hits;
}
function check(parent,kind,term,matches,message) {
  const section=el('div',undefined,'check');section.append(el('strong',kind+': '+term));
  if(!matches.length)section.append(el('p',message || 'Unverified — no matching source record. This does not establish exclusion.','badge unverified'));
  for(const m of matches) {
    section.append(el('p',m.name+' · '+m.detail),el('span',m.status,'badge unverified'));
    if(m.restrictions) section.append(el('p',m.restrictions));
    if(kind==='Medication') {
      const note=el('p','Restrictions unverified — ');
      link(note,'check the official formulary',m.source_url);section.append(note);
    } else link(section,'Source record',m.source_url);
  }
  parent.append(section);
}
form.elements.zip.addEventListener('input',()=>county.replaceChildren(new Option('Choose after ZIP lookup','')));
form.addEventListener('submit',async event=>{
  event.preventDefault();if(request)request.abort();request=new AbortController();const signal=request.signal;
  const zip=form.elements.zip.value.trim();const chosen=county.value;
  const drugs=terms(form.elements.medication.value),people=terms(form.elements.provider.value);
  results.setAttribute('aria-busy','true');results.replaceChildren(el('p','Searching…'));
  try {
    if(!/^\d{5}$/.test(zip))throw new Error('Enter a five-digit ZIP code.');
    if(people.length>3 || drugs.length>10)throw new Error('Search up to 3 providers and 10 medications at a time.');
    const [inventory,zipMap,formularies]=await data();if(signal.aborted)return;
    const counties=zipMap[zip] || [];county.replaceChildren(new Option('Select county',''));
    for(const c of counties)county.append(new Option(c.name,c.code));
    const selected=counties.find(c=>c.code===chosen) || (counties.length===1?counties[0]:null);
    county.value=selected?.code || '';
    if(!selected) {
      results.replaceChildren(el('h2','Choose your location'),el('p',counties.length?'This ZIP crosses county boundaries. Select your county, then search again.':'This ZIP is not in the prepared NC lookup. No plan availability inferred.'));
      if(counties.length)county.focus();return;
    }
    const plans=inventory.plans.filter(p=>p.counties.includes(selected.code));
    results.replaceChildren(el('h2',`${plans.length} plans · ${selected.name} County`),el('p',`Official 2027 county mapping. Data refreshed ${inventory.snapshot.retrieved_at.slice(0,10)}. Confirm eligibility and enrollment requirements.`));
    if(!plans.length)results.append(el('p','Devoted’s published mapping lists no 2027 plans for this county.'));
    const sections=new Map();
    for(const plan of plans) {
      const card=el('article',undefined,'plan');card.append(el('span',plan.business,'badge'),el('h3',plan.name),
        el('p',`${plan.carrier} · ${plan.year} · ${selected.name}, NC · ZIP ${zip}`),el('p','Monthly premium: '+plan.premium));
      card.append(el('small','Premium extracted from the Summary of Benefits. Other costs and conditions apply.'));
      for(const doc of plan.documents) {const row=el('p');link(row,({benefits:'Summary of Benefits',evidence:'Evidence of Coverage',formulary:'2027 Drug List'})[doc.kind],doc.url);card.append(row);}
      for(const drug of drugs)check(card,'Medication',drug,drugMatches(plan,drug,formularies));
      const providerSection=el('div');card.append(providerSection);sections.set(plan.id,providerSection);
      link(card,'Official provider search',`https://www.devoted.com/search-providers/#filterType=all&p=${encodeURIComponent(plan.name.includes('(PPO')?'PPO':'HMO')}&q=&s=NC&y=2027`);
      results.append(card);
    }
    if(people.length && plans.length) {
      const status=el('p','Checking live provider directory…');results.prepend(status);
      try {
        for(const term of people) {
          const found=await providers(term,plans,signal);if(signal.aborted)return;
          for(const plan of plans)check(sections.get(plan.id),'Provider',term,found.matches.get(plan.id),found.truncated?'Unverified — search incomplete; use the official directory.':undefined);
          if(found.truncated)results.append(el('p','Provider search was limited. Missing matches remain unverified; search by NPI or full name.'));
        }
        status.textContent='Live provider lookup complete. Confirm the exact office and current participation.';
      } catch(e) {
        if(signal.aborted)return;
        status.textContent='Live provider lookup unavailable. Use the official provider search links; no coverage inferred.';
      }
    }
  } catch(e) {if(!signal.aborted)results.replaceChildren(el('p',e.message));}
  finally {if(!signal.aborted)results.setAttribute('aria-busy','false');}
});
data().catch(()=>{});
