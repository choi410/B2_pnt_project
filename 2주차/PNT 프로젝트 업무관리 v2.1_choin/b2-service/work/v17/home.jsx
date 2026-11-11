import React,{useState,useEffect}from'react';
import{Plus,Search,ChevronLeft,ChevronRight,Maximize2,Minimize2,StickyNote}from'lucide-react';
import{useApp,api,Button,IconButton,Modal,PageHead,TaskRows,Empty,Status,Person,TaskAttentionDot,hasTaskAttention,day,dateText,norm}from'./app';
import{SortHeader,sortByColumn,dateValue}from'./table_sort';
import{WorkProposals}from'./work_proposals';
import{assignmentWaitingCount}from'./assignment_queue';
import{calendarEntries,calendarWeeks,eventsOn}from'./calendar_layout';
const statuses=['미착수','진행중','검토대기','보완요청','확인필요','완료'];

export function HomePage(){
 const{D,pid,tasks,meetings,reviewTask,mine,pm,overdue,filter,setFilter,setDialog,person,project,openTask,openMeeting,setWorkMeeting,guardLeave}=useApp();
 const[q,setQ]=useState(''),[limit,setLimit]=useState(30),[history,setHistory]=useState(false),[sort,setSort]=useState({key:'due',direction:'asc'}),[reviewSort,setReviewSort]=useState({key:'requested',direction:'asc'});
 useEffect(()=>{setLimit(30)},[q,filter]);
 const relevant=t=>pm(t.project_id)||mine(t)||t.created_by===D.user.id;
 const groups={mine:tasks.filter(t=>mine(t)&&t.status!=='완료'),review:tasks.filter(reviewTask),late:tasks.filter(t=>overdue(t)),missing:tasks.filter(t=>t.status!=='완료'&&(t.kind==='확인사항'||!(t.kind==='확인사항'?t.reviewer_id:t.owner_id)||!t.due)),all:tasks};
 const waitingDocs=meetings.filter(m=>pm(m.project_id)&&m.document_status==='검토 대기');
 const canReview=D.projects.some(p=>pm(p.id))||D.tasks.some(t=>t.reviewer_id===D.user.id&&t.owner_id!==D.user.id);
 const select=k=>guardLeave(()=>{setFilter(k);setWorkMeeting('');setHistory(false);setLimit(30)});
 const searchText=x=>norm(x.title+' '+(x.description||'')+' '+(project(x.project_id)?.name||'')).includes(norm(q));
 const shown=sortByColumn((groups[filter]||tasks).filter(searchText),sort,{title:t=>t.title,owner:t=>person(t.kind==='확인사항'?t.reviewer_id:t.owner_id)?.name,due:t=>dateValue(t.due),status:t=>statuses.indexOf(t.status)});
 const reviewTasks=history?tasks.filter(t=>(t.events||[]).some(e=>e.actor===D.user.id&&e.action==='완료 확인')):groups.review;
 const reviewDocs=history?meetings.filter(m=>pm(m.project_id)&&m.document_status==='확정'):waitingDocs;
 const reviews=sortByColumn([...reviewTasks.map(t=>({...t,type:'task',requester:t.owner_id,requested:t.submitted_at})),...reviewDocs.map(m=>({...m,type:'meeting',requester:m.author,requested:[...(m.document_events||[])].reverse().find(e=>e.action==='회의록 검토 요청')?.at||m.created_at}))].filter(searchText),reviewSort,{title:x=>x.title,requester:x=>person(x.requester)?.name,requested:x=>dateValue(x.requested),status:x=>x.type==='task'?x.status:x.document_status});
 return <><PageHead title="업무" text="내 업무를 처리하고, 요청받은 결과를 확인하세요."><Button icon={Plus} onClick={()=>setDialog({type:'field'})}>현장 이슈</Button>{D.projects.some(p=>pm(p.id))&&<Button primary icon={Plus} onClick={()=>setDialog({type:'new-task'})}>업무 등록</Button>}</PageHead>
 <div className="work-layout"><section className="main-list">
 <div className="tabs home-tabs">{[['mine','내 업무',groups.mine.length],['review','검토 요청',groups.review.length+waitingDocs.length],['late','기한 지남',groups.late.length],['missing','추가 확인',groups.missing.length],['all','전체',tasks.length],['proposals','업무 제안',assignmentWaitingCount(meetings,tasks)]].filter(([k])=>k!=='review'||canReview).map(([k,l,n])=><button key={k} className={(filter===k?'active ':'')+'task-attention-tab'} onClick={()=>select(k)}>{l}<em>{n}</em>{((k==='mine'&&groups.mine.some(t=>hasTaskAttention(t,'mine')))||(k==='review'&&groups.review.some(t=>hasTaskAttention(t,'review'))))&&<TaskAttentionDot tab/>}</button>)}</div>
 {filter!=='proposals'&&<div className="home-list-tools"><span className="muted">{filter==='review'?reviews.length+'건의 검토':shown.length+'건의 업무'}</span><div className="work-tools"><label className="search"><Search size={16}/><input aria-label="업무·검토 검색" placeholder="제목·프로젝트 검색" value={q} onChange={e=>setQ(e.target.value)}/></label></div></div>}

 {filter==='proposals'?<WorkProposals/>:filter==='review'?<><div className="review-list-meta"><span>업무 결과와 회의록 내용은 각각 검토합니다.</span><label className="check-line"><input type="checkbox" checked={history} onChange={e=>{setHistory(e.target.checked);setLimit(30)}}/>확인한 내역 보기</label></div>{reviews.length?<div className="task-table home-reviews"><div className="table-head">{[['title','검토할 내용'],['requester','요청자'],['requested','요청일'],['status','상태']].map(([k,l])=><SortHeader key={k} label={l} column={k} sort={reviewSort} onSort={setReviewSort}/>)}<span/></div>{reviews.slice(0,limit).map(x=><button className="task-row" key={x.type+x.id} onClick={()=>x.type==='task'?openTask(x.id):openMeeting(x.id)}><span className="task-main"><span><span className={'review-kind '+x.type}>{x.type==='task'?'업무':'회의록'}</span><b className="task-title-with-dot">{x.type==='task'&&hasTaskAttention(x)&&<TaskAttentionDot/>}<span>{x.title}</span></b><small>{project(x.project_id)?.name}</small></span></span><Person plain id={x.requester}/><span title={dateText(x.requested)}>{day(x.requested)}</span><Status value={x.type==='task'?x.status:x.document_status}/><ChevronRight size={16}/></button>)}</div>:<Empty title={history?'확인한 내역이 없습니다':'검토를 기다리는 항목이 없습니다'} text="업무 완료 요청과 회의록 승인 요청이 여기에 표시됩니다."/>}</>:shown.length?<TaskRows items={shown.slice(0,limit)} sort={sort} onSort={setSort}/>:<Empty title={q?'검색 결과가 없습니다':({mine:'내게 배정된 미완료 업무가 없습니다',late:'기한이 지난 업무가 없습니다',missing:'추가 확인할 업무가 없습니다',all:'등록된 업무가 없습니다'}[filter]||'표시할 업무가 없습니다')} text={q?'다른 제목이나 프로젝트 이름으로 검색해 보세요.':filter==='mine'?'배정받은 업무는 여기에 표시됩니다. 전체 탭에서 프로젝트 업무를 볼 수 있습니다.':'새 업무와 처리 상태가 여기에 표시됩니다.'}/>}
 {filter!=='proposals'&&(filter==='review'?reviews.length:shown.length)>limit&&<div className="load-more"><Button onClick={()=>setLimit(limit+30)}>30건 더 보기</Button></div>}</section></div></>;
}

