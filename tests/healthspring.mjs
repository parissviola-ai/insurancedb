import assert from 'node:assert/strict';
import {matchingYearPlans,healthspringMapping} from '../docs/healthspring.js';
const record=(id,year,end=`${year}-12-31`)=>({resourceType:'InsurancePlan',status:'active',
  identifier:[{value:id.replaceAll('-','_')+'_'+year+'0101'}],period:{start:`${year}-01-01`,end},
  network:[{reference:'Organization/network'}]});
const bundle=(...plans)=>({resourceType:'Bundle',entry:plans.map(resource=>({resource}))});
const id='H7849-113-001';
assert.equal(matchingYearPlans(bundle(record(id,2026)),id,2027).length,0);
assert.equal(matchingYearPlans(bundle(record('H7849-113-003',2027)),id,2027).length,0);
assert.equal(matchingYearPlans(bundle(record(id,2027,'2027-06-01')),id,2027).length,0);
assert.equal(matchingYearPlans(bundle(record(id,2027)),id,2027).length,1);
const old=globalThis.fetch;
globalThis.fetch=async url=>{assert.match(url,/H7849_113_001_20270101/);return {ok:true,json:async()=>bundle(record(id,2026))};};
assert.equal((await healthspringMapping({cms_id:id,year:2027})).status,'unverified');
globalThis.fetch=async()=>({ok:true,json:async()=>bundle(record(id,2027),record(id,2027))});
assert.equal((await healthspringMapping({cms_id:id,year:2027})).status,'unverified');
globalThis.fetch=async()=>({ok:true,json:async()=>bundle(record(id,2027))});
const result=await healthspringMapping({cms_id:id,year:2027});
assert.equal(result.status,'mapping-found');assert.match(result.message,/coverage remains unverified/);
globalThis.fetch=old;
console.log('HealthSpring checks passed: year/segment/period validation, historical rejection, ambiguity, and no automatic coverage claim.');
