const state=document.querySelector('#document-state'),county=document.querySelector('#document-county'),query=document.querySelector('#document-query'),type=document.querySelector('#document-type'),results=document.querySelector('#document-results'),gaps=document.querySelector('#document-gaps');
const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
const link=(parent,label,url)=>{if(!url?.startsWith('https://www.healthspring.com/'))return;const a=el('a',label);a.href=url;a.target='_blank';a.rel='noopener noreferrer';parent.append(a);};
let catalog,formularies;
function updateCounty(){county.replaceChildren(new Option('All counties',''));county.disabled=!state.value;if(state.value){const names=[...new Set(catalog.documents.filter(d=>d.state===state.value).flatMap(d=>d.counties || []))].sort();for(const name of names)county.append(new Option(name,name));}render();}
function render(){
 const needle=query.value.trim().toLowerCase();
 const rows=catalog.documents.filter(d=>(!state.value || d.state===state.value)&&(!county.value || d.business==='Part D'||d.counties?.includes(county.value))&&(!type.value || d.business===type.value)&&(!needle || `${d.name} ${d.cms_id || ''}`.toLowerCase().includes(needle)));
 results.replaceChildren();document.querySelector('#document-count').textContent=rows.length+' document entries · '+catalog.unique_pdf_count+' unique EOC PDFs collected across 15 target states';
 const wrap=el('div');wrap.className='comparison-scroll';const table=el('table'),head=el('tr');
 for(const label of ['State','Plan / segment','Counties','Evidence of Coverage','Formulary','Review status'])head.append(el('th',label));const thead=el('thead');thead.append(head);table.append(thead);const body=el('tbody');
 for(const d of rows){const row=el('tr');row.append(el('td',d.state),el('td',d.name+'\n'+(d.cms_id || 'Part D — regional CMS linkage requires review')),el('td',d.counties?.join(', ') || 'Statewide document'));
  const evidence=el('td');link(evidence,'Open 2027 EOC',d.url);row.append(evidence);
  const drug=el('td'),mapping=formularies.plan_links[d.state+':'+d.cms_id];
  if(d.business==='Part D'){const sources=formularies.source_entries.filter(f=>f.state===d.state&&f.name===d.name);for(const f of sources)link(drug,'Official 2027 formulary (shared PDP document)',f.url);if(!sources.length)drug.append(el('span','Unverified'));}
  else if(mapping?.urls.length)for(const url of mapping.urls)link(drug,'Open matched 2027 formulary',url);
  else drug.append(el('span',mapping?.status || 'Unverified'));
  row.append(drug);const review=el('td',d.verification_status==='Verified'?'Document checked; coverage still requires review':d.issues.join('; '));
  if(d.issues.some(i=>i.includes('county lists differ')))review.append(el('p','EOC page counties: '+d.source_counties.join(', ')));
  for(const note of d.source_notes || [])review.append(el('p',note));
  row.append(review);body.append(row);
 }
 table.append(body);wrap.append(table);results.append(wrap);if(!rows.length)results.append(el('p','No source documents match these filters. This does not establish exclusion.'));
 gaps.replaceChildren();const missing=catalog.missing_eocs.filter(m=>!state.value || m.state===state.value);
 if(missing.length){const detail=el('details');detail.append(el('summary','CMS plans with document checks still pending ('+missing.length+')'));for(const m of missing)detail.append(el('p',m.state+' · '+m.cms_id+' · '+m.name+' — '+m.reason));gaps.append(detail);}
}
try {
 [catalog,formularies]=await Promise.all(['healthspring-documents','healthspring-formularies'].map(async name=>{const r=await fetch('./data/'+name+'.json?v=healthspring-15-docs');if(!r.ok)throw Error('fetch');return r.json();}));
 for(const code of catalog.states)state.append(new Option(code,code));state.addEventListener('change',updateCounty);county.addEventListener('change',render);query.addEventListener('input',render);type.addEventListener('change',render);render();
} catch {document.querySelector('#document-count').textContent='Documents could not be loaded. Refresh to retry.';}
