/* Minimal XLSX writer: strings are explicit inline strings, never spreadsheet formulas. */
const utf8=new TextEncoder();
const xml=s=>String(s ?? '').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g,'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const bytes=s=>utf8.encode(s);
function column(index){let s='';for(let n=index+1;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;}
function sheet(rows){return '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="1" width="38" customWidth="1"/><col min="2" max="24" width="26" customWidth="1"/></cols><sheetData>'+rows.map((row,i)=>'<row r="'+(i+1)+'">'+row.map((value,j)=>'<c r="'+column(j)+(i+1)+'" t="inlineStr"><is><t xml:space="preserve">'+xml(value)+'</t></is></c>').join('')+'</row>').join('')+'</sheetData></worksheet>';}
function crc32(data){let crc=0xffffffff;for(const b of data){crc^=b;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return (crc^0xffffffff)>>>0;}
function record(size,values){const a=new Uint8Array(size),v=new DataView(a.buffer);for(const [offset,value,width] of values)width===2?v.setUint16(offset,value,true):v.setUint32(offset,value,true);return a;}
function zip(files){const pieces=[],central=[];let offset=0,size=0;
for(const [path,text] of files){const name=bytes(path),data=bytes(text),crc=crc32(data);
const local=record(30,[[0,0x04034b50,4],[4,20,2],[6,0x800,2],[14,crc,4],[18,data.length,4],[22,data.length,4],[26,name.length,2]]);
pieces.push(local,name,data);
const directory=record(46,[[0,0x02014b50,4],[4,20,2],[6,20,2],[8,0x800,2],[16,crc,4],[20,data.length,4],[24,data.length,4],[28,name.length,2],[42,offset,4]]);
central.push(directory,name);size+=46+name.length;offset+=30+name.length+data.length;}
return new Blob([...pieces,...central,record(22,[[0,0x06054b50,4],[8,files.length,2],[10,files.length,2],[12,size,4],[16,offset,4]])],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});}
export function workbook(sheets){
const files=[['[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+sheets.map((s,i)=>'<Override PartName="/xl/worksheets/sheet'+(i+1)+'.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>').join('')+'</Types>'],
['_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'],
['xl/workbook.xml','<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+sheets.map((s,i)=>'<sheet name="'+xml(s.name)+'" sheetId="'+(i+1)+'" r:id="rId'+(i+1)+'"/>').join('')+'</sheets></workbook>'],
['xl/_rels/workbook.xml.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+sheets.map((s,i)=>'<Relationship Id="rId'+(i+1)+'" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet'+(i+1)+'.xml"/>').join('')+'</Relationships>']];
sheets.forEach((s,i)=>files.push(['xl/worksheets/sheet'+(i+1)+'.xml',sheet(s.rows)]));return zip(files);
}
