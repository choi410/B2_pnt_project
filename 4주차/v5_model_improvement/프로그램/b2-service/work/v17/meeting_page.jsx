import React,{useState}from'react';
import{ArrowLeft,ArrowRight,FileText,Pencil,Send,Trash2,Check,Download}from'lucide-react';
import{useApp,api,Button,IconButton,Status,Person,Modal,dateText}from'./app';
import{SourceView}from'./evidence';
import{MeetingAI}from'./context_panels';
import{MeetingChangeStatus}from'./change_history';
import{Timeline}from'./details';
import{quoteFocus}from'./evidence_focus.mjs';

function Body({text}){return <div className="readable-body">{(text||'').split(/\r?\n/).map((line,i)=>/^(회의 ?안건|논의 ?내용|결정 ?사항|후속 ?조치|추가 ?확인 ?사항)$/.test(line.trim())?<h3 key={i}>{line}</h3>:line.trim()?<p key={i}>{line}</p>:<br key={i}/>)}</div>}
export function MeetingPage({sourceFocus=null}){
 const{D,meeting:m,setMeeting,project,pm,nav,setConfirm,run,reload,busy,showMeetingWork}=useApp();
 const[tab,setTab]=useState('original'),[edit,setEdit]=useState(false),[body,setBody]=useState(m.source),[title,setTitle]=useState(m.title),[date,setDate]=useState(m.date),[opinion,setOpinion]=useState(''),[versions,setVersions]=useState(false);
 const p=project(m.project_id),isPM=pm(p.id),canEdit=isPM||m.author===D.user.id,modified=m.source?.trim()!==m.original_source?.trim()||m.title!==m.original_title||m.date!==m.original_date;
 const focus=sourceFocus?.meetingId===m.id?sourceFocus:null;
 const evidence=quoteFocus(m.original_source||m.source,focus?.quotes||[]);
 const linked=D.tasks.filter(t=>t.meeting_id===m.id),drafts=(m.candidates||[]).filter(c=>c.state==='draft');
 const refresh=async()=>{const next=await api('/meetings/'+m.id);setMeeting(next);setBody(next.source);setTitle(next.title);setDate(next.date);await reload()};
 return <><button className="back-link" onClick={()=>{if(edit)setConfirm({title:'수정 중인 회의록',text:'입력한 내용을 저장하지 않고 목록으로 이동할까요?',action:()=>nav('minutes')});else nav('minutes')}}><ArrowLeft size={16}/>회의록 목록</button>
 <div className="document-header"><div className="document-meta"><span>{p.id} · {p.name}</span><small>v{m.revision}</small></div><h1>{m.title}</h1><div className="document-byline"><span>{m.date||'회의일 미정'}</span><Person id={m.author}/><div className="document-actions">{canEdit&&!edit&&<Button small icon={Pencil} disabled={['running','queued'].includes(m.analysis_state)} onClick={()=>setEdit(true)}>본문 수정</Button>}{isPM&&<IconButton icon={Trash2} label="회의록 삭제" onClick={()=>setConfirm({title:'휴지통으로 이동',text:'회의록을 휴지통으로 옮깁니다. 회의록은 휴지통에서 복구할 수 있습니다.',button:'이동',action:async()=>{await api('/meetings/'+m.id+'/trash','POST',{version:m.version});await reload();nav('minutes')}})}/>}</div></div></div>
 <MeetingChangeStatus meeting={m}/>

 {edit?<div className="editor-page"><div className="edit-grid"><label>회의 제목<input value={title} onChange={e=>setTitle(e.target.value)}/></label><label>회의일<input type="date" value={date||''} onChange={e=>setDate(e.target.value)}/></label></div><div className="editor-columns"><section><div className="pane-title">보관된 원본</div><SourceView record={{...m,source:m.original_source}}/></section><section><div className="pane-title">수정할 본문 · 새 버전으로 등록</div><textarea aria-label="수정할 본문" value={body} onChange={e=>setBody(e.target.value)}/></section></div><div className="editor-footer"><Button onClick={()=>setEdit(false)}>취소</Button><Button primary disabled={busy||body.trim().length<10||!title.trim()} onClick={()=>run(async()=>{await api('/meetings/'+m.id+'/content','PATCH',{version:m.version,title,meeting_date:date||null,body});await refresh();setEdit(false)},'수정본을 등록했습니다. 요구·변경 후보를 자동으로 다시 확인합니다.')}>수정본 등록</Button></div></div>:<>
 <div className="document-tabs tabs">{[['original','원본'],['ai','AI 정리'],...(modified?[['current','수정본']]:[])].map(([key,name])=><button key={key} className={tab===key?'active':''} onClick={()=>setTab(key)}>{name}</button>)}</div>
 {(tab==='original'||tab==='current')&&<div className="document-reading single"><section className="paper-area"><div className="paper-toolbar"><span>{tab==='original'?'업로드한 원본':'수정본 · v'+m.revision}</span><div className="button-group">{tab==='original'&&<a href={'/api/meetings/'+m.id+'/original/'+(m.source_type==='text'?'txt':'docx')}><Download size={14}/>원본 다운로드</a>}<button className="text-link" onClick={()=>setVersions(true)}>버전 정보</button></div></div>{tab==='original'?<SourceView record={{...m,source:m.original_source||m.source,lines:null}} original initialZoom={60} selected={evidence.selected} focusKey={focus?.key||''} autoFocusEvidence={!!focus} unmatchedQuotes={evidence.missing}/>:<article className="paper"><h2>{m.title}</h2><p className="field-note">v{m.revision} · {dateText(m.revisions?.at(-1)?.saved_at)}</p><Body text={m.source}/></article>}</section></div>}
 {tab==='ai'&&<MeetingAI meeting={m}/>}
 </>}
 {versions&&<Modal wide title="문서 버전 정보" close={()=>setVersions(false)}><div className="history-page"><h2>본문 버전</h2>{[...m.revisions].reverse().map(r=><details key={r.number}><summary><span>v{r.number} · {r.title}</span><small>{dateText(r.saved_at)} · <Person plain id={r.saved_by}/></small></summary><Body text={r.body}/></details>)}<h2>문서 처리 이력</h2><Timeline events={m.document_events}/></div></Modal>}
 </>;
}
