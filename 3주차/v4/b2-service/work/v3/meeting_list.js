const collator=new Intl.Collator('ko',{numeric:true,sensitivity:'base'});
const normalize=value=>String(value||'').replace(/[\s·_().-]/g,'').toLowerCase();
export const meetingSortColumns=[['title','회의록'],['project','프로젝트'],['date','회의일'],['author','등록자']];
export function nextMeetingSort(current,key){return {key,direction:current.key===key?(current.direction==='asc'?'desc':'asc'):key==='date'?'desc':'asc'}}
export function meetingNeedsStatus(m){return ['queued','running','failed'].includes(m.analysis_state)||!!m.analysis_stale}
export const meetingIsProcessing=m=>['queued','running'].includes(m.analysis_state);
export function meetingProgress(m){
 if(!meetingIsProcessing(m))return null;
 if(m.analysis_state==='queued')return {stage:'queued',label:'분석 대기',detail:m.progress?.queue_ahead>0?`앞선 회의록 ${m.progress.queue_ahead}건 처리 중`:'분석 시작을 기다리고 있습니다.'};
 if(m.analysis_phase==='loading')return {stage:'analyzing',label:'모델 준비 중',detail:'AI 모델을 불러오고 있습니다.'};
 if(m.analysis_phase==='retrying')return {stage:'analyzing',label:'추가 분석 중',detail:'빠진 내용과 근거를 다시 확인하고 있습니다.'};
 const chunk=/^combined:(\d+)\/(\d+)$/.exec(m.analysis_phase||'');
 if(chunk){
  const done=Number(chunk[1]),total=Number(chunk[2]);
  if(total>0&&done<=total){
   if(done===total)return {stage:'applying',label:'분석 결과 반영 중',detail:'회의록 정리·변경이력·일정을 갱신하고 있습니다.'};
   return {stage:'analyzing',label:'AI 분석 중',detail:`${total}개 구간 중 ${done}개 분석 완료`};
  }
 }
 return {stage:'analyzing',label:'AI 분석 중',detail:'핵심 내용과 요구·변경사항을 정리하고 있습니다.'};
}
export function meetingSections(meetings,projects,people,options){
 const filtered=sortedMeetings(meetings,projects,people,options);
 return {
  processing:filtered.filter(meetingIsProcessing).sort((a,b)=>compareValue(a.created_at||'',b.created_at||'','desc')||String(a.id).localeCompare(String(b.id))),
  registered:filtered.filter(m=>!meetingIsProcessing(m)),
 };
}
function compareValue(a,b,direction){
 // Missing meeting dates stay last; upload dates are never used as meeting dates.
 if(!a||!b)return a?-1:b?1:0;
 return collator.compare(a,b)*(direction==='desc'?-1:1);
}
export function sortedMeetings(meetings,projects,people,{projectId='',query='',sort={key:'date',direction:'desc'}}={}){
 const projectNames=new Map(projects.map(p=>[p.id,p.name]));
 const peopleNames=new Map(people.map(p=>[p.id,p.name]));
 const value=m=>sort.key==='project'?projectNames.get(m.project_id)||'':sort.key==='author'?peopleNames.get(m.author)||'':sort.key==='title'?m.title||'':m.date||'';
 const needle=normalize(query);
 return meetings.filter(m=>(!projectId||m.project_id===projectId)&&normalize([m.title,projectNames.get(m.project_id),...(m.points||[]).map(p=>p.text)].join(' ')).includes(needle)).sort((a,b)=>
  compareValue(value(a),value(b),sort.direction)
  ||compareValue(a.date||'',b.date||'','desc')
  ||compareValue(a.created_at||'',b.created_at||'','desc')
  ||collator.compare(a.title||'',b.title||'')
  ||String(a.id).localeCompare(String(b.id))
 );
}
