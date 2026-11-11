import React,{useState,useEffect}from'react';
import{ArrowLeft,ArrowRight,ChevronRight,FileText,ListTodo,Search,FolderOpen,CheckCheck,Clock,Inbox}from'lucide-react';
import{useApp,api,Empty,day,Status}from'./app';
import{PeriodCalendar}from'./home';
import{ProjectOverview}from'./context_panels';
import{ProjectStoryView}from'./story_view';
import{requirementGroups,meetingStory,taskProgress,taskCheckpoint,registered}from'./project_story';
import{assignmentWaitingCount}from'./assignment_queue';

export function DashboardPage(){
 const{D,pid,project,person,pm,tasks,meetings,mine,reviewTask,nav,openTask,openMeeting,openChangeTopic,setDialog}=useApp();
 const[data,setData]=useState(null),[error,setError]=useState(''),[query,setQuery]=useState(''),[limit,setLimit]=useState(5);
 useEffect(()=>{setQuery('');setLimit(5)},[pid]);
 useEffect(()=>{let alive=true,loading=false;setData(null);setError('');const refresh=async()=>{if(loading)return;loading=true;try{const next=await api('/changes'+(pid?'?project_id='+encodeURIComponent(pid):''));if(alive){setData(next);setError('')}}catch(e){if(alive)setError(e.message)}finally{loading=false}};refresh();const timer=setInterval(refresh,8000);return()=>{alive=false;clearInterval(timer)}},[pid,D.user.id]);
 const groups=requirementGroups(data?.events||[],data?.topics||[]);
 if(pid){
  const p=project(pid);if(!p)return null;
  const story=meetingStory(meetings,tasks,groups,person),checkpoints=tasks.map(t=>({...t,reason:taskCheckpoint(t,D.today),owner:person(t.kind==='확인사항'?t.reviewer_id:t.owner_id)?.name||'미정'})).filter(t=>t.reason).sort((a,b)=>Number(b.reason==='기한 지남')-Number(a.reason==='기한 지남')||(a.due||'9').localeCompare(b.due||'9'));
  return <><button className="back-link" onClick={()=>nav('home',undefined,'')}><ArrowLeft size={16}/>전체 프로젝트</button><ProjectStoryView key={pid} project={p} pmName={person(p.pm)?.name||'미정'} memberCount={p.members.length} progress={taskProgress(tasks)} meetings={story} checkpoints={checkpoints} editor={pm(pid)?<ProjectOverview id={pid} triggerOnly/>:null} calendar={<PeriodCalendar/>} onTopic={key=>openChangeTopic(key,pid)} onMeeting={openMeeting} onTask={openTask} onWork={()=>nav('work','all')} onAllTopics={()=>nav('changes','all')} loading={!data&&!error} error={error} today={D.today}/></>;
 }
 const rows=D.projects.map(p=>{const ts=tasks.filter(t=>t.project_id===p.id);return{...p,progress:taskProgress(ts),late:ts.filter(t=>t.status!=='완료'&&t.due&&t.due<D.today).length}}).sort((a,b)=>b.late-a.late||a.name.localeCompare(b.name,'ko'));
 const shown=rows.filter(p=>(p.name+' '+p.id).toLowerCase().includes(query.toLowerCase()));
 const recent=meetings.filter(registered).sort((a,b)=>(b.date||'').localeCompare(a.date||'')||(b.created_at||'').localeCompare(a.created_at||''));
 const myCount=tasks.filter(t=>mine(t)&&t.status!=='완료').length,reviewCount=tasks.filter(reviewTask).length+meetings.filter(m=>pm(m.project_id)&&m.document_status==='검토 대기').length,canReview=D.projects.some(p=>pm(p.id))||D.tasks.some(t=>t.reviewer_id===D.user.id&&t.owner_id!==D.user.id),waiting=assignmentWaitingCount(meetings,tasks);
 const dateLabel=new Intl.DateTimeFormat('ko-KR',{month:'long',day:'numeric',weekday:'long'}).format(new Date(D.today+'T12:00:00'));
 return <div className="overview-v2">
  <header className="overview-heading"><div><p>{dateLabel}</p><h1>프로젝트 대시보드</h1></div><span className="overview-scope">참여 프로젝트 <b>{rows.length}</b></span></header>
  <div className="overview-grid"><div className="overview-main">
   <section className="surface project-board" aria-label="프로젝트 현황">
    <header className="surface-heading"><h2>프로젝트 현황</h2><label className="search"><Search size={16}/><input aria-label="대시보드 프로젝트 검색" placeholder="프로젝트 찾기" value={query} onChange={e=>{setQuery(e.target.value);setLimit(5)}}/></label></header>
    <div className="project-board-list">{shown.slice(0,limit).map(p=>{const progress=p.progress,total=progress.total,percent=total?Math.round(progress.done/total*100):0,o=p.overview||{};return <button className="project-overview-row" key={p.id} aria-label={p.name+' 프로젝트 흐름 보기'} onClick={()=>nav('home',undefined,p.id)}>
     <span className="project-overview-name"><span className="project-symbol"><FolderOpen size={20}/></span><span><small>{p.id} · PM {person(p.pm)?.name||'미정'}</small><strong>{p.name}</strong></span><ChevronRight size={18}/></span>
     <span className="project-overview-middle"><span className={'project-stage-badge '+(!o.current_stage?'unset':'')}>{o.current_stage||'단계 미등록'}</span>{o.next_goal&&<span className="project-next-goal"><span>다음</span> {o.next_goal}</span>}</span>
     <span className="project-overview-bottom"><span className="project-progress-label">{total?<>등록 업무 <b>{progress.done}/{total}</b> 완료</>:'등록된 업무 없음'}</span><span className="project-progress-track" role="img" aria-label={total?`등록 업무 ${total}건 중 ${progress.done}건 완료`:'등록 업무 없음'}><i style={{width:percent+'%'}}/></span><span className="project-progress-percent">{total?percent+'%':'—'}</span>{p.late>0&&<span className="project-overdue"><Clock size={12}/>기한 지남 {p.late}</span>}</span>
    </button>})}</div>
    {!shown.length&&<Empty title={rows.length?'검색 결과가 없습니다':'첫 프로젝트를 시작하세요'} text={rows.length?'다른 프로젝트 이름으로 검색해 보세요.':'프로젝트를 등록하면 회의록과 업무를 연결할 수 있습니다.'} action={!rows.length&&<button className="btn primary" onClick={()=>setDialog({type:'projects'})}>프로젝트 관리</button>}/>}
    {shown.length>limit&&<button className="overview-more" onClick={()=>setLimit(limit+5)}>프로젝트 {shown.length-limit}개 더 보기<ChevronRight size={14}/></button>}
   </section>
   <section className="surface overview-recent" aria-label="최근 회의록"><header className="surface-heading"><h2>최근 회의록</h2><button className="text-link" onClick={()=>nav('minutes')}>전체 보기<ArrowRight size={14}/></button></header>{recent.slice(0,3).map(m=><button className="overview-meeting-row" key={m.id} onClick={()=>openMeeting(m.id)}><span className="document-symbol"><FileText size={18}/></span><span><strong>{m.title}</strong><small>{project(m.project_id)?.name} · {day(m.date)}</small></span><Status value={m.document_status}/><ChevronRight size={15}/></button>)}{!recent.length&&<p className="overview-empty">등록된 회의록이 없습니다.</p>}</section>
  </div><aside className="overview-aside">
   <section className="surface overview-mine" aria-label="내 업무 바로가기"><header className="surface-heading"><h2>{D.user.name}님의 업무</h2></header><div className="overview-shortcuts">{[[ListTodo,'mine','내 미완료 업무',myCount],...(canReview?[[CheckCheck,'review','검토 요청',reviewCount]]:[]),[Inbox,'proposals','배정할 업무 제안',waiting]].map(([Icon,key,name,n])=><button key={key} onClick={()=>nav('work',key)}><span className={'shortcut-icon shortcut-'+key}><Icon size={18}/></span><span>{key==='proposals'&&!D.projects.some(p=>pm(p.id))?'업무 제안':name}</span><b>{n}</b><ChevronRight size={14}/></button>)}</div></section>
   <section className="surface overview-calendar" aria-label="전체 프로젝트 일정"><PeriodCalendar/></section>
  </aside></div>
 </div>;
}
