import React from'react';
import{useApp}from'./app';

/* 대시보드 오른쪽 카드: 업무 완료 현황 + 구성원별 미완료 업무 (사이드바 '나의 업무'와 겹치지 않도록 팀 단위로 보여준다) */
const AVATAR_COLORS=['#1f3d63','#2f7a5b','#2a5fa8','#7a4fa3','#b5562f','#3f6f86'];
const assigneeOf=t=>t.kind==='확인사항'?t.reviewer_id:t.owner_id;

export function DashboardCards(){
 const app=useApp(),{D,nav,person}=app,tasks=app.tasks||[],today=D.today;
 const done=tasks.filter(t=>t.status==='완료').length,todo=tasks.filter(t=>t.status==='미착수').length,active=tasks.length-done-todo,total=tasks.length;
 const pct=n=>total?(n/total*100)+'%':'0%';
 const open=tasks.filter(t=>t.status!=='완료');
 const projectIds=new Set(tasks.map(t=>t.project_id));
 const projects=D.projects.filter(p=>!projectIds.size||projectIds.has(p.id));
 const memberIds=[...new Set([...projects.flatMap(p=>[p.pm,...(p.members||[])]),...open.map(assigneeOf)].filter(Boolean))];
 const pmIds=new Set(projects.map(p=>p.pm));
 const rows=memberIds.map((id,i)=>{const mine=open.filter(t=>assigneeOf(t)===id);return{id,name:person(id)?.name||id,pm:pmIds.has(id),count:mine.length,late:mine.filter(t=>t.due&&t.due<today).length,color:AVATAR_COLORS[i%AVATAR_COLORS.length]}})
  .sort((a,b)=>Number(b.pm)-Number(a.pm)||b.count-a.count||a.name.localeCompare(b.name,'ko'));
 const unassigned=open.filter(t=>!assigneeOf(t)),unassignedLate=unassigned.filter(t=>t.due&&t.due<today).length;
 return <>
  <section className="surface pnt-done-card" aria-label="업무 완료">
   <header><h2>업무 완료</h2><button type="button" className="text-link" onClick={()=>nav('work','all')}>업무 보기</button></header>
   <p className="pnt-done-num"><b>{done}</b><span>/ {total}건</span></p>
   <div className="pnt-done-bar" role="img" aria-label={`완료 ${done}건, 진행 ${active}건, 미착수 ${todo}건, 전체 ${total}건`}>
    <i className="d" style={{width:pct(done)}}/><i className="a" style={{width:pct(active)}}/><i className="t" style={{width:pct(todo)}}/></div>
   <ul className="pnt-done-legend"><li><i className="d"/>완료 {done}</li><li><i className="a"/>진행 {active}</li><li><i className="t"/>미착수 {todo}</li></ul>
   <p className="pnt-done-note">업무 완료 수이며 프로젝트 공정률과는 다릅니다.</p>
  </section>
  <section className="surface pnt-member-card" aria-label="구성원별 미완료 업무">
   <header><h2>구성원별 미완료 업무</h2><span>{open.length}건</span></header>
   <ul>
    {rows.map(r=><li key={r.id}><span className="pnt-m-avatar" style={{background:r.color}}>{r.name.slice(-2)}</span>
     <span className="pnt-m-name">{r.name}{r.pm&&<small>PM</small>}</span><b>{r.count}</b>{r.late>0?<em>지남 {r.late}</em>:<span className="pnt-m-gap"/>}</li>)}
    <li className="unassigned"><span className="pnt-m-avatar empty"/><span className="pnt-m-name">담당 미정</span><b>{unassigned.length}</b>{unassignedLate>0?<em>지남 {unassignedLate}</em>:<span className="pnt-m-gap"/>}</li>
   </ul>
  </section>
 </>;
}
