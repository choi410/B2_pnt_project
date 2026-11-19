// Field reports are existing tasks, never new meeting candidates.
export function unassignedFieldIssues(tasks){
 return tasks.filter(t=>!t.deleted_at&&t.status!=='완료'&&!t.owner_id&&t.kind==='업무'&&(t.events||[]).some(e=>e.action==='현장 이슈 접수'));
}
export function assignmentWaitingCount(meetings,tasks){
 return meetings.reduce((n,m)=>n+(m.pending||0),0)+unassignedFieldIssues(tasks).length;
}
