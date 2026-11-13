import React,{useState,useEffect}from'react';
import {projectStages} from './project_stages';
import {inferStage} from './stage_guess';
import{ArrowLeft,ChevronRight,ChevronDown,ChevronUp,FileText,Check}from'lucide-react';

/* Pure project views. The selected-project page starts with the current
   stage, next goal and three recent records. Details stay behind disclosures.
   Task completion is distinct from project progress; source verification and
   approved-baseline flags remain unchanged. Never infer missing project data. */

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
function StageRail({stages,current,onSelect,busy}){
 const currentIndex=stages.indexOf(current);
 const hasCurrent=currentIndex>=0;
 const nextStage=hasCurrent?stages[currentIndex+1]:null;
 return <>
  <div className={'project-stage-position '+(!hasCurrent?'unset':'')} role="status">
   <div>
    <span className="project-stage-caption">현재 단계</span>
    <strong>{hasCurrent?current:'미지정'}</strong>
   </div>
   {hasCurrent?<div className="project-stage-context">
    <b>{currentIndex+1} / {stages.length}단계</b>
    <span>{nextStage?'다음 단계 · '+nextStage:'마지막 단계'}</span>
   </div>:<span>현재 단계를 설정해 주세요.</span>}
  </div>
  <div className="project-stepper-scroll" tabIndex={0} aria-label="프로젝트 단계 가로 스크롤">
  <ol className="project-stepper" aria-label="프로젝트 단계">
   {stages.map((stage,index)=>{
    const state=index===currentIndex?'current':currentIndex>index?'past':'upcoming';
    const status=state==='current'?'현재 단계':state==='past'?'이전 단계':'예정';
    return <li key={stage} className={state} aria-current={state==='current'?'step':undefined}>
     <button type="button" className="project-step-button" disabled={!onSelect||busy||state==='current'}
      aria-label={stage+' · '+status+(onSelect&&state!=='current'?' · 현재 단계로 설정':'')}
      onClick={()=>onSelect?.(stage)}>
      <span className="project-step-node" aria-hidden="true">{state==='past'?<Check size={16}/>:index+1}</span>
      <span className="project-step-name">{stage}</span>
      <small>{status}</small>
     </button>
    </li>;
   })}
  </ol>
 </div></>;
}

/* ───────── 회의 안 요구·변경 항목 한 줄 ───────── */
function EventRow({e,onTopic}){
 const[label,k]=stateOf(e.state),needsCheck=k==='decision'&&!e.verified;
 return <li className={'sv-event '+(e.current?'is-current ':'')+(needsCheck?'needs-check ':'')+(e.stale?'is-stale':'')}>
  <button type="button" onClick={()=>onTopic?.(e.key)} aria-label={`${e.title} 변경 흐름 보기`}>
   <span className={'sv-state st-'+k}>{label}</span>
   <span className="sv-event-body">
    <span className="sv-event-title">{e.title}{e.category&&<small> · {e.category}</small>}</span>
    <span className="sv-event-value">{e.before&&<><s>{e.before}</s><span className="sv-arrow" aria-hidden="true">→</span></>}<strong>{e.value||<span className="sv-unset">내용 미기재</span>}</strong></span>
    {(e.current||needsCheck||e.stale||(e.verified&&!e.current))&&<span className="sv-event-flags">
     {e.current&&<em className="sv-flag current"><Check size={11}/>현재 기준</em>}
     {needsCheck&&<em className="sv-flag pending">원문 확인 전</em>}
     {e.verified&&!e.current&&<em className="sv-flag muted">확인됨</em>}
     {e.stale&&<em className="sv-flag muted">이전 본문</em>}
    </span>}
   </span>
   <ChevronRight size={14} aria-hidden="true"/>
  </button>
 </li>;
}

function MeetingTasks({tasks=[],onTask}){
 if(!tasks.length)return null;
 return <div className="sv-tasks"><span className="sv-tasks-head">이 회의에서 나온 업무 <small>{tasks.length}건</small></span><ul>{tasks.map(t=><li key={t.id}><button type="button" onClick={()=>onTask?.(t.id)}><span className="sv-task-title">{t.title}</span><span className="sv-task-meta">{t.owner||'담당 미정'} · {t.due?day(t.due):'기한 미정'}</span><StatusBadge value={t.status}/></button></li>)}</ul></div>;
}

