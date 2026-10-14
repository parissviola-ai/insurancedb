/* Public FHIR requests only; no login, credentials, or patient identifiers. */
const fhirBase = 'https://fhir.devoted.com/fhir/';
const fhirCache = new Map();
async function fhirGet(url, signal) {
  const parsed = new URL(url);
  if (parsed.origin !== 'https://fhir.devoted.com' || !/^\/fhir(?:\/|$)/.test(parsed.pathname)) throw new Error('Unexpected directory URL');
  const cached=fhirCache.get(url);
  if(cached && Date.now()-cached.time<300000)return cached.data;
  const response = await fetch(url, {signal, credentials:'omit', headers:{Accept:'application/fhir+json'}});
  if (!response.ok) throw new Error('Provider directory request failed');
  const data = await response.json();
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
  else if(words.length>1) {query.given=words[0];query.family=words[words.length-1];}
  else query.name=term;
  return query;
}
export async function providers(term, plans, signal, selection=null) {
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
        if(a.state!=='NC') continue;
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

export async function providerSuggestions(term,signal) {
  const people=await fhirSearch('Practitioner',{...personQuery(term),_count:'5'},signal,1);
  const options=[],seen=new Set();let truncated=people.truncated;
  for(const person of people.rows.slice(0,5)) {
    const roles=await fhirSearch('PractitionerRole',{practitioner:'Practitioner/'+person.id,_count:'100'},signal);
    truncated ||= roles.truncated;
    const npi=(person.identifier || []).find(i=>i.system==='http://hl7.org/fhir/sid/us-npi')?.value || 'not supplied';
    const name=person.name?.[0] || {};const display=name.text || [...(name.given || []),name.family || ''].join(' ');
    for(const role of roles.rows) {
      if(role.active!==true || !role.period?.start || role.period.start>'2027-01-01' || !role.period.end || role.period.end<'2027-12-31')continue;
      for(const ref of role.location || []) {
        const key=person.id+'|'+ref.reference;if(seen.has(key))continue;
        const location=await fhirGet(fhirBase+ref.reference,signal);const a=location.address || {};if(a.state!=='NC')continue;
        seen.add(key);
        const office=a.text || [...(a.line || []),a.city,a.state,a.postalCode].filter(Boolean).join(', ');
        const specialties=(role.specialty || []).flatMap(s=>s.text?[s.text]:(s.coding || []).map(c=>c.display || 'Taxonomy '+c.code));
        options.push({personId:person.id,locationId:location.id,name:display,npi,office,specialty:specialties.join('; ') || 'Specialty not supplied',manual:false});
        if(options.length>=20)return {options,truncated:true};
      }
    }
  }
  return {options,truncated};
}
