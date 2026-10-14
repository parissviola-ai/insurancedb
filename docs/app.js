import {providers} from './provider.js?v=15-states';
import {rankPlans,priorityKeys} from './ranking.js';
import {workbook} from './excel.js';
import {medicationPicker} from './medications.js';
import {providerPicker} from './provider-picker.js?v=typeahead-letters';
const form=document.querySelector('#search'); const results=document.querySelector('#results');
const state=document.querySelector('#state');state.append(new Option('Select state',''));for(const code of ['NC','SC','GA','FL','AL','TN','VA','KY','LA','TX','OH','PA','DE','MI','NY'])state.append(new Option(code,code));
const business=form.elements.business;business.replaceChildren(new Option('Medicare Advantage','Medicare Advantage'));
form.elements.carrier.value='Devoted Health';form.elements.carrier.readOnly=true;
const county=form.elements.county;
function el(tag,text,cls) {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function link(parent,label,url) {if(!/^https:\/\//.test(url))return;const n=el('a',label);n.href=url;n.target='_blank';n.rel='noopener noreferrer';parent.append(n);}
let dataPromise;let request;
async function data() {
  if(!dataPromise) dataPromise=Promise.all(['plans','zip-counties','formularies'].map(async name=> {
    const r=await fetch('./data/'+name+'.json');if(!r.ok)throw new Error('Prepared plan data could not be loaded. Please retry.');return r.json();
  })).catch(e=>{dataPromise=null;throw e;});
  return dataPromise;
}
const picker=medicationPicker(data);
const providerInput=providerPicker();
function terms(value) {return value.split('\n').map(s=>s.trim()).filter(Boolean);}
function drugMatches(plan,term,formularies) {
  const hits=[];
  for(const doc of plan.documents.filter(d=>d.kind==='formulary')) {
    const rows=formularies[doc.url]?.rows || [];
    const selection=comparisonState?.drugSelections.find(i=>i.label===term);
    for(const row of rows.filter(r=>selection && !selection.manual ? r.name===selection.name : r.name.toLowerCase().includes((selection?.name || term).toLowerCase())).slice(0,5)) hits.push({
      name:row.name,detail:`Tier ${row.tier} · PDF page ${row.page}`,status:'Review required',
      restrictions:row.restrictions || '',
      cost:plan.drug_costs?.tiers?.[row.tier] || null, cost_context:plan.drug_costs || {},
      source_url:doc.url+'#page='+row.page});
  }
  return hits;
}
function check(parent,kind,term,matches,message) {
  const section=el('div',undefined,'check');section.append(el('strong',kind+': '+term));
  if(!matches.length)section.append(el('p',message || 'Unverified — no matching source record. This does not establish exclusion.','badge unverified'));
  for(const m of matches) {
    section.append(el('p',m.name+' · '+m.detail),el('span',m.status,'badge unverified'));
    if(m.restrictions) section.append(el('p',m.restrictions));
    if(kind==='Medication') {
      if(m.cost) {
        section.append(el('p',`Plan-listed Tier ${m.detail.match(/Tier (\d+)/)?.[1] || ''} ${m.cost.type}: ${m.cost.display}`));
        section.append(el('small','30-day supply · network retail pharmacy · initial coverage · standard schedule without Extra Help'));
        section.append(el('p',m.cost_context.conditions,'metadata'));
        section.append(el('p',m.cost_context.deductible_note,'metadata'));
        link(section,'Check plan cost-sharing rules',m.cost.source_url);
      } else section.append(el('p','Copay unverified — review plan cost-sharing rules.','metadata'));
      const note=el('p');
      link(note,'check the official formulary',m.source_url);section.append(note);
    } else link(section,'Source record',m.source_url);
  }
  parent.append(section);
}
let comparisonState=null;
const priorityLabel=value=>({0:'Not a priority',1:'Low',3:'Medium',5:'High'})[value] || 'Not a priority';
const money=value=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(value);
function renderComparison() {
  if(!comparisonState)return;
  const {container,plans,drugs,people,providerStatus}=comparisonState;
  const weights={};for(const key of priorityKeys)weights[key]=Number(form.elements['weight_'+key].value);
  const ranked=rankPlans(plans,weights,drugs.length>0);
  container.replaceChildren(el('h2','Compare plans'));
  const best=ranked.filter(r=>r.score!==null && Math.abs(r.score-ranked[0].score)<0.0001);
  if(best.length)container.append(el('p',`Top benefit match${best.length>1?'es (tie)':''}: ${best.map(r=>r.plan.name).join('; ')}. Based only on your selected benefit priorities.`,'recommendation'));
  else container.append(el('p','No ranking available. Select priorities or review missing benefit amounts.'));
  container.append(el('p','Scores compare selected allowances, in-network medical costs, and plan premiums within these results. Dental reimbursement rules differ. Medication, provider, and eligibility checks must be completed before choosing a plan. Missing amounts are unverified, never treated as $0.'));
  const wrap=el('div',undefined,'comparison-scroll');const table=el('table');table.append(el('caption','2027 plans for your selected county'));
  const head=el('tr');for(const name of ['Plan','Benefit match','Monthly premium','Dental / year','OTC','Medical maximum / year','Specialist / visit','Hospital / 7-day stay','Eyewear / year','Advanced hearing aid / aid','Transportation / year','Medications','Providers / facilities','Details']){const th=el('th',name);th.scope='col';head.append(th);}const thead=el('thead');thead.append(head);table.append(thead);
  const body=el('tbody');
  for(const {plan,score,reason} of ranked){
    const row=el('tr');if(score!==null && best.some(r=>r.plan.id===plan.id))row.className='top-match';
    const name=el('th',plan.name);name.scope='row';row.append(name,el('td',score===null?reason:`${Math.round(score)} / 100`));
    for(const key of ['premium','dental','otc','moop','specialist','hospital','vision','hearing','transportation']){
      const cell=el('td');const metric=plan.benefit_metrics?.[key];
      if(metric){link(cell,key==='transportation'?metric.amount+' one-way rides'+(metric.amount===0?' (not covered)':''):money(metric.amount)+(key==='otc'?' / quarter':''),metric.source_url);if(key==='otc')cell.append(el('small',money(metric.amount*4)+' annual equivalent'));if(key!=='premium' && key!=='otc')cell.append(el('small',metric.notes));}
      else cell.append(el('span','Unverified'));
      row.append(cell);
    }
    row.append(el('td',drugs.length?(plan.ma_only?'MA only — separate drug plan required':'Formulary matches require review'):'Not assessed'));
    row.append(el('td',people.length?(providerStatus.get(plan.id) || 'Checking directory…'):'Enter a provider or facility name or NPI to check network participation.'));
    const detail=el('td');const a=el('a','View details');a.href='#plan-'+plan.id;a.addEventListener('click',()=>{const d=document.querySelector('#plan-'+plan.id);if(d)d.open=true;});detail.append(a);row.append(detail);body.append(row);
  }
  table.append(body);wrap.append(table);
  const topScroll=el('div',undefined,'comparison-top-scroll');
  topScroll.tabIndex=0;topScroll.setAttribute('role','region');
  topScroll.setAttribute('aria-label','Scroll plan comparison horizontally');
  const track=el('div');topScroll.append(track);
  container.append(el('p','Scroll across to compare all benefits.','comparison-scroll-hint'),topScroll,wrap);
  topScroll.addEventListener('scroll',()=>{if(wrap.scrollLeft!==topScroll.scrollLeft)wrap.scrollLeft=topScroll.scrollLeft;});
  wrap.addEventListener('scroll',()=>{if(topScroll.scrollLeft!==wrap.scrollLeft)topScroll.scrollLeft=wrap.scrollLeft;});
  const sizeTrack=()=>{track.style.width=table.scrollWidth+'px';topScroll.scrollLeft=wrap.scrollLeft;};
  const observer=new ResizeObserver(sizeTrack);observer.observe(table);
  if(container.scrollObserver)container.scrollObserver.disconnect();container.scrollObserver=observer;
  requestAnimationFrame(sizeTrack);
  const exportButton=el('button','Export comparison to Excel');exportButton.type='button';
  exportButton.disabled=!plans.length;
  exportButton.addEventListener('click',()=>exportComparison(ranked,weights));container.append(exportButton);
  container.append(el('p','Export contains the current search and priorities. Add the candidate name, notes, and reviewer decision in Excel after downloading.','metadata'));
  container.append(el('small','Score: weighted, relative benefit amounts. Higher allowances and ride counts, and lower medical costs and premiums score higher; equal values tie. Only plans with amounts for every selected priority are scored. Special-needs plans are not ranked; compare them manually after confirming eligibility.'));
}
function exportComparison(ranked,weights) {
  const s=comparisonState;
  const intake=[['Field','Value'],['Candidate name (complete offline)',''],['Additional notes (complete offline)',''],
    ['Export generated',new Date().toISOString()],['Plan data snapshot',s.snapshot],['Plan year','2027'],
    ['ZIP',s.zip],['County',s.county],['State',s.state],['Carrier','Devoted Health'],['Line of business','Medicare Advantage'],
    ['Drug cost assumptions','30-day supply; network retail pharmacy; initial coverage; standard schedule without Extra Help. Exact coverage, pharmacy participation, price, and deductible completion are not verified.'],
    ['Medications entered',s.drugs.join('\n') || 'None'],['Providers / facilities entered',s.people.join('\n') || 'None'],
    ['Dental priority',priorityLabel(weights.dental)],['OTC priority',priorityLabel(weights.otc)],['Lower premium priority',priorityLabel(weights.premium)],
    ['Medical maximum priority',priorityLabel(weights.moop)],['Specialist priority',priorityLabel(weights.specialist)],['Hospital priority',priorityLabel(weights.hospital)],['Vision priority',priorityLabel(weights.vision)],['Hearing priority',priorityLabel(weights.hearing)],['Transportation priority',priorityLabel(weights.transportation)],
    ['Special-needs plans included',s.includeSpecial?'Yes — eligibility must be confirmed':'No'],
    ['Ranking scope','Benefit amounts, selected in-network medical costs, and plan premium only. Medication/provider coverage and eligibility require separate review.'],
    ['Missing data','Unverified, never treated as zero. OTC annual equivalent assumes four quarters, not rollover.'],
    ['Privacy','Generated locally. Candidate name and notes are blank and entered only in the downloaded workbook.']];
  const rows=[['Plan','Plan ID','Benefit match / 100','Ranking status','Monthly premium','Dental / year','Dental conditions','OTC / quarter','OTC annual equivalent','Medical maximum / year','Specialist / visit','Hospital / 7-day stay','Eyewear / year','Advanced hearing aid / aid','Transportation one-way rides / year','Other benefit conditions','Medication review','Provider review','Eligibility','Summary of Benefits','Evidence of Coverage','Formulary','Reviewer choice (offline)','Reviewer notes (offline)']];
  for(const r of ranked){const p=r.plan,m=p.benefit_metrics || {},doc=kind=>p.documents.find(d=>d.kind===kind)?.url || 'Not available';
    rows.push([p.name,p.locator,r.score===null?'Unranked':Math.round(r.score),r.score===null?r.reason:'Relative benefit match only',
      m.premium?money(m.premium.amount):'Unverified',m.dental?money(m.dental.amount):'Unverified',m.dental?.notes || 'Unverified',
      m.otc?money(m.otc.amount):'Unverified',m.otc?money(m.otc.amount*4):'Unverified',
      ...['moop','specialist','hospital','vision','hearing','transportation'].map(k=>m[k]?(k==='transportation'?m[k].amount+' one-way rides':money(m[k].amount)):'Unverified'),
      ['moop','specialist','hospital','vision','hearing','transportation'].map(k=>k+': '+(m[k]?.notes || 'Unverified')).join('\n'),
      s.drugs.length?(p.ma_only?'Separate Part D needed':'Unverified — check exact drugs and restrictions'):'Not assessed',
      s.people.length?(s.providerStatus.get(p.id) || 'Pending — directory lookup not complete'):'Enter a provider or facility name or NPI to check network participation.',
      p.special_needs?'Special-needs eligibility must be confirmed':'Confirm enrollment eligibility',doc('benefits'),doc('evidence'),doc('formulary'),'','']);
  }
  const coverage=[['Plan','Check','Entered value','Candidate match','Office or drug detail','Review status','Restrictions / conditions','Source','Plan-listed tier cost','Cost assumptions','Cost source','Deductible conditions','Follow-up call notes (complete offline)']];
  for(const c of s.coverage){
    if(!c.matches.length)coverage.push([c.plan,c.kind,c.term,'','',c.partial?'Incomplete search — unverified':'No match — unverified','','']);
    for(const m of c.matches)coverage.push([c.plan,c.kind,c.term,m.name,m.detail,c.partial?'Partial search — review required':m.status,m.restrictions || 'Check the official formulary for restrictions.',m.source_url,m.cost?.display || (c.kind==='Medication'?'Unverified':'Not applicable'),
      m.cost?'30-day network retail; initial coverage; without Extra Help. '+m.cost_context.conditions:'',m.cost?.source_url || '',m.cost_context?.deductible_note || '']);
  }
  for(const p of s.plans)for(const term of s.people)if(!s.coverage.some(c=>c.plan===p.name && ['Provider','Facility'].includes(c.kind) && c.term===term))coverage.push([p.name,'Provider',term,'','','Lookup pending or unavailable — unverified','','']);
  const a=el('a');const url=URL.createObjectURL(workbook([{name:'Intake and priorities',rows:intake},{name:'Plan comparison',rows},{name:'Coverage review',rows:coverage}]));
  a.href=url;a.download=`plan-comparison-2027-${s.zip}.xlsx`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
for(const key of priorityKeys)form.elements['weight_'+key].addEventListener('change',renderComparison);
let locationRevision=0;
async function updateCounty(autoState=true) {
  const revision=++locationRevision;
  const zip=form.elements.zip.value.trim();const chosen=county.value;
  county.replaceChildren(new Option(/^\d{5}$/.test(zip)?'Loading counties…':'Enter a five-digit ZIP',''));
  if(!/^\d{5}$/.test(zip))return;
  try {
    const [,zipMap]=await data();if(revision!==locationRevision)return;
    const zipStates=[...new Set((zipMap[zip] || []).map(c=>c.state))];
    if(autoState && zipStates.length===1 && state.value!==zipStates[0]) {
      state.value=zipStates[0];state.dispatchEvent(new Event('change'));return;
    }
    if(autoState && zipStates.length>1) {
      state.value='';state.dispatchEvent(new Event('change'));return;
    }
    if(zipStates.length>1 && !state.value){county.replaceChildren(new Option('Choose a state for this ZIP',''));return;}
    const counties=(zipMap[zip] || []).filter(c=>c.state===state.value);
    county.replaceChildren(new Option(counties.length?'Select county':'ZIP not found in selected state',''));
    for(const c of counties)county.append(new Option(c.name,c.code));
    county.value=counties.length===1?counties[0].code:(counties.some(c=>c.code===chosen)?chosen:'');
  } catch(e) {if(revision===locationRevision)county.replaceChildren(new Option('County lookup unavailable — retry search',''));}
}
form.elements.zip.addEventListener('input',()=>updateCounty(true));
state.addEventListener('change',()=>{request?.abort();county.value='';updateCounty(false);comparisonState?.container.scrollObserver?.disconnect();comparisonState=null;results.replaceChildren(el('p','State changed. Search again to compare plans.'));});
form.addEventListener('submit',async event=>{
  event.preventDefault();comparisonState?.container.scrollObserver?.disconnect();comparisonState=null;if(request)request.abort();request=new AbortController();const signal=request.signal;
  const zip=form.elements.zip.value.trim();const chosen=county.value;
  const drugSelections=picker.getSelections();
  const providerSelections=providerInput.getSelections();
  const drugs=drugSelections.map(i=>i.label),people=providerSelections.map(i=>i.label);
  results.setAttribute('aria-busy','true');results.replaceChildren(el('p','Searching…'));
  try {
    if(providerInput.hasPending())throw new Error('Select or add the provider you typed, or clear the provider field before searching.');
    if(picker.hasPending())throw new Error('Add the medication you typed, or clear the medication field before searching.');
    if(!/^\d{5}$/.test(zip))throw new Error('Enter a five-digit ZIP code.');
    if(people.length>3 || drugs.length>10)throw new Error('Search up to 3 providers/facilities and 10 medications at a time.');
    const [inventory,zipMap,formularies]=await data();if(signal.aborted)return;
    const counties=(zipMap[zip] || []).filter(c=>c.state===state.value);county.replaceChildren(new Option('Select county',''));
    for(const c of counties)county.append(new Option(c.name,c.code));
    const selected=counties.find(c=>c.code===chosen) || (counties.length===1?counties[0]:null);
    county.value=selected?.code || '';
    if(!selected) {
      results.replaceChildren(el('h2','Choose your location'),el('p',counties.length?'This ZIP crosses county boundaries. Select your county, then search again.':'This ZIP is not in the prepared lookup for the selected state. No plan availability inferred.'));
      if(counties.length)county.focus();return;
    }
    const plans=inventory.plans.filter(p=>p.state===state.value && p.counties.includes(selected.code) && (form.elements.special_needs.checked || !p.special_needs));
    results.replaceChildren(el('h2',`${plans.length} plans · ${selected.name} County`),el('p',`Official 2027 county mapping. Data refreshed ${inventory.snapshot.retrieved_at.slice(0,10)}. Confirm eligibility and enrollment requirements.`));
    if(!plans.length)results.append(el('p','Devoted’s published mapping lists no 2027 plans for this county.'));
    const comparison=el('section',undefined,'panel');results.append(comparison);
    comparisonState={container:comparison,plans,drugs,drugSelections,people,providerSelections,providerStatus:new Map(),coverage:[],zip,county:selected.name,state:state.value,snapshot:inventory.snapshot.retrieved_at,includeSpecial:form.elements.special_needs.checked};renderComparison();
    const sections=new Map();
    for(const plan of plans) {
      const card=el('article',undefined,'plan');card.append(el('span',plan.business,'badge'),el('h3',plan.name),
        el('p',`${plan.carrier} · ${plan.year} · ${selected.name}, ${state.value} · ZIP ${zip}`),el('p','Monthly premium: '+plan.premium));
      card.append(el('small','Premium extracted from the Summary of Benefits. Other costs and conditions apply.'));
      for(const doc of plan.documents) {const row=el('p');link(row,({benefits:'Summary of Benefits',evidence:'Evidence of Coverage',formulary:'2027 Drug List'})[doc.kind],doc.url);card.append(row);}
      for(const drug of drugs){const matches=drugMatches(plan,drug,formularies);check(card,'Medication',drug,matches);comparisonState.coverage.push({plan:plan.name,kind:'Medication',term:drug,matches});}
      const providerSection=el('div');card.append(providerSection);sections.set(plan.id,providerSection);
      link(card,'Official provider search',`https://www.devoted.com/search-providers/#filterType=all&p=${encodeURIComponent(plan.name.includes('(PPO')?'PPO':'HMO')}&q=&s=${encodeURIComponent(state.value)}&y=2027`);
      const details=el('details');details.id='plan-'+plan.id;details.append(el('summary',plan.name+' · Plan details'),card);results.append(details);
    }
    if(people.length && plans.length) {
      const status=el('p','Checking live provider directory…');results.prepend(status);
      try {
        for(const term of people) {
          const found=await providers(term,plans,signal,providerSelections.find(p=>p.label===term));if(signal.aborted)return;
          for(const plan of plans) {
            const matches=found.matches.get(plan.id);
            comparisonState.coverage.push({plan:plan.name,kind:providerSelections.find(p=>p.label===term)?.kind==='facility'?'Facility':'Provider',term,matches,partial:found.truncated});
            check(sections.get(plan.id),providerSelections.find(p=>p.label===term)?.kind==='facility'?'Facility':'Provider',term,matches,found.truncated?'Unverified — search incomplete; use the official directory.':undefined);
            const previous=comparisonState.providerStatus.get(plan.id);
            const uncertain=found.truncated || !matches.length || previous?.includes('Unverified');
            comparisonState.providerStatus.set(plan.id,uncertain?'Unverified — review directory':'Matches found — verify all offices');
          }
          renderComparison();
          if(found.truncated)results.append(el('p','Provider search was limited. Missing matches remain unverified; search by NPI or full name.'));
        }
        status.textContent='Live provider lookup complete. Confirm the exact office and current participation.';
      } catch(e) {
        if(signal.aborted)return;
        for(const plan of plans)comparisonState.providerStatus.set(plan.id,'Directory unavailable — unverified');renderComparison();
        status.textContent='Live provider lookup unavailable. Use the official provider search links; no coverage inferred.';
      }
    }
  } catch(e) {if(!signal.aborted)results.replaceChildren(el('p',e.message));}
  finally {if(!signal.aborted)results.setAttribute('aria-busy','false');}
});
data().catch(()=>{});
