import {preparedPlan} from './website-coverage.js';
import {rankPlans,priorityKeys} from './ranking.js';
import {workbook} from './excel.js';

export const benefits=[['premium','Monthly premium'],['dental','Dental / year'],['otc','OTC / quarter'],['moop','Medical maximum / year'],['specialist','Specialist / visit'],['hospital','Hospital / 7-day stay'],['vision','Eyewear / year'],['hearing','Advanced hearing aid / aid'],['transportation','Transportation rides / year']];
const money=value=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(value);
const priority=value=>({0:'Not a priority',1:'Low',3:'Medium',5:'High'})[value] || 'Not a priority';
const finite=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0;
const date=value=>value?new Date(value).toLocaleString():'Unverified';

export function comparisonPlans(livePlans,inventory){
  return livePlans.map(live=>{
    const saved=preparedPlan(live,inventory);
    const extracted=live.document_data;
    const verified=extracted&&extracted.carrier===live.carrier&&extracted.official_id===live.official_id&&extracted.year===live.year&&extracted.state===live.state;
    const documents=[...(saved?.documents || []),...(verified?extracted.documents:[])].map(d=>({...d})).filter((d,i,all)=>all.findIndex(x=>x.url===d.url)===i);
    const metrics={};
    for(const [key,value] of Object.entries(saved?.benefit_metrics || {})){
      if(!finite(value.amount))continue;
      const document=documents.find(d=>value.source_url?.split('#')[0]===d.url);
      metrics[key]={...value,origin:'Matched source document',source_retrieved_at:document?.retrieved_at || saved.verified_on || ''};
    }
    if(verified)for(const [key,value] of Object.entries(extracted.benefit_metrics || {}))if(finite(value.amount))metrics[key]={...value,origin:'Official plan PDF'};
    if(verified)for(const key of Object.keys(extracted.benefit_unavailable || {}))delete metrics[key];
    // Public shopping data belongs to this exact returned record; it need not
    // borrow a CMS segment or benefits from a similar-sounding imported plan.
    for(const [key,value] of Object.entries(live.shopping_metrics || {}))if(benefits.some(([k])=>k===key)&&finite(value.amount)&&value.source_url)metrics[key]={...value,origin:'Public shopping response',source_retrieved_at:live.checked_at};
    if(finite(live.premium))metrics.premium={amount:live.premium,period:'month',notes:live.premium_notes || 'Monthly plan premium only. Part B and other costs still apply.',source_url:live.source_url,origin:'Public shopping response',source_retrieved_at:live.checked_at};
    return {...live,documents,benefit_metrics:metrics,benefit_unavailable:{...saved?.benefit_unavailable,...(verified?extracted.benefit_unavailable:{})},benefit_review_notes:{...saved?.benefit_review_notes,...(verified?extracted.benefit_review_notes:{})},
      ma_only:typeof live.has_drug_coverage==='boolean'?!live.has_drug_coverage:Boolean(saved?.ma_only),special_needs:Boolean(live.special_needs || saved?.special_needs),
      prepared_match:Boolean(saved),prepared_source_date:saved?.verified_on || '',provider_search_url:saved?.provider_search_url,
      scope_note:saved?.scope_note || '',drug_costs:saved?.drug_costs};
  });
}
export function visibleRanked(plans,weights,options={}){
  const shown=plans.filter(p=>(!options.carrier || p.carrier===options.carrier)&&(!options.business || p.business===options.business)&&(options.includeSpecial || !p.special_needs));
  const medical=rankPlans(shown.filter(p=>p.business==='Medicare Advantage'),weights,options.needsDrugs);
  const other=shown.filter(p=>p.business!=='Medicare Advantage').map(plan=>({plan,score:null,reason:'Different product type — compare separately'}));
  return [...medical,...other];
}
export function coverageLabel(check){
  if(check.status==='listed_in_network')return 'Listed in plan network';
  if(check.status==='network_candidates')return 'Network matches — choose office';
  if(check.status==='dated_directory_listing')return 'Listed in dated directory';
  if(check.status==='directory_candidates')return 'Possible directory matches';
  if(check.status==='no_drug_benefit')return 'No prescription coverage';
  if(check.status==='not_connected')return 'Not checked — connection needed';
  if(check.status==='unavailable')return 'Check unavailable';
  if(check.status==='not_applicable')return 'Not applicable';
  if(check.status==='review_required' && check.matches?.length){
    const tier=check.matches[0].detail?.match(/Tier ([^ ·]+)/)?.[1];
    return (check.result_type==='formulary_listing'?'Formulary match':'Possible drug matches')+(tier?' · Tier '+tier:'');
  }
  if(check.status==='pending')return 'Checking…';
  return 'Not verified';
}
function summary(checks,requested){
  if(!requested)return 'Not requested';
  if(!checks?.length)return 'Checking…';
  if(checks.length===1)return coverageLabel(checks[0]);
  const listed=checks.filter(c=>c.status==='listed_in_network').length;
  if(listed)return `${listed} of ${checks.length} listed in plan network`;
  const found=checks.filter(c=>c.matches?.length).length;
  if(found)return `${found} of ${checks.length} have matches — open details`;
  if(checks.every(c=>c.status==='no_drug_benefit'))return 'No prescription coverage';
  if(checks.every(c=>c.status==='not_applicable'))return 'Not applicable';
  return 'Not verified — open details';
}

