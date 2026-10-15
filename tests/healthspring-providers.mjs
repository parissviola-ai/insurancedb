import assert from 'node:assert/strict';
import fs from 'node:fs';
import {healthspringSuggestions,pdfMatches} from '../docs/healthspring-providers.js';
const root=new URL('../docs/',import.meta.url);
const manifest=JSON.parse(fs.readFileSync(new URL('data/healthspring-directory-index.json',root)));
assert.equal(manifest.directories.length,38);assert(manifest.directories.every(d=>d.status==='Indexed'));
const original=globalThis.fetch;let requests=0;
globalThis.fetch=async url=>{requests++;const file=String(url).split('?')[0].replace(/^\.\//,'');return {ok:true,json:async()=>JSON.parse(fs.readFileSync(new URL(file,root)))};};
assert.equal((await healthspringSuggestions('Carolinas','facility','LA')).unsupported,true);
assert.equal((await healthspringSuggestions('Hospital','facility','FL')).needsDirectory,true);
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
const hmo=(await healthspringSuggestions('1952622805','provider','NC','provider-pharmacy-directory-north-carolina-hmo')).options[0];
assert(hmo);assert.equal(pdfMatches(hmo,plans).get('correct').length,0);
const florida=manifest.directories.find(d=>d.states.includes('FL'));
assert((await healthspringSuggestions('Medical','facility','FL',florida.id)).pdf);
globalThis.fetch=original;
console.log('PDF provider checks passed: local lookup, names/NPI, source pages, state/segment/year isolation and unverified status.');
