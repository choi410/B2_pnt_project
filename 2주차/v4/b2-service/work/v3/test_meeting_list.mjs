import assert from 'node:assert/strict';
import {sortedMeetings,nextMeetingSort,meetingNeedsStatus,meetingSections,meetingProgress} from './meeting_list.js';
const projects=[{id:'p-z',name:'가온'},{id:'p-a',name:'한빛'}];
const people=[{id:'u-z',name:'김양일'},{id:'u-a',name:'진효창'}];
const meetings=[
 {id:'a',title:'점검 10',project_id:'p-z',author:'u-a',date:'2026-11-02',created_at:'2026-11-12'},
 {id:'b',title:'점검 2',project_id:'p-a',author:'u-z',date:'2026-11-09',created_at:'2026-11-11'},
 {id:'c',title:'점검 1',project_id:'p-z',author:'u-a',date:'2026-11-06',created_at:'2026-11-10',points:[{text:'속도 검토'}]},
 {id:'d',title:'회의일 미정',project_id:'p-z',author:'u-z',date:'',created_at:'2026-11-13'},
];
const ids=options=>sortedMeetings(meetings,projects,people,options).map(m=>m.id);
assert.deepEqual(ids(),['b','c','a','d']);
assert.deepEqual(ids({sort:{key:'date',direction:'asc'}}),['a','c','b','d']);
assert.deepEqual(ids({sort:{key:'title',direction:'asc'}}),['c','b','a','d']);
assert.deepEqual(ids({sort:{key:'project',direction:'asc'}}),['c','a','d','b']);
assert.deepEqual(ids({sort:{key:'project',direction:'desc'}}),['b','c','a','d']);
assert.deepEqual(ids({sort:{key:'author',direction:'asc'}}),['b','d','c','a']);
assert.deepEqual(ids({projectId:'p-z',query:'속도',sort:{key:'title',direction:'desc'}}),['c']);
assert.deepEqual(meetings.map(m=>m.id),['a','b','c','d']);
// Sorting covers the whole filtered collection, so later pages keep the same order.
const many=Array.from({length:18},(_,i)=>({id:String(i),title:'검토 '+i,date:'2026-11-'+String(i+1).padStart(2,'0'),project_id:'p-z'})).reverse();
const ordered=sortedMeetings(many,projects,people,{query:'검토',sort:{key:'date',direction:'asc'}});
assert.deepEqual(ordered.slice(8,16).map(m=>m.date),Array.from({length:8},(_,i)=>'2026-11-'+String(i+9).padStart(2,'0')));
assert.deepEqual(nextMeetingSort({key:'date',direction:'desc'},'title'),{key:'title',direction:'asc'});
assert.deepEqual(nextMeetingSort({key:'title',direction:'asc'},'title'),{key:'title',direction:'desc'});
assert.deepEqual(nextMeetingSort({key:'title',direction:'desc'},'date'),{key:'date',direction:'desc'});
assert.equal(meetingNeedsStatus({analysis_state:'ready'}),false);
for(const analysis_state of ['queued','running','failed'])assert.equal(meetingNeedsStatus({analysis_state}),true);
assert.equal(meetingNeedsStatus({analysis_state:'ready',analysis_stale:true}),true);
console.log('Meeting sort, pagination, filtering and attention-state checks passed');

// Processing is independent of selected sort and pagination, with newest uploads first.
const inflight=[
 {...meetings[0],id:'run-old',analysis_state:'running',analysis_phase:'notes',date:'2020-01-01',created_at:'2026-11-12'},
 {...meetings[1],id:'wait-new',analysis_state:'queued',date:'2019-01-01',created_at:'2026-11-13'},
 {...meetings[2],id:'fail',analysis_state:'failed'},
];
for(const key of ['title','project','date','author']){
 const sections=meetingSections([...meetings,...inflight],projects,people,{sort:{key,direction:'asc'}});
 assert.deepEqual(sections.processing.map(m=>m.id),['wait-new','run-old']);
 assert(sections.registered.some(m=>m.id==='fail'));
 assert(!sections.registered.some(m=>['wait-new','run-old'].includes(m.id)));
}
assert.deepEqual(meetingSections(inflight,projects,people,{projectId:'p-z'}).processing.map(m=>m.id),['run-old']);
assert.equal(meetingSections(inflight,projects,people,{query:'없는 제목'}).processing.length,0);
const finished=inflight.map(m=>m.id==='wait-new'?{...m,analysis_state:'ready'}:m);
const sections=meetingSections([...meetings,...finished],projects,people);
assert.deepEqual(sections.processing.map(m=>m.id),['run-old']);
assert.equal(sections.registered.filter(m=>m.id==='wait-new').length,1);
assert.equal(meetingProgress({analysis_state:'queued'}).stage,'queued');
assert.equal(meetingProgress({analysis_state:'running',analysis_phase:'notes'}).stage,'analyzing');
assert.equal(meetingProgress({analysis_state:'running',analysis_phase:'combined:1/3'}).detail,'3개 구간 중 1개 분석 완료');
assert.equal(meetingProgress({analysis_state:'running',analysis_phase:'combined:3/3'}).stage,'applying');
assert.equal(meetingProgress({analysis_state:'running',analysis_phase:'combined:3/0'}).stage,'analyzing');
assert.equal(meetingProgress({analysis_state:'ready'}),null);
assert.equal(meetingProgress({analysis_state:'failed'}),null);
console.log('Processing section, state transitions and actual phase labels passed');
