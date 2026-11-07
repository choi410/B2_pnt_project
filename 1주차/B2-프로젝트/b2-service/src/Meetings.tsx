import React, {useEffect, useRef, useState} from 'react';
import {AlertTriangle, ArrowLeft, ArrowRight, Check, CheckCheck, ChevronRight, CircleCheckBig, CircleDot, CircleHelp, ClipboardList, Download, FileText, FolderOpen, GitCompareArrows, Layers3, LoaderCircle, Plus, Search, ShieldCheck, Sparkles, Trash2, Upload, UserCheck, X} from 'lucide-react';

type Item={category:'고객요구'|'설계변경'|'할일';content:string;owner:string|null;due:string|null;agreement:string|null;evidence_ids:string[]};
type Point={content:string;evidence_ids:string[]};
type Analysis={summary:string;items:Item[];review_points:Point[]};
type Input={project:string;title:string;meeting_date:string;source:string;warnings:string[]};
type LinkedWork={id:string;source_index:number;category:string;content:string;owner:string|null;due:string|null;agreement:string|null;status:string|null;version:number;updated_at:string};
type Meeting=Input&{reference_info:{project_id:string;code:string;seq:number;event_count:number}|null;id:string;status:string;version:number;created_at:string;updated_at:string;reviewer_id:string|null;reviewer_name:string|null;reviewed_at:string|null;analysis:Analysis|null;reviewed:Analysis|null;error:string|null;metrics:{seconds:number;attempts:number;model:string}|null;lines:{id:string;text:string}[];work_items:LinkedWork[]};
type Row=Pick<Meeting,'id'|'title'|'project'|'meeting_date'|'status'|'created_at'|'updated_at'|'reference_info'>&{item_count:number;review_count:number};
const blank:Input={project:'',title:'',meeting_date:'',source:'',warnings:[]};
const empty:Analysis={summary:'',items:[],review_points:[]};
const statusLabel:Record<string,string>={queued:'분석 대기',analyzing:'AI 분석 중',review:'검토 대기',failed:'직접 검토 필요',saved:'검토 저장 완료'};
type ActionBucket='need'|'doing'|'done';
const bucketLabel:Record<ActionBucket,string>={need:'조치 필요',doing:'조치',done:'완료'};
const itemComparable=(item:Item)=>({category:item.category,content:item.content,owner:item.owner,due:item.due,agreement:item.agreement,evidence_ids:[...item.evidence_ids].sort()});
function draftMatch(item:Item,index:number,analysis:Analysis|null){
 if(!analysis)return null;
 const evidence=new Set(item.evidence_ids);
 return analysis.items.find(candidate=>candidate.category===item.category&&candidate.evidence_ids.some(id=>evidence.has(id)))||analysis.items[index]||null;
}
function changeKind(item:Item,index:number,analysis:Analysis|null){
 const before=draftMatch(item,index,analysis);if(!before)return '사용자 추가';
 return JSON.stringify(itemComparable(before))===JSON.stringify(itemComparable(item))?'':'변경됨';
}
const dateTime=(value:string)=>new Intl.DateTimeFormat('ko-KR',{year:'numeric',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Seoul'}).format(new Date(value));
async function api<T>(path:string,options?:RequestInit):Promise<T>{
 const response=await fetch('/api'+path,options);
 const result=await response.json();
 if(!response.ok) throw new Error(typeof result.detail==='string'?result.detail:'입력한 항목과 날짜, 근거를 확인해 주세요.');
 return result;
}
const json=(body:unknown):RequestInit=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export function Meetings({project='',initialId='',startNew=false,actorId='pm',onRegistered,onOpenWork,onOpenRequirements,onDirtyChange}:{project?:string;initialId?:string;startNew?:boolean;actorId?:string;onRegistered:()=>void;onOpenWork:(project:string)=>void;onOpenRequirements?:(projectId:string)=>void;onDirtyChange:(dirty:boolean)=>void}){
 const [view,setView]=useState<'list'|'input'|'review'>(startNew?'input':'list');
 const [rows,setRows]=useState<Row[]>([]); const [input,setInput]=useState<Input>({...blank,project});
 const [record,setRecord]=useState<Meeting|null>(null); const [draft,setDraft]=useState<Analysis>(empty);
 const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');
 const [confirmed,setConfirmed]=useState(false);const [highlight,setHighlight]=useState<string[]>([]);
 const [query,setQuery]=useState('');const [filter,setFilter]=useState('all');const [help,setHelp]=useState(false);
 const [savedFilter,setSavedFilter]=useState<'all'|ActionBucket>('all');
 const [dirty,setDirty]=useState(false); const fileRef=useRef<HTMLInputElement>(null);
 useEffect(()=>{window.scrollTo({top:0});},[view]);
 const pending=record && ['queued','analyzing'].includes(record.status);
 const saved=record?.status==='saved';
 async function refresh(){try{setRows((await api<Row[]>('/meetings')).filter(r=>!project||(r.project||'미분류')===project));}catch(e){setError((e as Error).message);}}
 useEffect(()=>{onDirtyChange(dirty);},[dirty]);
 useEffect(()=>{if(initialId)openRecord(initialId);},[initialId]);
 useEffect(()=>{refresh(); const interval=setInterval(refresh,6000);return()=>clearInterval(interval);},[]);
 useEffect(()=>{
  if(!record || !pending)return;
  const id=record.id;let cancelled=false;
  const timer=setInterval(async()=>{
   try{const next=await api<Meeting>('/meetings/'+id);if(cancelled)return;
    setRecord(next);if(!['queued','analyzing'].includes(next.status)){setDraft(next.reviewed||next.analysis||empty);setConfirmed(false);refresh();}
   }catch(e){if(!cancelled)setError((e as Error).message);}
  },1800);return()=>{cancelled=true;clearInterval(timer);};
 },[record?.id,pending]);
 useEffect(()=>{const listener=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',listener);return()=>window.removeEventListener('beforeunload',listener);},[dirty]);
 function canLeave(){return !dirty||window.confirm('아직 저장하지 않은 수정 내용이 있습니다. 화면을 이동할까요?');}
 function goList(){if(!canLeave())return;setDirty(false);setSavedFilter('all');setView('list');setError('');refresh();}
 function newMeeting(){if(!canLeave())return;setInput({...blank,project});setRecord(null);setDraft(empty);setDirty(false);setSavedFilter('all');setView('input');setError('');setNotice('');}
 function editInput<K extends keyof Input>(key:K,value:Input[K]){setInput(previous=>({...previous,[key]:value}));setDirty(true);}
 async function useSample(){
  if(input.source && !window.confirm('입력한 내용을 가상 회의록 예시로 바꿀까요?'))return;
  setBusy(true);setError('');try{setInput(await api<Input>('/sample'));setDirty(true);setNotice('팀 양식으로 작성한 가상 회의록을 불러왔습니다. 원문을 확인하고 분석해 주세요.');}catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 async function upload(file:File){
  if(input.source && !window.confirm('입력한 내용을 선택한 Word 문서로 바꿀까요?'))return;
  if(file.size>4*1024*1024){setError('4MB 이하의 Word 파일을 선택해 주세요.');return;}
  setBusy(true);setError('');setNotice('');
  try{const form=new FormData();form.append('file',file);setInput(await api<Input>('/import',{method:'POST',body:form}));setDirty(true);setNotice(file.name+' 파일을 불러왔습니다.');}catch(e){setError((e as Error).message);}finally{setBusy(false);if(fileRef.current)fileRef.current.value='';}
 }
 async function analyze(){
  setBusy(true);setError('');setNotice('');
  try{const next=await api<Meeting>('/meetings',json(input));setRecord(next);setDraft(next.reviewed||next.analysis||empty);setConfirmed(false);setDirty(false);setView('review');refresh();}catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 async function openRecord(id:string){
  if(!canLeave())return;setBusy(true);setError('');setNotice('');
  try{const next=await api<Meeting>('/meetings/'+id);setRecord(next);setDraft(next.reviewed||next.analysis||empty);setConfirmed(false);setHighlight([]);setSavedFilter('all');setDirty(false);setView('review');}catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 function changeDraft(next:Analysis){setDraft(next);setConfirmed(false);setDirty(true);}
 function editItem(index:number,part:Partial<Item>){changeDraft({...draft,items:draft.items.map((item,i)=>i===index?{...item,...part}:item)});}
 function showEvidence(ids:string[]){setHighlight(ids);document.getElementById('source-'+ids[0])?.scrollIntoView({behavior:'smooth',block:'center'});}
 async function save(){
  if(!record)return;setBusy(true);setError('');
  try{const next=await api<Meeting>('/meetings/'+record.id+'/review',json({version:record.version,reviewed:confirmed,analysis:draft,actor_id:actorId}));setRecord(next);setDraft(next.reviewed!);setDirty(false);setNotice('검토한 항목을 프로젝트 업무 목록에 등록했습니다. 담당자와 진행 상태는 업무 목록에서 관리합니다.');refresh();onRegistered();}catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 async function retry(){if(!record)return;setBusy(true);setError('');try{setRecord(await api<Meeting>('/meetings/'+record.id+'/retry',{method:'POST'}));setDirty(false);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 const filtered=rows.filter(row=>(filter==='all'||(filter==='saved'?row.status==='saved':row.status!=='saved'))&&[row.title,row.project].join(' ').toLowerCase().includes(query.toLowerCase()));
 const counts={all:rows.length,review:rows.filter(row=>row.status!=='saved').length,saved:rows.filter(row=>row.status==='saved').length};
 const linkedWork=(index:number)=>record?.work_items?.find(item=>item.source_index===index);
 const actionBucket=(item:Item,index:number):ActionBucket=>{
  const work=linkedWork(index);
  if(item.category==='할일'){
   if(!work?.owner||!work?.due||work.status==='보완요청')return 'need';
   return work.status==='완료'?'done':'doing';
  }
  return ['확정','취소'].includes(work?.agreement||item.agreement||'')?'done':'need';
 };
 const savedItems=draft.items.map((item,index)=>({item,index,work:linkedWork(index),bucket:actionBucket(item,index),change:changeKind(item,index,record?.analysis||null),before:draftMatch(item,index,record?.analysis||null)}));
 const statusCounts={need:savedItems.filter(entry=>entry.bucket==='need').length+draft.review_points.length,doing:savedItems.filter(entry=>entry.bucket==='doing').length,done:savedItems.filter(entry=>entry.bucket==='done').length};
 const changedCount=savedItems.filter(entry=>entry.change).length+(record?.analysis&&record.analysis.summary!==draft.summary?1:0);
 const displayedItems=saved&&savedFilter!=='all'?savedItems.filter(entry=>entry.bucket===savedFilter):savedItems;

 return <div className="app-shell">
  <aside className="sidebar">
   <div className="brand"><span className="brand-symbol"><Layers3 size={24}/></span><div>B2<span>PROJECT WORKSPACE</span></div></div>
   <div className="workspace-label">프로젝트 업무 관리</div>
   <nav><button className={view!=='input'?'nav-item active':'nav-item'} onClick={goList}><ClipboardList size={19}/>회의록 관리<span className="nav-count">{counts.all}</span></button><button className={view==='input'?'nav-item active':'nav-item'} onClick={newMeeting}><Plus size={19}/>새 회의록</button></nav>
   <div className="sidebar-note"><span className="live-dot"/>로컬 워크스페이스<p>이 PC에 기록을 저장합니다.<br/>클라우드 연결 전 단계입니다.</p></div>
   <button className="help-button" onClick={()=>setHelp(true)}><CircleHelp size={18}/>사용 도움말<ChevronRight size={15}/></button>
  </aside>
  <div className="workspace">
   <header className="topbar"><div>프로젝트 업무 관리 <ChevronRight size={14}/><strong>회의록</strong></div><div><button className="icon-button" aria-label="사용 도움말" onClick={()=>setHelp(true)}><CircleHelp size={17}/></button><span className="environment"><span className="live-dot"/>내 PC에서 실행 중</span></div></header>
   <main>
    <div className="page-heading"><div><p className="eyebrow">MEETING WORKSPACE</p><h1>{view==='list'?'회의록 관리':view==='input'?'새 회의록 입력':saved?'저장한 회의록':'분석 결과 검토'}</h1><p>{view==='list'?'회의에서 나온 요구사항과 후속 조치를 한곳에서 확인하세요.':view==='input'?'Word 문서를 올리거나 회의 내용을 직접 붙여넣어 주세요.':'원문과 대조해 담당자, 기한, 합의 내용을 확인해 주세요.'}</p></div>{view==='list'?<button className="primary" onClick={newMeeting}><Plus size={18}/>새 회의록</button>:<button className="secondary" onClick={goList}><ArrowLeft size={16}/>목록으로</button>}</div>
    {error&&<div className="message error" role="alert">{error}<button aria-label="오류 닫기" onClick={()=>setError('')}><X size={16}/></button></div>}
    {notice&&<div className="message success" role="status"><CheckCheck size={18}/>{notice}</div>}

    {view==='list'&&<>
     <div className="stats"><div><span>전체 회의록</span><strong>{counts.all}<small>건</small></strong><FileText size={22}/></div><div><span>확인할 회의록</span><strong>{counts.review}<small>건</small></strong><ClipboardList size={22}/></div><div><span>검토 저장 완료</span><strong>{counts.saved}<small>건</small></strong><ShieldCheck size={22}/></div></div>
     <section className="card meeting-list"><div className="list-toolbar"><div className="tabs">{[['all','전체'],['review','검토 대기'],['saved','저장 완료']].map(([key,label])=><button key={key} className={filter===key?'selected':''} onClick={()=>setFilter(key)}>{label}</button>)}</div><label className="search"><Search size={17}/><input aria-label="회의록 검색" placeholder="회의명, 프로젝트 검색" value={query} onChange={e=>setQuery(e.target.value)}/></label></div>
      {filtered.length?<div className="table-scroll"><table><thead><tr><th>회의명 / 프로젝트</th><th>회의 일시</th><th>관리 항목</th><th>검토 상태</th><th></th></tr></thead><tbody>{filtered.map(row=><tr key={row.id}><td><button className="row-title" onClick={()=>openRecord(row.id)}>{row.title}</button><span className="muted block">{row.project||'프로젝트 미지정'}</span></td><td>{row.meeting_date||'일시 미입력'}</td><td>{row.reference_info?`${row.reference_info.event_count}개 이력`:row.item_count+'건'}</td><td><span className={'status '+row.status}>{row.reference_info?'제공된 가상자료':statusLabel[row.status]}</span></td><td><button className="icon-button" aria-label={row.title+' 열기'} onClick={()=>openRecord(row.id)}><ArrowRight size={18}/></button></td></tr>)}</tbody></table></div>:<div className="empty-state"><span className="empty-icon"><FolderOpen size={35}/></span><h2>{rows.length?'조건에 맞는 회의록이 없습니다':'첫 회의록을 등록해 보세요'}</h2><p>{rows.length?'검색어 또는 검토 상태를 바꾸어 주세요.':'회의록에서 필요한 정보를 추출하고, 검토한 내용을 저장합니다.'}</p>{!rows.length&&<button className="secondary" onClick={newMeeting}>회의록 입력하기<ArrowRight size={16}/></button>}</div>}
     </section><p className="footnote"><ShieldCheck size={15}/>검토 저장 완료는 기록 확인을 뜻합니다. 실제 업무 완료나 고객 승인과는 별도로 관리합니다.</p>
    </>}

    {view==='input'&&<>
     <Steps stage={1}/><div className="input-grid"><section className="card form-card"><div className="section-title"><h2>회의 내용</h2><span className="muted">기본 정보는 비워 두어도 됩니다</span></div>
      <div className="metadata"><label className="wide">회의명<input value={input.title} onChange={e=>editInput('title',e.target.value)} placeholder="예: 코팅 설비 설계 검토 회의" maxLength={200}/></label><label>프로젝트명<input value={input.project} onChange={e=>editInput('project',e.target.value)} placeholder="프로젝트를 구분할 이름" maxLength={160}/></label><label>회의 일시<input value={input.meeting_date} onChange={e=>editInput('meeting_date',e.target.value)} placeholder="예: 2026-11-04 14:00" maxLength={100}/></label></div>
      <div className="upload-area" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(!busy&&e.dataTransfer.files[0])upload(e.dataTransfer.files[0]);}}><Upload size={25}/><div><strong>Word 회의록을 여기에 놓아 주세요</strong><p>.docx · 최대 4MB · 본문과 표의 텍스트를 불러옵니다</p></div><button className="secondary" disabled={busy} onClick={()=>fileRef.current?.click()}>파일 선택</button><input hidden type="file" ref={fileRef} accept=".docx" onChange={e=>{if(e.target.files?.[0])upload(e.target.files[0]);}}/></div>
      <label className="source-label">회의록 원문<textarea className="source-input" value={input.source} onChange={e=>editInput('source',e.target.value)} placeholder={'회의 안건\n\n논의 내용\n\n결정 사항\n\n추가 확인 사항\n\n후속 조치'} maxLength={12000}/></label>
      <div className="input-caption"><span>불러온 내용은 분석 전에 수정할 수 있습니다.</span><span>{input.source.length.toLocaleString()} / 12,000자</span></div>
      {input.warnings.map(w=><p className="warning" key={w}>{w}</p>)}
      <div className="form-footer"><span>분석 후 원문을 보며 검토합니다.</span><button className="primary" disabled={busy||input.source.trim().length<10} onClick={analyze}>{busy?<LoaderCircle className="spin" size={17}/>:<Sparkles size={17}/>}AI로 분석하기<ArrowRight size={16}/></button></div>
     </section><aside className="input-aside"><section className="sample-card"><span className="pill">팀 양식으로 작성한 예시</span><FileText size={31}/><h2>코팅 설비<br/>설계 검토 회의</h2><p>고객 요구, 검토 중인 변경안,<br/>담당자와 기한이 정해진 후속 조치를<br/>담은 가상 회의록입니다.</p><button className="primary" disabled={busy} onClick={useSample}>예시 불러오기<ArrowRight size={16}/></button><a className="download-link" href="/api/sample/docx"><Download size={15}/>작성한 Word 회의록 받기</a></section><section className="quiet-guide"><h3>분석에서 확인할 내용</h3><p><Check size={16}/>고객이 요구한 조건</p><p><Check size={16}/>설계 변경의 합의 여부</p><p><Check size={16}/>후속 조치의 담당자와 기한</p><p className="muted">정해지지 않은 내용은 미정으로 남깁니다. AI가 놓친 항목은 검토 화면에서 추가할 수 있습니다.</p></section></aside></div>
    </>}

    {view==='review'&&record&&<>
     <>{!record.reference_info&&<Steps stage={saved?4:pending?2:3}/>}</><div className="record-heading"><div><h2>{record.title}</h2><p>{record.project||'프로젝트 미지정'}<span>·</span>{record.meeting_date||'회의 일시 미입력'}</p></div><span className={'status '+record.status}>{record.reference_info?'제공된 가상자료':statusLabel[record.status]}</span></div>
     {saved&&!record.reference_info&&<>
      <section className="review-audit-summary"><div className="reviewer-confirm"><span><UserCheck size={19}/></span><div><strong>{record.reviewer_name||'검토자'}님이 원문 대조를 완료했습니다</strong><small>{dateTime(record.reviewed_at||record.updated_at)} · AI 초안과 최종 결과를 함께 보관합니다</small></div></div><div><span>사용자 변경</span><strong>{changedCount}<small>건</small></strong></div><div><span>근거 연결</span><strong>{draft.items.filter(item=>item.evidence_ids.length>0).length}/{draft.items.length}</strong></div></section>
      <div className="action-status-board" role="group" aria-label="조치 상태 필터">
       <button className={'action-status need '+(savedFilter==='need'?'active':'')} aria-pressed={savedFilter==='need'} onClick={()=>setSavedFilter(savedFilter==='need'?'all':'need')}><span className="action-status-icon"><AlertTriangle size={20}/></span><span><strong>조치 필요</strong><small>담당자·기한·합의 확인</small></span><b>{statusCounts.need}</b></button>
       <button className={'action-status doing '+(savedFilter==='doing'?'active':'')} aria-pressed={savedFilter==='doing'} onClick={()=>setSavedFilter(savedFilter==='doing'?'all':'doing')}><span className="action-status-icon"><CircleDot size={20}/></span><span><strong>조치</strong><small>담당자가 처리 중</small></span><b>{statusCounts.doing}</b></button>
       <button className={'action-status done '+(savedFilter==='done'?'active':'')} aria-pressed={savedFilter==='done'} onClick={()=>setSavedFilter(savedFilter==='done'?'all':'done')}><span className="action-status-icon"><CircleCheckBig size={20}/></span><span><strong>완료</strong><small>합의 또는 조치 완료</small></span><b>{statusCounts.done}</b></button>
      </div>
      {changedCount>0&&<button className="important-change-bar" onClick={()=>setSavedFilter('all')}><GitCompareArrows size={18}/><strong>중요 변경 {changedCount}건</strong><span>AI 초안에서 사용자가 수정하거나 추가한 내용을 항목에서 확인할 수 있습니다.</span><ArrowRight size={16}/></button>}
      {savedFilter!=='all'&&<div className="active-status-filter"><span>{bucketLabel[savedFilter]} 항목만 표시 중</span><button onClick={()=>setSavedFilter('all')}>전체 보기</button></div>}
     </>}
     <div className="review-grid"><section className="card source-pane"><div className="pane-title"><h2><FileText size={18}/>회의록 원문</h2><span>{record.lines.length}개 행</span></div><div className="source-lines">{record.lines.map(line=><div id={'source-'+line.id} key={line.id} className={'source-line '+(highlight.includes(line.id)?'highlight':'')}><span>{line.id}</span><p>{line.text}</p></div>)}</div></section>
      <section className="result-pane">
       {record.reference_info?<section className="card reference-meeting-note"><strong>{record.reference_info.seq}차 회의 · 제공자료 이력 {record.reference_info.event_count}건</strong><p>이 회의록은 제공된 가상 기준자료입니다. AI 분석 결과나 실제 사용자의 검토 결과로 표시하지 않습니다.</p><p>요구사항 화면에서 회의 간 변화와 당시 승인값을 확인할 수 있습니다.</p><button className="primary" onClick={()=>onOpenRequirements?.(record.reference_info!.project_id)}>요구사항·변경 이력 보기<ArrowRight size={15}/></button></section>:pending?<div className="card analysis-wait" role="status"><span className="analysis-orb"><Sparkles size={30}/></span><h2>{record.status==='queued'?'분석 순서를 기다리고 있습니다':'회의록을 읽고 있습니다'}</h2><p>고객 요구, 설계 변경안과 후속 조치를<br/>원문 근거와 함께 정리합니다.</p><LoaderCircle className="spin" size={23}/><small>첫 실행은 모델을 불러오는 시간이 더 필요합니다.<br/>목록으로 이동해도 분석은 계속됩니다.</small></div>:<>
       {record.error&&<div className="message error"><div>{record.error}<button className="secondary retry" disabled={busy} onClick={retry}>분석 다시 실행</button></div></div>}
       {(record.warnings||[]).map(w=><div className="message warning" key={w}>{w}</div>)}
       <section className="card summary-card"><div className="pane-title"><h2><Sparkles size={18}/>{saved?'검토한 요약':'AI 요약'}</h2>{record.metrics&&<span>{record.metrics.seconds}초 · {record.metrics.attempts}회 실행</span>}</div>{saved?<p className="saved-summary">{draft.summary||'저장된 회의 요약이 없습니다.'}</p>:<><label className="sr-only" htmlFor="summary">회의 요약</label><textarea id="summary" value={draft.summary} onChange={e=>changeDraft({...draft,summary:e.target.value})} placeholder="회의의 핵심 내용을 정리해 주세요."/></>}</section>
       <div className="items-heading"><h2>관리 항목 <span>{saved&&savedFilter!=='all'?`${displayedItems.length}/${draft.items.length}`:draft.items.length}</span></h2>{!saved&&<button className="text-button" onClick={()=>changeDraft({...draft,items:[...draft.items,{category:'할일',content:'',owner:null,due:null,agreement:null,evidence_ids:[]}]})}><Plus size={16}/>항목 추가</button>}</div>
       {!displayedItems.length&&<p className="empty-inline">{savedFilter==='all'?'추출된 관리 항목이 없습니다. 원문에 항목이 있다면 직접 추가해 주세요.':`${bucketLabel[savedFilter as ActionBucket]} 상태의 관리 항목이 없습니다.`}</p>}
       {displayedItems.map(({item,index,work,bucket,change,before})=><article className={'card item-card saved-result '+(saved&&change?'changed ':'')+(saved?'action-'+bucket:'')} key={index}>
        <div className="item-top"><span className="item-index">{String(index+1).padStart(2,'0')}</span>{saved?<span className="saved-category">{item.category}</span>:<select aria-label={`항목 ${index+1} 종류`} value={item.category} onChange={e=>editItem(index,{category:e.target.value as Item['category'],agreement:e.target.value==='할일'?null:'불명확'})}>{['고객요구','설계변경','할일'].map(c=><option key={c}>{c}</option>)}</select>}{saved&&change&&<span className="change-chip"><GitCompareArrows size={12}/>{change}</span>}<span className="grow"/>{saved?<span className={'action-chip '+bucket}>{bucketLabel[bucket]}</span>:<button className="icon-button" aria-label={`항목 ${index+1} 제외`} onClick={()=>changeDraft({...draft,items:draft.items.filter((_,i)=>i!==index)})}><Trash2 size={16}/></button>}</div>
        {saved?<p className="saved-item-content">{item.content}</p>:<textarea aria-label={`항목 ${index+1} 내용`} className="item-content" value={item.content} onChange={e=>editItem(index,{content:e.target.value})}/>} 
        {saved?<div className="saved-item-facts"><div className={(work?.owner||item.owner)?'':'missing'}><span>담당자</span><strong>{work?.owner||item.owner||'미정 · 지정 필요'}</strong></div><div className={(work?.due||item.due)?'':'missing'}><span>{item.category==='할일'?'조치 기한':'해당 항목 기한'}</span><strong>{work?.due||item.due||'미정 · 지정 필요'}</strong></div><div><span>{item.category==='할일'?'진행 상태':'합의 상태'}</span><strong>{work?.status||work?.agreement||item.agreement||'미정'}</strong></div></div>:<div className="item-fields"><label>담당자<input placeholder="미정" value={item.owner||''} onChange={e=>editItem(index,{owner:e.target.value||null})}/></label><label>{item.category==='할일'?'조치 기한':'해당 항목 기한'}<input aria-label={`항목 ${index+1} 기한`} type="date" value={item.due||''} onChange={e=>editItem(index,{due:e.target.value||null})}/></label>{item.category!=='할일'&&<label>합의 상태<select value={item.agreement||'불명확'} onChange={e=>editItem(index,{agreement:e.target.value})}>{['검토중','확정','취소','불명확'].map(v=><option key={v}>{v}</option>)}</select></label>}</div>}
        {saved&&change&&<details className="ai-diff"><summary><GitCompareArrows size={14}/>AI 초안과 비교</summary>{before?<div><span>AI 초안</span><p>{before.content}</p><small>담당자 {before.owner||'미정'} · 기한 {before.due||'미정'} · 상태 {before.agreement||'해당 없음'}</small><span>최종 확인</span><p>{item.content}</p></div>:<p>AI 초안에는 없었으며 사용자가 원문 검토 과정에서 추가한 항목입니다.</p>}</details>}
        <Evidence ids={item.evidence_ids} record={record} saved={saved} onShow={showEvidence} onChange={ids=>editItem(index,{evidence_ids:ids})}/>
       </article>)}
       {(!saved||savedFilter==='all'||savedFilter==='need')&&<><div className="items-heading"><h2>추가 확인 사항 <span>{draft.review_points.length}</span></h2>{!saved&&<button className="text-button" onClick={()=>changeDraft({...draft,review_points:[...draft.review_points,{content:'',evidence_ids:[]}]})}><Plus size={16}/>추가</button>}</div>
       {draft.review_points.map((point,index)=><article className="card point-card saved-review-point" key={index}><div className="point-heading"><span className="action-chip need">조치 필요</span>{!saved&&<button className="icon-button" aria-label={`확인 사항 ${index+1} 제외`} onClick={()=>changeDraft({...draft,review_points:draft.review_points.filter((_,i)=>i!==index)})}><Trash2 size={16}/></button>}</div>{saved?<p className="saved-point-content">{point.content}</p>:<textarea aria-label={`확인 사항 ${index+1}`} value={point.content} onChange={e=>changeDraft({...draft,review_points:draft.review_points.map((p,i)=>i===index?{...p,content:e.target.value}:p)})}/>}<Evidence ids={point.evidence_ids} record={record} saved={saved} onShow={showEvidence} onChange={ids=>changeDraft({...draft,review_points:draft.review_points.map((p,i)=>i===index?{...p,evidence_ids:ids}:p)})}/></article>)}
       {!draft.review_points.length&&<p className="empty-inline">등록된 추가 확인 사항이 없습니다.</p>}</>}
       </>}
      </section></div>
     {!pending&&!record.reference_info&&<div className={'review-footer '+(saved?'saved-review-footer':'')}>{saved?<><div className="saved-note"><ShieldCheck size={20}/><div><strong>검토한 기록이 저장되었습니다</strong><p>AI 초안 {record.analysis?.items.length||0}건을 검토해 {draft.items.length}건으로 저장했습니다. 업무 완료·고객 승인은 별도입니다.</p></div></div><button className="primary" onClick={()=>onOpenWork(record.project)}>업무 목록 열기<ArrowRight size={16}/></button><a className="secondary" href={'/api/meetings/'+record.id+'/export'}><Download size={17}/>기록 내보내기</a></>:<><label className="review-check"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/><span><strong>원문과 비교해 내용을 확인했습니다</strong><small>검토 저장은 고객 승인 또는 실제 업무 완료를 뜻하지 않습니다.</small></span></label><button className="primary" disabled={busy||!confirmed} onClick={save}><CheckCheck size={18}/>{busy?'등록 중…':'검토 후 업무 등록'}</button></>}</div>}
    </>}
   </main><footer className="app-footer">B2 Workspace <span>회의록 입력 · 근거 확인 · 검토 저장</span></footer>
  </div>
  {help&&<div className="modal-backdrop" onClick={()=>setHelp(false)}><section className="help-modal" role="dialog" aria-modal="true" aria-label="사용 도움말" onClick={e=>e.stopPropagation()}><button className="modal-close icon-button" aria-label="도움말 닫기" onClick={()=>setHelp(false)}><X size={20}/></button><p className="eyebrow">QUICK GUIDE</p><h2>회의록을 검토하고 저장하는 방법</h2><ol><li>새 회의록에서 Word 파일을 올리거나 텍스트를 붙여넣습니다.</li><li>AI 분석 후 근거 번호를 눌러 원문과 비교합니다.</li><li>내용·담당자·기한·합의 상태를 수정하고 누락된 항목을 추가합니다.</li><li>확인 체크 후 저장합니다. 목록에서 다시 열고 JSON으로 내보낼 수 있습니다. 등록된 항목은 업무 목록에서 계속 관리합니다.</li></ol><p>가상 회의록은 팀 양식을 사용한 예시입니다. 실제 PNT 사내 문서가 아닙니다.</p><p>현재는 이 PC에서 체험 역할을 전환하며 사용하는 MVP입니다. 클라우드 공유, 실제 사용자 로그인, 근거 기반 질문하기는 연결하지 않았습니다.</p><p>표와 본문의 텍스트를 읽습니다. 사진·도면 해석은 지원하지 않습니다. AI 결과는 저장 전에 직접 확인해 주세요.</p><button className="primary" onClick={()=>setHelp(false)}>확인했습니다</button></section></div>}
 </div>;
}

function Steps({stage}:{stage:number}){return <ol className="steps">{['회의록 입력','AI 분석','내용 검토','저장 완료'].map((text,i)=><li key={text} className={stage===i+1?'current':stage>i+1?'done':''}><span>{stage>i+1?<Check size={13}/>:i+1}</span>{text}{i<3&&<ChevronRight size={15}/>}</li>)}</ol>;}
function Evidence({ids,record,saved,onShow,onChange}:{ids:string[];record:Meeting;saved:boolean;onShow:(ids:string[])=>void;onChange:(ids:string[])=>void}){
 return <div className="evidence"><div><span>원문 근거</span>{ids.map(id=><button key={id} onClick={()=>onShow([id])}>{id}<ArrowRight size={11}/></button>)}{!ids.length&&<span className="missing">근거를 선택해 주세요</span>}</div>{!saved&&<details><summary>근거 편집</summary><div className="evidence-picker">{record.lines.map(line=><label key={line.id}><input type="checkbox" checked={ids.includes(line.id)} onChange={e=>onChange(e.target.checked?[...ids,line.id]:ids.filter(id=>id!==line.id))}/><span><b>{line.id}</b> {line.text}</span></label>)}</div></details>}</div>;
}

