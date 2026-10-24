import {readSearchContext} from './search-context.js';
import {evaluateWebsiteCoverage} from './website-coverage.js';
// Public plan search sends location only. Medication matches run locally;
// provider checks use existing directories. Member identifiers are never collected.
const form=document.querySelector('#search');
const button=document.querySelector('#search-carrier-websites');
const output=document.querySelector('#website-results');
let controller;let selectedWebsiteCounty='';let selectedWebsiteZip='';
function node(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
function reset(){controller?.abort();button.disabled=false;output.hidden=true;output.replaceChildren();output.setAttribute('aria-busy','false');}
for(const name of ['zip','county','state','year','business'])form.elements[name].addEventListener('change',reset);
form.elements.zip.addEventListener('input',reset);
document.addEventListener('plan-search-selections-changed',reset);
for(const id of ['medication-search','provider-search'])document.querySelector('#'+id).addEventListener('input',reset);
function link(parent,url,label){try{const u=new URL(url);if(u.protocol!=='https:'||u.username||u.password)return;const a=node('a',label);a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';parent.append(a);}catch{}}
async function search(chosenCounty=''){
  controller?.abort();controller=new AbortController();const signal=controller.signal;
  output.hidden=false;output.replaceChildren(node('h2','Plans from public carrier websites'));
  const params=new URLSearchParams();
  for(const name of ['zip','year'])params.set(name,form.elements[name].value.trim());
  // Search every carrier and product returned by the connected Medicare
  // shopping sites, independent of the imported-plan carrier filter.
  if(chosenCounty){selectedWebsiteCounty=chosenCounty;selectedWebsiteZip=params.get('zip');}
  if(selectedWebsiteCounty && selectedWebsiteZip===params.get('zip'))params.set('county',selectedWebsiteCounty);
  else if(form.elements.county.value)params.set('county_name',form.elements.county.selectedOptions[0].textContent);
  if(!/^[0-9]{5}$/.test(params.get('zip'))){output.append(node('p','Enter a five-digit ZIP code.'));return;}
  if(!location.pathname.startsWith('/dashboard/')){
    output.append(node('p','Public website searches require the private backend. This static dashboard is not connected to it. Carrier availability has not been checked.'));return;
  }
  let context;try{context=readSearchContext();if(context.pending)throw new Error('Add or select the medication/provider you typed, or clear it before searching.');}catch(error){output.append(node('p',error.message));return;}
  button.disabled=true;output.setAttribute('aria-busy','true');
  output.append(node('p','Searching public carrier shopping sites in parallel. This can take up to 90 seconds.'));
  try{
    const response=await fetch('/api/carrier-websites?'+params,{signal,credentials:'same-origin',headers:{Accept:'application/json'}});
    const data=await response.json();if(signal.aborted)return;
    if(!response.ok)throw new Error(data.error||'Carrier search unavailable. No plan availability determined.');
    output.replaceChildren(node('h2','Plans from public carrier websites'));
    if(data.needs_county){
      output.append(node('p','This ZIP crosses county boundaries. Select your county to search all carriers.'));
      const label=node('label','County');const select=node('select');select.append(new Option('Select county',''));
      for(const c of data.counties)select.append(new Option(`${c.name}, ${c.state}`,c.code));
      const go=node('button','Search all carriers');go.type='button';go.addEventListener('click',()=>{if(select.value)search(select.value);});
      label.append(select);output.append(label,go);select.focus();return;
    }
    if(data.location)output.append(node('p',`${data.location.zip} · ${data.location.county_name} County, ${data.location.state} · ${data.location.year}`));
    output.append(node('p',data.notice));
    const coverageCells=new Map();
    if(data.plans.length){
      output.append(node('h3',`${data.plans.length} plans returned`));
      const wrap=node('div');wrap.className='comparison-scroll';const table=node('table');const head=node('tr');
      for(const text of ['Carrier','Plan','Plan ID','Product','Monthly premium','Source / checked','Medications','Providers / facilities'])head.append(node('th',text));
      const thead=node('thead');thead.append(head);table.append(thead);const body=node('tbody');
      for(const p of data.plans){const tr=node('tr');
        for(const value of [p.carrier,p.name+(p.special_needs?' — special eligibility required':''),p.official_id,p.business,p.premium===null?'Unverified':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(p.premium)])tr.append(node('td',value));
        const source=node('td');link(source,p.source_url,'Official shopping source');source.append(node('p',new Date(p.checked_at).toLocaleString()));tr.append(source);
        const drugs=node('td',context.medications.length?'Checking matched formularies…':'Not requested');
        const providers=node('td',context.providers.length?'Checking connected directories…':'Not requested');
        tr.append(drugs,providers);coverageCells.set(p.id,{drugs,providers});body.append(tr);
      }
      table.append(body);wrap.append(table);output.append(wrap);
    }
    output.append(node('h3','Carrier search status'));
    const statuses=node('ul');
    for(const c of data.carriers){const item=node('li');item.append(node('strong',`${c.carrier}: ${c.status.replaceAll('_',' ')}`),node('p',c.message));
      if(c.source_checked_at)item.append(node('p',`Website checked: ${new Date(c.source_checked_at).toLocaleString()}`));
      item.append(node('p',c.checked_at?`Plans checked: ${new Date(c.checked_at).toLocaleString()}`:'Plans checked: not verified'));
      link(item,c.source_url,'Carrier website');statuses.append(item);
    }
    output.append(statuses);
    if(context.medications.length || context.providers.length){
      output.append(node('p','Medication results are formulary candidates. Provider results may be live listings or dated PDF candidates. Missing or disconnected sources remain unverified. Exact prescription, pharmacy, provider identity and office require confirmation.'));
      await evaluateWebsiteCoverage(data.plans,context,signal,(plan,checks)=>{if(signal.aborted)return;const cells=coverageCells.get(plan.id);if(!cells)return;renderChecks(cells.drugs,checks.medications,plan,'medication');renderChecks(cells.providers,checks.providers,plan,'provider');});
    }
  }catch(error){if(!signal.aborted)output.replaceChildren(node('h2','Carrier website search unavailable'),node('p',error.message||'No plan availability determined. Please retry.'));}
  finally{if(!signal.aborted){button.disabled=false;output.setAttribute('aria-busy','false');}}
}
button.addEventListener('click',()=>search());

function renderChecks(cell,checks,plan,kind){
  cell.replaceChildren();if(!checks.length){cell.append(node('span','Not requested'));return;}
  for(const check of checks){
    const section=node('details');section.append(node('summary',`${check.query}: ${check.status.replaceAll('_',' ')}`),node('p',check.message));
    for(const match of check.matches){section.append(node('p',match.name+(match.detail?' · '+match.detail:'')));if(match.restrictions)section.append(node('p',match.restrictions));if(match.source_date)section.append(node('p','Source retrieved: '+match.source_date));link(section,match.source_url,'Review source');}
    if(!check.matches.length)link(section,plan.review_sources?.[kind] || plan.source_url,'Review on carrier site');
    cell.append(section);
  }
}
