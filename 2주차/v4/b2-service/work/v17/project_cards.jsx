import React,{useState,useEffect,useRef}from'react';
import{MoreHorizontal,ChevronRight,Info}from'lucide-react';
import{useApp,Modal,day}from'./app';
import{ProjectOverview}from'./context_panels';
import{ProjectTrashButton}from'./project_trash';
import{ProjectFocus}from'./project_focus';

export function RecordRing({summary,loading,error}){
 const unavailable=loading||error;
 let offset=0;
 const description=unavailable?(error?'기록을 불러오지 못했습니다':'기록을 불러오는 중입니다'):'요구·변경 기록 '+summary.total+'건. '+summary.segments.filter(s=>s.count).map(s=>s.label+' '+s.count+'건').join(', ');
 return <div className="project-card-chart" aria-busy={loading}>
  <div className="record-ring" role="img" aria-label={description}>
   <svg viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r="49" fill="none" stroke="#edf2f7" strokeWidth="10"/>
    {!unavailable&&summary.total>0&&summary.segments.filter(s=>s.count).map(s=>{const size=s.count/summary.total*100,start=offset;offset+=size;return <circle key={s.key} cx="60" cy="60" r="49" fill="none" pathLength="100" stroke={s.color} strokeWidth="10" strokeDasharray={size+' '+(100-size)} strokeDashoffset={-start} transform="rotate(-90 60 60)"/>})}
   </svg><span aria-hidden="true"><b>{unavailable?'—':summary.total}<small>{!unavailable?'건':''}</small></b><span>요구·변경 기록</span></span>
  </div>
  {unavailable?<p className="record-ring-notice" role={error?'alert':'status'}>{error?'기록을 불러오지 못했습니다.':'기록을 불러오는 중…'}</p>:<ul className="record-ring-legend" aria-label="기록 상태별 건수">{summary.segments.filter(s=>s.key!=='기타'||s.count>0).map(s=><li key={s.key}><i style={{background:s.color}} aria-hidden="true"/><span>{s.label}</span><b>{s.count}<small>건</small></b></li>)}</ul>}
 </div>;
}

export function ProjectCard({project:p,summary,loading,error,onOpen,onInfo}){
 const{person,pm}=useApp(),[menu,setMenu]=useState(false),menuRef=useRef(null),trigger=useRef(null),menuId=React.useId();
 useEffect(()=>{if(!menu)return;const outside=e=>{if(!menuRef.current?.contains(e.target))setMenu(false)},escape=e=>{if(e.key==='Escape'){setMenu(false);trigger.current?.focus()}};document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape)}},[menu]);
 const latest=summary.latestChange;
 return <article className="project-card" aria-label={p.name+' 프로젝트 현황'}>
  <div className="project-card-top"><small>{p.id}</small><div className="project-card-menu-wrap" ref={menuRef} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))setMenu(false)}}>
   <button type="button" className="project-card-menu-toggle" ref={trigger} aria-label={p.name+' 프로젝트 메뉴'} aria-expanded={menu} aria-controls={menu?menuId:undefined} onClick={()=>setMenu(!menu)}><MoreHorizontal size={20}/></button>
   {menu&&<div id={menuId} className="project-card-menu" role="group" aria-label="프로젝트 메뉴"><button type="button" onClick={()=>{setMenu(false);onInfo()}}><Info size={16}/>프로젝트 정보</button>{pm(p.id)&&<ProjectTrashButton project={p} compactMenu onPrompt={()=>setMenu(false)}/>}</div>}
  </div></div>
  <button type="button" className="project-card-title" aria-label={p.name+' 프로젝트 흐름 보기'} onClick={onOpen}><h3>{p.name}</h3><ChevronRight size={18}/></button>
  <div className="project-card-meta"><span>PM {person(p.pm)?.name||'미정'}</span><span>{summary.latestMeeting?'최근 회의 '+(summary.latestMeeting.date?day(summary.latestMeeting.date):'날짜 미정'):'회의록 없음'}</span></div>
  <ProjectFocus project={p} compact/>
  <div className="project-card-latest"><div><small>최근 변화</small>{latest&&!loading&&!error&&<time dateTime={latest.e.date}>{day(latest.e.date)}</time>}</div>
   {loading||error?<p className="project-card-empty">{error?'기록을 불러온 뒤 표시합니다.':'최근 변화를 불러오는 중…'}</p>:latest?<><strong title={latest.e.title}>{latest.e.title}<span>{latest.e.state}</span></strong><p title={latest.e.value}>{latest.e.value}</p>{latest.e.stale&&<small className="project-card-stale">본문 변경 · 원문 확인 필요</small>}</>:<p className="project-card-empty">아직 요구·변경 기록이 없습니다.</p>}
  </div>
 </article>;
}

export function ProjectCardInfo({id,close}){
 const{project,person,pm}=useApp(),p=project(id);if(!p)return null;
 const o=p.overview||{},fields=[['프로젝트 번호',p.id],['PM',person(p.pm)?.name||'미정'],['참여 인원',p.members.length+'명'],['고객사',o.customer],['장비·호기',o.equipment],['착수일',o.start_date],['납기일',o.due_date]].filter(([,v])=>v);
 return <Modal title="프로젝트 정보" close={close}><div className="project-card-info"><h3>{p.name}</h3><dl>{fields.map(([name,value])=><div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>{o.purpose&&<section><h4>목적</h4><p>{o.purpose}</p></section>}{o.scope&&<section><h4>범위</h4><p>{o.scope}</p></section>}{pm(id)&&<ProjectOverview id={id} triggerOnly meetingBased/>}</div></Modal>;
}
