const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const{calendarEntries,calendarWeeks,eventsOn}=await import('data:text/javascript;base64,'+Buffer.from(fs.readFileSync(__dirname+'/calendar_layout.js','utf8')).toString('base64'));
 const tasks=[{id:'period',title:'주간 경계',start:'2026-11-08',due:'2026-11-12'},{id:'deadline',title:'기한만',due:'2026-11-10'},{id:'done',status:'완료',start:'2026-11-01',due:'2026-11-30'},{id:'undated'}];
 const entries=calendarEntries(tasks,[]);assert.equal(entries.length,2);assert.equal(entries.find(e=>e.recordId==='deadline').start,'2026-11-10');assert.equal(eventsOn(entries,'2026-11-09').length,1);
 const segments=calendarWeeks('2026-11',entries).flatMap(w=>w.segments).filter(e=>e.recordId==='period');assert.equal(segments.length,2);assert(segments[0].continuesAfter&&segments[1].continuesBefore);
 const many=calendarEntries(Array.from({length:5},(_,i)=>({id:String(i),title:'겹침',start:'2026-11-09',due:'2026-11-12'})),[]);const week=calendarWeeks('2026-11',many).find(w=>w.dates[0]==='2026-11-09');assert.equal(week.segments.length,2);assert.equal(week.overflow[0],3);assert.equal(eventsOn(many,'2026-11-10').length,5);
 const leap=calendarWeeks('2028-02',[]);assert(leap.flatMap(w=>w.dates).includes('2028-02-29'));
 console.log('PASS: genuine date ranges, due-only date, completed/undated omission, week continuation, overlapping counts, leap day.');
})();
