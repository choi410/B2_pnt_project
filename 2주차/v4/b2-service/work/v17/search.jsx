import React,{useState,useEffect,useRef}from'react';
import{Search,Check,FileText,ArrowRight,X,Loader2}from'lucide-react';
import{useApp,api,Status,Empty,Button,IconButton,Modal,norm}from'./app';
import{ProjectQuestion}from'./questions';
import{TaskDialog}from'./details';
import{SourceView}from'./evidence';

function Highlight({text='',terms}){
 const escaped=terms.filter(Boolean).sort((a,b)=>b.length-a.length).map(s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'));
 if(!escaped.length)return text;
 return String(text).split(new RegExp('('+escaped.join('|')+')','gi')).map((part,i)=>terms.some(t=>norm(t)===norm(part))?<mark key={i}>{part}</mark>:part);
}

function MeetingPreview({id,terms,meta}){
 const[record,setRecord]=useState(null),[error,setError]=useState(''),[original,setOriginal]=useState(false),[retry,setRetry]=useState(0);
 useEffect(()=>{let active=true;setRecord(null);setError('');setOriginal(false);
  api('/meetings/'+id).then(m=>{if(!active)return;if(m.deleted_at)setError('휴지통으로 이동한 회의록입니다. 검색 목록을 새로 확인해 주세요.');else setRecord(m)}).catch(e=>{if(active)setError(e.message)});
  return()=>{active=false};
 },[id,meta?.version,retry]);
 if(error)return <div className="keyword-preview-error" role="alert"><p>{error}</p><Button small onClick={()=>setRetry(retry+1)}>다시 불러오기</Button></div>;
 if(!record)return <p className="keyword-loading" role="status"><Loader2 className="spin" size={17}/>회의록을 불러오고 있습니다.</p>;
 const hasOriginal=record.preview_pages>0||(record.original_source&&record.original_source!==record.source);
 return <><div className="keyword-record-meta"><Status value={record.document_status}/><small>{record.date||'회의일 미정'} · v{record.revision}</small></div><h3 className="keyword-record-title"><Highlight text={record.title} terms={terms}/></h3>
  <div className="keyword-body-toolbar"><b>{original?'등록 원본':'본문 · v'+record.revision}</b>{hasOriginal&&<button className="text-link" onClick={()=>setOriginal(!original)}>{original?'검색된 본문 보기':'원본 보기'}</button>}</div>
  {original?<div className="keyword-original"><SourceView record={{...record,source:record.original_source||record.source,lines:null}} original/></div>:<div className="keyword-meeting-text">{(record.source||'').split(/\r?\n/).map((line,i)=>line.trim()?<p key={i}><Highlight text={line} terms={terms}/></p>:<div className="keyword-paragraph-gap" key={i}/>)}</div>}
 </>
}

function TaskPreview({task,terms,onOpen,buttonRef}){
 const{person}=useApp();
 return <><div className="keyword-record-meta"><Status value={task.status}/><small>{task.kind==='확인사항'?'추가 확인':'업무'}</small></div><h3 className="keyword-record-title"><Highlight text={task.title} terms={terms}/></h3>
  <dl className="keyword-task-facts"><dt>담당자</dt><dd>{person(task.kind==='확인사항'?task.reviewer_id:task.owner_id)?.name||'미지정'}</dd><dt>완료 목표일</dt><dd>{task.due||'미정'}</dd><dt>검토자</dt><dd>{task.requires_review===false?'별도 검토 없음':person(task.reviewer_id)?.name||'미지정'}</dd></dl>
  <h4>해야 할 일</h4><p className="keyword-task-text"><Highlight text={task.description||task.title} terms={terms}/></p><h4>처리 내용</h4><p className="keyword-task-text">{task.result||'아직 등록된 처리 내용이 없습니다.'}</p>
  <div className="keyword-task-open"><button ref={buttonRef} className="btn primary" onClick={onOpen}>업무 상세 열기<ArrowRight size={16}/></button></div>
 </>
}

export function SearchDialog(){
 const{D,project,setDialog}=useApp();
 const[q,setQ]=useState(''),[scope,setScope]=useState('all'),[mode,setMode]=useState('search'),[selected,setSelected]=useState(null),[taskId,setTaskId]=useState(null);
 const listRef=useRef(null),previewRef=useRef(null),taskButton=useRef(null),focusAfterClose=useRef(false);
 const terms=q.trim().split(/\s+/).filter(Boolean),match=text=>terms.length>0&&terms.every(t=>norm(text).includes(norm(t)));
 const tasks=[],meetings=D.meetings.filter(m=>match(m.title+' '+m.source));
 const currentTask=selected?.type==='task'?D.tasks.find(t=>t.id===selected.id):null,currentMeeting=selected?.type==='meeting'?D.meetings.find(m=>m.id===selected.id):null;
 useEffect(()=>{if(previewRef.current)previewRef.current.scrollTop=0},[selected?.id,selected?.type]);
 useEffect(()=>{if(focusAfterClose.current&&!taskId){focusAfterClose.current=false;taskButton.current?.focus({preventScroll:true})}},[taskId]);
 const resetSelection=()=>{setSelected(null);if(listRef.current)listRef.current.scrollTop=0};
 const closeTask=()=>{focusAfterClose.current=true;setTaskId(null)};
 function excerpt(text=''){const idx=norm(text).indexOf(norm(terms[0]));return (idx>40?'…':'')+text.slice(Math.max(0,idx-40),Math.max(0,idx-40)+160)+(text.length>160?'…':'')}
 const count=(scope==='task'?0:meetings.length)+(scope==='meeting'?0:tasks.length);
 return <><Modal wide variant="search-assistant" title="회의록 검색·AI 질문" close={()=>setDialog(null)}>
  <div className="tabs search-mode-tabs"><button className={mode==='search'?'active':''} onClick={()=>setMode('search')}>검색</button><button className={mode==='ask'?'active':''} onClick={()=>setMode('ask')}>AI 질문</button></div>
  <div hidden={mode!=='ask'}><ProjectQuestion/></div>
  <div hidden={mode!=='search'}>
   <label className="search search-large"><Search size={21}/><input autoFocus value={q} onChange={e=>{setQ(e.target.value);resetSelection()}} placeholder="사양, 고객 요구, 회의 내용 검색" aria-label="전체 검색어"/></label>
   <p className="field-note">저장된 원문에서 검색어가 포함된 근거를 찾습니다.</p>

   <div className={'keyword-workspace '+(selected?'has-preview':'')}>
    <div ref={listRef} className="search-results keyword-results" aria-label="검색 결과 목록">
     {scope!=='task'&&meetings.map(m=><button key={'meeting-'+m.id} aria-pressed={selected?.type==='meeting'&&selected.id===m.id} onClick={()=>setSelected({type:'meeting',id:m.id})}><FileText size={18}/><span><small>회의록 · {project(m.project_id)?.name} · {m.date||'회의일 미정'}</small><b><Highlight text={m.title} terms={terms}/></b><p><Highlight text={excerpt(m.source||'')} terms={terms}/></p></span><ArrowRight size={16}/></button>)}
     {scope!=='meeting'&&tasks.map(t=><button key={'task-'+t.id} aria-pressed={selected?.type==='task'&&selected.id===t.id} onClick={()=>setSelected({type:'task',id:t.id})}><Check size={18}/><span><small>업무 · {project(t.project_id)?.name||t.project_id}</small><b><Highlight text={t.title} terms={terms}/></b><p><Highlight text={excerpt(t.description||'')} terms={terms}/></p><Status value={t.status}/></span><ArrowRight size={16}/></button>)}
     {q&&!count&&<Empty title="검색 결과가 없습니다" text="더 짧은 단어나 다른 표현으로 검색해 보세요."/>}{!q&&<Empty title="찾고 싶은 내용을 입력하세요" text="예: 커버, 시운전, 속도, 납기"/>}
    </div>
    {selected&&<section className="keyword-preview" aria-label="검색 결과 미리보기"><header><div><b>{selected.type==='meeting'?'회의록 미리보기':'업무 미리보기'}</b><small>{project((currentTask||currentMeeting)?.project_id)?.name}</small></div><IconButton icon={X} label="미리보기 닫기" onClick={()=>setSelected(null)}/></header><div ref={previewRef} className="keyword-preview-scroll">
     {selected.type==='meeting'?(currentMeeting?<MeetingPreview key={selected.id} id={selected.id} meta={currentMeeting} terms={terms}/>:<p>이 회의록은 현재 검색 목록에서 확인할 수 없습니다.</p>):currentTask?<TaskPreview task={currentTask} terms={terms} onOpen={()=>setTaskId(currentTask.id)} buttonRef={taskButton}/>:<p>이 업무는 현재 검색 목록에서 확인할 수 없습니다.</p>}
    </div></section>}
   </div>
  </div>
 </Modal>{taskId&&<TaskDialog key={taskId} id={taskId} onClose={closeTask}/>}</>
}
