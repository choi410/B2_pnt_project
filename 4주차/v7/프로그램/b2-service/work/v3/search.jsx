import React,{useState,useEffect,useRef,useCallback} from 'react';
import {MessageCircle,FileText,FolderOpen,Loader2,X,ArrowUpRight,ChevronRight,Plus} from 'lucide-react';
import {api,Button,Modal} from './app';

const progress={queued:'질문 대기 중',searching:'관련 회의록을 찾는 중',waiting_model:'다른 AI 분석이 끝나면 답변합니다.',answering:'근거를 확인하며 답변하는 중'};
const dateLabel=value=>value?value.replaceAll('-','.'):'날짜 미정';

export function QuestionPanel({D,open,close,onOpenProject}){
 const[scope,setScope]=useState(''),[question,setQuestion]=useState(''),[askedQuestion,setAskedQuestion]=useState('');
 const[job,setJob]=useState(null),[preview,setPreview]=useState(null),[selectedSource,setSelectedSource]=useState(''),[projectId,setProjectId]=useState('');
 const[error,setError]=useState(''),[sourceError,setSourceError]=useState(''),[busy,setBusy]=useState(false),[sourceBusy,setSourceBusy]=useState(false);
 const seq=useRef(0),sourceSeq=useRef(0),autoPreviewJob=useRef(null),sourceBox=useRef(null),questionInput=useRef(null);
 const pending=busy||Boolean(job&&!['done','failed'].includes(job.state));
 const answer=job?.state==='done'?job.result:null;
 useEffect(()=>{
  if(!job?.id||['done','failed'].includes(job.state))return;
  let active=true;
  const timer=setTimeout(async()=>{try{const r=await api('/questions/'+job.id);if(active)setJob(r)}catch(e){if(active){setError(e.message);setJob(j=>({...j,state:'failed'}))}}},1200);
  return()=>{active=false;clearTimeout(timer)};
 },[job]);
 useEffect(()=>{
  if(!preview||!open)return;
  const box=sourceBox.current,row=box?.querySelector('.highlight');
  if(row)box.scrollTop=Math.max(0,box.scrollTop+row.getBoundingClientRect().top-box.getBoundingClientRect().top-16);
 },[preview,open]);
 useEffect(()=>()=>{seq.current++;sourceSeq.current++},[]);

 const show=useCallback(async sourceId=>{
  if(!job?.id)return;
  const n=++sourceSeq.current;
  setSelectedSource(sourceId);setProjectId('');setPreview(null);setSourceBusy(true);setSourceError('');
  try{const r=await api('/questions/'+job.id+'/sources/'+sourceId);if(n===sourceSeq.current)setPreview(r)}
  catch(e){if(n===sourceSeq.current)setSourceError(e.message)}
  finally{if(n===sourceSeq.current)setSourceBusy(false)}
 },[job?.id]);
 useEffect(()=>{
  if(!open||!answer||autoPreviewJob.current===job.id)return;
  autoPreviewJob.current=job.id;
  const first=(answer.points||[]).flatMap(p=>p.sources||[]).find(id=>answer.sources?.some(s=>s.id===id));
  if(first)show(first);
 },[open,answer,job?.id,show]);

 function clearPreview(){sourceSeq.current++;setPreview(null);setSelectedSource('');setProjectId('');setSourceError('');setSourceBusy(false)}
 function newQuestion(){
  if(pending)return;
  seq.current++;autoPreviewJob.current=null;clearPreview();setScope('');setQuestion('');setAskedQuestion('');setJob(null);setError('');questionInput.current?.focus();
 }
 async function submit(e,chosenProject=''){
  e?.preventDefault();const text=question.trim();if(pending||text.length<2)return;
  const n=++seq.current;
  autoPreviewJob.current=null;clearPreview();setScope(chosenProject);setAskedQuestion(text);setBusy(true);setError('');setJob(null);
  try{const r=await api('/questions','POST',{project_id:chosenProject||null,question:text});if(n===seq.current)setJob(r)}
  catch(e){if(n===seq.current)setError(e.message)}
  finally{if(n===seq.current)setBusy(false)}
 }
 function selectProject(id){clearPreview();setProjectId(id)}

 if(!open)return null;
 const groups=Object.values((answer?.points||[]).reduce((out,p)=>{
  const id=p.project_id||scope||'all';
  (out[id]??={id,name:p.project_name||D.projects.find(x=>x.id===id)?.name||'',points:[]}).points.push(p);return out;
 },{}));
 const project=D.projects.find(p=>p.id===projectId);
 const projectResult=answer?.projects?.find(p=>p.id===projectId);
 const pm=project&&(D.people?.find(p=>p.id===project.pm)?.name||projectResult?.pm||'미정');
 const latestMeeting=project&&(D.meetings||[]).filter(m=>m.project_id===projectId).sort((a,b)=>(b.date||'').localeCompare(a.date||'')||(b.created_at||'').localeCompare(a.created_at||''))[0];
 const showingProject=Boolean(projectId)||answer?.kind==='projects';
 const hasSources=(answer?.points||[]).some(p=>(p.sources||[]).some(id=>answer.sources?.some(s=>s.id===id)));
 const hasResult=Boolean(job||busy);
 return <Modal wide className="question-dialog" title="AI 질문" close={close}>
  <div className="question-toolbar">
   <label className="question-intro" htmlFor="ai-question-input">프로젝트나 회의 내용을 물어보세요.</label>
   <Button icon={Plus} disabled={pending||!(question||job||error)} title={pending?'답변이 완료되면 새 질문을 시작할 수 있습니다.':'질문과 답변을 비우고 새로 시작'} onClick={newQuestion}>새 질문</Button>
  </div>
  <form className="global-search-form" onSubmit={submit}>
   <input id="ai-question-input" ref={questionInput} autoFocus placeholder="예: 롤프레스 납품일은 언제야?" maxLength={500} disabled={pending} value={question} onChange={e=>setQuestion(e.target.value)}/>
   <Button type="submit" primary disabled={pending||question.trim().length<2} icon={pending?Loader2:MessageCircle}>질문하기</Button>
  </form>
  {error&&<p className="error-box" role="alert">{error}</p>}
  {!job&&!busy&&<div className="question-examples"><span>예시 질문</span>{['롤프레스 프로젝트 찾아줘','현재 납품일은 언제야?','최근 회의에서 보류된 사항은?'].map(q=><button type="button" key={q} onClick={()=>{setQuestion(q);questionInput.current?.focus()}}>{q}</button>)}</div>}
  <div className={'question-workspace '+(hasResult?'with-context':'')}>
   <section className="question-answer-pane" aria-label="AI 답변" aria-busy={pending}>
    {hasResult&&<div className="question-asked"><span>질문</span><p>{job?.question||askedQuestion}</p></div>}
    {pending&&<div role="status" className="question-waiting"><Loader2 className="spin" size={20}/><span>{progress[job?.state]||'답변 준비 중'}</span></div>}
    {job?.error&&<p className="error-box" role="alert">{job.error}</p>}
    {answer&&<>
     {answer.message&&<p className="question-answer-message">{answer.message}</p>}
     {groups.map(g=><section className="question-answer-group" key={g.id}>
      {g.name&&<h3><FolderOpen size={17} aria-hidden="true"/><span>{g.name}</span></h3>}
      {g.points.map((p,i)=><article key={i} className={'question-answer-point '+((p.sources||[]).includes(selectedSource)?'is-referenced':'')}>
       <p>{p.text}</p>
       {(p.sources||[]).length>0&&<div className="question-source-links" aria-label="답변의 원문 근거">{p.sources.map(id=>{
        const s=answer.sources?.find(x=>x.id===id);if(!s)return null;
        return <button type="button" key={id} aria-pressed={selectedSource===id} aria-label={'원문 근거: '+s.title+' · '+dateLabel(s.date)} title={s.title} onClick={()=>show(id)}><FileText size={14}/><span>{dateLabel(s.date)}<small>{s.title}</small></span></button>;
       })}</div>}
      </article>)}
     </section>)}
     {answer.kind==='clarification'&&<div className="question-choices">{answer.projects?.map(p=><Button key={p.id} onClick={()=>submit(null,p.id)}>{p.name}</Button>)}</div>}
     {answer.kind==='projects'&&<div className="question-project-results">{answer.projects?.map(p=><button type="button" key={p.id} className={projectId===p.id?'selected':''} aria-pressed={projectId===p.id} onClick={()=>selectProject(p.id)}><FolderOpen size={19} aria-hidden="true"/><span><small>{p.id} · PM {p.pm}</small><strong>{p.name}</strong></span><ChevronRight size={18} aria-hidden="true"/></button>)}</div>}
     {answer.notice&&<p className="answer-notice">{answer.notice}</p>}
     {answer.omitted_projects?.length>0&&<p className="answer-notice">답변에 포함되지 않은 프로젝트: {answer.omitted_projects.map(p=>p.name).join(', ')}</p>}
    </>}
    {!hasResult&&!error&&<div className="question-empty"><MessageCircle size={26} aria-hidden="true"/><h3>회의에서 정한 내용을 찾아보세요.</h3><p>답변과 원문 근거를 함께 확인할 수 있습니다.</p></div>}
   </section>
   {hasResult&&<aside className="question-context-pane" aria-label={showingProject?'프로젝트 정보':'답변 원문 근거'}>
    <div className="question-context-heading"><h2>{showingProject?'프로젝트 정보':'원문 근거'}</h2>{(preview||sourceBusy||sourceError||projectId)&&<button type="button" className="icon-button" aria-label={showingProject?'프로젝트 정보 닫기':'원문 근거 닫기'} onClick={clearPreview}><X size={17}/></button>}</div>
    {sourceBusy?<p role="status" className="question-context-status"><Loader2 className="spin" size={17}/>원문을 불러오는 중…</p>
     :sourceError?<div className="question-context-error"><p role="alert">{sourceError}</p><Button onClick={()=>show(selectedSource)}>다시 불러오기</Button></div>
     :projectId?(project?<div className="question-project-preview">
       <span className="question-project-code">{project.id}</span><h3>{project.name}</h3>
       <dl><div><dt>프로젝트 PM</dt><dd>{pm}</dd></div><div><dt>최근 회의</dt><dd>{latestMeeting?<><time>{dateLabel(latestMeeting.date)}</time><span>{latestMeeting.title}</span></>:'등록된 회의록이 없습니다.'}</dd></div></dl>
       <Button primary icon={ArrowUpRight} onClick={()=>onOpenProject(project.id)}>변경이력 보기</Button>
      </div>:<p className="question-context-placeholder">이 프로젝트를 현재 목록에서 찾을 수 없습니다.</p>)
     :preview?<>
       <div className="question-source-meta"><p>{preview.project_name}</p><time>{dateLabel(preview.date)}</time><h3>{preview.title}</h3><span>등록된 회의록 본문{preview.revision>1?' · 수정본':''}</span></div>
       <div className="question-source-lines" ref={sourceBox}>{preview.lines?.map(l=><p key={l.id} className={preview.highlight?.includes(l.id)?'highlight':''}>{l.text}</p>)}</div>
      </>
     :<div className="question-context-placeholder">{showingProject?<><FolderOpen size={24} aria-hidden="true"/><p>{answer.projects?.length?'프로젝트를 선택하면 이곳에서 정보를 확인할 수 있습니다.':'검색된 프로젝트가 없습니다.'}</p></>:<><FileText size={24} aria-hidden="true"/><p>{pending?'답변에 사용한 회의록을 이곳에 표시합니다.':hasSources?'답변 아래의 근거 회의록을 선택하면 원문을 확인할 수 있습니다.':'표시할 원문 근거가 없습니다.'}</p></>}</div>}
   </aside>}
  </div>
 </Modal>;
}
