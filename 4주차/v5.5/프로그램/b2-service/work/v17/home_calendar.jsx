import React,{useState,useEffect}from'react';
import{ChevronLeft,ChevronRight,Maximize2,Minimize2,StickyNote}from'lucide-react';
import{useApp,api,Button,IconButton,Modal,day}from'./app';
import{calendarEntries,calendarWeeks,eventsOn}from'./calendar_layout';

export function HomeCalendar({meetings:providedMeetings}={}){
 const{D,meetings:scopedMeetings,openMeeting,run,busy,setFormDirty}=useApp();
 const meetings=providedMeetings??scopedMeetings;
 const[month,setMonth]=useState(D.today.slice(0,7)),[selected,setSelected]=useState(D.today),[limit,setLimit]=useState(8),[expanded,setExpanded]=useState(false);
 const[page,setPage]=useState(null),[error,setError]=useState(''),[draft,setDraft]=useState(null),[pending,setPending]=useState(null),[deleteConfirm,setDeleteConfirm]=useState(false),[retry,setRetry]=useState(0);
 const[y,m]=month.split('-').map(Number),entries=calendarEntries([],meetings),weeks=calendarWeeks(month,entries),events=eventsOn(entries,selected);
 const range='start='+weeks[0].dates[0]+'&end='+weeks.at(-1).dates[6],ready=page?.range===range,memos=ready?page.memos:{},memo=memos[selected]||'';
 const dirty=!!draft&&draft.text!==draft.initial;
 useEffect(()=>{setFormDirty(dirty);return()=>setFormDirty(false)},[dirty]);
 useEffect(()=>{let live=true;setError('');api('/calendar/memos?'+range).then(memos=>live&&setPage({range,memos})).catch(e=>live&&setError(e.message));return()=>{live=false}},[range,D.user.id,retry]);
 const changeSelection=(date,nextMonth)=>{setSelected(date);if(nextMonth)setMonth(nextMonth);setLimit(8);setDraft(null);setDeleteConfirm(false)};
 const choose=(date,nextMonth)=>dirty?setPending({date,month:nextMonth}):changeSelection(date,nextMonth);
 function move(n){const d=new Date(y,m-1+n,1),next=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0');choose(next+'-01',next)}
 const save=(text,after)=>run(async()=>{const date=draft?.date||selected;const saved=await api('/calendar/memos/'+date,'PUT',{text});setPage(current=>current?.range===range?{range,memos:{...current.memos,[date]:saved.text}}:current);setDraft(null);setDeleteConfirm(false);setFormDirty(false);if(after){changeSelection(after.date,after.month);setPending(null)}},text.trim()?'내 메모를 저장했습니다.':'내 메모를 삭제했습니다.');
 const open=e=>{setExpanded(false);openMeeting(e.recordId,meetings.find(m=>m.id===e.recordId)?.project_id)};
 function calendar(large){return <section className={'calendar period-calendar memo-calendar '+(large?'is-expanded':'')}>
  <div className="section-title"><h2>{y}년 {m}월</h2><div className="period-controls"><IconButton icon={ChevronLeft} label="이전 달" onClick={()=>move(-1)}/><IconButton icon={ChevronRight} label="다음 달" onClick={()=>move(1)}/><button type="button" className="period-zoom" onClick={()=>setExpanded(!large)}>{large?<Minimize2 size={15}/>:<Maximize2 size={15}/>}<span>{large?'축소':'확대'}</span></button></div></div>
  <div className="period-weekdays">{'월화수목금토일'.split('').map(x=><span key={x}>{x}</span>)}</div>
  {weeks.map(w=>{const lanes=w.segments.length?Math.max(...w.segments.map(e=>e.lane))+1:0,overflow=w.overflow.some(Boolean),hasMemo=w.dates.some(d=>memos[d]),memoRow=lanes+2+Number(overflow);return <div className="period-week" key={w.dates[0]} style={{gridTemplateRows:'var(--memo-date-row)'+' var(--memo-event-row)'.repeat(lanes+Number(overflow))+(hasMemo?' var(--memo-note-row)':'')}}>
   {w.dates.map((date,i)=><button type="button" key={date} className={'period-date '+(date===selected?'selected ':'')+(date===D.today?'today ':'')+(!date.startsWith(month)?'outside':'')} style={{gridColumn:i+1,gridRow:1}} aria-label={date+' 일정 '+eventsOn(entries,date).length+'건'+(memos[date]?' · 내 메모 있음':'')} aria-pressed={date===selected} onClick={()=>choose(date)}>{Number(date.slice(-2))}</button>)}
   {w.segments.map(e=><button type="button" key={e.id} className={'period-bar '+e.type+(e.continuesBefore?' continues-before':'')+(e.continuesAfter?' continues-after':'')} style={{gridColumn:(e.from+1)+' / '+(e.to+2),gridRow:e.lane+2}} title={e.title+' · '+e.start} onClick={()=>open(e)}>{e.continuesBefore?'‹ ':''}{e.title}{e.continuesAfter?' ›':''}</button>)}
   {w.overflow.map((n,i)=>n>0&&<button type="button" key={'more'+i} className="period-more" style={{gridColumn:i+1,gridRow:lanes+2}} aria-label={w.dates[i]+' 숨겨진 일정 '+n+'건 보기'} onClick={()=>choose(w.dates[i])}>+{n}건</button>)}
   {w.dates.map((date,i)=>memos[date]&&<button type="button" key={'memo'+date} className="period-memo-label" style={{gridColumn:i+1,gridRow:memoRow}} aria-label={date+' 내 메모 보기: '+memos[date]} title={memos[date]} onClick={()=>choose(date)}>{large?<><StickyNote size={13}/><span className="memo-label-full">{memos[date].split('\n')[0]}</span><span className="memo-label-short">메모</span></>:'메모'}</button>)}
  </div>})}
  <div className="calendar-legend"><span className="legend-meeting"/> 회의록 <span className="legend-memo"/> 내 메모</div>
  <div className="calendar-detail-grid"><section><div className="agenda-heading"><b>{day(selected)} 일정</b><span>{events.length}건</span></div><div className="agenda">{events.length?events.slice(0,limit).map(e=><button type="button" key={e.id} onClick={()=>open(e)}><span className="agenda-dot meeting"/><span><small>회의록</small><b>{e.title}</b></span><ChevronRight size={13}/></button>):<p className="muted">등록된 일정이 없습니다.</p>}</div>{events.length>limit&&<Button small onClick={()=>setLimit(limit+8)}>일정 더 보기</Button>}</section>
   <section className="calendar-memo"><div className="calendar-memo-heading"><span><StickyNote size={16}/><b>{day(selected)} 내 메모</b></span>{ready&&!draft&&<button type="button" className="text-link" onClick={()=>setDraft({date:selected,text:memo,initial:memo})}>{memo?'수정':'메모 추가'}</button>}</div>
    {error?<p role="alert">{error} <button type="button" className="text-link" onClick={()=>setRetry(x=>x+1)}>다시 불러오기</button></p>:!ready?<p role="status" className="muted">메모를 불러오는 중…</p>:draft&&(!expanded||large)?<form onSubmit={e=>{e.preventDefault();if(draft.text.trim())save(draft.text)}}><textarea aria-label={day(selected)+' 내 메모'} placeholder="나만 볼 수 있는 날짜별 메모" rows={3} maxLength={1000} value={draft.text} onChange={e=>{setDraft({...draft,text:e.target.value});setDeleteConfirm(false)}}/><div className="calendar-memo-actions">{memo&&<Button small danger type="button" disabled={busy} onClick={()=>setDeleteConfirm(true)}>삭제</Button>}<Button small type="button" disabled={busy} onClick={()=>{setDraft(null);setPending(null);setDeleteConfirm(false)}}>취소</Button><Button small primary type="submit" disabled={busy||!draft.text.trim()}>저장</Button></div></form>:memo?<p className="calendar-memo-text">{memo}</p>:<p className="calendar-memo-empty">날짜를 선택해 메모를 남기세요.</p>}
    {deleteConfirm&&(!expanded||large)&&<div className="calendar-memo-confirm" role="alert"><p>이 날짜의 내 메모를 삭제할까요?</p><Button small disabled={busy} onClick={()=>setDeleteConfirm(false)}>유지</Button><Button small danger disabled={busy} onClick={()=>save('')}>메모 삭제</Button></div>}
   </section></div>
  {pending&&(!expanded||large)&&<div className="calendar-memo-confirm" role="alert"><p>작성 중인 메모를 저장하고 이동할까요?</p><Button small disabled={busy} onClick={()=>setPending(null)}>계속 작성</Button><Button small disabled={busy} onClick={()=>{changeSelection(pending.date,pending.month);setPending(null)}}>저장하지 않고 이동</Button><Button small primary disabled={busy||!draft?.text.trim()} onClick={()=>save(draft.text,pending)}>저장 후 이동</Button></div>}
 </section>}
 return <>{calendar(false)}{expanded&&<Modal title="캘린더 · 내 메모" close={()=>setExpanded(false)} variant="calendar-zoom" wide>{calendar(true)}</Modal>}</>;
}
