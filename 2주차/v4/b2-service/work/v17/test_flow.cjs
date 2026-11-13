const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const {timelineGroups,filterChangeGroups,changeStateLabel}=await import('data:text/javascript;base64,'+Buffer.from(fs.readFileSync(__dirname+'/change_groups.js','utf8')).toString('base64'));
 const topic={id:'speed',project_id:'p1',title:'압연 속도',category:'사양',current_event_id:'base',current_value:'120 m/min'};
 const event=(id,date,state,review='검토 전',extra={})=>({id,project_id:'p1',topic_id:'speed',title:'압연 속도',category:'사양',effective_date:date,business_state:state,review_state:review,after:id,...extra});
 const events=[event('request','2026-11-02','요청'),event('new-agreement','2026-11-05','확정'),event('base','2026-11-01','확정','확인됨',{after:'120 m/min'}),event('hold','2026-11-03','보류'),event('withdraw','2026-11-04','철회'),event('excluded','2026-11-06','요청','제외'),event('superseded','2026-11-07','확정','검토 전',{superseded_by_revision:2})];
 const groups=timelineGroups(events,[topic]);assert.equal(groups.length,1);assert.deepEqual(groups[0].events.map(e=>e.id),['base','request','hold','withdraw','new-agreement']);assert.equal(groups[0].current.id,'base');assert.equal(groups[0].needsAttention,1);
 assert.equal(timelineGroups(events,[topic],'attention')[0].events.length,5,'Attention keeps the full chronology');
 assert.deepEqual(timelineGroups(events,[topic],'excluded')[0].events.map(e=>e.id),['excluded']);
 const noId=event('same-title','2026-11-08','요청','검토 전',{topic_id:null});assert.equal(timelineGroups([...events,noId],[topic]).length,1);
 const outside=event('outside','2026-11-08','확정','확인됨',{project_id:'p2',topic_id:null});const category=event('category','2026-11-08','요청','검토 전',{topic_id:null,category:'납기'});
 const separated=timelineGroups([...events,outside,category],[topic]);assert.equal(separated.length,3);assert.equal(separated.find(g=>g.project_id==='p2').current,null,'A confirmed orphan stays visible without inventing a baseline');
 assert.equal(timelineGroups([event('fresh-request','2026-11-02','요청')],[topic],'attention').length,0);assert.equal(timelineGroups([event('stale','2026-11-02','요청','검토 전',{source_changed:true})],[topic],'attention').length,1);
 assert.equal(filterChangeGroups(groups,'120').length,1);assert.equal(changeStateLabel(events[1]),'결정');assert.equal(changeStateLabel(events[2]),'결정');
 const afterConfirm=events.map(e=>e.id==='new-agreement'?{...e,review_state:'확인됨'}:e);const updated=timelineGroups(afterConfirm,[{...topic,current_event_id:'new-agreement'}])[0];assert.equal(updated.current.id,'new-agreement');assert.equal(updated.needsAttention,0);
 console.log('PASS: automatic unified chronology; confirmed baseline only; attention context; exclusion/restore grouping; source staleness; project/category isolation; source search.');
})();
