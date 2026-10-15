let dataPromise;
export async function healthspringSuggestions(term,kind,state){
 if(state!=='NC')return {options:[],truncated:false,pdf:true,unsupported:true};
 if(!dataPromise)dataPromise=fetch('./data/healthspring-providers.json?v=healthspring-pdf').then(r=>{if(!r.ok)throw Error('PDF directory unavailable');return r.json();}).catch(e=>{dataPromise=null;throw e;});
 const data=await dataPromise;const words=term.toLowerCase().trim().split(/\s+/);
 const matches=data.rows.filter(r=>r.kind===kind&&(/^\d{10}$/.test(term)?r.npi===term:words.every(w=>r.name.toLowerCase().includes(w))));
 return {options:matches.slice(0,15).map(r=>({...r,personId:r.npi || r.locationId,directory_pdf:true,source_url:data.source_url+'#page='+r.page,directory_date:data.directory_date,plan_ids:data.plan_ids,specialty:r.kind==='facility'?'Hospital':'PDF provider listing'})),truncated:matches.length>15,pdf:true};
}
export function pdfMatches(selection,plans){
 return new Map(plans.map(plan=>[plan.id,selection?.directory_pdf && plan.year===2027 && plan.state==='NC' && selection.plan_ids.includes(plan.cms_id)?[{
  name:selection.name,detail:selection.office+(selection.phone?' · Phone '+selection.phone:'')+' · PDF page '+selection.page+' · Directory dated '+selection.directory_date,
  status:'2027 PDF listing — confirm current participation',restrictions:selection.restrictions,source_url:selection.source_url,
 }]:[]]));
}
