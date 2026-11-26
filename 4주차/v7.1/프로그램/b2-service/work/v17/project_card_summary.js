import{homeSummary}from'./home_summary';

export const RECORD_STATES=[
 {key:'요청',label:'요청',color:'#3978c6'},
 {key:'확정',label:'결정',color:'#4d927c'},
 {key:'보류',label:'보류',color:'#c99438'},
 {key:'철회',label:'철회',color:'#8998ab'},
 {key:'기타',label:'기타',color:'#8b79a9'},
];

// Historical records, not subject completion or project progress.
export function projectCardSummary(projectId,meetings,events,groups){
 const home=homeSummary(meetings,groups,projectId),visible=new Set(home.ordered.map(m=>m.id));
 const unique=new Map();
 for(const e of events){
  if(e.project_id!==projectId||!visible.has(e.meeting_id)||e.review_state==='제외'||e.superseded_by_revision||e.source_deleted)continue;
  unique.set(e.id,e);
 }
 const records=[...unique.values()],counts=new Map(RECORD_STATES.map(s=>[s.key,0]));
 for(const e of records){const key=counts.has(e.business_state)?e.business_state:'기타';counts.set(key,counts.get(key)+1)}
 const segments=RECORD_STATES.map(s=>({...s,count:counts.get(s.key)}));
 const ids=new Set(records.map(e=>e.id));
 return{total:records.length,segments,meetingCount:home.ordered.length,subjectCount:groups.filter(g=>g.project_id===projectId&&g.events.some(e=>ids.has(e.id))).length,latestMeeting:home.latest,latestChange:home.recent[0]||null};
}