export function exportSheets(state,ranked,weights){
  const location=state.data.location || {};
  const intake=[['Field','Value'],['Candidate name (complete offline)',''],['Additional notes (complete offline)',''],['Export generated',new Date().toISOString()],
    ['Search mode','Public carrier websites'],['ZIP',location.zip],['County',location.county_name],['State',location.state],['Year',location.year],
    ['Carrier filter',state.filters.carrier || 'All returned carriers'],['Product filter',state.filters.business || 'All returned products'],['Special-needs plans included',state.filters.includeSpecial?'Yes — eligibility review required':'No'],
    ['Medications',state.context.medications.map(s=>s.label || s.name).join('\n') || 'None'],['Providers / facilities',state.context.providers.map(s=>s.label || s.name || s.term).join('\n') || 'None'],
    ...priorityKeys.map(key=>[key+' priority',priority(weights[key])]),['Ranking scope','Relative benefit amounts for comparable Medicare Advantage plans only. Special-needs plans are not ranked; standalone Part D plans are separate.'],
    ['Missing values','Unverified, never treated as zero. Pharmacy costs and current provider participation require confirmation.'],['Data freshness','Shopping retrieval and matched document dates are separate. Checking a carrier site does not refresh imported benefit documents.'],
    ['Privacy','Generated locally. Add candidate names and review notes only after downloading. No member identifiers are collected.']];
  const rows=[['Carrier','Plan','Official plan ID','Year','Product','Benefit match / 100','Ranking status',...benefits.map(([,label])=>label),'OTC annual equivalent','Medication review','Provider review','Shopping source','Shopping checked','Matched benefit documents','Reviewer choice (offline)','Reviewer notes (offline)']];
  const sources=[['Carrier','Plan','Official plan ID','Benefit','Amount','Period','Conditions','Source','Source type','Source retrieved']];
  const coverage=[['Carrier','Plan','Official plan ID','Check','Entered value','Check status','Message','Candidate','Office / drug detail','Restrictions','Source','Source date','Plan-listed tier cost','Cost conditions','Cost source','Follow-up notes (offline)']];
  for(const {plan:p,score,reason} of ranked){
    const checks=state.coverage.get(p.id);
    rows.push([p.carrier,p.name,p.official_id,p.year,p.business,score===null?'Unranked':Math.round(score),score===null?reason:'Relative benefit match only',
      ...benefits.map(([k])=>p.business==='Part D'&&k!=='premium'?'Not applicable — drug-only plan':p.benefit_metrics[k]?.amount ?? p.benefit_unavailable[k] ?? 'Unverified'),p.benefit_metrics.otc?p.benefit_metrics.otc.amount*4:'Unverified',
      summary(checks?.medications,state.context.medications.length),summary(checks?.providers,state.context.providers.length),p.source_url,p.checked_at,p.documents.map(d=>d.kind+': '+d.url+' (retrieved '+(d.retrieved_at || 'unverified')+')').join('\n'),'','']);
    for(const [key,label] of benefits){const m=p.benefit_metrics[key];sources.push([p.carrier,p.name,p.official_id,label,m?.amount ?? 'Unverified',m?.period || '',m?.notes || p.benefit_unavailable[key] || p.benefit_review_notes[key] || 'Unverified',m?.source_url || '',m?.origin || '',m?.source_retrieved_at || '']);}
    for(const [kind,selections] of [['medications',state.context.medications],['providers',state.context.providers]]){
      const values=checks?.[kind] || selections.map(s=>({kind:kind==='medications'?'Medication':s.kind==='facility'?'Facility':'Provider',query:s.label || s.name || s.term,status:'pending',message:'Check pending or unavailable — unverified',matches:[]}));
      for(const check of values){if(!check.matches.length)coverage.push([p.carrier,p.name,p.official_id,check.kind,check.query,check.status,check.message,'','','',p.review_sources?.[kind==='medications'?'medication':'provider'] || p.source_url,'','','','','']);
        for(const m of check.matches)coverage.push([p.carrier,p.name,p.official_id,check.kind,check.query,check.status,check.message,m.name,m.detail || '',m.restrictions || '',m.source_url,m.source_date || '',m.cost?.display || 'Unverified',m.cost?['Tier schedule only — not a verified prescription quote',m.cost_context?.conditions,m.cost_context?.deductible_note].filter(Boolean).join(' · '):'',m.cost?.source_url || '','']);}
    }
  }
  const carriers=[['Carrier','Status','Returned plans','Message','Official source','Plans checked','Website entry checked']];
  for(const c of state.data.carriers)carriers.push([c.carrier,c.status,c.plan_count,c.message,c.source_url,c.checked_at || 'Not verified',c.source_checked_at || '']);
  return [{name:'Intake and priorities',rows:intake},{name:'Plan comparison',rows},{name:'Coverage review',rows:coverage},{name:'Benefit sources',rows:sources},{name:'Carrier status',rows:carriers}];
}
function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function link(parent,text,url){try{const u=new URL(url);if(u.protocol!=='https:'||u.username||u.password)return;const a=node('a',text);a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';parent.append(a);}catch{}}
function metricValue(key,m){return key==='transportation'?m.amount+' one-way rides':money(m.amount);}
function metricCell(parent,plan,key,documentStatus){if(plan.business==='Part D'&&key!=='premium'){parent.append(node('span','Not applicable — drug-only plan'));return;}const m=plan.benefit_metrics[key];
  if(m){link(parent,metricValue(key,m),m.source_url);if(key==='otc')parent.append(node('small',money(m.amount*4)+' annual equivalent; four quarters, no rollover assumed.'));if(m.notes)parent.append(node('small',m.notes));}
  else parent.append(node('span',plan.benefit_unavailable[key] || documentStatus || 'Unverified'));
}
function renderChecks(container,checks,plan,kind,requested){
  container.replaceChildren();if(!requested){container.append(node('p','Not requested'));return;}
  if(!checks?.length){container.append(node('p','Checking connected sources…'));return;}
  for(const check of checks){const section=node('div',undefined,'check');section.append(node('strong',(check.display_name || check.query)+': '+coverageLabel(check)),node('p',check.message));
    const evidence=node('details');evidence.append(node('summary','Sources and conditions'));
    for(const match of check.matches){section.append(node('p',match.name===check.display_name?(match.detail || match.name):match.name+(match.detail?' · '+match.detail:'')));if(match.restrictions)evidence.append(node('p',match.restrictions));if(match.cost){section.append(node('p','Plan-listed tier cost: '+match.cost.display+' (not an exact prescription quote)'));if(match.cost_context?.conditions)section.append(node('small',match.cost_context.conditions));if(match.cost_context?.deductible_note)section.append(node('small',match.cost_context.deductible_note));link(section,'Review cost-sharing rules',match.cost.source_url);}
      if(match.source_date)evidence.append(node('small','Source retrieved: '+date(match.source_date)));link(evidence,'Review source',match.source_url);}
    if(check.search_partial)evidence.append(node('p','Directory search was partial. Only the displayed positive listings were found.'));
    if(check.matches.length)section.append(evidence);
    if(!check.matches.length)link(section,'Check on carrier site',plan.review_sources?.[kind] || plan.source_url);container.append(section);
  }
}
export function websiteComparison(container,data,plans,context,form,options={}){
  const state={data,plans,context,coverage:new Map(),filters:{carrier:'',business:'',includeSpecial:form.elements.special_needs.checked}};
  const controls=node('div',undefined,'grid two');const carrierLabel=node('label','Compare carriers');const carrierFilter=node('select');carrierFilter.setAttribute('aria-label','Compare carriers');carrierFilter.append(new Option('All returned carriers',''));
  for(const name of [...new Set(plans.map(p=>p.carrier))].sort())carrierFilter.append(new Option(name,name));carrierLabel.append(carrierFilter);
  const productLabel=node('label','Compare product type');const productFilter=node('select');productFilter.setAttribute('aria-label','Compare product type');productFilter.append(new Option('All returned products',''));
  for(const type of [...new Set(plans.map(p=>p.business))].sort())productFilter.append(new Option(type,type));productLabel.append(productFilter);controls.append(carrierLabel,productLabel);
  const comparison=node('section');const detailList=node('section');container.append(controls,comparison,detailList);
  let destroyed=false;let bulkRunning=false;let documentProgress=null;const loading=new Set();const queued=new Set();const failures=new Map();
  let observer;let ranked=[];let weights={};let coverageCells=new Map();let detailCells=new Map();const openDetails=new Set();
  function paintCoverage(p){const checks=state.coverage.get(p.id),cells=coverageCells.get(p.id),details=detailCells.get(p.id);
    if(cells){cells.drugs.textContent=summary(checks?.medications,context.medications.length);cells.people.textContent=summary(checks?.providers,context.providers.length);}
    if(details){renderChecks(details.drugs,checks?.medications,p,'medication',context.medications.length);renderChecks(details.people,checks?.providers,p,'provider',context.providers.length);}
  }
  async function pull(p,refresh=false){
    if(destroyed||loading.has(p.id)||!options.loadDocuments)return;
    queued.delete(p.id);loading.add(p.id);failures.delete(p.id);render();
    try{await options.loadDocuments(p,refresh);}catch(error){if(!destroyed)failures.set(p.id,error.message || 'PDF pull unavailable.');}
    finally{loading.delete(p.id);if(!destroyed)render();}
  }
  async function loadPlanDocuments(targets){
    if(destroyed||bulkRunning||!options.loadDocuments)return;
    const queue=targets.filter(p=>['Aetna','UnitedHealthcare / AARP'].includes(p.carrier));
    if(!queue.length)return;
    bulkRunning=true;for(const p of queue)queued.add(p.id);documentProgress={done:0,total:queue.length};render();
    const worker=async()=>{while(queue.length&&!destroyed){const p=queue.shift();await pull(p);documentProgress.done++;if(!destroyed)render();}};
    try{await Promise.all([worker(),worker()]);}finally{bulkRunning=false;if(!destroyed)render();}
  }
  function render(){
    if(destroyed)return;
    observer?.disconnect();coverageCells=new Map();detailCells=new Map();comparison.replaceChildren();detailList.replaceChildren();
    weights=Object.fromEntries(priorityKeys.map(k=>[k,Number(form.elements['weight_'+k].value)]));state.filters.includeSpecial=form.elements.special_needs.checked;
    ranked=visibleRanked(plans,weights,{...state.filters,needsDrugs:context.medications.length>0});
    comparison.append(node('h3',`${plans.length} plans returned`),node('p',`${ranked.length} shown with the current carrier, product and special-needs filters. Change priorities above to update rankings without another website search.`));
    const top=ranked.filter(r=>r.score!==null && Math.abs(r.score-ranked.find(x=>x.score!==null)?.score)<0.0001);
    if(top.length)comparison.append(node('p','Top benefit match'+(top.length>1?'es (tie)':'')+': '+top.map(r=>r.plan.name).join('; '),'recommendation'));
    else comparison.append(node('p','No ranking available for the current priorities. Review missing amounts or change priorities.'));
    comparison.append(node('p','Rankings compare selected benefits, not overall suitability. Missing amounts stay unverified. Special-needs and Part D plans are not ranked against other medical plans.'));
    const wrap=node('div',undefined,'comparison-scroll');const table=node('table');table.append(node('caption',`${data.location?.year || ''} public website plans for ZIP ${data.location?.zip || ''}`));
    const head=node('tr');for(const title of ['Carrier / plan','Benefit match',...benefits.map(([,label])=>label),'Medications','Providers / facilities','Details']){const th=node('th',title);th.scope='col';head.append(th);}const thead=node('thead');thead.append(head);table.append(thead);const body=node('tbody');
    for(const {plan:p,score,reason} of ranked){const tr=node('tr');if(top.some(t=>t.plan.id===p.id))tr.className='top-match';const label=node('th',p.name);label.scope='row';label.append(node('small',p.carrier+' · '+p.official_id+' · '+p.business));tr.append(label,node('td',score===null?reason:Math.round(score)+' / 100'));
      for(const [key] of benefits){const td=node('td');metricCell(td,p,key,loading.has(p.id)?'Reading plan documents…':queued.has(p.id)?'Waiting for plan documents…':failures.has(p.id)?'Document check failed — open details':undefined);tr.append(td);}
      const drugs=node('td'),people=node('td');coverageCells.set(p.id,{drugs,people});tr.append(drugs,people);
      const action=node('td');const a=node('a','View details');a.href='#website-plan-'+encodeURIComponent(p.id);a.addEventListener('click',event=>{event.preventDefault();const details=document.getElementById('website-plan-'+p.id);details.open=true;details.scrollIntoView({block:'nearest',behavior:'smooth'});});action.append(a);tr.append(action);body.append(tr);
      const details=node('details');details.id='website-plan-'+p.id;details.open=openDetails.has(p.id);details.addEventListener('toggle',()=>{if(details.open)openDetails.add(p.id);else openDetails.delete(p.id);});details.append(node('summary',p.carrier+' · '+p.name),node('p',p.official_id+' · '+p.business+' · '+p.year));
      if(p.special_needs)details.append(node('p','Special-needs eligibility must be confirmed. This plan is not ranked.'));
      link(details,'Official shopping source',p.source_url);details.append(node('p','Shopping checked: '+date(p.checked_at),'metadata'));
      details.append(node('p',p.document_data?.documents?.some(d=>d.identity_verified)?'Official PDF sources are attached. Amounts below retain their document dates.':p.prepared_match?'Benefits below use matched official documents. Their dates may differ from today’s shopping check.':'Only verified shopping values are available. Other benefits remain unverified.'));
      const list=node('dl');for(const [key,title] of benefits){list.append(node('dt',title));const dd=node('dd');metricCell(dd,p,key,loading.has(p.id)?'Reading plan documents…':queued.has(p.id)?'Waiting for plan documents…':undefined);const m=p.benefit_metrics[key];if(m)dd.append(node('small',m.origin+' · retrieved '+date(m.source_retrieved_at)));if(!m&&p.benefit_review_notes[key])dd.append(node('small',p.benefit_review_notes[key]));list.append(dd);}details.append(list);
      for(const doc of p.documents){const row=node('p');link(row,({benefits:'Summary of Benefits',evidence:'Evidence of Coverage',formulary:'Formulary',provider_directory:'Provider directory',prior_authorization:'Prior Authorization Criteria',step_therapy:'Step Therapy Criteria',formulary_deletions:'Formulary deletions',changes:'Annual Notice of Changes',highlights:'Benefit highlights',stars:'Star ratings',enrollment:'Enrollment form',vendor_information:'Vendor information sheet'})[doc.kind] || doc.label || doc.kind,doc.url);row.append(node('small',doc.retrieved_at?' · PDF retrieved '+date(doc.retrieved_at):doc.source_date?' · carrier updated '+doc.source_date:' · linked from the carrier plan page'));details.append(row);}
      if(p.review_sources?.medication)link(details,p.carrier==='HealthSpring'?'Check prescriptions on HealthSpring':'Check prescriptions on carrier site',p.review_sources.medication);
      if(p.review_sources?.pharmacy){details.append(document.createTextNode(' · '));link(details,p.carrier==='HealthSpring'?'Choose pharmacy on HealthSpring':'Find a pharmacy on carrier site',p.review_sources.pharmacy);details.append(node('small',' These tools open on the carrier site. Enter drug and pharmacy choices there; exact quotes are not imported into this comparison.'));}
      if(['Aetna','UnitedHealthcare / AARP'].includes(p.carrier)&&options.loadDocuments){const pullButton=node('button',loading.has(p.id)?'Reading official PDFs…':p.document_data?'Refresh official PDFs':'Pull official PDFs');pullButton.type='button';pullButton.disabled=loading.has(p.id);pullButton.addEventListener('click',()=>pull(p,Boolean(p.document_data)));details.append(pullButton);if(failures.has(p.id))details.append(node('p',failures.get(p.id)));if(p.document_data){details.append(node('p',p.document_data.documents.some(d=>d.identity_verified)?'Official PDFs read and cached on this computer.':'Documents linked; extraction needs review.'));if(p.document_data.issues?.length){const issues=node('details');issues.append(node('summary','Documents needing review'));for(const issue of p.document_data.issues)issues.append(node('p',issue));details.append(issues);}}}
      if(p.benefit_notice)details.append(node('p',p.benefit_notice));
      if(p.scope_note)details.append(node('p',p.scope_note));const drugDetails=node('div'),providerDetails=node('div');details.append(node('h4','Medication review'),drugDetails,node('h4','Provider / facility review'),providerDetails);detailCells.set(p.id,{drugs:drugDetails,people:providerDetails});detailList.append(details);paintCoverage(p);
    }
    table.append(body);wrap.append(table);const scroll=node('div',undefined,'comparison-top-scroll');scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label','Scroll carrier comparison horizontally');const track=node('div');scroll.append(track);
    scroll.addEventListener('scroll',()=>{wrap.scrollLeft=scroll.scrollLeft;});wrap.addEventListener('scroll',()=>{scroll.scrollLeft=wrap.scrollLeft;});const size=()=>{track.style.width=table.scrollWidth+'px';};observer=new ResizeObserver(size);observer.observe(table);requestAnimationFrame(size);
    const docTargets=ranked.map(r=>r.plan).filter(p=>['Aetna','UnitedHealthcare / AARP'].includes(p.carrier));
    if(docTargets.length&&options.loadDocuments){const bulk=node('button',bulkRunning?'Reading plan documents…':'Pull official PDFs for displayed Aetna / UHC plans');bulk.type='button';bulk.disabled=bulkRunning;bulk.addEventListener('click',()=>loadPlanDocuments(docTargets));comparison.append(bulk,node('p','Reads summaries, coverage documents and formularies. Shared PDFs are reused from the local cache. Large provider directories stay linked for review.','metadata'));}
    if(documentProgress){const progress=node('p',bulkRunning?`Filling Aetna / UHC benefits automatically: ${documentProgress.done} of ${documentProgress.total} plans checked. Amounts appear as documents are read.`:`Automatic benefit checks complete: ${documentProgress.done} of ${documentProgress.total} plans checked.`, 'metadata');progress.setAttribute('role','status');comparison.append(progress);if(failures.size)comparison.append(node('p',`${failures.size} plan document checks could not finish. Open plan details to review or retry.`));}
    comparison.append(node('p','Scroll across to compare benefits.','comparison-scroll-hint'),scroll,wrap);
    const download=node('button','Export comparison to Excel');download.type='button';download.disabled=!ranked.length;
    download.addEventListener('click',()=>{const blob=workbook(exportSheets(state,ranked,weights));const url=URL.createObjectURL(blob);const a=node('a');a.href=url;a.download=`carrier-comparison-${data.location?.year || ''}-${data.location?.zip || ''}.xlsx`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);});comparison.append(download,node('p','Export includes the displayed plans, priorities, benefit sources, medication/provider checks and every carrier status. Add candidate names and reviewer notes offline.','metadata'));
  }
  carrierFilter.addEventListener('change',()=>{state.filters.carrier=carrierFilter.value;render();});productFilter.addEventListener('change',()=>{state.filters.business=productFilter.value;render();});
  const targets=[...priorityKeys.map(k=>form.elements['weight_'+k]),form.elements.special_needs];for(const target of targets)target.addEventListener('change',render);
  render();return {loadDocumentsAutomatically:()=>loadPlanDocuments(plans),updateCoverage(id,checks){state.coverage.set(id,checks);const p=plans.find(p=>p.id===id);if(p)paintCoverage(p);},updateDocuments(id,result){const index=plans.findIndex(p=>p.id===id);const live=data.plans.find(p=>p.id===id);if(index<0||!live||result.carrier!==live.carrier||result.official_id!==live.official_id||result.year!==live.year||result.state!==live.state||result.zip!==data.location.zip||result.county!==data.location.county)throw new Error('PDF response did not match this plan and location.');live.document_data=result;live.review_sources={...live.review_sources,...result.review_sources};Object.assign(plans[index],comparisonPlans([live],options.inventory || {plans:[]})[0]);render();},destroy(){destroyed=true;observer?.disconnect();for(const target of targets)target.removeEventListener('change',render);}};
}
