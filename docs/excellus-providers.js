let pending;
export async function excellusSuggestions(term,kind,state){
 if(state!=='NY')return {options:[],pdf:true,unsupported:true};
 if(!pending)pending=fetch('./data/excellus-providers.json?v=excellus-2027').then(r=>{if(!r.ok)throw Error('Excellus PDF directory unavailable');return r.json();}).catch(e=>{pending=null;throw e;});
 const data=await pending,words=term.toLowerCase().trim().split(/\s+/);
 const matches=data.rows.filter(r=>r.kind===kind&&(!/^\d{10}$/.test(term))&&words.every(w=>r.name.toLowerCase().includes(w)));
 return {pdf:true,truncated:matches.length>15,options:matches.slice(0,15).map(r=>({...r,personId:r.locationId,directory_pdf:true,directory_name:'Excellus 2027 Medicare Blue Choice directory',directory_date:data.directory_date,source_url:data.url+'#page='+r.page,source_states:['NY'],plan_ids:data.plan_ids,specialty:kind==='facility'?'PDF facility listing':'PDF provider listing'}))};
}