function MeetingItem({m,onMeeting,onTopic,onTask}){
 const[more,setMore]=useState(false),events=m.events||[],shown=more?events:events.slice(0,3);
 const analysis=m.analysisState&&m.analysisState!=='ready'?(['queued','running'].includes(m.analysisState)?'요구·변경 분석 중':m.analysisState==='failed'?'분석 실패 · 변경 이력에서 다시 찾기':m.analysisState==='stale'?'최신 본문 분석 필요':'분석 전'):'';
 return <li><details className="sv-meeting-fold"><summary><time dateTime={m.date||undefined}>{m.date||'날짜 미정'}</time><span>{m.title}</span><ChevronDown size={16}/></summary><div className="sv-fold-body">
  <button type="button" className="sv-source-link" onClick={()=>onMeeting?.(m.id)}><FileText size={15}/>회의록 보기<ChevronRight size={14}/></button>
  {analysis&&<p className="sv-analysis">{analysis}</p>}
  {events.length>0?<ul className="sv-events">{shown.map(e=><EventRow key={e.id} e={e} onTopic={onTopic}/>)}</ul>:<p className="sv-quiet">추출된 요구·변경 항목이 없습니다.</p>}
  {events.length>3&&<button type="button" className="sv-more" onClick={()=>setMore(!more)}>{more?<><ChevronUp size={13}/>접기</>:<><ChevronDown size={13}/>항목 {events.length-3}건 더 보기</>}</button>}
  <MeetingTasks tasks={m.tasks} onTask={onTask}/>
 </div></details></li>;
}

/* Compact project view: source records stay available behind disclosures. */
const DIGEST_HEADS={"결정사항":"decisions","합의사항":"decisions","추가확인사항":"checks","확인사항":"checks","확인필요사항":"checks","후속조치":"followups","향후조치":"followups","actionitem":"followups","actionitems":"followups"},DIGEST_STOP=new Set(["회의안건","안건","논의내용","논의사항","참고사항","기타","첨부"]);
function parseMinutes(lines){let o={decisions:[],checks:[],followups:[]},c=null;for(const l of lines||[]){const t=String(l&&l.text||"").trim();if(!t)continue;const k=t.replace(/[\s:：\[\]]/g,"").toLowerCase();if(DIGEST_HEADS[k]){c=DIGEST_HEADS[k];continue}if(DIGEST_STOP.has(k)){c=null;continue}if(c&&o[c].length<6)o[c].push(t.replace(/^\s*(?:\d+[.)]|[-•·])\s*/,""))}return o}

/* ───────── 최신 회의록 요약: 회의록 원문의 결정 사항·추가 확인 사항·후속 조치를 그대로 정리 (AI 미사용) ───────── */
function MinutesDigest({meeting,onMeeting}){
 const[digest,setDigest]=useState(null);
 useEffect(()=>{if(!meeting)return;let alive=true;setDigest(null);fetch('/api/meetings/'+encodeURIComponent(meeting.id),{credentials:'same-origin'}).then(r=>r.ok?r.json():null).then(x=>{if(alive)setDigest(parseMinutes(x?.lines))}).catch(()=>{if(alive)setDigest(parseMinutes([]))});return()=>{alive=false}},[meeting?.id]);
 if(!meeting)return <p className="sv-quiet">요약할 회의록이 없습니다.</p>;
 const groups=[['결정 사항',digest?.decisions],['추가 확인 사항',digest?.checks],['후속 조치',digest?.followups]].filter(([,x])=>x?.length);
 return <section className="sv-minutes-digest" aria-label="회의록 요약"><div className="sv-digest-head"><span>회의록 요약</span><button type="button" className="sv-link" onClick={()=>onMeeting?.(meeting.id)}>{(meeting.date?meeting.date+' · ':'')+meeting.title}<ChevronRight size={13}/></button></div>
  {!digest?<p className="sv-quiet">회의록을 불러오는 중입니다.</p>:groups.length?groups.map(([t,x])=><div key={t} className="sv-digest-group"><h3>{t}</h3><ul>{x.map((s,i)=><li key={i}>{s}</li>)}</ul></div>):<p className="sv-quiet">회의록에서 결정 사항·후속 조치 항목을 찾지 못했습니다.</p>}
 </section>;
}


