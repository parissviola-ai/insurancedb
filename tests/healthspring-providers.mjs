import assert from 'node:assert/strict';
import fs from 'node:fs';
import {healthspringSuggestions,pdfMatches} from '../docs/healthspring-providers.js';
const data=JSON.parse(fs.readFileSync(new URL('../docs/data/healthspring-providers.json',import.meta.url)));
const original=globalThis.fetch;let requests=0;
globalThis.fetch=async()=>{requests++;return {ok:true,json:async()=>data};};
assert.equal((await healthspringSuggestions('Carolinas','facility','FL')).unsupported,true);assert.equal(requests,0);
const hospital=(await healthspringSuggestions('Carolinas Medical','facility','NC')).options.find(o=>o.office.includes('1000 Blythe'));
assert(hospital);assert.equal(hospital.phone,'(704) 355-2000');assert.equal(hospital.page,1011);
const doctor=(await healthspringSuggestions('1952622805','provider','NC')).options[0];
assert.equal(doctor.name,'Wingler, Cody A');assert.equal(doctor.page,21);
assert((await healthspringSuggestions('Cody Wingler','provider','NC')).options.some(o=>o.npi==='1952622805'));
const plans=[{id:'correct',cms_id:'H7849-113-001',state:'NC',year:2027},
 {id:'other-segment',cms_id:'H7849-113-003',state:'NC',year:2027},
 {id:'old-year',cms_id:'H7849-113-001',state:'NC',year:2026}];
const matches=pdfMatches(hospital,plans);assert.equal(matches.get('correct').length,1);assert.equal(matches.get('other-segment').length,0);assert.equal(matches.get('old-year').length,0);
assert.match(matches.get('correct')[0].status,/confirm current participation/);assert.match(matches.get('correct')[0].source_url,/#page=1011/);
globalThis.fetch=original;
console.log('PDF provider checks passed: local lookup, names/NPI, source pages, state/segment/year isolation and unverified status.');
