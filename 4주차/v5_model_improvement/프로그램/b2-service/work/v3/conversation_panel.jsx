import React,{useState,useEffect,useLayoutEffect,useRef} from 'react';
import {createPortal} from 'react-dom';
import {Sparkles,FileText,FolderOpen,Loader2,X,ArrowUp,ArrowUpRight,SquarePen,History,MoreHorizontal,Trash2,ChevronRight,Pencil} from 'lucide-react';
import {api,Button,Modal} from './app';
import {groupedMeetings} from './chat_results.mjs';

const phases={queued:'질문 대기 중',searching:'회의록을 찾는 중',waiting_model:'다른 AI 분석이 끝나면 답변합니다.',answering:'근거를 확인하며 답변하는 중'};
const active=m=>!['done','failed'].includes(m.state);
const day=s=>s?s.slice(0,10).replaceAll('-','.'):'날짜 미정';
const hour=s=>s?new Date(s).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',hour12:false}):'';
function fitInput(el){if(!el)return;el.style.height='0px';const style=getComputedStyle(el);el.style.height=Math.min(parseFloat(style.maxHeight),Math.max(parseFloat(style.minHeight),el.scrollHeight))+'px'}
const historyDate=s=>{const d=new Date(s);return Number.isNaN(d.getTime())?'':d.toLocaleDateString('sv-SE',{timeZone:'Asia/Seoul'})};
function historyGroup(s){const d=historyDate(s),today=historyDate(new Date()),yesterday=historyDate(Date.now()-86400000),week=historyDate(Date.now()-6*86400000);return d===today?'오늘':d===yesterday?'어제':d>=week?'지난 7일':'이전 대화'}
const historyStamp=s=>historyDate(s)===historyDate(new Date())?hour(s):day(s);

function MeetingSearchResults({result,onOpen}){
 const [page,setPage]=useState(0),items=result.meetings||[],size=5,pages=Math.max(1,Math.ceil(items.length/size));
 return <div className="chat-meeting-results">
  {result.project_counts?.length>0&&<details className="chat-result-counts"><summary>프로젝트별 검색 건수</summary><ul>{result.project_counts.map(p=><li key={p.project_id}>{p.project_name} <b>{p.count}건</b></li>)}</ul></details>}
  <ol start={page*size+1}>{items.slice(page*size,(page+1)*size).map(item=><li key={item.source_id}><button onClick={e=>onOpen(result.sources.find(s=>s.id===item.source_id),e.currentTarget)}><span className="chat-meeting-meta">{day(item.date)} · {item.project_name}</span><strong>{item.title}</strong>{item.snippet&&<span className="chat-meeting-snippet">{item.snippet}</span>}<span className="chat-meeting-open">{item.matched_lines?'관련 원문 '+item.matched_lines+'개 보기':'원문에서 보기'} <ChevronRight size={13}/></span></button></li>)}</ol>
  {pages>1&&<nav className="chat-meeting-pages" aria-label="검색 회의록 페이지"><button disabled={page===0} onClick={()=>setPage(page-1)}>이전</button><span>{page+1} / {pages} · {items.length}건</span><button disabled={page===pages-1} onClick={()=>setPage(page+1)}>다음</button></nav>}
 </div>;
}

function MeetingLookupResults({result,onOpen}){
 const [page,setPage]=useState(0),size=8,groups=groupedMeetings(result),items=groups.flatMap(g=>g.items.map(item=>({item,group:g}))),pages=Math.max(1,Math.ceil(items.length/size));
 const visible=items.slice(page*size,(page+1)*size);
 return <div className="chat-lookup-results">
  {result.group_by&&<div className="chat-lookup-counts">{groups.map(g=><span key={g.key}>{g.label} <b>{g.items.length}건</b></span>)}</div>}
  {visible.map(({item,group},i)=><React.Fragment key={item.source_id}>
   {result.group_by&&(i===0||visible[i-1].group.key!==group.key)&&<h4>{group.label} <small>{group.items.length}건</small></h4>}
   <button className="chat-lookup-row" onClick={e=>onOpen(result.sources.find(s=>s.id===item.source_id),e.currentTarget)}>
    <span className="chat-lookup-date">{day(item.group_date||item.date)}</span>
    <span><strong>{item.title}</strong><small>{item.project_name}{result.lookup_order==='registered_at'?' · 회의일 '+day(item.date):''}</small></span>
    <ChevronRight size={16}/>
   </button>
  </React.Fragment>)}
  {pages>1&&<nav className="chat-meeting-pages" aria-label="조회 회의록 페이지"><button disabled={!page} onClick={()=>setPage(page-1)}>이전</button><span>{page+1} / {pages} · {items.length}건</span><button disabled={page===pages-1} onClick={()=>setPage(page+1)}>다음</button></nav>}
 </div>;
}