/* ───────── 최신 회의록으로 프로젝트 단계를 추정 (규칙 기반, stage_guess.js) ───────── */
const meetingCache=new Map();
const loadMeeting=id=>{if(!meetingCache.has(id))meetingCache.set(id,fetch('/api/meetings/'+encodeURIComponent(id),{credentials:'same-origin'}).then(r=>r.ok?r.json():null).catch(()=>null));return meetingCache.get(id)};
function useStageGuess(meetings,overview){
 const latest=[...(meetings||[])].sort((a,b)=>(b.date||'').localeCompare(a.date||'')||(b.created_at||'').localeCompare(a.created_at||''))[0];
 const stages=projectStages(overview);
 const[result,setResult]=useState(null);
 useEffect(()=>{let alive=true;setResult(null);if(!latest)return;loadMeeting(latest.id).then(m=>{if(alive&&m)setResult(inferStage(m,stages))});return()=>{alive=false}},[latest?.id,latest?.revision,stages.join('|')]);
 return result;
}
function StageRailGuess({stages,current,onSelect,busy,guess}){
 const idx=s=>stages.indexOf(s),meetingLabel=guess?`『${guess.meetingTitle||'회의록'}』${guess.meetingDate?` (${guess.meetingDate})`:''}`:'';
 const basis=guess?.top?.hits.slice(0,4).join(', ')||'';
 if(!current&&guess?.stage)return <div className="pnt-stage-guess">
  <StageRail stages={stages} current={guess.stage} onSelect={onSelect} busy={busy}/>
  <div className="pnt-guess-note" role="status"><span><b>회의록 기준 자동 추정</b>최근 회의록 {meetingLabel}에서 <em>{basis}</em> 내용이 가장 많아 ‘{guess.stage}’ 단계로 판단했습니다. 아직 확정되지 않았습니다.</span>
   {onSelect&&<button type="button" className="btn small primary" disabled={busy} onClick={()=>onSelect(guess.stage)}>이 단계로 확정</button>}</div>
 </div>;
 const later=current&&guess?.stage&&guess.stage!==current&&idx(guess.stage)>idx(current);
 return <><StageRail stages={stages} current={current} onSelect={onSelect} busy={busy}/>
  {later&&<div className="pnt-guess-note subtle" role="status"><span>최근 회의록 {meetingLabel}은 <b>‘{guess.stage}’</b> 단계 내용에 가깝습니다 (근거: <em>{basis}</em>).</span>{onSelect&&<button type="button" className="btn small" disabled={busy} onClick={()=>onSelect(guess.stage)}>{guess.stage}(으)로 변경</button>}</div>}
  {!current&&guess&&!guess.stage&&<div className="pnt-guess-note subtle" role="status"><span>최근 회의록 {meetingLabel}만으로는 단계를 판단할 근거가 부족합니다. 단계를 직접 선택해 주세요.</span></div>}
 </>;
}

