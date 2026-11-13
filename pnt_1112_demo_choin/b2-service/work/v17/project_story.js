import{timelineGroups,compareChangeEvents,changeStateLabel}from'./change_groups';
const normalize=s=>String(s||'').normalize('NFKC').trim().replace(/\s+/g,' ').toLocaleLowerCase('ko');
// Reading groups only: preserve topic IDs, original titles and recorded decisions.
// Measurement qualifiers are retained; unrelated equipment and categories never merge.
const family=s=>normalize(s).replace(/((?:장력|압력|온도))\s*범위$/,'$1');
export const categoryLabel=c=>({'사양':'사양·성능','납기':'일정·납기','요구사항':'고객 요구'}[c]||c);
export function requirementGroups(events,topics,mode='all'){
 const exact=timelineGroups(events,topics,mode==='excluded'?'excluded':'all'),groups=new Map();
 for(const source of exact){
  const key=JSON.stringify([source.project_id,source.category,family(source.title)]);
  if(!groups.has(key))groups.set(key,{key,project_id:source.project_id,category:source.category,title:source.title,events:[],topics:[],titles:[],baselines:[],needsAttention:0});
  const g=groups.get(key);g.events.push(...source.events);g.needsAttention+=source.needsAttention;g.titles.push(source.title);
  if(source.topic)g.topics.push(source.topic);if(source.current)g.baselines.push(source.current);
 }
 return [...groups.values()].map(g=>{
  g.events.sort(compareChangeEvents);g.titles=[...new Set(g.titles)];g.title=g.titles.reduce((a,b)=>a.length<=b.length?a:b);g.latest=g.events.at(-1);
  const bases=[...new Map(g.baselines.map(e=>[e.id,e])).values()].sort(compareChangeEvents),last=bases.at(-1);
  g.conflicting=last?bases.filter(e=>e.effective_date===last.effective_date):[];
  g.conflict=new Set(g.conflicting.map(e=>normalize(e.after))).size>1;
  g.current=g.conflict?null:last||null;g.grouped=g.titles.length>1;g.topic=g.topics.length===1?g.topics[0]:null;
  return g;
 }).filter(g=>mode!=='attention'||g.needsAttention||g.conflict).sort((a,b)=>Number(b.events.length>1)-Number(a.events.length>1)||Number(b.needsAttention>0||b.conflict)-Number(a.needsAttention>0||a.conflict)||compareChangeEvents(b.latest,a.latest));
}
export function taskProgress(tasks){
 const done=tasks.filter(t=>t.status==='완료').length,todo=tasks.filter(t=>t.status==='미착수').length;
 return{total:tasks.length,done,todo,active:tasks.length-done-todo};
}
export const registered=m=>!m.deleted_at&&!!(m.registered_revision||m.document_status==='확정');
export function meetingStory(meetings,tasks,groups,person=()=>null){
 const byMeeting=new Map();
 for(const g of groups)for(const e of g.events){
  if(e.review_state==='제외'||e.superseded_by_revision)continue;
  if(!byMeeting.has(e.meeting_id))byMeeting.set(e.meeting_id,[]);
  byMeeting.get(e.meeting_id).push({id:e.id,key:g.key,title:g.title,category:g.category,value:e.after,before:e.before,state:changeStateLabel(e),verified:e.review_state==='확인됨',current:g.current?.id===e.id,stale:!!(e.source_changed||e.source_deleted)});
 }
 return meetings.filter(registered).map(m=>({id:m.id,title:m.title,date:m.date,created_at:m.created_at,events:(byMeeting.get(m.id)||[]).sort((a,b)=>Number(b.current)-Number(a.current)||a.title.localeCompare(b.title,'ko')),tasks:tasks.filter(t=>t.meeting_id===m.id).map(t=>({id:t.id,title:t.title,status:t.status,owner:person(t.kind==='확인사항'?t.reviewer_id:t.owner_id)?.name||'미정',due:t.due})),analysisState:m.change_scan_state||'idle'})).sort((a,b)=>(a.date||'').localeCompare(b.date||'')||(a.created_at||'').localeCompare(b.created_at||'')||a.id.localeCompare(b.id));
}
export function taskCheckpoint(t,today){
 if(t.status==='완료')return'';
 const owner=t.kind==='확인사항'?t.reviewer_id:t.owner_id;
 return t.due&&t.due<today?'기한 지남':t.status==='검토대기'?'검토 대기':t.status==='보완요청'?'보완 요청':!owner?'담당 미정':!t.due?'기한 미정':t.kind==='확인사항'||t.status==='확인필요'?'추가 확인':'';
}
