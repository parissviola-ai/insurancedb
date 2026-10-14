import assert from 'node:assert/strict';
import {providers} from '../docs/provider.js';
const base='https://fhir.devoted.com/fhir/';
const resources={
 'Practitioner/person':{resourceType:'Practitioner',id:'person',name:[{text:'Test Provider'}]},
 'Location/selected':{resourceType:'Location',id:'selected',address:{state:'NC',text:'Selected office'}},
 'Location/other':{resourceType:'Location',id:'other',address:{state:'NC',text:'Other office'}}
};
globalThis.fetch=async url=>{let d=resources[String(url).slice(base.length)];if(String(url).includes('PractitionerRole?'))d={resourceType:'Bundle',entry:[{resource:{id:'role',active:true,period:{start:'2027-01-01',end:'2027-12-31'},extension:[{url:'https://example.org/network-reference',valueReference:{reference:'Organization/network'}}],location:[{reference:'Location/other'}]}}]};assert(d,'Unexpected query '+url);return {ok:true,json:async()=>d};};
const plans=[{id:'plan',network:[{reference:'Organization/network'}]}];
const selected=await providers('Test Provider',plans,new AbortController().signal,{personId:'person',locationId:'selected',manual:false});
assert.equal(selected.matches.get('plan').length,0,'Different office must not match');
const other=await providers('Test Provider',plans,new AbortController().signal,{personId:'person',locationId:'other',manual:false});
assert.equal(other.matches.get('plan').length,1);
assert.equal(other.matches.get('plan')[0].detail,'Other office');
const wrongNetwork=await providers('Test Provider',[{id:'plan',network:[{reference:'Organization/different'}]}],new AbortController().signal,{personId:'person',locationId:'other',manual:false});
assert.equal(wrongNetwork.matches.get('plan').length,0);
console.log('Provider identity, exact office and network isolation passed');

const wrongState=await providers('Test Provider',[{...plans[0],state:'FL'}],new AbortController().signal,{personId:'person',locationId:'other',manual:false});assert.equal(wrongState.matches.get('plan').length,0);
