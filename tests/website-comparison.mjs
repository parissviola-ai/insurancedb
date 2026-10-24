import assert from 'node:assert/strict';
import {comparisonPlans,visibleRanked,exportSheets,coverageLabel} from '../docs/website-comparison.js';
import {workbook} from '../docs/excel.js';
const saved={id:'saved',carrier:'Devoted Health',locator:'H1234-001-000-2027',year:2027,state:'NC',name:'Fixture saved',ma_only:false,
  documents:[{kind:'benefits',url:'https://example.com/benefits.pdf',retrieved_at:'2026-10-15T00:00:00Z'}],
  benefit_metrics:{premium:{amount:50,period:'month',source_url:'https://example.com/benefits.pdf#page=2'},dental:{amount:1000,period:'year',notes:'Network conditions',source_url:'https://example.com/benefits.pdf#page=3'},otc:{amount:25,period:'quarter',source_url:'https://example.com/benefits.pdf#page=4'}},
  benefit_unavailable:{hearing:'Not covered — source conditions apply'},verified_on:'2026-10-15'};
const live={id:'live',carrier:'Devoted Health',official_id:'H1234-001-000',year:2027,state:'NC',name:'Fixture live',business:'Medicare Advantage',premium:0,source_url:'https://example.com/shop',checked_at:'2026-10-24T00:00:00Z'};
const [matched,unmatched,wrongYear,noSegment]=comparisonPlans([live,{...live,id:'other',carrier:'Aetna'},{...live,id:'old',year:2026},{...live,id:'short',official_id:'H1234-001'}],{plans:[saved]});
assert.equal(matched.benefit_metrics.premium.amount,0);assert.equal(saved.benefit_metrics.premium.amount,50);
assert.equal(matched.benefit_metrics.premium.source_retrieved_at,live.checked_at);
assert.equal(matched.benefit_metrics.dental.source_retrieved_at,saved.documents[0].retrieved_at);
assert.equal(matched.benefit_metrics.dental.amount,1000);
for(const p of [unmatched,wrongYear,noSegment]){assert.equal(p.prepared_match,false);assert.equal(p.benefit_metrics.dental,undefined);}
const [shopping]=comparisonPlans([{...live,shopping_metrics:{moop:{amount:0,period:'year',source_url:live.source_url},dental:{amount:-1,source_url:live.source_url}}}],{plans:[]});
assert.equal(shopping.benefit_metrics.moop.amount,0);assert.equal(shopping.benefit_metrics.dental,undefined);
const snp={...matched,id:'snp',special_needs:true};const pdp={...matched,id:'pdp',business:'Part D'};const medicalOnly={...matched,id:'ma',ma_only:true};
let ranked=visibleRanked([matched,unmatched,snp,pdp],{dental:5},{includeSpecial:true});
assert.notEqual(ranked.find(r=>r.plan.id==='live').score,null);
assert.equal(ranked.find(r=>r.plan.id==='other').score,null);assert.equal(ranked.find(r=>r.plan.id==='snp').score,null);assert.equal(ranked.find(r=>r.plan.id==='pdp').score,null);
assert(!visibleRanked([matched,snp],{premium:5}).some(r=>r.plan.id==='snp'));
assert.equal(visibleRanked([medicalOnly],{premium:5},{needsDrugs:true})[0].score,null);
assert(visibleRanked([matched],{}).every(r=>r.score===null));
assert(visibleRanked([matched,unmatched],{premium:5},{carrier:'Aetna'}).every(r=>r.plan.carrier==='Aetna'));
assert(visibleRanked([matched,pdp],{premium:5},{business:'Part D'}).every(r=>r.plan.business==='Part D'));
const state={data:{location:{zip:'28202',county_name:'Mecklenburg',state:'NC',year:2027},carriers:[{carrier:'Aetna',status:'unavailable',plan_count:0,message:'Failed, not no plans',source_url:live.source_url}]},
  context:{medications:[{name:'Fixture medication'}],providers:[{term:'Fixture provider'}]},filters:{includeSpecial:true},coverage:new Map()};
