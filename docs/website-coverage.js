import {providers as liveProviders} from './provider.js?v=excellus-2027';
import {pdfMatches,healthspringSuggestions} from './healthspring-providers.js?v=excellus-2027';
import {excellusSuggestions} from './excellus-providers.js?v=excellus-2027';
const carrier=name=>name==='Excellus BlueCross BlueShield'?'Excellus':name;
export function officialId(plan){
  const id=plan.official_id || plan.cms_id || plan.locator?.replace(/-20\d{2}$/,'') || '';
  return /^[HSR]\d{4}-\d{3}-\d{3}$/.test(id)?id:null;
}
export function preparedPlan(plan,inventory){
  const id=officialId(plan);if(!id)return null;
  const matches=inventory.plans.filter(p=>carrier(p.carrier)===carrier(plan.carrier)&&p.year===plan.year&&p.state===plan.state&&officialId(p)===id);
  // A plan-name or contract/PBP match alone cannot identify a CMS segment.
  return matches.length===1?matches[0]:null;
}
export function medicationChecks(plan,prepared,items,formularies){
  return items.map(item=>{
    const base={kind:'Medication',query:item.label || item.name,matches:[],status:'unverified',message:'No matching formulary record. This does not establish exclusion.'};
    if(plan.has_drug_coverage===false || prepared?.ma_only)return {...base,message:'This source identifies a medical-only plan. Separate prescription coverage is required.'};
    if(!prepared)return {...base,status:'not_connected',message:'No formulary has been verified for this exact carrier, plan segment, state and year.'};
    const docs=(prepared.documents || []).filter(d=>d.kind==='formulary');
    if(!docs.length)return {...base,status:'not_connected',message:'No matched formulary is connected for this exact plan.'};
    for(const doc of docs){
      for(const row of (formularies[doc.url]?.rows || []).filter(r=>item.manual?r.name.toLowerCase().includes(item.name.toLowerCase()):r.name===item.name).slice(0,5)){
        base.matches.push({name:row.name,detail:`Tier ${row.tier} · PDF page ${row.page}`,restrictions:row.restrictions || 'Confirm tier and all restrictions in the source.',source_url:doc.url+'#page='+row.page,source_date:doc.retrieved_at || formularies[doc.url]?.retrieved_at || '',status:'Formulary candidate — review required'});
      }
    }
    if(base.matches.length){base.status='review_required';base.message='Source-table candidates only. Confirm the exact strength, form, pharmacy, PA/ST/QL and current formulary. Costs are not estimated.';}
    return base;
  });
}
let healthspringPromise;
async function healthspringFormularies(){
  if(!healthspringPromise)healthspringPromise=fetch('./data/healthspring-formularies.json').then(r=>{if(!r.ok)throw Error('Formulary data unavailable');return r.json();}).catch(e=>{healthspringPromise=null;throw e;});
  return healthspringPromise;
}
function checkFor(selection,message='Automated provider checks are not connected for this exact plan. Review the provider identity and office in the official carrier directory.'){
  return {kind:selection.kind==='facility'?'Facility':'Provider',query:selection.label || selection.name || selection.term,status:'not_connected',message,matches:[]};
}
export async function evaluateWebsiteCoverage(plans,context,signal,onUpdate=()=>{}){
  const records=new Map(plans.map(p=>[p.id,{medications:[],providers:context.providers.map(s=>checkFor(s))}]));
  for(const p of plans.filter(p=>p.business==='Part D'))for(const check of records.get(p.id).providers){check.status='not_applicable';check.message='Standalone prescription drug plans do not establish medical provider network participation. Check the pharmacy network separately.';}
  let inventory,formularies;
  try{[inventory,,formularies]=await context.loadData();}
  catch{for(const p of plans){const row=records.get(p.id);for(const check of row.providers){check.status='unavailable';check.message='Exact-plan source data could not be loaded. Provider participation remains unverified.';}row.medications=context.medications.map(s=>({kind:'Medication',query:s.label || s.name,status:'unavailable',message:'Prepared formulary data could not be loaded. Coverage remains unverified.',matches:[]}));onUpdate(p,row);}return records;}
  if(signal?.aborted)return records;
  const matched=new Map(plans.map(p=>[p.id,preparedPlan(p,inventory)]));
  // The HealthSpring library explicitly maps full CMS segments to formularies.
  // Shared PDP documents without regional CMS linkage are never auto-attached.
  if(context.medications.length && plans.some(p=>p.carrier==='HealthSpring')){
    try{const library=await healthspringFormularies();
      for(const p of plans.filter(p=>p.carrier==='HealthSpring' && p.year===library.year)){
        if(matched.get(p.id))continue;
        const id=officialId(p),mapping=library.plan_links[p.state+':'+id];
        if(!id || !mapping)continue;
        const urls=mapping.urls.filter(url=>library.documents[url]?.applicable_cms_ids?.includes(id));
        if(!urls.length && mapping.status!=='No included Part D')continue;
        matched.set(p.id,{...p,cms_id:id,ma_only:mapping.status==='No included Part D',documents:urls.map(url=>({kind:'formulary',url,retrieved_at:library.documents[url].retrieved_at}))});
        formularies={...formularies,...Object.fromEntries(urls.map(url=>[url,library.documents[url]]))};
      }
    }catch{/* Other carriers and already imported plans remain usable. */}
  }
  for(const p of plans){const row=records.get(p.id);row.medications=medicationChecks(p,matched.get(p.id),context.medications,formularies);onUpdate(p,row);}
  const devoted=plans.filter(p=>p.carrier==='Devoted Health'&&matched.get(p.id)&&p.year===2027).map(p=>({...matched.get(p.id),id:p.id}));
  await Promise.all(context.providers.map(async(selection,index)=>{
    if(signal?.aborted)return;
    // Live Devoted queries require its own exact resource IDs. A PDF candidate
    // from another carrier is searched by NPI/name, never treated as a FHIR ID.
    if(devoted.length){try{
      const native=!selection.directory_pdf && (selection.manual || selection.personId || selection.orgId);
      const input=native?selection:{manual:true,kind:selection.kind,term:/^\d{10}$/.test(selection.npi || '')?selection.npi:selection.name || selection.term};
      const term=input.term || input.name || selection.name || selection.term;
      const found=await liveProviders(term,devoted,signal,input);
      for(const p of devoted){const check=records.get(p.id).providers[index];check.matches=found.matches.get(p.id) || [];check.status=check.matches.length?'review_required':'unverified';check.message=found.truncated?'Directory search was partial. Confirm identity, exact office and current participation.':'Live directory results use the imported exact plan-network mapping. Confirm the provider identity, office and current participation.';onUpdate(p,records.get(p.id));}
    }catch{for(const p of devoted){const check=records.get(p.id).providers[index];check.status='unavailable';check.message='Live provider directory unavailable. No network participation inferred.';onUpdate(p,records.get(p.id));}}}
    for(const name of ['HealthSpring','Excellus BlueCross BlueShield']){
      const group=plans.filter(p=>p.carrier===name&&p.year===2027&&p.business!=='Part D');if(!group.length || signal?.aborted)continue;
      try{
        const term=/^\d{10}$/.test(selection.npi || '')?selection.npi:selection.name || selection.term;
        let options=selection.directory_pdf?[selection]:[];
        if(!options.length){
          const found=name==='HealthSpring'?await healthspringSuggestions(term,selection.kind || 'provider',group[0].state,context.directoryId):await excellusSuggestions(term,selection.kind || 'provider',group[0].state);
          options=found.options || [];
        }
        const exact=group.map(p=>({...p,cms_id:officialId(p)}));
        for(const p of group){const check=records.get(p.id).providers[index];
          for(const option of options){const found=pdfMatches(option,exact);check.matches.push(...(found.get(p.id) || []));}
          check.matches=check.matches.slice(0,5);
          if(!check.matches.length){check.status='unverified';check.message='No applicable PDF candidate was verified for this exact plan. Missing listings do not establish exclusion; use the official directory.';}
          if(check.matches.length){check.status='review_required';check.message='Dated PDF candidates for this exact plan. Confirm identity, office and current participation; these are not live network checks.';}
          onUpdate(p,records.get(p.id));
        }
      }catch{for(const p of group){records.get(p.id).providers[index].message='PDF directory search unavailable. Participation remains unverified.';onUpdate(p,records.get(p.id));}}
    }
  }));
  return records;
}
