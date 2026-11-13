import React,{useState}from'react';
import{ProjectStageRail,MinutesDigest,projectStages}from'./project_home_reference';
import{ArrowLeft,ChevronRight,ChevronDown,ChevronUp,FileText,Check}from'lucide-react';

/* Project views read registered meetings and source-backed changes.
   Meeting chronology is not an inferred manufacturing stage or completion rate. */

const STATUSES=['미착수','진행중','검토대기','보완요청','확인필요','완료'];
const statusLabel=s=>({'진행중':'진행 중','검토대기':'검토 대기','보완요청':'보완 요청','확인필요':'추가 확인'}[s]||s||'미정');
const StatusBadge=({value})=><span className={'status s-'+(STATUSES.indexOf(value)>=0?STATUSES.indexOf(value):0)}><i/>{statusLabel(value)}</span>;
const day=s=>s?String(s).slice(5,10).replace('-','.'):'미정';

/* 상태 → 색 키. 라벨은 전달된 state 그대로. '결정'·'결정으로 추출'·'확정'·'합의'는 모두 결정 계열(녹색). */
const STATE_KEY={'결정':'decision','결정으로 추출':'decision','확정':'decision','합의':'decision','요청':'request','보류':'hold','철회':'withdrawn'};
const stateOf=s=>[s||'기록',STATE_KEY[s]||'other'];

/* ───────── 업무 완료 막대 ───────── */
function pct(progress){
 const total=progress?.total||0;if(!total)return null;
 const raw={done:(progress.done||0)/total*100,active:(progress.active||0)/total*100,todo:(progress.todo||0)/total*100};
 const out={done:Math.round(raw.done),active:Math.round(raw.active),todo:Math.round(raw.todo)};
 const diff=100-(out.done+out.active+out.todo);if(diff){const k=Object.keys(raw).sort((a,b)=>raw[b]-raw[a])[0];out[k]+=diff}
 return out;
}
export function CompletionBar({progress,compact=false}){
 const p=pct(progress);
 if(!p)return <div className={'sv-bar-wrap '+(compact?'compact':'')}><div className="sv-bar is-empty" role="img" aria-label="업무 완료율 산정 전"/><span className="sv-bar-text sv-unset">산정 전 · 등록된 업무 없음</span></div>;
 return <div className={'sv-bar-wrap '+(compact?'compact':'')}>
  <div className="sv-bar" role="img" aria-label={`업무 완료 ${progress.done}건, 진행 중 ${progress.active}건, 미착수 ${progress.todo}건, 전체 ${progress.total}건`}>
   {p.done>0&&<i className="seg done" style={{flexBasis:p.done+'%'}}/>}{p.active>0&&<i className="seg active" style={{flexBasis:p.active+'%'}}/>}{p.todo>0&&<i className="seg todo" style={{flexBasis:p.todo+'%'}}/>}
  </div>
  <span className="sv-bar-text"><b>{progress.done}</b><span className="sv-of">/ {progress.total} 완료</span>{!compact&&<span className="sv-bar-detail">진행 중 {progress.active} · 미착수 {progress.todo}</span>}</span>
 </div>;
}

/* ───────── 프로젝트 단계 레일 ───────── */
function StageRail({stages=[],current}){
 if(!stages.length)return <p className="sv-stages-empty">프로젝트 단계가 아직 등록되지 않았습니다. PM이 단계를 등록하면 여기에 표시됩니다.</p>;
 return <ol className="sv-stages" aria-label="프로젝트 단계">{stages.map(s=><li key={s} className={s===current?'current':''} aria-current={s===current?'step':undefined}><i aria-hidden="true"/><span>{s}</span></li>)}</ol>;
}

/* ───────── 회의 안 요구·변경 항목 한 줄 ───────── */
function EventRow({e,onTopic}){
 const[label,k]=stateOf(e.state);
 return <li className={'sv-event '+(e.stale?'is-stale':'')}>
  <button type="button" onClick={()=>onTopic?.(e.key)} aria-label={`${e.title} 변경 흐름 보기`}>
   <span className={'sv-state st-'+k}>{label}</span>
   <span className="sv-event-body">
    <span className="sv-event-title">{e.title}{e.category&&<small> · {e.category}</small>}</span>
    <span className="sv-event-value">{e.before&&<><s>{e.before}</s><span className="sv-arrow" aria-hidden="true">→</span></>}<strong>{e.value||<span className="sv-unset">내용 미기재</span>}</strong></span>
    {e.stale&&<span className="sv-event-flags">
     {e.stale&&<em className="sv-flag muted">이전 본문</em>}
    </span>}
   </span>
   <ChevronRight size={14} aria-hidden="true"/>
  </button>
 </li>;
}

