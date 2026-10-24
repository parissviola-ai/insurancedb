// Search selections stay in memory and are shared by both result views.
let read;
export function registerSearchContext(reader){read=reader;}
export function readSearchContext(){
  if(!read)throw new Error('Search inputs are still loading. Please retry.');
  return read();
}