ranked=visibleRanked([matched],{premium:5},{includeSpecial:true});
const sheets=exportSheets(state,ranked,{premium:5});assert.equal(sheets.length,5);
assert.equal(sheets.find(s=>s.name==='Plan comparison').rows.length,2);
assert.equal(sheets.find(s=>s.name==='Carrier status').rows[1][1],'unavailable');
assert(sheets.find(s=>s.name==='Coverage review').rows.some(row=>row.includes('pending')));
for(const sheet of sheets)for(const row of sheet.rows)assert.equal(row.length,sheet.rows[0].length,`Column count ${sheet.name}`);
const blob=workbook(sheets);assert(blob.size>5000);
console.log('Website comparison passed: exact joins, live zero premium, independent source dates, missing-data/SNP/PDP ranking, filters and five-sheet coverage-aware export.');

assert.equal(coverageLabel({status:'listed_in_network'}),'Listed in plan network');
assert.equal(coverageLabel({status:'dated_directory_listing'}),'Listed in dated directory');
assert.equal(coverageLabel({status:'network_candidates'}),'Network matches — choose office');
assert.equal(coverageLabel({status:'not_connected'}),'Not checked — connection needed');
assert.equal(coverageLabel({status:'no_drug_benefit'}),'No prescription coverage');
assert.equal(coverageLabel({status:'review_required',result_type:'formulary_listing',matches:[{detail:'Tier 3 · PDF page 23'}]}),'Formulary match · Tier 3');
console.log('Concise coverage labels preserve live, dated, candidate, unconnected and no-drug-benefit distinctions.');
const pdfResult={carrier:live.carrier,official_id:live.official_id,year:2027,state:'NC',documents:[{kind:'benefits',url:'https://example.com/new.pdf',identity_verified:true}],
  benefit_metrics:{dental:{amount:2000,period:'year',source_url:'https://example.com/new.pdf#page=3',source_retrieved_at:'2026-10-24T01:00:00Z'}},
  benefit_unavailable:{vision:'Every 2 years — not an annual allowance'},benefit_review_notes:{vision:'$150 every 2 years'}};
const withPDF=comparisonPlans([{...live,document_data:pdfResult}],{plans:[saved]})[0];
assert.equal(withPDF.benefit_metrics.dental.amount,2000);assert.equal(withPDF.benefit_metrics.premium.amount,0);
assert.equal(withPDF.benefit_metrics.vision,undefined);assert.equal(withPDF.benefit_metrics.dental.origin,'Official plan PDF');
const wrongPDF=comparisonPlans([{...live,document_data:{...pdfResult,official_id:'H9999-999-999'}}],{plans:[saved]})[0];
assert.equal(wrongPDF.benefit_metrics.dental.amount,1000);
console.log('PDF comparison updates preserve source binding, live premium and nonannual benefit exclusions.');
const drugLive={...live,business:'Part D',drug_details:[{label:'Drug deductible',description:'$700 per year; tier rules apply.',source_url:live.source_url}]};
const drugPlan=comparisonPlans([drugLive],{plans:[]})[0];
assert.equal(drugPlan.drug_details[0].description,'$700 per year; tier rules apply.');
const drugSheets=exportSheets(state,[{plan:drugPlan,score:null,reason:'Compare separately'}],{});
const comparisonSheet=drugSheets.find(s=>s.name==='Plan comparison');
const detailIndex=comparisonSheet.rows[0].indexOf('Drug coverage details');
assert(detailIndex>=0);assert(comparisonSheet.rows[1][detailIndex].includes('$700'));
for(const sheet of drugSheets)for(const row of sheet.rows)assert.equal(row.length,sheet.rows[0].length);
console.log('Part D drug benefit details remain source-linked in comparison and Excel.');
