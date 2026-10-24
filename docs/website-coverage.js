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
export function nameCandidate(source,query){
  const ignored=new Set(['capsule','capsules','tablet','tablets','suspension','susp','reconstituted','oral','solution','injection','extended','release','immediate','chewable','selected','strength','potassium','hydrochloride']);
  const tokens=(query.toLowerCase().match(/[a-z]{4,}/g) || []).filter(t=>!ignored.has(t));
  if(!tokens.length)return false;
  const text=source.toLowerCase();return tokens.every(t=>text.includes(t));
}

export function medicationChecks(plan,prepared,items,formularies){
  return items.map(item=>{
    const base={kind:'Medication',query:item.label || item.name,display_name:item.name,matches:[],status:'unverified',message:'No formulary match found. This does not mean the drug is excluded.'};
    if(plan.has_drug_coverage===false || prepared?.ma_only)return {...base,status:'no_drug_benefit',message:'Medical-only plan. Separate prescription coverage is needed.'};
    if(!prepared)return {...base,status:'not_connected',message:'Drug checks are not connected for this plan.'};
    const docs=(prepared.documents || []).filter(d=>d.kind==='formulary');
    if(!docs.length)return {...base,status:'not_connected',message:'Drug checks are not connected for this plan.'};
    for(const doc of docs){
      for(const row of (formularies[doc.url]?.rows || []).filter(r=>prepared.document_search?nameCandidate(r.name,item.name):item.manual?r.name.toLowerCase().includes(item.name.toLowerCase()):r.name===item.name).slice(0,5)){
        base.matches.push({name:row.name,detail:`Tier ${row.tier} · PDF page ${row.page}`,restrictions:row.restrictions || 'Confirm tier and all restrictions in the source.',source_url:doc.url+'#page='+row.page,source_date:doc.retrieved_at || formularies[doc.url]?.retrieved_at || '',status:'Formulary candidate — review required',cost:prepared.drug_costs?.tiers?.[row.tier] || null,cost_context:prepared.drug_costs || {}});
      }
    }
    if(base.matches.length){base.status='review_required';base.result_type=item.manual||prepared.document_search?'formulary_candidates':'formulary_listing';base.message=item.manual||prepared.document_search?'Possible drug matches. Select the exact strength and form.':'Confirm the selected strength and form, then check pharmacy costs and restrictions.';}
    return base;
  });
}
let healthspringPromise;
async function healthspringFormularies(){
  if(!healthspringPromise)healthspringPromise=fetch('./data/healthspring-formularies.json').then(r=>{if(!r.ok)throw Error('Formulary data unavailable');return r.json();}).catch(e=>{healthspringPromise=null;throw e;});
  return healthspringPromise;
}
function checkFor(selection,message='Provider checks are not connected for this plan.'){
  return {kind:selection.kind==='facility'?'Facility':'Provider',query:selection.label || selection.name || selection.term,display_name:selection.name || selection.term,status:'not_connected',message,matches:[]};
}
export async function evaluateWebsiteCoverage(plans,context,signal,onUpdate=()=>{}){
  const records=new Map(plans.map(p=>[p.id,{medications:[],providers:context.providers.map(s=>checkFor(s))}]));
  for(const p of plans.filter(p=>p.business==='Part D'))for(const check of records.get(p.id).providers){check.status='not_applicable';check.message='Standalone prescription drug plans do not establish medical provider network participation. Check the pharmacy network separately.';}
  let inventory,formularies;
  try{[inventory,,formularies]=await context.loadData();}
  catch{for(const p of plans){const row=records.get(p.id);for(const check of row.providers){check.status='unavailable';check.message='Exact-plan source data could not be loaded. Provider participation remains unverified.';}row.medications=context.medications.map(s=>({kind:'Medication',query:s.label || s.name,status:'unavailable',message:'Prepared formulary data could not be loaded. Coverage remains unverified.',matches:[]}));onUpdate(p,row);}return records;}
  if(signal?.aborted)return records;
  const matched=new Map(plans.map(p=>[p.id,preparedPlan(p,inventory)]));
  for(const p of plans){const docs=p.document_data;if(!docs||docs.carrier!==p.carrier||docs.official_id!==p.official_id||docs.year!==p.year||docs.state!==p.state)continue;
    const sources=docs.documents.filter(d=>d.kind==='formulary'&&d.identity_verified&&docs.formularies[d.url]);if(!sources.length)continue;
    matched.set(p.id,{...p,documents:sources,document_search:true});formularies={...formularies,...docs.formularies};
  }
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
      for(const p of devoted){const check=records.get(p.id).providers[index];check.matches=found.matches.get(p.id) || [];const exactOffice=!selection.manual&&!selection.directory_pdf&&Boolean(selection.locationId);check.status=check.matches.length?(exactOffice?'listed_in_network':'network_candidates'):'unverified';check.message=check.matches.length?(exactOffice?'This office is listed for this plan. Confirm participation before enrollment.':'Select the exact provider and office from the network matches.'):'No network match found. This does not establish exclusion.';check.search_partial=found.truncated;onUpdate(p,records.get(p.id));}
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
          if(check.matches.length){check.status=selection.directory_pdf?'dated_directory_listing':'directory_candidates';check.message='Dated directory listing. Confirm the provider, office and current participation.';}
          onUpdate(p,records.get(p.id));
        }
      }catch{for(const p of group){records.get(p.id).providers[index].message='PDF directory search unavailable. Participation remains unverified.';onUpdate(p,records.get(p.id));}}
    }
  }));
  return records;
}