export function ProjectStoryView({project,pmName,memberCount,progress,meetings=[],checkpoints=[],editor,calendar,onBack,onTopic,onMeeting,onTask,onWork,onAllTopics,onStageChange,stageBusy,loading,error,today}){
 const stageGuess=useStageGuess(meetings,project?.overview);
 const[infoOpen,setInfoOpen]=useState(false),[showOld,setShowOld]=useState(false);
 const o=project?.overview||{},sorted=[...meetings].sort((a,b)=>(b.date||'').localeCompare(a.date||'')||(b.created_at||'').localeCompare(a.created_at||''));
 const recent=sorted.flatMap(m=>(m.events||[]).map(e=>({m,e}))).slice(0,3),visibleMeetings=showOld?sorted:sorted.slice(0,5),checks=checkpoints.slice(0,3),late=checkpoints.filter(c=>c.reason==='기한 지남').length;
 const dueLate=o.due_date&&today&&o.due_date<today,total=progress?.total||0,done=progress?.done||0;
 const props=[['고객',o.customer],['장비',o.equipment],['PM',pmName],['참여 인원',memberCount?memberCount+'명':''],['착수',o.start_date],['납기',o.due_date]].filter(([,value])=>value);
 return <div className="story-view sv-simple">
  <header className="sv-simple-head">
   {onBack&&<button type="button" className="sv-back" onClick={onBack}><ArrowLeft size={14}/>전체 프로젝트</button>}
   <div className="sv-simple-title"><div><h1>{project?.name||'프로젝트'}</h1>{o.current_stage&&<span className="sv-current-stage">{o.current_stage}</span>}</div><button type="button" className="sv-info-toggle" aria-expanded={infoOpen} aria-controls="project-summary-info" onClick={()=>setInfoOpen(!infoOpen)}>프로젝트 정보{infoOpen?<ChevronUp size={16}/>:<ChevronDown size={16}/>}</button></div>
   {infoOpen&&<section id="project-summary-info" className="sv-info-panel" aria-label="프로젝트 정보"><div className="sv-info-heading"><small>{project?.id}</small></div><dl className="sv-props">{props.map(([name,value])=><div key={name}><dt>{name}</dt><dd className={name==='납기'&&dueLate?'sv-late':''}>{value}</dd></div>)}</dl>{o.purpose&&<p><b>목적</b>{o.purpose}</p>}{o.scope&&<p><b>범위</b>{o.scope}</p>}</section>}
  </header>
  <div className="sv-simple-grid"><div className="sv-simple-main">
   <section className="sv-flow-focus" aria-label="프로젝트 진행 흐름"><div className="project-stepper-heading"><h2>진행 흐름</h2>{editor}</div><StageRailGuess stages={projectStages(o)} current={o.current_stage} onSelect={onStageChange} busy={stageBusy} guess={stageGuess}/><p className="project-stepper-unset">{onStageChange?'단계를 누르면 현재 단계로 변경할 수 있습니다.':'프로젝트 PM이 현재 단계를 설정할 수 있습니다.'}</p>
    <MinutesDigest meeting={sorted[0]} onMeeting={onMeeting}/>

   </section>
   <section className="sv-recent-changes" aria-label="최근 변화"><div className="sv-section-head"><h2>최근 변화</h2>{onAllTopics&&<button type="button" className="sv-link" onClick={onAllTopics}>전체 보기<ChevronRight size={14}/></button>}</div>
    {error&&<p className="warning" role="alert">{error}</p>}
    {loading?<p className="sv-quiet" role="status">기록을 불러오는 중입니다.</p>:!recent.length?<p className="sv-quiet">표시할 요구·변경 기록이 없습니다.</p>:<ol className="sv-recent-list">{recent.map(({m,e})=><li key={e.id}><details className="sv-change-fold"><summary><time dateTime={m.date||undefined}>{m.date||'날짜 미정'}</time><span className="sv-change-summary"><span className="sv-change-name">{e.title}</span><span className="sv-change-value">{e.before&&<><s>{e.before}</s><span className="sv-arrow" aria-hidden="true">→</span></>}<strong>{e.value||''}</strong></span></span><ChevronDown size={17}/></summary><div className="sv-fold-body"><p className="sv-change-digest"><span>{(m.date?m.date+' ':'')}『{m.title}』에서 정리된 변경입니다.</span><span>이 회의에서 변경 <b>{(m.events||[]).length}건</b>과 업무 <b>{(m.tasks||[]).length}건</b>이 함께 나왔습니다.</span></p><ul className="sv-events"><EventRow e={e} onTopic={onTopic}/></ul><button type="button" className="sv-source-link" onClick={()=>onMeeting?.(m.id)}><FileText size={14}/><span>{m.title}</span><ChevronRight size={14}/></button><MeetingTasks tasks={m.tasks} onTask={onTask}/></div></details></li>)}</ol>}
   </section>
   <details className="sv-records-fold"><summary>회의별 기록 <span>{sorted.length}건</span><ChevronDown size={16}/></summary>{sorted.length?<ol className="sv-meeting-folds">{visibleMeetings.map(m=><MeetingItem key={m.id} m={m} onMeeting={onMeeting} onTopic={onTopic} onTask={onTask}/>)}</ol>:<p className="sv-quiet">등록된 회의록이 없습니다.</p>}{sorted.length>5&&<button type="button" className="sv-more" onClick={()=>setShowOld(!showOld)}>{showOld?'이전 회의 접기':'이전 회의 '+(sorted.length-5)+'건 더 보기'}</button>}</details>
  </div><aside className="sv-simple-side">
   {calendar&&<section className="sv-calendar" aria-label="일정">{calendar}</section>}
   <details className="sv-check-fold"><summary>업무 점검 <span>{checkpoints.length}건</span>{late>0&&<small>기한 지남 {late}</small>}<ChevronDown size={16}/></summary>{checks.length?<ul className="sv-check-list">{checks.map(c=><li key={c.id}><button type="button" onClick={()=>onTask?.(c.id)}><span className="sv-check-main"><b>{c.title}</b><small>{c.owner||'담당 미정'} · {c.due?day(c.due):'기한 미정'}</small></span><span className={'sv-reason r-'+String(c.reason||'').replace(/\s/g,'')}>{c.reason||statusLabel(c.status)}</span></button></li>)}</ul>:<p className="sv-quiet">점검할 업무가 없습니다.</p>}{onWork&&<button type="button" className="sv-link" onClick={onWork}>업무 전체 보기<ChevronRight size={14}/></button>}</details>
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