function MeetingTasks({tasks=[],onTask}){
 if(!tasks.length)return null;
 return <div className="sv-tasks"><span className="sv-tasks-head">연결 업무 <small>{tasks.length}건</small></span><ul>{tasks.map(t=><li key={t.id}><button type="button" onClick={()=>onTask?.(t.id)}><span className="sv-task-title">{t.title}</span><span className="sv-task-meta">{t.owner||'담당 미정'} · {t.due?day(t.due):'기한 미정'}</span><StatusBadge value={t.status}/></button></li>)}</ul></div>;
}

function MeetingItem({m,onMeeting,onTopic,onTask}){
 const[more,setMore]=useState(false),events=m.events||[],shown=more?events:events.slice(0,3);
 const analysis=m.analysisState&&m.analysisState!=='ready'?(['queued','running'].includes(m.analysisState)?'요구·변경 분석 중':m.analysisState==='failed'?'분석 실패 · 변경 이력에서 다시 찾기':m.analysisState==='stale'?'최신 본문 분석 필요':'분석 전'):'';
 return <li><details className="sv-meeting-fold"><summary><time dateTime={m.date||undefined}>{m.date||'날짜 미정'}</time><span>{m.title}</span><ChevronDown size={16}/></summary><div className="sv-fold-body">
  <button type="button" className="sv-source-link" onClick={()=>onMeeting?.(m.id)}><FileText size={15}/>회의록 보기<ChevronRight size={14}/></button>
  {analysis&&<p className="sv-analysis">{analysis}</p>}
  {events.length>0?<ul className="sv-events">{shown.map(e=><EventRow key={e.id} e={e} onTopic={onTopic}/>)}</ul>:<p className="sv-quiet">추출된 요구·변경 항목이 없습니다.</p>}
  {events.length>3&&<button type="button" className="sv-more" onClick={()=>setMore(!more)}>{more?<><ChevronUp size={13}/>접기</>:<><ChevronDown size={13}/>항목 {events.length-3}건 더 보기</>}</button>}
  
 </div></details></li>;
}

/* Compact project view: source records stay available behind disclosures. */
export function ProjectStoryView({project,pmName,memberCount,progress,meetings=[],homeData={chronology:[],recent:[],ordered:[],latest:null},latestDetail,digestError,onStageChange,stageBusy,checkpoints=[],editor,calendar,onBack,onTopic,onMeeting,onTask,onWork,onAllTopics,loading,error,today}){
 const[infoOpen,setInfoOpen]=useState(false);
 const o=project?.overview||{};
 const recent=homeData.recent,checks=checkpoints.slice(0,3),late=checkpoints.filter(c=>c.reason==='기한 지남').length;
 const dueLate=o.due_date&&today&&o.due_date<today,total=progress?.total||0,done=progress?.done||0;
 const props=[['고객',o.customer],['장비',o.equipment],['PM',pmName],['참여 인원',memberCount?memberCount+'명':''],['착수',o.start_date],['납기',o.due_date]].filter(([,value])=>value);
 return <div className="story-view sv-simple reference-project-home">
  <header className="sv-simple-head">
   {onBack&&<button type="button" className="sv-back" onClick={onBack}><ArrowLeft size={14}/>전체 프로젝트</button>}
   <div className="sv-simple-title"><div><h1>{project?.name||'프로젝트'}</h1>{o.current_stage&&<span className="sv-current-stage">{o.current_stage}</span>}</div><button type="button" className="sv-info-toggle" aria-expanded={infoOpen} aria-controls="project-summary-info" onClick={()=>setInfoOpen(!infoOpen)}>프로젝트 정보{infoOpen?<ChevronUp size={16}/>:<ChevronDown size={16}/>}</button></div>
   {infoOpen&&<section id="project-summary-info" className="sv-info-panel" aria-label="프로젝트 정보"><div className="sv-info-heading"><small>{project?.id}</small></div><dl className="sv-props">{props.map(([name,value])=><div key={name}><dt>{name}</dt><dd className={name==='납기'&&dueLate?'sv-late':''}>{value}</dd></div>)}</dl>{o.purpose&&<p><b>목적</b>{o.purpose}</p>}{o.scope&&<p><b>범위</b>{o.scope}</p>}</section>}
  </header>
  <div className="sv-simple-grid"><div className="sv-simple-main">
   <section className="sv-flow-focus" aria-label="프로젝트 진행 흐름">
    <div className="project-stepper-heading"><h2>진행 흐름</h2>{editor}</div>
    <ProjectStageRail stages={projectStages(o)} current={o.current_stage} onSelect={onStageChange} busy={stageBusy}/>
    <p className="project-stepper-unset">{onStageChange?'단계를 누르면 현재 단계로 변경할 수 있습니다.':'프로젝트 PM이 현재 단계를 설정할 수 있습니다.'}</p>
    {o.next_goal&&<div className="sv-simple-goal"><span>다음 목표</span><strong>{o.next_goal}</strong>{o.next_goal_date&&<time dateTime={o.next_goal_date}>{o.next_goal_date}</time>}</div>}
    <MinutesDigest meeting={homeData.latest} detail={latestDetail} error={digestError} onMeeting={onMeeting}/>
   </section>
   <section className="sv-recent-changes" aria-label="최근 변화"><div className="sv-section-head"><h2>최근 변화 <small className="home-recent-hint">대상별 최신 기록</small></h2>{onAllTopics&&<button type="button" className="sv-link" onClick={onAllTopics}>전체 보기<ChevronRight size={14}/></button>}</div>
    {error&&<p className="warning" role="alert">{error}</p>}
    {loading?<p className="sv-quiet" role="status">기록을 불러오는 중입니다.</p>:!recent.length?<p className="sv-quiet">표시할 요구·변경 기록이 없습니다.</p>:<>
     <div className="sv-change-columns" aria-hidden="true"><span>항목</span><span>상태</span><span>최신 내용</span><span/></div>
     <ol className="sv-recent-list">{recent.map(({m,e,event})=>{const[label,k]=stateOf(e.state),compare=e.state==='결정'&&!!e.before;return <li key={e.id}><details className="sv-change-fold">
      <summary><span className="sv-change-heading"><b>{e.title}</b><time dateTime={e.date||m.date||undefined}>{e.date||m.date||'날짜 미정'}</time></span><span className={'sv-state st-'+k}>{label}</span><span className="sv-latest-result">{compare&&<><span>{e.before}</span> → </>}{e.value||'내용 미기재'}</span><ChevronDown size={17}/></summary>
      <div className="sv-fold-body"><p className="sv-change-full">{e.value||'내용 미기재'}</p>{e.before&&<p className="sv-change-previous">이전 기록 · {e.before}</p>}{e.stale&&<p className="warning">원문이 변경되었습니다. 최신 회의록을 확인해 주세요.</p>}
       {!!event?.quotes?.length&&<div className="sv-change-quotes"><h3>원문 근거</h3>{event.quotes.map((quote,index)=><blockquote key={index}>{quote}</blockquote>)}</div>}
       <div className="sv-change-links"><button type="button" className="sv-source-link" onClick={()=>onMeeting?.(m.id)}><FileText size={14}/><span>{m.title}</span><ChevronRight size={14}/></button><button type="button" className="sv-link" onClick={()=>onTopic?.(e.key)}>변경 이력 보기<ChevronRight size={14}/></button></div>
      </div></details></li>})}</ol></>}

   </section>
  </div><aside className="sv-simple-side">
   {calendar&&<section className="sv-calendar" aria-label="일정">{calendar}</section>}
  </aside></div>
 </div>;
}

