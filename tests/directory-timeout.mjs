import assert from 'node:assert/strict';
import {providerSuggestions} from '../docs/provider.js';
const nativeTimer=globalThis.setTimeout;
globalThis.setTimeout=(fn,delay,...args)=>nativeTimer(fn,delay===20000?5:delay,...args);
globalThis.fetch=async (_url,{signal})=>({ok:true,json:()=>new Promise((resolve,reject)=>{signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true});})});
try {
 await assert.rejects(()=>providerSuggestions('1457924003',new AbortController().signal,'FL'),/Directory request timed out/);
 console.log('Slow response body is canceled and reported as a timeout, not exclusion');
} finally {globalThis.setTimeout=nativeTimer;}
