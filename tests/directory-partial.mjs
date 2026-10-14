import assert from 'node:assert/strict';
import {providerSuggestions} from '../docs/provider.js';
globalThis.fetch=async url=>{const u=new URL(url);let d;
if(u.pathname.endsWith('/Practitioner'))d={resourceType:'Bundle',entry:[{resource:{id:'test',name:[{text:'Test provider'}]}}]};
else if(u.pathname.endsWith('/PractitionerRole'))d={resourceType:'Bundle',entry:[{resource:{active:true,period:{start:'2027-01-01',end:'2027-12-31'},location:[{reference:'Location/missing'},{reference:'Location/valid'}]}}]};
else if(u.pathname.endsWith('/missing'))return {ok:false,status:404};
else d={resourceType:'Location',id:'valid',address:{state:'FL',text:'Valid office'}};
return {ok:true,json:async()=>d};};
const r=await providerSuggestions('Test Provider',new AbortController().signal,'FL');assert.equal(r.options.length,1);assert.equal(r.options[0].office,'Valid office');assert(r.unavailable && r.truncated);console.log('Failed office preserves valid suggestions and marks results incomplete');
