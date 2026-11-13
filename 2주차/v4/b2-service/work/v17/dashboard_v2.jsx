import React,{useState,useEffect}from'react';
import{ArrowLeft,ArrowRight,ChevronRight,FileText,ListTodo,Search,FolderOpen,CheckCheck,Clock,Inbox}from'lucide-react';
import{useApp,api,Empty,day,Status}from'./app';
import{PeriodCalendar}from'./home';
import{ProjectOverview}from'./context_panels';
import{ProjectStoryView}from'./story_view';
import{meetingStory,taskProgress,taskCheckpoint,registered}from'./project_story';
import{historyGroups as requirementGroups}from'./change_subjects';
import{assignmentWaitingCount}from'./assignment_queue';
import{homeSummary}from'./home_summary';
import{HomeDashboard}from'./home_dashboard';

export function DashboardPage({projectView=false}){
 const{D,pid:selectedProject,project,person,pm,mine,reviewTask,nav,openTask,openMeeting,openChangeTopic,setDialog,setConfirm,reload,busy}=useApp();
 const pid=projectView?selectedProject:'',tasks=D.tasks.filter(t=>!pid||t.project_id===pid),meetings=D.meetings.filter(m=>!pid||m.project_id===pid);
 const showMeeting=id=>{const m=meetings.find(item=>item.id===id);return openMeeting(id,m?.project_id)};
 const[data,setData]=useState(null),[error,setError]=useState(''),[query,setQuery]=useState(''),[limit,setLimit]=useState(5);
 useEffect(()=>{setQuery('');setLimit(5)},[pid]);
 useEffect(()=>{let alive=true,loading=false;setData(null);setError('');const refresh=async()=>{if(loading)return;loading=true;try{const next=await api('/changes'+(pid?'?project_id='+encodeURIComponent(pid):''));if(alive){setData(next);setError('')}}catch(e){if(alive)setError(e.message)}finally{loading=false}};refresh();const timer=setInterval(refresh,8000);return()=>{alive=false;clearInterval(timer)}},[pid,D.user.id]);
 const groups=requirementGroups(data?.events||[],data?.topics||[]);
 const homeData=homeSummary(meetings,groups,pid),latest=homeData.latest;
 const[latestDetail,setLatestDetail]=useState(null),[followupError,setFollowupError]=useState('');
 useEffect(()=>{let live=true;setLatestDetail(null);setFollowupError('');if(pid&&latest)api('/meetings/'+latest.id).then(m=>{if(live)setLatestDetail(m)}).catch(()=>{if(live)setFollowupError('회의록을 불러오지 못했습니다. 다시 열어 주세요.')});return()=>{live=false}},[pid,latest?.id,latest?.version,latest?.revision]);
 if(projectView&&pid){
  const p=project(pid);if(!p)return null;
  const story=meetingStory(meetings,tasks,groups,person),checkpoints=tasks.map(t=>({...t,reason:taskCheckpoint(t,D.today),owner:person(t.kind==='확인사항'?t.reviewer_id:t.owner_id)?.name||'미정'})).filter(t=>t.reason).sort((a,b)=>Number(b.reason==='기한 지남')-Number(a.reason==='기한 지남')||(a.due||'9').localeCompare(b.due||'9'));
  const changeStage=stage=>{
   const o=p.overview||{};
   setConfirm({title:'현재 단계 변경',text:p.name+'의 현재 단계를 ‘'+stage+'’(으)로 변경할까요?',button:'현재 단계로 설정',action:async()=>{
    await api('/projects/'+p.id+'/focus','PATCH',{version:o.version||1,current_stage:stage,next_goal:o.next_goal||'',next_goal_date:o.next_goal_date||''});
    await reload();
   }});
  };
  return <><button className="back-link" onClick={()=>nav('project',undefined,'')}><ArrowLeft size={16}/>전체 프로젝트</button><ProjectStoryView key={pid} project={p} pmName={person(p.pm)?.name||'미정'} memberCount={p.members.length} progress={taskProgress(tasks)} meetings={story} homeData={homeData} latestDetail={latestDetail} digestError={followupError} onStageChange={pm(pid)?changeStage:undefined} stageBusy={busy} checkpoints={checkpoints} editor={pm(pid)?<ProjectOverview id={pid} triggerOnly/>:null} calendar={<PeriodCalendar meetings={meetings}/>} onTopic={key=>openChangeTopic(key,pid)} onMeeting={showMeeting} onTask={openTask} onAllTopics={()=>nav('changes','all')} loading={!data&&!error} error={error} today={D.today}/></>;
 }
 const rows=D.projects.map(p=>{const ts=tasks.filter(t=>t.project_id===p.id);return{...p,progress:taskProgress(ts),late:ts.filter(t=>t.status!=='완료'&&t.due&&t.due<D.today).length}}).sort((a,b)=>b.late-a.late||a.name.localeCompare(b.name,'ko'));
 const shown=rows.filter(p=>(p.name+' '+p.id).toLowerCase().includes(query.toLowerCase()));
 const recent=meetings.filter(registered).sort((a,b)=>(b.date||'').localeCompare(a.date||'')||(b.created_at||'').localeCompare(a.created_at||''));
 const myCount=tasks.filter(t=>mine(t)&&t.status!=='완료').length,reviewCount=tasks.filter(reviewTask).length+meetings.filter(m=>pm(m.project_id)&&m.document_status==='검토 대기').length,canReview=D.projects.some(p=>pm(p.id))||D.tasks.some(t=>t.reviewer_id===D.user.id&&t.owner_id!==D.user.id),waiting=assignmentWaitingCount(meetings,tasks);
 const dateLabel=new Intl.DateTimeFormat('ko-KR',{month:'long',day:'numeric',weekday:'long'}).format(new Date(D.today+'T12:00:00'));
 const projectBoard=<section className="surface project-board" aria-label={projectView?'프로젝트 목록':'프로젝트 현황'}>
    <header className="surface-heading"><h2>{projectView?'프로젝트 목록':'프로젝트 현황'}</h2><label className="search"><Search size={16}/><input aria-label={projectView?'프로젝트 검색':'대시보드 프로젝트 검색'} placeholder="프로젝트 찾기" value={query} onChange={e=>{setQuery(e.target.value);setLimit(5)}}/></label></header>
    <div className="project-board-list">{shown.slice(0,limit).map(p=>{const lastMeeting=homeSummary(meetings,[],p.id).latest;return <button className="project-overview-row" key={p.id} aria-label={p.name+' 프로젝트 흐름 보기'} onClick={()=>nav('project',undefined,p.id)}>
     <span className="project-overview-name"><span className="project-symbol"><FolderOpen size={20}/></span><span><small>{p.id} · PM {person(p.pm)?.name||'미정'}</small><strong>{p.name}</strong></span><ChevronRight size={18}/></span>
     <span className="project-overview-middle home-last-meeting">{lastMeeting?'최근 회의 · '+(lastMeeting.date||'날짜 미정'):'등록된 회의록이 없습니다'}</span>
     <span className="project-overview-bottom demo-record-counts"><span>회의록 <b>{meetings.filter(m=>m.project_id===p.id&&registered(m)).length}</b>건</span><span>요구·변경 항목 <b>{groups.filter(g=>g.project_id===p.id).length}</b>개</span></span>
    </button>})}</div>
    {!shown.length&&<Empty title={rows.length?'검색 결과가 없습니다':'첫 프로젝트를 시작하세요'} text={rows.length?'다른 프로젝트 이름으로 검색해 보세요.':'프로젝트를 등록하면 회의록과 요구·변경 기록을 함께 확인할 수 있습니다.'} action={!rows.length&&<button className="btn primary" onClick={()=>setDialog({type:'projects'})}>프로젝트 관리</button>}/>}
    {shown.length>limit&&<button className="overview-more" onClick={()=>setLimit(limit+5)}>프로젝트 {shown.length-limit}개 더 보기<ChevronRight size={14}/></button>}
   </section>;
 if(projectView)return <div className="overview-v2 project-directory">
  <header className="overview-heading"><h1>프로젝트</h1><span className="overview-scope">참여 프로젝트 <b>{rows.length}</b></span></header>
  {projectBoard}
 </div>;
 return <HomeDashboard groups={groups} changesLoading={!data&&!error} changesError={error} calendar={<PeriodCalendar meetings={D.meetings.filter(m=>!selectedProject||m.project_id===selectedProject)}/>}/>;
}
