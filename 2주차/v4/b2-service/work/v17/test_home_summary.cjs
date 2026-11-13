const assert=require('node:assert/strict'),esbuild=require('esbuild');
const built=esbuild.buildSync({entryPoints:[__dirname+'/home_summary.js'],bundle:true,platform:'node',format:'cjs',write:false});
const mod={exports:{}};new Function('module','exports',built.outputFiles[0].text)(mod,mod.exports);
const{homeSummary,meetingFollowups}=mod.exports;
const meeting=(id,date,extra={})=>({id,date,project_id:'p1',registered_revision:1,revision:1,created_at:'2026-11-11',...extra});
const meetings=[meeting('new','2026-11-09'),meeting('old','2026-11-02',{created_at:'2026-11-12'}),meeting('middle','2026-11-05'),meeting('foreign','2026-11-10',{project_id:'p2'}),meeting('draft','2026-11-11',{registered_revision:null}),meeting('trash','2026-11-12',{deleted_at:'today'})];
const event=(id,mid,date,extra={})=>({id,meeting_id:mid,effective_date:date,review_state:'검토 전',business_state:'요청',after:id,...extra});
const groups=[
 {key:'speed',project_id:'p1',title:'압연 속도',events:[event('a','new','2026-11-09'),event('b','new','2026-11-10',{business_state:'확정'}),event('c','middle','2026-11-05'),event('excluded','new','2026-11-11',{review_state:'제외'}),event('superseded','new','2026-11-12',{superseded_by_revision:2}),event('deleted','trash','2026-11-13')]},
 {key:'cover',project_id:'p1',title:'점검 커버 개폐 방식',events:[event('d','old','2026-11-02')]},
 {key:'due',project_id:'p1',title:'장비 납품일',events:[event('e','middle','2026-11-05')]},
 {key:'foreign',project_id:'p2',title:'압연 속도',events:[event('f','foreign','2026-11-10')]}
];
const before=JSON.stringify({meetings,groups});
const home=homeSummary(meetings,groups,'p1');
assert.deepEqual(home.chronology.map(m=>m.id),['old','middle','new'],'Chronology uses meeting dates, not upload order');
assert.equal(home.latest.id,'new');assert.deepEqual(home.recent.map(x=>x.e.id),['b','e','d'],'One latest active record per subject keeps older distinct subjects visible');
assert.equal(home.recent[0].e.state,'결정');assert.equal(home.recent[0].e.date,'2026-11-10','Change date stays consistent with the history page');
assert.equal(JSON.stringify({meetings,groups}),before,'Read-only summaries never mutate stored records');
assert.equal(homeSummary(meetings,groups,'empty').latest,null);assert.equal(homeSummary(meetings,groups,'p2').recent.length,1);
const many=Array.from({length:9},(_,i)=>meeting('m'+i,'2026-11-'+String(i+1).padStart(2,'0')));
assert.deepEqual(homeSummary(many,[],'p1').chronology.map(m=>m.id),['m4','m5','m6','m7','m8'],'Only the latest five meetings appear in the compact flow');
const detail={revision:1,overview:{revision:1},reviewed_bundle:{candidates:[{kind:'업무',title:'도면 개정',description:'도면을 개정한다.'},{kind:'업무',description:'도면을 개정한다.'},{kind:'확인사항',description:'납기 미정'},{kind:'업무',title:'고객 공유'}]},ai_snapshot:{bundle:{candidates:[{kind:'업무',title:'AI가 잘못 추출한 초안'}]}}};
assert.deepEqual(meetingFollowups(detail).items.map(i=>i.text),['도면을 개정한다.','고객 공유'],'Use reviewed meeting actions; avoid title/description duplicates and raw AI drafts');
assert.deepEqual(meetingFollowups({...detail,revision:2}),{state:'stale',items:[]},'Do not show outdated actions as current');
assert.equal(meetingFollowups({revision:1}).state,'missing');
assert.deepEqual(meetingFollowups({...detail,reviewed_bundle:{candidates:[]}}),{state:'ready',items:[]},'No fallback to an older meeting or invented next goal');
console.log('PASS: dated meeting flow; latest distinct subjects; project/archive isolation; immutable sources; reviewed followups and stale revision protection.');