function sourceLineKind(text){
 const heading=text.trim().replace(/^#{1,6}\s+|^(?:\d{1,2}[.)]|[가-하][.)])\s+/,'').replace(/[:：]\s*$/,'');
 const sections=/^(?:회의록|회의\s*(?:개요|정보|안건|내용|목적)|핵심\s*요약|주요\s*(?:논의|내용|안건)|논의\s*(?:내용|사항)|결정\s*(?:사항|내용)|합의\s*사항|추가\s*(?:확인\s*사항|요청)|확인\s*사항|후속\s*조치|향후\s*(?:계획|일정)|요구\s*사항|변경\s*사항|검토\s*사항|안건|결론)$/;
 if(sections.test(heading)||/^#{1,6}\s+\S/.test(text)&&text.length<70)return 'heading';
 if(/^(?:회의명|회의\s*제목|회의일|일시|장소|프로젝트|고객사|참석자|작성자)\s*[:：]/.test(text))return 'meta';
 if(/^(?:\d{1,3}[.)]|[-•·▪○])\s+/.test(text))return 'item';
 return 'paragraph';
}
function SourceLine({line,highlight}){
 const kind=sourceLineKind(line.text),Tag=kind==='heading'?'h3':'p';
 const parts=kind==='item'?line.text.match(/^((?:\d{1,3}[.)]|[-•·▪○])\s+)([\s\S]*)$/):kind==='meta'?line.text.match(/^([^:：]+[:：]\s*)([\s\S]*)$/):null;
 return <Tag data-source-line={line.id} className={'chat-source-line source-'+kind+(highlight?' highlight':'')}>{parts?<><span className="source-prefix">{parts[1]}</span><span>{parts[2]}</span></>:line.text}</Tag>;
}

function SourceDialog({source,busy,error,onRetry,onClose,backgroundRef}){
 const body=useRef(null),closeButton=useRef(null),preview=source.preview;
 function goToEvidence(){
  const box=body.current,row=box?.querySelector('.highlight');if(!box||!row)return;
  const heading=[...box.querySelectorAll('.source-heading')].filter(el=>el.compareDocumentPosition(row)&Node.DOCUMENT_POSITION_FOLLOWING).at(-1);
  const anchor=heading&&row.offsetTop-heading.offsetTop<box.clientHeight*.45?heading:row;
  const delta=anchor.getBoundingClientRect().top-box.getBoundingClientRect().top;
  box.scrollTop=Math.max(0,box.scrollTop+delta-24);
 }
 useLayoutEffect(()=>{
  const background=backgroundRef.current?.closest('.chat-dialog'),wasInert=background?.inert;
  closeButton.current?.focus({preventScroll:true});if(background)background.inert=true;
  return()=>{if(background)background.inert=wasInert};
 },[backgroundRef]);
 useLayoutEffect(()=>{
  const box=body.current;if(!box)return;box.scrollTop=0;
  goToEvidence();
 },[preview]);
 function handleKeys(e){
  if(e.key==='Escape'){e.preventDefault();e.stopPropagation();onClose();return}
  if(e.key!=='Tab')return;
  const controls=[...e.currentTarget.querySelectorAll('button:not([disabled]),a[href],[tabindex]:not([tabindex="-1"])')],first=controls[0],last=controls.at(-1);
  if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}
  else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}
 }
 return createPortal(<div className="chat-source-overlay" onMouseDown={e=>{if(e.target===e.currentTarget){e.stopPropagation();onClose()}}}>
  <section className="chat-source-dialog" role="dialog" aria-modal="true" aria-label="원문 근거" aria-describedby="chat-source-title" onKeyDown={handleKeys}>
   <header><div><p className="chat-source-label">원문 근거</p><h2 id="chat-source-title">{preview?.title||source.title||'회의록 원문'}</h2><p className="chat-source-details">{preview?.project_name||source.project_name}{(preview?.project_name||source.project_name)&&' · '}회의일 {day(preview?.date||source.date)}{preview&&<span> · 답변 당시 원문 v{preview.revision}</span>}</p></div><button ref={closeButton} className="icon-button" aria-label="원문 근거 닫기" onClick={onClose}><X size={22}/></button></header>
   {!busy&&!error&&preview?.highlight?.length>0&&<div className="chat-source-reading-tools"><span><i aria-hidden="true"/>답변 근거 {preview.highlight.length}곳 강조</span><button onClick={goToEvidence}>근거로 이동</button></div>}
   {busy?<div className="chat-source-status" role="status"><Loader2 className="spin" size={20}/>원문을 불러오는 중…</div>:error?<div className="chat-source-status"><p role="alert">{error}</p><Button onClick={onRetry}>다시 불러오기</Button></div>:preview?<div className="chat-source-body" ref={body} tabIndex={0} role="region" aria-label="회의록 원문"><article className="chat-source-document">{preview.lines.length?preview.lines.map(line=><SourceLine key={line.id} line={line} highlight={preview.highlight?.includes(line.id)}/>):<p className="muted">표시할 원문 내용이 없습니다.</p>}</article></div>:null}
  </section>
 </div>,document.body);
}

