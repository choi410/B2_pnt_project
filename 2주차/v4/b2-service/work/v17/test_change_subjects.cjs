const fs=require('node:fs'),assert=require('node:assert/strict'),esbuild=require('esbuild');
(async()=>{
 const code=esbuild.buildSync({entryPoints:[__dirname+'/change_subjects.js'],bundle:true,write:false,format:'esm',platform:'node'}).outputFiles[0].text;
 const {historyGroups,decisionComparisonIds,missingRecordSeed}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
 const event=(id,title,category,after,extra={})=>({id,title,category,after,project_id:'p1',effective_date:'2026-11-0'+id,business_state:'요청',review_state:'검토 전',quotes:[after],...extra});
 const events=[
  event('1','점검 커버 방식','사양','여닫이 방식 적용',{business_state:'확정'}),
  event('2','점검 커버 형식','사양','측면 슬라이드로 변경 요청'),
  event('3','점검 커버 구조','사양','슬라이드 요청 철회, 여닫이 유지',{business_state:'철회'}),
  event('4','장비 납품일','납기','2026-12-18',{business_state:'확정'}),
  event('5','납기','납기','납품일을 2026-12-23으로 변경 요청'),
  event('6','납기','납기','납품일 변경은 보류',{business_state:'보류'}),
  event('7','압연 속도','사양','120 m/min',{business_state:'확정',review_state:'확인됨',topic_id:'speed'}),
  event('8','압연 속도','사양','135 m/min 요청'),
  event('9','압연 속도','사양','135 m/min 합의',{business_state:'확정'}),
 ];
 const topics=[{id:'speed',project_id:'p1',title:'압연 속도',category:'사양',current_event_id:'7'}];
 const before=JSON.stringify({events,topics}),groups=historyGroups(events,topics);
 assert.equal(groups.length,3);assert.deepEqual(groups.map(g=>g.events.length),[3,3,3]);
 assert.deepEqual(groups.find(g=>g.title.includes('커버')).events.map(e=>e.id),['1','2','3']);
 assert.equal(groups.find(g=>g.title==='압연 속도').current.id,'7','New unverified decision does not replace baseline');
 assert.equal(JSON.stringify({events,topics}),before,'Never mutate stored events or topics');
 assert.equal(historyGroups(events,topics,'attention').length,3);
 assert.equal(historyGroups(events.map(e=>e.id==='2'?{...e,review_state:'제외'}:e),topics,'excluded')[0].events[0].id,'2');
 const isolated=[...events,event('10','점검 커버 방식','사양','여닫이 적용',{project_id:'p2'}),event('11','설치일','납기','설치 예정 12/20'),event('12','점검 커버 재질','사양','SUS304'),event('13','점검 커버 형식','요구사항','여닫이 적용')];
 assert.equal(historyGroups(isolated,topics).length,7,'Project, category, material and installation dates stay distinct');
 const machines=[event('1','점검 커버 방식','사양','1호기 커버 여닫이 적용'),event('2','점검 커버 형식','사양','2호기 커버 슬라이드 요청')];
 assert.equal(historyGroups(machines,[]).length,2,'Explicit different machines never merge');
 assert.equal(historyGroups(machines.map(e=>({...e,title:'점검 커버 방식'})),[]).length,2,'Even identical titles stay separate for different machine numbers');
 assert.equal(historyGroups([event('1','점검 커버 구조','사양','프레임 두께 변경'),event('2','점검 커버 방식','사양','슬라이드 적용')],[]).length,2,'Structural changes without opening evidence stay separate');
 assert.equal(historyGroups([event('1','장비 납품일','납기','12/18'),event('2','납기','납기','부품 납품일 12/20')],[]).length,2,'Parts delivery is not equipment delivery');
 const conflictEvents=[event('1','점검 커버 방식','사양','여닫이 적용',{effective_date:'2026-11-01',business_state:'확정',review_state:'확인됨',topic_id:'a'}),event('2','점검 커버 형식','사양','슬라이드 적용',{effective_date:'2026-11-01',business_state:'확정',review_state:'확인됨',topic_id:'b'})];
 const conflictTopics=conflictEvents.map(e=>({id:e.topic_id,title:e.title,project_id:'p1',category:'사양',current_event_id:e.id}));
 const conflict=historyGroups(conflictEvents,conflictTopics)[0];assert.equal(conflict.conflict,true);assert.equal(conflict.current,null);
 assert.ok(groups.every(g=>g.originalKeys.length),'Old dashboard links can resolve merged subjects');
 assert.equal(decisionComparisonIds(groups.find(g=>g.title==='압연 속도')).size,0,'Different-day decisions and unreviewed status alone are not conflicts');
 assert.equal(decisionComparisonIds({events:conflictEvents.map(e=>({...e,review_state:'검토 전'}))}).size,2,'Same-date different decisions need comparison even before human review');
 assert.equal(decisionComparisonIds({events:conflictEvents.map(e=>({...e,after:'같은 내용'}))}).size,0);
 const seed=missingRecordSeed(groups.find(g=>g.title.includes('커버')));
 assert.equal(seed.project_id,'p1');assert.equal(seed.category,'사양');assert.ok(seed.title.includes('커버'));assert.equal(seed.meeting_id,undefined,'Never guess the source meeting');
 assert.deepEqual(missingRecordSeed(null,'p2'),{project_id:'p2'});
 console.log('PASS: 9 records → 3 subjects; chronology; unchanged data; isolated projects/machines/schedules; confirmed baseline and conflicts; excluded records.');
})();
