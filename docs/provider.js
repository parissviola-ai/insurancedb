/* Public FHIR requests only; no login, credentials, or patient identifiers. */
const fhirBase = 'https://fhir.devoted.com/fhir/';
const fhirCache = new Map();
async function fhirGet(url, signal) {
  const parsed = new URL(url);
  if (parsed.origin !== 'https://fhir.devoted.com' || !/^\/fhir(?:\/|$)/.test(parsed.pathname)) throw new Error('Unexpected directory URL');
  const cached=fhirCache.get(url);
  if(cached && Date.now()-cached.time<300000)return cached.data;
  const controller=new AbortController();let timedOut=false;
  const cancel=()=>controller.abort();if(signal?.aborted)controller.abort();signal?.addEventListener('abort',cancel,{once:true});
  const timer=setTimeout(()=>{timedOut=true;controller.abort();},20000);
  let data;
  try {
    const response=await fetch(url,{signal:controller.signal,credentials:'omit',headers:{Accept:'application/fhir+json'}});
    if(!response.ok){const error=new Error('Directory returned HTTP '+response.status);error.status=response.status;throw error;}
    data=await response.json();
  } catch(error){if(timedOut)throw new Error('Directory request timed out');if(error instanceof TypeError)throw new Error('Browser could not connect to the directory');if(error instanceof SyntaxError)throw new Error('Directory returned an unreadable response');throw error;}
  finally{clearTimeout(timer);signal?.removeEventListener('abort',cancel);}
  if (data.resourceType === 'OperationOutcome') throw new Error('Provider directory search failed');
  if (fhirCache.size > 200) fhirCache.clear();
  fhirCache.set(url,{time:Date.now(),data}); return data;
}
async function fhirSearch(type, params, signal, maxPages=2) {
  let url=fhirBase+type+'?'+new URLSearchParams(params); const rows=[];
  for(let page=0;page<maxPages;page++) {
    const bundle=await fhirGet(url,signal);
    if(bundle.resourceType!=='Bundle') throw new Error('Invalid directory response');
    for(const entry of bundle.entry || []) if(entry.resource && entry.search?.mode!=='outcome') rows.push(entry.resource);
    url=(bundle.link || []).find(l=>l.relation==='next')?.url;
    if(!url) return {rows,truncated:false};
  }
  return {rows,truncated:true};
}
function personQuery(term) {
  const words=term.trim().split(/\s+/); const query={_count:'10'};
  if(/^\d{10}$/.test(term)) query.identifier='http://hl7.org/fhir/sid/us-npi|'+term;
  else if(words.length>1) {query.given=words[0];query.family=words.slice(1).join(' ');}
  else query.name=term;
  return query;
}
export async function providers(term, plans, signal, selection=null) {
  if(selection?.kind==='facility')return facilityMatches(selection,plans,signal);
  const people=selection && !selection.manual ? {rows:[await fhirGet(fhirBase+'Practitioner/'+selection.personId,signal)],truncated:false} : await fhirSearch('Practitioner',personQuery(selection?.term || term),signal,1);
  const matches=new Map(plans.map(p=>[p.id,[]])); let truncated=people.truncated;
  for(const person of people.rows.slice(0,10)) {
    const roles=await fhirSearch('PractitionerRole',{practitioner:'Practitioner/'+person.id,_count:'100'},signal);
    truncated ||= roles.truncated;
    for(const role of roles.rows) {
      if(role.active!==true || !role.period?.start || role.period.start>'2027-01-01' || !role.period.end || role.period.end<'2027-12-31') continue;
      const networks=(role.extension || []).filter(e=>e.url.endsWith('/network-reference')).map(e=>e.valueReference?.reference);
      const eligible=plans.filter(p=>(p.network || []).some(n=>networks.includes(n.reference)));
      if(!eligible.length) continue;
      for(const ref of role.location || []) {
        if(selection && !selection.manual && ref.reference!=='Location/'+selection.locationId)continue;
        const location=await fhirGet(fhirBase+ref.reference,signal); const a=location.address || {};
        if(a.state!==(plans[0]?.state || 'NC')) continue;
        const name=person.name?.[0] || {}; const label=name.text || [...(name.given || []),name.family || ''].join(' ');
        const detail=a.text || [...(a.line || []),a.city,a.state,a.postalCode].filter(Boolean).join(', ');
        for(const plan of eligible) {
          const list=matches.get(plan.id);
          if(list.length<20) list.push({name:label,detail,status:'Listed in network',
            restrictions:'Directory lists this office in the plan network for 2027. Confirm identity and current participation before enrollment.',
            source_url:fhirBase+'PractitionerRole/'+role.id});
          else truncated=true;
        }
      }
    }
  }
  return {matches,truncated};
}

