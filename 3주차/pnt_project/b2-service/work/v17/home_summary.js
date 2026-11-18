import{registered}from'./project_story';
import{compareChangeEvents,changeStateLabel}from'./change_groups';

// Read models only. Meeting dates and source records never imply project completion.
export function homeSummary(meetings,groups,projectId){
 const ordered=meetings.filter(m=>registered(m)&&m.project_id===projectId).sort((a,b)=>(b.date||'').localeCompare(a.date||'')||(b.created_at||'').localeCompare(a.created_at||'')||a.id.localeCompare(b.id));
 const byId=new Map(ordered.map(m=>[m.id,m]));
 const recent=groups.filter(g=>g.project_id===projectId).flatMap(g=>{
  const events=g.events.filter(e=>byId.has(e.meeting_id)&&e.review_state!=='제외'&&!e.superseded_by_revision).slice().sort(compareChangeEvents);
  const event=events.at(-1);if(!event)return[];
  return[{m:byId.get(event.meeting_id),event,e:{id:event.id,key:g.key,title:g.title,category:g.category,value:event.after,before:event.before,state:changeStateLabel(event),stale:!!(event.source_changed||event.source_deleted),date:event.effective_date||byId.get(event.meeting_id).date}}];
 }).sort((a,b)=>compareChangeEvents(b.event,a.event)||a.e.title.localeCompare(b.e.title,'ko')).slice(0,3);
 return{ordered,latest:ordered[0]||null,chronology:ordered.slice(0,5).reverse(),recent};
}

export function meetingFollowups(meeting){
 if(!meeting)return{state:'empty',items:[]};
 if(!meeting.overview)return{state:'missing',items:[]};
 if(meeting.overview.revision!==meeting.revision)return{state:'stale',items:[]};
 const candidates=meeting.reviewed_bundle?.candidates;
 if(!Array.isArray(candidates))return{state:'missing',items:[]};
 const seen=new Set(),items=[];
 for(const item of candidates){
  if(item.kind!=='업무')continue;
  const text=String(item.description||item.title||'').trim(),key=text.replace(/\s+/g,' ');
  if(!key||seen.has(key))continue;
  seen.add(key);items.push({text,evidence:item.evidence||[]});
 }
 return{state:'ready',items};
}
