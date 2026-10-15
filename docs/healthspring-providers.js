let manifestPromise;const indexes=new Map();
async function manifest(){if(!manifestPromise)manifestPromise=fetch('./data/healthspring-directory-index.json?v=healthspring-all-directories').then(r=>{if(!r.ok)throw Error('Directory catalog unavailable');return r.json();}).catch(e=>{manifestPromise=null;throw e;});return manifestPromise;}
export async function healthspringDirectories(state){return (await manifest()).directories.filter(d=>d.states.includes(state)&&d.status==='Indexed');}
export async function healthspringSuggestions(term,kind,state,directoryId){
 const available=await healthspringDirectories(state);
 if(!available.length)return {options:[],truncated:false,pdf:true,unsupported:true};
 const directory=available.find(d=>d.id===(directoryId || (state==='NC'?'provider-pharmacy-directory-north-carolina-ppo':'')));
 if(!directory)return {options:[],truncated:false,pdf:true,needsDirectory:true};
 if(!indexes.has(directory.id)){if(indexes.size>=3)indexes.delete(indexes.keys().next().value);indexes.set(directory.id,fetch(directory.index_file+'?v=healthspring-all-directories').then(r=>{if(!r.ok)throw Error('PDF directory unavailable');return r.json();}).catch(e=>{indexes.delete(directory.id);throw e;}));}
 const data=await indexes.get(directory.id),words=term.toLowerCase().trim().split(/\s+/);
 const matches=data.rows.filter(r=>r.kind===kind&&(/^\d{10}$/.test(term)?r.npi===term:words.every(w=>r.name.toLowerCase().includes(w))));
 return {options:matches.slice(0,15).map(r=>({...r,locationId:directory.id+':'+r.locationId,personId:r.npi || r.locationId,directory_pdf:true,source_url:directory.url+'#page='+r.page,directory_date:directory.directory_date || 'not extracted',directory_name:directory.name,plan_ids:directory.plan_ids,source_states:directory.states,specialty:r.kind==='facility'?'Hospital':'PDF provider listing'})),truncated:matches.length>15,pdf:true,directory};
}
export function pdfMatches(selection,plans){
 return new Map(plans.map(plan=>[plan.id,selection?.directory_pdf && plan.year===2027 && selection.source_states?.includes(plan.state) && selection.plan_ids.includes(plan.cms_id)?[{
  name:selection.name,detail:selection.office+(selection.phone?' · Phone '+selection.phone:'')+' · '+selection.directory_name+' · PDF page '+selection.page+' · Directory dated '+selection.directory_date,
  status:'2027 PDF listing — confirm current participation',restrictions:selection.restrictions,source_url:selection.source_url,
 }]:[]]));
}
