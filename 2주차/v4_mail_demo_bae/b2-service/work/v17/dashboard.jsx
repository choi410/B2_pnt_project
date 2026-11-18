import React,{useState,useEffect}from'react';
import{ArrowLeft,ArrowRight,FileText,GitBranch,CalendarDays,CheckCheck}from'lucide-react';
import{useApp,api,Empty,day}from'./app';
import{PeriodCalendar}from'./home';
import{ProjectOverview}from'./context_panels';
import{ProjectStoryView,CompletionBar}from'./story_view';
import{requirementGroups,meetingStory,taskProgress,taskCheckpoint,registered}from'./project_story';
import{changeStateLabel,compareChangeEvents}from'./change_groups';
import{assignmentWaitingCount}from'./assignment_queue';

export function DashboardPage(){
 const{D,pid,project,person,pm,tasks,meetings,mine,reviewTask,nav,openTask,openMeeting,openChangeTopic}=useApp();
 const[data,setData]=useState(null),[error,setError]=useState(''),[limit,setLimit]=useState(5);
 useEffect(()=>{setLimit(5)},[pid]);
 useEffect(()=>{let alive=true,loading=false;setData(null);setError('');const refresh=async()=>{if(loading)return;loading=true;try{const d=await api('/changes'+(pid?'?project_id='+encodeURIComponent(pid):''));if(alive){setData(d);setError('')}}catch(e){if(alive)setError(e.message)}finally{loading=false}};refresh();const timer=setInterval(refresh,8000);return()=>{alive=false;clearInterval(timer)}},[pid,D.user.id]);
 const groups=requirementGroups(data?.events||[],data?.topics||[]);
 if(pid){
  const p=project(pid);if(!p)return null;
  const story=meetingStory(meetings,tasks,groups,person),checkpoints=tasks.map(t=>({...t,reason:taskCheckpoint(t,D.today),owner:person(t.kind==='확인사항'?t.reviewer_id:t.owner_id)?.name||'미정'})).filter(t=>t.reason).sort((a,b)=>Number(b.reason==='기한 지남')-Number(a.reason==='기한 지남')||(a.due||'9').localeCompare(b.due||'9'));
  return <><button className="back-link" onClick={()=>nav('home',undefined,'')}><ArrowLeft size={16}/>홈 대시보드</button><ProjectStoryView key={pid} project={p} pmName={person(p.pm)?.name||'미정'} memberCount={p.members.length} progress={taskProgress(tasks)} meetings={story} checkpoints={checkpoints} editor={pm(pid)?<ProjectOverview id={pid} triggerOnly/>:null} calendar={<PeriodCalendar/>} onTopic={key=>openChangeTopic(key,pid)} onMeeting={openMeeting} onTask={openTask} onWork={()=>nav('work','all')} onAllTopics={()=>nav('changes','all')} loading={!data&&!error} error={error} today={D.today}/></>;
 }
 const rows=D.projects.filter(p=>!pid||p.id===pid).map(p=>{const ts=tasks.filter(t=>t.project_id===p.id);return{...p,progress:taskProgress(ts),late:ts.filter(t=>t.status!=='완료'&&t.due&&t.due<D.today).length}}).sort((a,b)=>b.late-a.late||a.name.localeCompare(b.name,'ko'));
 const recent=meetings.filter(registered).sort((a,b)=>(b.date||'').localeCompare(a.date||'')||(b.created_at||'').localeCompare(a.created_at||''));
 const visibleMeetings=new Set(recent.map(m=>m.id)),changes=groups.filter(g=>g.latest&&visibleMeetings.has(g.latest.meeting_id)).sort((a,b)=>compareChangeEvents(b.latest,a.latest)).slice(0,3);
 const myTasks=tasks.filter(t=>mine(t)&&t.status!=='완료').length,reviewCount=tasks.filter(reviewTask).length+meetings.filter(m=>pm(m.project_id)&&m.document_status==='검토 대기').length,canReview=D.projects.some(p=>pm(p.id))||D.tasks.some(t=>t.reviewer_id===D.user.id&&t.owner_id!==D.user.id),waiting=assignmentWaitingCount(meetings,tasks);
 return <div className="portal-home">
  <header className="portal-heading"><div><h1>홈</h1><p>{pid?project(pid)?.name:'전체 프로젝트'} <span>현황</span></p></div><time dateTime={D.today}>{new Intl.DateTimeFormat('ko-KR',{year:'numeric',month:'long',day:'numeric',weekday:'long'}).format(new Date(D.today+'T12:00:00'))}</time></header>
  <div className="portal-grid"><div className="portal-main">
   <section className="portal-panel portal-projects" aria-label="프로젝트 현황"><header className="portal-panel-head"><h2>프로젝트 현황 <small>{rows.length}</small></h2><span>등록 업무 기준</span></header>
    {!rows.length&&<Empty title="등록된 프로젝트가 없습니다" text="상단 프로젝트 메뉴에서 프로젝트를 등록하세요."/>}
    {rows.slice(0,limit).map(p=><article className="portal-project" key={p.id}>
     <div className="portal-project-title"><div><small>{p.id} · PM {person(p.pm)?.name||'미정'}</small><h3>{p.name}</h3></div><button className="text-link" aria-label={p.name+' 흐름 보기'} onClick={()=>nav('home',undefined,p.id)}>흐름 보기 <ArrowRight size={14}/></button></div>
     <div className="portal-project-body"><div className="portal-project-stage"><div className="portal-stage-title"><span>현재 단계</span><b>{p.overview?.current_stage||'미등록'}</b></div>{p.overview?.stages?.length>0&&<ol className="portal-stage-track" aria-label={p.name+' 단계'}>{p.overview.stages.map(s=><li key={s} aria-current={s===p.overview.current_stage?'step':undefined} className={s===p.overview.current_stage?'current':''}><i/>{s}</li>)}</ol>}<p className="portal-next"><span>다음 목표</span>{p.overview?.next_goal||'아직 등록되지 않았습니다.'}</p></div><div className="portal-project-progress"><div className="portal-stage-title"><span>등록 업무 완료율</span><b>{p.progress.total?Math.round(p.progress.done/p.progress.total*100)+'%':'산정 전'}</b></div><CompletionBar progress={p.progress} compact/>{p.late>0?<button className="portal-late" onClick={()=>nav('work','late',p.id)}>기한 지난 업무 {p.late}건 <ArrowRight size={12}/></button>:<span className="portal-no-late">기한 지난 업무 없음</span>}</div></div>
    </article>)}
    {rows.length>limit&&<button className="portal-more" onClick={()=>setLimit(limit+5)}>프로젝트 더 보기 ({rows.length-limit})</button>}
   </section>
   <section className="portal-panel portal-activity" aria-label="최근 회의와 변경"><header className="portal-panel-head"><h2>최근 회의·변경</h2><span>회의일 기준</span></header>
    <div className="portal-feed"><div className="portal-feed-heading"><h3><FileText size={16}/>회의록</h3><button className="text-link" onClick={()=>nav('minutes')}>전체 보기 <ArrowRight size={13}/></button></div>
     {recent.slice(0,3).map(m=><button className="portal-feed-row" key={m.id} onClick={()=>openMeeting(m.id)}><time>{day(m.date)}</time><span><b>{m.title}</b><small>{project(m.project_id)?.name}</small></span><ArrowRight size={14}/></button>)}{!recent.length&&<p className="portal-empty">등록을 마친 회의록이 없습니다.</p>}
    </div>
    <div className="portal-feed"><div className="portal-feed-heading"><h3><GitBranch size={16}/>요구·변경 기록</h3><button className="text-link" onClick={()=>nav('changes','all')}>전체 보기 <ArrowRight size={13}/></button></div>
     {error?<p className="warning" role="alert">{error}</p>:!data?<p className="portal-empty" role="status">변경 기록을 불러오는 중입니다.</p>:changes.length?changes.map(g=><button className="portal-feed-row portal-change-row" key={g.key} onClick={()=>openChangeTopic(g.key,g.project_id)}><time>{day(g.latest.effective_date)}</time><span><b>{g.title} <em>{changeStateLabel(g.latest)}</em></b><span className="portal-change-value">{g.latest.before&&<><s>{g.latest.before}</s><span aria-hidden="true"> → </span></>}{g.latest.after||'내용 미기재'}</span><small>{project(g.project_id)?.name}{(g.latest.source_changed||g.latest.source_deleted)?' · 원문 변경·삭제됨':g.latest.review_state!=='확인됨'?' · 원문 확인 전':''}</small></span><ArrowRight size={14}/></button>):<p className="portal-empty">등록된 회의에서 찾은 요구·변경 기록이 없습니다.</p>}
    </div>
   </section>
  </div><aside className="portal-side">
   <section className="portal-panel portal-calendar"><header className="portal-panel-head"><h2><CalendarDays size={17}/>일정</h2><span>{pid?'선택 프로젝트':'전체 프로젝트'}</span></header><PeriodCalendar/></section>
   <section className="portal-panel portal-my" aria-label="내 업무 요약"><header className="portal-panel-head"><h2><CheckCheck size={17}/>내 업무 요약</h2><span>{pid?'선택 프로젝트':'전체 프로젝트'}</span></header><div className="portal-work-links">
    <button onClick={()=>nav('work','mine')}><span>내 미완료 업무</span><b>{myTasks}<small>건</small></b><ArrowRight size={14}/></button>
    {canReview&&<button onClick={()=>nav('work','review')}><span>내가 검토할 요청</span><b>{reviewCount}<small>건</small></b><ArrowRight size={14}/></button>}
    <button onClick={()=>nav('work','proposals')}><span>업무 제안·담당 미정</span><b>{waiting}<small>건</small></b><ArrowRight size={14}/></button>
   </div></section>
  </aside></div>
 </div>;
}
