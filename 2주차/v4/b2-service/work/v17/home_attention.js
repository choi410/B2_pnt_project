import{compareChangeEvents}from'./change_groups';
import{registered}from'./project_story';

// Latest requests/holds only. Decisions and withdrawn requests are not outstanding work.
export function pendingChanges(groups,meetings){
 const sources=new Map(meetings.filter(registered).map(m=>[m.id,m]));
 return groups.flatMap(g=>{
  const event=g.events.filter(e=>sources.has(e.meeting_id)&&e.review_state!=='제외'&&!e.superseded_by_revision).slice().sort(compareChangeEvents).at(-1);
  if(!event||!['요청','보류'].includes(event.business_state)||event.source_changed||event.source_deleted)return[];
  const m=sources.get(event.meeting_id);
  return[{id:'change:'+event.id,project_id:g.project_id,meeting_id:m.id,meeting_title:m.title,meeting_date:m.date,
   title:g.title,description:event.after,owner_id:event.owner_id||null,owner_basis:'기록 담당',due:event.due||'',
   reasons:[event.business_state==='보류'?'보류 사유 확인':'요청 검토'],quotes:event.quotes||[],origin:'요구·변경',topic_key:g.key,
   note:'회의록에 기록된 요청·보류 사항입니다. 확정된 변경 또는 배정된 업무를 뜻하지 않습니다.'}];
 });
}

export function orderAttention(items){
 const priority=i=>i.reasons.some(r=>r==='기한 지남'||r==='기한 경과')?0:i.reasons.some(r=>r==='담당자 미정'||r==='담당 확인')?1:2;
 return [...items].sort((a,b)=>priority(a)-priority(b)||(a.due||'9999').localeCompare(b.due||'9999')||(b.meeting_date||'').localeCompare(a.meeting_date||'')||a.title.localeCompare(b.title,'ko'));
}