/* ───────── 전체 프로젝트 ───────── */
export function PortfolioStoryView({rows=[],onSelect,today}){
 const ago=d=>{if(!d||!today)return '';const n=Math.round((Date.parse(today)-Date.parse(d))/86400000);return n===0?'오늘':n>0?n+'일 전':''};
 if(!rows.length)return <p className="sv-none">참여 중인 프로젝트가 없습니다. PM이 참여자로 추가하면 여기에 표시됩니다.</p>;
 return <div className="story-view portfolio">
  <div className="sv-portfolio-head" aria-hidden="true"><span>프로젝트</span><span>단계</span><span>업무 완료</span><span>최근 회의</span><span/></div>
  <ul className="sv-portfolio">
   {rows.map(r=><li key={r.id}><button type="button" className="sv-project" onClick={()=>onSelect?.(r.id)} aria-label={r.name+' 열기'}>
    <span className="sv-p-name"><b>{r.name}</b><small>{[r.customer,r.equipment].filter(Boolean).join(' · ')||<span className="sv-unset">고객·장비 미등록</span>}</small></span>
    <span className="sv-p-stage">{r.stage?<b>{r.stage}</b>:<span className="sv-unset">미등록</span>}</span>
    <span className="sv-p-bar"><CompletionBar progress={r.progress} compact/>{(r.late>0||r.unassigned>0)&&<span className="sv-p-flags">{r.late>0&&<em className="sv-flag late">기한 지남 {r.late}</em>}{r.unassigned>0&&<em className="sv-flag pending">담당·기한 미정 {r.unassigned}</em>}</span>}</span>
    <span className="sv-p-meeting">{r.latestMeetingDate?<><b>{r.latestMeetingTitle||'회의록'}</b><small>{day(r.latestMeetingDate)}{ago(r.latestMeetingDate)&&` · ${ago(r.latestMeetingDate)}`}</small></>:<span className="sv-unset">등록된 회의 없음</span>}</span>
    <ChevronRight size={16} aria-hidden="true"/>
   </button></li>)}
  </ul>
  <p className="sv-note">막대는 업무 완료율(완료 / 진행 중 / 미착수)이며 프로젝트 진척률이 아닙니다.</p>
 </div>;
}