export function QuestionPanel({D,open,close,onOpenProject}){
 const[list,setList]=useState([]),[thread,setThread]=useState(null),[draft,setDraft]=useState(''),[sending,setSending]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState('');
 const[side,setSide]=useState(null),[source,setSource]=useState(null),[sourceBusy,setSourceBusy]=useState(false),[sourceError,setSourceError]=useState(''),[menu,setMenu]=useState(''),[deleting,setDeleting]=useState(null),[deleteBusy,setDeleteBusy]=useState(false),[historyOpen,setHistoryOpen]=useState(false);
 const[renaming,setRenaming]=useState(null),[renameBusy,setRenameBusy]=useState(false),[renameError,setRenameError]=useState('');
 const renameInput=useRef(null),renameTrigger=useRef(null),renameSeq=useRef(0),titleOverrides=useRef(new Map());
 const turnSeq=useRef(0),sourceSeq=useRef(0),listSeq=useRef(0),input=useRef(null),chatScroll=useRef(null),sourceReturn=useRef(null),followBottom=useRef(true),currentId=useRef('');
 currentId.current=thread?.id||'';
 const pending=thread?.messages.some(active),otherPending=list.some(t=>t.pending&&t.id!==thread?.id);
 const withTitle=t=>t&&titleOverrides.current.has(t.id)?{...t,title:titleOverrides.current.get(t.id)}:t;
 async function refreshList(){const n=++listSeq.current;try{const r=await api('/conversations');if(n===listSeq.current)setList(r.items.map(withTitle))}catch(e){if(n===listSeq.current)setError(e.message)}}
 function cancelRename(restore=true){if(renameBusy)return;renameSeq.current++;setRenaming(null);setRenameError('');if(restore)requestAnimationFrame(()=>renameTrigger.current?.isConnected&&renameTrigger.current.focus({preventScroll:true}))}
 function beginRename(item,trigger){renameSeq.current++;renameTrigger.current=trigger;setMenu('');setRenaming({id:item.id,title:item.title});setRenameError('')}
 useLayoutEffect(()=>{if(renaming){renameInput.current?.focus({preventScroll:true});renameInput.current?.select()}},[renaming?.id]);
 async function saveRename(e){
  e.preventDefault();if(!renaming||renameBusy||!renaming.title.trim())return;
  const n=renameSeq.current,id=renaming.id;setRenameBusy(true);setRenameError('');
  try{const r=await api('/conversations/'+id,'PATCH',{title:renaming.title});titleOverrides.current.set(id,r.title);listSeq.current++;setList(items=>items.map(item=>item.id===id?{...item,title:r.title}:item));setThread(t=>t?.id===id?{...t,title:r.title}:t);if(n===renameSeq.current){setRenaming(null);requestAnimationFrame(()=>renameTrigger.current?.isConnected&&renameTrigger.current.focus({preventScroll:true}))}}
  catch(e){if(n===renameSeq.current)setRenameError(e.message)}finally{setRenameBusy(false)}
 }
 function clearSource(restore=false){sourceSeq.current++;setSource(null);setSourceBusy(false);setSourceError('');const previous=sourceReturn.current;sourceReturn.current=null;if(restore&&previous)requestAnimationFrame(()=>{if(chatScroll.current)chatScroll.current.scrollTop=previous.top;if(previous.element?.isConnected)previous.element.focus({preventScroll:true})})}
 function closeSource(){clearSource(true)}
 function clearSide(){setSide(null);clearSource()}
 function closeHistoryOnSmallScreen(){if(window.matchMedia('(max-width:850px)').matches)setHistoryOpen(false)}
 function startNew(){turnSeq.current++;cancelRename(false);setThread(null);currentId.current='';setDraft('');setError('');setLoading(false);setMenu('');clearSide();followBottom.current=true;input.current?.focus()}
 useLayoutEffect(()=>{
  turnSeq.current++;sourceSeq.current++;
  if(open){titleOverrides.current.clear();startNew();refreshList()}else{listSeq.current++;renameSeq.current++;setRenaming(null);setRenameError('');setMenu('');setDeleting(null);setHistoryOpen(false)}
 },[open]);
 useEffect(()=>()=>{turnSeq.current++;sourceSeq.current++;listSeq.current++},[]);
 useLayoutEffect(()=>{if(open)fitInput(input.current)},[open,draft,historyOpen,side]);
 useEffect(()=>{if(!open||!input.current)return;let width=-1;const observer=new ResizeObserver(entries=>{const next=entries[0].contentRect.width;if(next!==width){width=next;fitInput(input.current)}});observer.observe(input.current);return()=>observer.disconnect()},[open]);
 useEffect(()=>{
  if(!open||!pending||!thread?.id)return;
  let valid=true,busy=false;const id=thread.id,n=turnSeq.current;
  const timer=setInterval(async()=>{if(busy)return;busy=true;try{const r=await api('/conversations/'+id);if(valid&&n===turnSeq.current&&currentId.current===id){setThread(withTitle(r));setError('');if(!r.messages.some(active))refreshList()}}catch(e){if(valid&&n===turnSeq.current)setError(e.message)}finally{busy=false}},1200);
  return()=>{valid=false;clearInterval(timer)};
 },[open,thread]);
 useEffect(()=>{
  if(!open||!list.some(t=>t.pending)||pending)return;
  const timer=setInterval(refreshList,2000);return()=>clearInterval(timer);
 },[open,list,pending]);
 const tail=thread?.messages.at(-1);
 useEffect(()=>{if(open&&!source&&followBottom.current&&chatScroll.current)chatScroll.current.scrollTop=chatScroll.current.scrollHeight},[open,thread?.id,tail?.id,tail?.state,loading]);
 useEffect(()=>{if(!menu)return;const handler=e=>{if(!e.target.closest('.chat-history-row'))setMenu('')};document.addEventListener('click',handler);return()=>document.removeEventListener('click',handler)},[menu]);
 async function selectThread(id){
  if(sending)return;
  const n=++turnSeq.current;cancelRename(false);clearSide();setMenu('');setError('');setLoading(true);setDraft('');closeHistoryOnSmallScreen();followBottom.current=true;
  try{const r=await api('/conversations/'+id);if(n===turnSeq.current){setThread(withTitle(r));currentId.current=id}}
  catch(e){if(n===turnSeq.current)setError(e.message)}finally{if(n===turnSeq.current)setLoading(false)}
 }
 async function send(e,question=draft,projectId=null,meetingId=null){
  e?.preventDefault();const text=question.trim();if(text.length<2||sending||pending||otherPending)return;
  const n=++turnSeq.current,cid=thread?.id||null;setSending(true);setError('');setMenu('');clearSide();followBottom.current=true;
  try{const r=await api('/conversations/questions','POST',{conversation_id:cid,project_id:projectId,meeting_id:meetingId,question:text});if(n===turnSeq.current){setThread(withTitle(r));currentId.current=r.id;setDraft('')}refreshList()}
  catch(e){if(n===turnSeq.current)setError(e.message)}finally{setSending(false)}
 }
 async function showSource(message,item,trigger){
  if(!source)sourceReturn.current={element:trigger||document.activeElement,top:chatScroll.current?.scrollTop||0};
  const n=++sourceSeq.current,cid=thread.id;setSource({...item,mid:message.id,sid:item.id});setSourceBusy(true);setSourceError('');
  try{const r=await api('/conversations/'+cid+'/messages/'+message.id+'/sources/'+item.id);if(n===sourceSeq.current)setSource({...item,mid:message.id,sid:item.id,preview:r})}
  catch(e){if(n===sourceSeq.current)setSourceError(e.message)}finally{if(n===sourceSeq.current)setSourceBusy(false)}
 }
 function showProject(id){clearSide();setSide({kind:'project',id});closeHistoryOnSmallScreen()}
 async function removeThread(){
  if(!deleting||deleteBusy)return;setDeleteBusy(true);setError('');
  try{await api('/conversations/'+deleting.id,'DELETE');if(thread?.id===deleting.id)startNew();setDeleting(null);setMenu('');await refreshList()}
  catch(e){setError(e.message);setDeleting(null)}finally{setDeleteBusy(false)}
 }
 if(!open)return null;
 const sourceMessage=source?thread?.messages.find(m=>m.id===source.mid):null;
 const project=side?.kind==='project'?D.projects.find(p=>p.id===side.id):null;
 const latestMeeting=project&&(D.meetings||[]).filter(m=>m.project_id===project.id).sort((a,b)=>(b.date||'').localeCompare(a.date||'')||(b.created_at||'').localeCompare(a.created_at||''))[0];

 return <Modal wide className="chat-dialog" title="AI" close={source?closeSource:close}>
  <div className="chat-toolbar"><span className="chat-current-title" title={thread?.title||'새 대화'}>{thread?.title||'새 대화'}</span><div className="chat-toolbar-actions"><Button className="chat-history-toggle" icon={History} aria-expanded={historyOpen} aria-controls="ai-chat-history" onClick={()=>{setHistoryOpen(!historyOpen);setMenu('')}}>최근 대화</Button><Button icon={SquarePen} disabled={sending||renameBusy} onClick={startNew}>새 대화</Button></div></div>
  <div className={'chat-layout '+(side?'has-context ':'')+(historyOpen?'history-open':'')}>
   <aside id="ai-chat-history" className="chat-history" aria-label="최근 대화"><div className="chat-history-heading"><h3>최근 대화 <span className="chat-history-count" aria-label={list.length+'개 대화'}>{list.length}</span></h3><button className="icon-button chat-history-close" aria-label="대화 목록 닫기" onClick={()=>setHistoryOpen(false)}><X size={16}/></button></div>
    <div className="chat-history-scroll">{list.length?list.map((item,index)=><React.Fragment key={item.id}>
     {(index===0||historyGroup(item.updated_at)!==historyGroup(list[index-1].updated_at))&&<h4 className="chat-history-group-label">{historyGroup(item.updated_at)}</h4>}
     <div className={'chat-history-row '+(thread?.id===item.id?'selected ':'')+(renaming?.id===item.id?'editing':'')} onKeyDown={e=>{if(e.key==='Escape'&&menu===item.id){e.preventDefault();e.stopPropagation();setMenu('');e.currentTarget.querySelector('.chat-more')?.focus()}}}>
     {renaming?.id===item.id?<form className="chat-rename-form" onSubmit={saveRename} onKeyDown={e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();cancelRename()}if(e.key==='Enter'&&e.nativeEvent.isComposing)e.preventDefault()}}>
      <label htmlFor="chat-rename-title">대화 이름</label><input ref={renameInput} id="chat-rename-title" maxLength={60} value={renaming.title} disabled={renameBusy} aria-invalid={!!renameError} aria-describedby={renameError?'chat-rename-error':undefined} onChange={e=>{setRenaming({...renaming,title:e.target.value});setRenameError('')}}/>
      {renameError&&<p id="chat-rename-error" role="alert">{renameError}</p>}<div className="chat-rename-actions"><small>{renaming.title.length}/60</small><button type="button" disabled={renameBusy} onClick={()=>cancelRename()}>취소</button><button type="submit" disabled={renameBusy||!renaming.title.trim()}>{renameBusy?<Loader2 className="spin" size={14}/>:null}{renameBusy?'저장 중':'저장'}</button></div>
     </form>:<button className="chat-history-select" disabled={sending||renameBusy} title={item.title} aria-pressed={thread?.id===item.id} onClick={()=>selectThread(item.id)}><span>{item.title}</span><small>{item.pending?<><Loader2 className="spin" size={11}/>답변 중</>:historyStamp(item.updated_at)}</small></button>}
     <button className="icon-button chat-more" aria-label={item.title+' 대화 메뉴'} aria-expanded={menu===item.id} disabled={renameBusy||renaming?.id===item.id} onClick={()=>setMenu(menu===item.id?'':item.id)}><MoreHorizontal size={17}/></button>
     {menu===item.id&&<div className="chat-row-menu"><button disabled={item.pending||sending||renameBusy} title={item.pending?'답변 생성이 끝난 뒤 수정할 수 있습니다.':''} onClick={e=>beginRename(item,e.currentTarget.closest('.chat-history-row').querySelector('.chat-more'))}><Pencil size={14}/>이름 수정</button><button className="chat-delete-action" disabled={item.pending||sending||renameBusy} title={item.pending?'답변 생성이 끝난 뒤 삭제할 수 있습니다.':''} onClick={()=>{setDeleting(item);setMenu('')}}><Trash2 size={14}/>삭제</button></div>}
    </div></React.Fragment>):<div className="chat-history-empty"><Sparkles size={22}/><p>아직 저장된 대화가 없습니다.</p><small>질문을 보내면 여기에 모입니다.</small></div>}</div>
   </aside>
   <section className="chat-center" aria-label="대화">
    <div className="chat-messages" ref={chatScroll} onScroll={e=>{const b=e.currentTarget;followBottom.current=b.scrollHeight-b.scrollTop-b.clientHeight<90}}>
     {loading?<p className="chat-loading" role="status"><Loader2 className="spin" size={18}/>대화를 불러오는 중…</p>:thread?.messages.length?thread.messages.map(message=>{
      const result=message.result,groups=Object.values((result?.points||[]).reduce((out,p)=>{const id=p.project_id||'all';(out[id]??={id,name:p.project_name||D.projects.find(x=>x.id===id)?.name||'',points:[]}).points.push(p);return out},{}));
      return <article className="chat-turn" key={message.id} aria-label="질문과 답변"><div className="chat-user-row"><p className="chat-user-message">{message.question}</p></div><div className="chat-assistant"><div className="chat-speaker"><Sparkles size={15}/><b>PNT AI</b><time title={message.completed_at||message.created_at}>{hour(message.completed_at||message.created_at)}</time></div>
       {active(message)?<p className="chat-loading" role="status"><Loader2 className="spin" size={17}/>{phases[message.state]||'답변 준비 중'}</p>:message.state==='failed'?<div className="chat-answer-error"><p role="alert">{message.error||'답변을 완료하지 못했습니다.'}</p><button onClick={()=>{setDraft(message.question);input.current?.focus()}}>질문 다시 입력</button></div>:<>
        {message.context_label&&<p className="chat-answer-note">조회 범위 · {message.context_label}</p>}
        {result?.message&&<p className="chat-answer-text">{result.message}</p>}
        {result?.mode==='meeting_search'&&<MeetingSearchResults result={result} onOpen={(s,button)=>showSource(message,s,button)}/>}
        {result?.mode==='meeting_lookup'&&result.meetings&&<MeetingLookupResults result={result} onOpen={(s,button)=>showSource(message,s,button)}/>}
        {(result?.mode==='meeting_lookup'&&result.meetings?[]:groups).map(g=><section className="chat-answer-group" key={g.id}>{g.name&&<h3><FolderOpen size={15}/>{g.name}</h3>}{g.points.map((point,index)=><div className="chat-point" key={index}><p className="chat-answer-text">{point.text}</p>{point.sources?.length>0&&<div className="chat-proof-links">{point.sources.map(id=>{const s=result.sources?.find(s=>s.id===id);return s&&<button key={id} aria-pressed={source?.mid===message.id&&source?.sid===id} title={s.title} onClick={e=>showSource(message,s,e.currentTarget)}><FileText size={14}/>{result.mode==='meeting_lookup'?'회의록 보기':'원문 근거'} <span>{day(s.date)}</span><ChevronRight size={13}/></button>})}</div>}</div>)}</section>)}
        {result?.kind==='projects'&&<div className="chat-project-results">{result.projects?.map(p=><button key={p.id} onClick={()=>showProject(p.id)}><FolderOpen size={17}/><span><small>{p.id} · PM {p.pm}</small><strong>{p.name}</strong>{p.created_at&&<small className="chat-project-date">생성일 {day(p.created_at)}</small>}</span><ChevronRight size={16}/></button>)}</div>}
        {result?.kind==='clarification'&&result.projects?.length>0&&<div className="chat-project-choices">{result.projects.map(p=><Button key={p.id} disabled={sending||pending||otherPending} onClick={()=>send(null,message.question,p.id)}>{p.name}</Button>)}</div>}
        {result?.kind==='clarification'&&result.meetings?.length>0&&<div className="chat-project-choices">{result.meetings.map(m=><Button key={m.id} disabled={sending||pending||otherPending} onClick={()=>send(null,message.question,null,m.id)}>{day(m.date)} · {m.title}</Button>)}</div>}
        {result?.notice&&<p className="chat-answer-note">{message.context_label&&result.notice.startsWith(message.context_label)?result.notice.slice(message.context_label.length).replace(/^ · /,''):result.notice}</p>}
        {result?.omitted_projects?.length>0&&<p className="chat-answer-note">답변에 포함되지 않은 프로젝트: {result.omitted_projects.map(p=>p.name).join(', ')}</p>}
       </>}
      </div></article>;
     }):<div className="chat-welcome"><Sparkles size={28}/><h3>무엇이 궁금하세요?</h3><p>프로젝트와 회의 내용을 물어보세요.</p><div className="chat-examples">{['롤프레스 프로젝트 찾아줘','현재 납품일은 언제야?','최근 회의에서 보류된 사항은?'].map(q=><button key={q} disabled={sending} onClick={()=>{setDraft(q);input.current?.focus()}}>{q}</button>)}</div></div>}
    </div>
    <div className="chat-compose-area">{error&&<p className="chat-form-error" role="alert">{error}</p>}{otherPending&&<p className="chat-compose-note">다른 대화의 답변이 끝나면 질문을 보낼 수 있습니다.</p>}<form className="chat-composer" onSubmit={send}><textarea ref={input} autoFocus rows={1} maxLength={500} disabled={sending||pending} aria-label="질문 입력" placeholder={thread?'이어서 물어보세요':'궁금한 내용을 입력하세요'} value={draft} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();send(e)}}}/><button type="submit" className="chat-send" aria-label="질문 보내기" disabled={sending||pending||otherPending||draft.trim().length<2}>{sending||pending?<Loader2 className="spin" size={19}/>:<ArrowUp size={20}/>}</button></form><p className="chat-compose-note">답변의 근거는 회의록에서 확인할 수 있습니다.</p></div>
   </section>
   {side&&<aside className="chat-context" aria-label="프로젝트 정보"><div className="chat-context-heading"><h3>프로젝트 정보</h3><button className="icon-button" aria-label="프로젝트 정보 닫기" onClick={clearSide}><X size={18}/></button></div>
    {project?<div className="chat-context-scroll"><small className="muted">{project.id}</small><h2 className="chat-project-title">{project.name}</h2><dl className="chat-project-info"><dt>프로젝트 PM</dt><dd>{D.people.find(p=>p.id===project.pm)?.name||'미정'}</dd><dt>최근 회의</dt><dd>{latestMeeting?<>{day(latestMeeting.date)}<p>{latestMeeting.title}</p></>:'등록된 회의록이 없습니다.'}</dd></dl><Button primary icon={ArrowUpRight} onClick={()=>onOpenProject(project.id)}>변경이력 보기</Button></div>:<p>현재 접근할 수 없는 프로젝트입니다.</p>}
   </aside>}
  </div>
  {source&&<SourceDialog source={source} busy={sourceBusy} error={sourceError} onRetry={()=>showSource(sourceMessage,source)} onClose={closeSource} backgroundRef={chatScroll}/>}
  {deleting&&<div className="chat-delete-overlay"><section className="chat-delete-confirm" role="alertdialog" aria-modal="true" aria-labelledby="chat-delete-heading"><h3 id="chat-delete-heading">이 대화를 삭제할까요?</h3><p>{deleting.title}</p><p className="muted">질문·답변 기록이 삭제됩니다. 회의록과 프로젝트 자료는 유지됩니다.</p><div className="actions"><Button disabled={deleteBusy} onClick={()=>setDeleting(null)}>취소</Button><Button primary disabled={deleteBusy} icon={Trash2} onClick={removeThread}>대화 삭제</Button></div></section></div>}
 </Modal>;
}
