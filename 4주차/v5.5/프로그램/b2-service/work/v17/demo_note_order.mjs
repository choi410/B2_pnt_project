const keys=['summary','decisions','candidates'];
// Keep distinct details, but do not render an identical title twice.
export function followupText(item){
 const title=(item.title||'').trim(),description=(item.description||'').trim();
 const normalized=text=>text.replace(/\s+/g,' ').trim();
 return title&&description&&normalized(title)===normalized(description)?description:[title,description].filter(Boolean).join('\n');
}
// Preserve editorial order without changing AI classifications.
export function orderedNotes(bundle){
 const rows=keys.flatMap(key=>(bundle[key]||[]).map((item,index)=>({key,index,item,id:item.note_id||(key==='candidates'?'candidate-'+item.id:key+'-'+index)})));
 const byId=new Map(rows.map(row=>[row.id,row]));
 return [...new Set([...(bundle.note_order||[]),...rows.map(row=>row.id)])].map(id=>byId.get(id)).filter(Boolean);
}
export function prepareNotes(bundle){
 const rows=orderedNotes(bundle),out={...bundle,note_order:rows.map(row=>row.id)};
 for(const key of keys)out[key]=(bundle[key]||[]).map((item,index)=>({...item,note_id:rows.find(row=>row.key===key&&row.index===index).id}));
 return out;
}
export function insertNote(bundle,after,id){
 const out=prepareNotes(bundle),index=out.summary.length;
 const anchor=after&&orderedNotes(out).find(row=>row.key===after.key&&row.index===after.index);
 const at=anchor?out.note_order.indexOf(anchor.id)+1:out.note_order.length;
 out.summary.push({note_id:id,text:'',evidence:[]});out.note_order.splice(at,0,id);
 return {bundle:out,selection:{key:'summary',index}};
}
export function deleteNote(bundle,key,index){
 const out=prepareNotes(bundle),id=out[key][index]?.note_id;
 out[key]=out[key].filter((_,i)=>i!==index);out.note_order=out.note_order.filter(x=>x!==id);
 return out;
}