export async function providerSuggestions(term,signal,state='NC') {
  const query={...personQuery(term),_count:'5'};
  if(query.family){query['family:contains']=query.family;delete query.family;}
  if(!/^\d{10}$/.test(term))query['_has:PractitionerRole:practitioner:location.address-state']=state;
  let people=await fhirSearch('Practitioner',query,signal,1);
  const words=term.trim().split(/\s+/);
  for(let i=2;!people.rows.length && i<Math.min(words.length,5);i++){
    const alternate={...query,'family:contains':words.slice(i).join(' '),given:words[0]};
    people=await fhirSearch('Practitioner',alternate,signal,1);
  }
  if(!people.rows.length && words.length>1){
    const partial={...query,given:words[0]};delete partial.family;
    partial['family:contains']=words[words.length-1];
    people=await fhirSearch('Practitioner',partial,signal,1);
  }
  const options=[],seen=new Set();let truncated=people.truncated,unavailable=false;
  for(const person of people.rows.slice(0,5)) {
    let roles;try{roles=await fhirSearch('PractitionerRole',{practitioner:'Practitioner/'+person.id,_count:'100'},signal);}catch(error){if(signal?.aborted)throw error;unavailable=true;truncated=true;continue;}
    truncated ||= roles.truncated;
    const npi=(person.identifier || []).find(i=>i.system==='http://hl7.org/fhir/sid/us-npi')?.value || 'not supplied';
    const name=person.name?.[0] || {};const display=name.text || [...(name.given || []),name.family || ''].join(' ');
    for(const role of roles.rows) {
      if(role.active!==true || !role.period?.start || role.period.start>'2027-01-01' || !role.period.end || role.period.end<'2027-12-31')continue;
      for(const ref of role.location || []) {
        const key=person.id+'|'+ref.reference;if(seen.has(key))continue;
        let location;try{location=await fhirGet(fhirBase+ref.reference,signal);}catch(error){if(signal?.aborted)throw error;unavailable=true;truncated=true;continue;}const a=location.address || {};if(a.state!==state)continue;
        seen.add(key);
        const office=a.text || [...(a.line || []),a.city,a.state,a.postalCode].filter(Boolean).join(', ');
        const specialties=(role.specialty || []).flatMap(s=>s.text?[s.text]:(s.coding || []).map(c=>c.display || 'Taxonomy '+c.code));
        options.push({personId:person.id,locationId:location.id,name:display,npi,office,specialty:specialties.join('; ') || 'Specialty not supplied',manual:false});
        if(options.length>=20)return {options,truncated:true,unavailable};
      }
    }
  }
  return {options,truncated,unavailable};
}

function active2027(r){return r.active===true && r.period?.start && r.period.start<='2027-01-01' && r.period.end && r.period.end>='2027-12-31';}
function officeText(location){const a=location.address || {};return a.text || [...(a.line || []),a.city,a.state,a.postalCode].filter(Boolean).join(', ');}
function phoneOf(...resources){return resources.flatMap(r=>r?.telecom || []).find(t=>t.system==='phone')?.value || '';}
export async function facilitySuggestions(term,signal,state='NC'){
 const q={_count:'5'};if(!/^\d{10}$/.test(term))q['_has:OrganizationAffiliation:participating-organization:location.address-state']=state;if(/^\d{10}$/.test(term))q.identifier='http://hl7.org/fhir/sid/us-npi|'+term;else q.name=term;
 const organizations=await fhirSearch('Organization',q,signal,1);const options=[],seen=new Set();let truncated=organizations.truncated;
 for(const org of organizations.rows){
  const affiliations=await fhirSearch('OrganizationAffiliation',{'participating-organization':'Organization/'+org.id,_count:'100'},signal);truncated ||= affiliations.truncated;
  for(const affiliation of affiliations.rows){if(!active2027(affiliation))continue;
   for(const ref of affiliation.location || []){const key=org.id+'|'+ref.reference;if(seen.has(key))continue;const location=await fhirGet(fhirBase+ref.reference,signal);if(location.address?.state!==state)continue;seen.add(key);
    const npi=(org.identifier || []).find(i=>i.system==='http://hl7.org/fhir/sid/us-npi')?.value || 'not supplied';
    const type=(org.type || []).flatMap(t=>t.text?[t.text]:(t.coding || []).map(c=>c.display || c.code)).join('; ') || 'Facility';
    options.push({kind:'facility',orgId:org.id,locationId:location.id,name:org.name || 'Unnamed facility',npi,office:officeText(location),specialty:type,phone:phoneOf(location,org,affiliation),manual:false});
    if(options.length>=20)return {options,truncated:true};
   }
  }
 }
 return {options,truncated};
}
async function facilityMatches(selection,plans,signal){
 const matches=new Map(plans.map(p=>[p.id,[]]));
 if(selection.manual)return {matches,truncated:false};
 const org=await fhirGet(fhirBase+'Organization/'+selection.orgId,signal);
 const affiliations=await fhirSearch('OrganizationAffiliation',{'participating-organization':'Organization/'+selection.orgId,_count:'100'},signal);
 for(const affiliation of affiliations.rows){if(!active2027(affiliation) || !(affiliation.location || []).some(l=>l.reference==='Location/'+selection.locationId))continue;
  const location=await fhirGet(fhirBase+'Location/'+selection.locationId,signal);if(location.address?.state!==(plans[0]?.state || 'NC'))continue;
  for(const plan of plans){if(!(plan.network || []).some(n=>(affiliation.network || []).some(a=>a.reference===n.reference)))continue;
   matches.get(plan.id).push({name:org.name,detail:officeText(location)+(phoneOf(location,org,affiliation)?' · Phone '+phoneOf(location,org,affiliation):''),status:'Facility listed in network',restrictions:'Facility location is listed for this network in 2027. Call to confirm services and participation. Clinicians at the facility require separate checks.',source_url:fhirBase+'OrganizationAffiliation/'+affiliation.id});
  }
 }
 return {matches,truncated:affiliations.truncated};
}
