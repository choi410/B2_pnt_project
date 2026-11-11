const collator=new Intl.Collator('ko',{numeric:true,sensitivity:'base'});
const normalized=value=>String(value||'').normalize('NFKC').trim().replace(/\s+/g,' ').toLocaleLowerCase('ko');
export function compareChangeEvents(a,b){
 return collator.compare(a.effective_date||'',b.effective_date||'')||
  collator.compare(a.meeting_created_at||a.created_at||'',b.meeting_created_at||b.created_at||'')||
  collator.compare(a.created_at||'',b.created_at||'')||collator.compare(a.id,b.id);
}
// Presentation groups only: never write a topic_id or merge stored records here.
export function changeGroups(events,topics,mode){
 const state=mode==='history'?'확인됨':'검토 전',groups=new Map();
 for(const e of events.filter(e=>e.review_state===state)){
  const matches=topics.filter(t=>t.project_id===e.project_id&&(e.topic_id?t.id===e.topic_id:t.category===e.category&&normalized(t.title)===normalized(e.title)));
  const topic=matches.length===1?matches[0]:null;
  if(mode==='history'&&!topic)continue;
  const key=JSON.stringify([e.project_id,e.topic_id||topic?.id||null,...(e.topic_id||topic?[]:[e.category,normalized(e.title)])]);
  if(!groups.has(key))groups.set(key,{key,project_id:e.project_id,title:topic?.title||e.title,category:topic?.category||e.category,topic,events:[]});
  groups.get(key).events.push(e);
 }
 return [...groups.values()].map(g=>({...g,events:g.events.sort(compareChangeEvents)})).sort((a,b)=>
  compareChangeEvents(b.events.at(-1),a.events.at(-1))||collator.compare(a.title,b.title));
}
export function filterChangeGroups(groups,query,projectName=()=> ''){
 const q=normalized(query);
 return groups.filter(g=>!q||normalized([g.title,g.category,projectName(g.project_id),g.topic?.current_value,...g.events.flatMap(e=>[e.title,e.before,e.after,e.meeting_title])].join(' ')).includes(q));
}

// All source-backed records share one chronology. Inclusion is not approval.
export function timelineGroups(events,topics,mode='all'){
 const active=events.filter(e=>!e.superseded_by_revision),groups=new Map();
 for(const e of active.filter(e=>mode==='excluded'?e.review_state==='제외':e.review_state!=='제외')){
  const matches=topics.filter(t=>t.project_id===e.project_id&&t.category===e.category&&
   (e.topic_id?t.id===e.topic_id:normalized(t.title)===normalized(e.title)));
  const topic=matches.length===1?matches[0]:null;
  const key=JSON.stringify([e.project_id,e.topic_id||topic?.id||null,...(e.topic_id||topic?[]:[e.category,normalized(e.title)])]);
  if(!groups.has(key))groups.set(key,{key,project_id:e.project_id,title:topic?.title||e.title,category:topic?.category||e.category,topic,events:[]});
  groups.get(key).events.push(e);
 }
 return [...groups.values()].map(g=>{
  const current=active.find(e=>e.id===g.topic?.current_event_id&&e.review_state==='확인됨'&&e.business_state==='확정'&&e.project_id===g.project_id)||null;
  return {...g,events:g.events.sort(compareChangeEvents),current,
   needsAttention:g.events.filter(e=>e.review_state==='검토 전'&&(e.business_state==='확정'||e.source_changed||e.source_deleted)).length};
 }).filter(g=>mode!=='attention'||g.needsAttention>0).sort((a,b)=>compareChangeEvents(b.events.at(-1),a.events.at(-1))||collator.compare(a.title,b.title));
}

export function changeStateLabel(e){
 if(e.business_state==='확정')return e.review_state==='확인됨'?'결정':'결정으로 추출';
 return {요청:'요청',보류:'보류',철회:'철회'}[e.business_state]||e.business_state;
}