export function PeriodCalendar(){
 const {D,tasks,meetings,openTask,openMeeting,run,busy}=useApp();
 const [month,setMonth]=useState(D.today.slice(0,7));
 const [selected,setSelected]=useState(D.today);
 const [limit,setLimit]=useState(8);
 const [expanded,setExpanded]=useState(false);
 const [memoPage,setMemoPage]=useState(null);
 const [memoError,setMemoError]=useState('');
 const [draft,setDraft]=useState(null);
 const [y,m]=month.split('-').map(Number);
 const entries=calendarEntries(tasks,meetings);
 const weeks=calendarWeeks(month,entries);
 const events=eventsOn(entries,selected);

 const range='start='+weeks[0].dates[0]+'&end='+weeks.at(-1).dates[6];
 const memoReady=memoPage?.range===range;
 const memos=memoReady?memoPage.memos:{};
 const memo=memos[selected];

 useEffect(()=>{
  let active=true;
  setMemoError('');
  api('/calendar/memos?'+range).then(memos=>{
   if(active)setMemoPage({range,memos});
  }).catch(e=>{
   if(active)setMemoError(e.message);
  });
  return()=>{active=false};
 },[range]);

 const select=date=>{
  if(date!==selected)setDraft(null);
  setSelected(date);setLimit(8);
 };
 function saveMemo(text){
  const date=selected;
  return run(async()=>{
   const saved=await api('/calendar/memos/'+date,'PUT',{text});
   setMemoPage(current=>current?.range===range?{range,memos:{...current.memos,[date]:saved.text}}:current);
   setDraft(current=>current?.date===date?null:current);
  },text.trim()?'메모를 저장했어요.':'메모를 삭제했어요.');
 }
 const open=e=>e.type==='task'?openTask(e.recordId):openMeeting(e.recordId);
 const shrink=()=>setExpanded(false);

 function move(n){
  const d=new Date(y,m-1+n,1);
  const next=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0');
  setMonth(next);
  select(next+'-01');
 }

 function renderCalendar(large){
  return <section className="calendar period-calendar">
   <div className="section-title">
    <h2>{y}년 {m}월</h2>
    <div className="period-controls">
     <IconButton icon={ChevronLeft} label="이전 달" onClick={()=>move(-1)}/>
     <IconButton icon={ChevronRight} label="다음 달" onClick={()=>move(1)}/>
     <button type="button" className="period-zoom" onClick={large?shrink:()=>setExpanded(true)}>
      {large?<Minimize2 size={15}/>:<Maximize2 size={15}/>}<span>{large?'축소':'확대'}</span>
     </button>
    </div>
   </div>
   <div className="period-weekdays">{'월화수목금토일'.split('').map(x=><span key={x}>{x}</span>)}</div>
   {weeks.map(w=>{
    const lanes=w.segments.length?Math.max(...w.segments.map(e=>e.lane))+1:0;
    const hasOverflow=w.overflow.some(Boolean);
    const rows='var(--period-date-row, 28px)'+' var(--period-event-row, 18px)'.repeat(lanes+Number(hasOverflow));
    return <div className="period-week" key={w.dates[0]} style={{gridTemplateRows:rows}}>
     {w.dates.map((date,i)=><button key={date}
      className={'period-date '+(date===selected?'selected ':'')+(date===D.today?'today ':'')+(!date.startsWith(month)?'outside':'')}
      style={{gridColumn:i+1,gridRow:1}} aria-label={date+' 일정 '+eventsOn(entries,date).length+'건'+(memos[date]?' · 내 메모 있음':'')}
      aria-pressed={date===selected} onClick={()=>select(date)}>
      {Number(date.slice(-2))}{memos[date]&&<i className="period-memo-dot" aria-hidden="true"/>}
     </button>)}
     {w.segments.map(e=>{
      const description=e.title+' · '+e.start+(e.start!==e.end?' ~ '+e.end:'');
      return <button key={e.id}
       className={'period-bar '+e.type+(e.continuesBefore?' continues-before':'')+(e.continuesAfter?' continues-after':'')}
       style={{gridColumn:(e.from+1)+' / '+(e.to+2),gridRow:e.lane+2}}
       aria-label={description} title={description} onClick={()=>open(e)}>
       {e.continuesBefore?'‹ ':''}{e.title}{e.continuesAfter?' ›':''}
      </button>;
     })}
     {w.overflow.map((n,i)=>n>0&&<button key={w.dates[i]} className="period-more"
      style={{gridColumn:i+1,gridRow:lanes+2}} aria-label={w.dates[i]+' 숨겨진 일정 '+n+'건 보기'}
      onClick={()=>select(w.dates[i])}>+{n}건</button>)}
    </div>;
   })}
   <div className="calendar-legend"><span className="legend-task"/> 업무 <span className="legend-meeting"/> 회의록</div>
   <div className="agenda-heading"><b>{day(selected)} 일정</b><span>{events.length}건</span></div>
   <div className="agenda">{events.length?events.slice(0,limit).map(e=><button key={e.id} onClick={()=>open(e)}>
    <span className={'agenda-dot '+e.type}/>
    <span><small>{e.type==='meeting'?'회의':e.start===e.end?'업무 · '+day(e.end)+' 기한':'업무 · '+day(e.start)+'~'+day(e.end)}</small><b>{e.title}</b></span>
    <ChevronRight size={13}/>
   </button>):<p className="muted">등록된 일정이 없습니다.</p>}</div>
   {events.length>limit&&<Button small onClick={()=>setLimit(limit+8)}>일정 더 보기</Button>}
   <div className="calendar-memo">
    <div className="calendar-memo-heading">
     <span><StickyNote size={15}/><b>{day(selected)} 내 메모</b></span>
     {memoReady&&!draft&&<button type="button" className="period-zoom" onClick={()=>setDraft({date:selected,text:memo||''})}>
      {memo?'메모 수정':'메모 추가'}
     </button>}
    </div>
    {memoError&&<p className="muted" role="status">{memoError}</p>}
    {draft&&(!expanded||large)?<form onSubmit={e=>{e.preventDefault();if(draft.text.trim())saveMemo(draft.text)}}>
     <textarea aria-label={day(selected)+' 내 메모'} placeholder="이 날짜에 기억할 내용을 적어보세요."
      autoFocus maxLength={1000} rows={3} value={draft.text}
      onChange={e=>setDraft({...draft,text:e.target.value})}/>
     <div className="calendar-memo-actions">
      {memo&&<Button small danger type="button" disabled={busy} onClick={()=>saveMemo('')}>삭제</Button>}
      <Button small type="button" disabled={busy} onClick={()=>setDraft(null)}>취소</Button>
      <Button small primary type="submit" disabled={busy||!draft.text.trim()}>저장</Button>
     </div>
    </form>:memo&&<p className="calendar-memo-text">{memo}</p>}
   </div>
  </section>;
 }

 return <>
  {renderCalendar(false)}
  {expanded&&<Modal title="프로젝트 일정" close={shrink} variant="calendar-zoom" wide>
   {renderCalendar(true)}
  </Modal>}
 </>;
}
