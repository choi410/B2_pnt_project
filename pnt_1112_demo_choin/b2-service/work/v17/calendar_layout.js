const dateText=d=>d.toISOString().slice(0,10);
export function calendarEntries(tasks,meetings){
 return [...tasks.filter(t=>t.status!=='완료'&&t.due).map(t=>({id:'task/'+t.id,recordId:t.id,type:'task',title:t.title,start:t.start&&t.start<=t.due?t.start:t.due,end:t.due})),...meetings.filter(m=>m.date).map(m=>({id:'meeting/'+m.id,recordId:m.id,type:'meeting',title:m.title,start:m.date,end:m.date}))];
}
export const eventsOn=(entries,date)=>entries.filter(e=>e.start<=date&&e.end>=date);
export function calendarWeeks(month,entries){
 const[y,m]=month.split('-').map(Number),first=new Date(Date.UTC(y,m-1,1)),offset=(first.getUTCDay()+6)%7,days=new Date(Date.UTC(y,m,0)).getUTCDate();
 return Array.from({length:Math.ceil((offset+days)/7)},(_,week)=>{
  const dates=Array.from({length:7},(_,day)=>dateText(new Date(Date.UTC(y,m-1,1-offset+week*7+day))));
  const lanes=[],segments=entries.filter(e=>e.start<=dates[6]&&e.end>=dates[0]).map(e=>({...e,from:e.start<dates[0]?0:dates.indexOf(e.start),to:e.end>dates[6]?6:dates.indexOf(e.end)})).sort((a,b)=>a.from-b.from||(b.to-b.from)-(a.to-a.from)||a.id.localeCompare(b.id)).map(e=>{
   let lane=lanes.findIndex(end=>end<e.from);if(lane<0)lane=lanes.length;lanes[lane]=e.to;
   return {...e,lane,continuesBefore:e.start<dates[0],continuesAfter:e.end>dates[6]};
  });
  return {dates,segments:segments.filter(e=>e.lane<2),overflow:dates.map((_,day)=>segments.filter(e=>e.lane>=2&&e.from<=day&&e.to>=day).length)};
 });
}
