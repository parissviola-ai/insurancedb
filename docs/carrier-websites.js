import {comparisonPlans,websiteComparison} from './website-comparison.js';
import {readSearchContext} from './search-context.js';
import {evaluateWebsiteCoverage} from './website-coverage.js';
// Public plan search sends location only. Medication matches run locally;
// provider checks use existing directories. Member identifiers are never collected.
const form=document.querySelector('#search');
const button=document.querySelector('#search-carrier-websites');
const output=document.querySelector('#website-results');
let controller;let comparison;let selectedWebsiteCounty='';let selectedWebsiteZip='';
function node(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
function reset(){controller?.abort();comparison?.destroy();comparison=null;button.disabled=false;output.hidden=true;output.replaceChildren();output.setAttribute('aria-busy','false');}
for(const name of ['zip','county','state','year','business'])form.elements[name].addEventListener('change',reset);
form.elements.zip.addEventListener('input',reset);
document.addEventListener('plan-search-selections-changed',reset);
for(const id of ['medication-search','provider-search'])document.querySelector('#'+id).addEventListener('input',reset);
function link(parent,url,label){try{const u=new URL(url);if(u.protocol!=='https:'||u.username||u.password)return;const a=node('a',label);a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';parent.append(a);}catch{}}
async function search(chosenCounty=''){
  controller?.abort();comparison?.destroy();comparison=null;controller=new AbortController();const signal=controller.signal;
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
    let inventory={plans:[]};
    try{[inventory]=await context.loadData();}catch{output.append(node('p','Saved benefit documents could not be loaded. Shopping results remain available; missing benefits are unverified.'));}
    if(signal.aborted)return;
    const plans=comparisonPlans(data.plans,inventory);
    const comparisonContainer=node('section');output.append(comparisonContainer);
    comparison=websiteComparison(comparisonContainer,data,plans,context,form,{inventory,loadDocuments:async(plan,refresh=false)=>{
      const query=new URLSearchParams({carrier:plan.carrier,plan_id:plan.official_id,zip:data.location.zip,county:data.location.county,year:data.location.year});
      if(refresh)query.set('refresh','1');
      const response=await fetch('/api/plan-documents?'+query,{signal,credentials:'same-origin'});const documents=await response.json();if(signal.aborted)return;
      if(!response.ok)throw new Error(documents.error || 'Official PDF pull unavailable.');
      comparison.updateDocuments(plan.id,documents);
      const live=data.plans.find(p=>p.id===plan.id);
      if(context.medications.length||context.providers.length)await evaluateWebsiteCoverage([live],context,signal,(p,checks)=>{if(!signal.aborted)comparison?.updateCoverage(p.id,checks);});
    }});
    const carrierStatus=node('details');
    const attention=data.carriers.filter(c=>!['success','included_under_healthspring'].includes(c.status)).length;
    carrierStatus.append(node('summary','Carrier search status'+(attention?' · '+attention+' need attention':'')));
    carrierStatus.open=!data.plans.length;
    const statuses=node('ul');
    for(const c of data.carriers){const item=node('li');item.append(node('strong',`${c.carrier}: ${c.status.replaceAll('_',' ')}`),node('p',c.message));
      if(c.source_checked_at)item.append(node('p',`Website checked: ${new Date(c.source_checked_at).toLocaleString()}`));
      item.append(node('p',c.checked_at?`Plans checked: ${new Date(c.checked_at).toLocaleString()}`:'Plans checked: not verified'));
      link(item,c.source_url,'Carrier website');statuses.append(item);
    }
    carrierStatus.append(statuses);output.append(carrierStatus);
    const documentTask=comparison.documentsReady;
    if(context.medications.length || context.providers.length){
      output.append(node('p','Open plan details for medication, provider and source information. “Not checked” does not mean “not covered.”'));
      await evaluateWebsiteCoverage(data.plans,context,signal,(plan,checks)=>{if(!signal.aborted&&!plan.document_data)comparison?.updateCoverage(plan.id,checks);});
    }
    await documentTask;
  }catch(error){if(!signal.aborted)output.replaceChildren(node('h2','Carrier website search unavailable'),node('p',error.message||'No plan availability determined. Please retry.'));}
  finally{if(!signal.aborted){button.disabled=false;output.setAttribute('aria-busy','false');}}
}
button.addEventListener('click',()=>search());
