import React,{useState,useEffect,useRef} from 'react';
import {MessageCircle,FileText,Loader2,X,ArrowUpRight,Plus} from 'lucide-react';
import {api,Button,Modal} from './app';

const progress={queued:'질문 대기 중',searching:'관련 회의록을 찾는 중',waiting_model:'다른 AI 분석이 끝나면 답변합니다.',answering:'근거를 확인하며 답변하는 중'};
export function QuestionPanel({D,open,close,onOpenProject}){
 const[scope,setScope]=useState(''),[question,setQuestion]=useState(''),[job,setJob]=useState(null),[preview,setPreview]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[sourceBusy,setSourceBusy]=useState(false);
 const seq=useRef(0),sourceSeq=useRef(0),sourceBox=useRef(null),questionInput=useRef(null);
 const pending=busy||job&&!['done','failed'].includes(job.state);
 useEffect(()=>{if(!job?.id||['done','failed'].includes(job.state))return;let active=true;const timer=setTimeout(async()=>{try{const r=await api('/questions/'+job.id);if(active)setJob(r)}catch(e){if(active){setError(e.message);setJob(j=>({...j,state:'failed'}))}}},1200);return()=>{active=false;clearTimeout(timer)}},[job]);
 useEffect(()=>{if(!preview||!open)return;const row=sourceBox.current?.querySelector('.highlight');if(row)sourceBox.current.scrollTop=Math.max(0,row.offsetTop-sourceBox.current.offsetTop-16)},[preview,open]);
 useEffect(()=>()=>{seq.current++;sourceSeq.current++},[]);
 function newQuestion(){if(pending)return;seq.current++;sourceSeq.current++;setScope('');setQuestion('');setJob(null);setPreview(null);setError('');setSourceBusy(false);questionInput.current?.focus()}
 async function submit(e,projectId=''){e?.preventDefault();if(pending)return;const n=++seq.current;setScope(projectId);setBusy(true);setError('');setPreview(null);sourceSeq.current++;setSourceBusy(false);setJob(null);try{const r=await api('/questions','POST',{project_id:projectId||null,question:question.trim()});if(n===seq.current)setJob(r)}catch(e){if(n===seq.current)setError(e.message)}finally{if(n===seq.current)setBusy(false)}}
 async function show(sourceId){const n=++sourceSeq.current;setSourceBusy(true);setError('');try{const r=await api('/questions/'+job.id+'/sources/'+sourceId);if(n===sourceSeq.current)setPreview(r)}catch(e){if(n===sourceSeq.current)setError(e.message)}finally{if(n===sourceSeq.current)setSourceBusy(false)}}
 if(!open)return null;
 const answer=job?.state==='done'?job.result:null;
 const groups=Object.values((answer?.points||[]).reduce((out,p)=>{const id=p.project_id||scope||'all';(out[id]??={id,name:p.project_name||D.projects.find(x=>x.id===id)?.name||'',points:[]}).points.push(p);return out},{}));
 return <Modal wide title="AI 질문" close={close}>
  <div className="question-toolbar"><p className="question-intro">프로젝트를 찾거나 회의에서 정한 내용을 물어보세요.</p><Button icon={Plus} disabled={pending||!(question||job||error)} title={pending?'답변이 완료되면 새 질문을 시작할 수 있습니다.':'질문과 답변을 비우고 새로 시작'} onClick={newQuestion}>새 질문</Button></div>
  <form className="global-search-form" onSubmit={submit}><input ref={questionInput} autoFocus aria-label="AI 질문" placeholder="예: 롤프레스 납품일은 언제야?" maxLength={500} disabled={pending} value={question} onChange={e=>setQuestion(e.target.value)}/><Button type="submit" primary disabled={pending||question.trim().length<2} icon={pending?Loader2:MessageCircle}>질문</Button></form>
  {error&&<p className="error-box" role="alert">{error}</p>}
  {!job&&<div className="question-examples"><span>예시 질문</span>{['롤프레스 프로젝트 찾아줘','현재 납품일은 언제야?','최근 회의에서 보류된 사항은?'].map(q=><button key={q} onClick={()=>setQuestion(q)}>{q}</button>)}</div>}
  <div className={'search-content '+(preview||sourceBusy?'with-preview':'')}>
   <section className="search-results" aria-label="AI 답변">
    {job&&!['done','failed'].includes(job.state)&&<p role="status" className="analysis-status"><Loader2 className="spin" size={17}/>{progress[job.state]||'답변 준비 중'}</p>}
    {job?.error&&<p role="alert">{job.error}</p>}
    {answer&&<>{answer.message&&<p>{answer.message}</p>}{groups.map(g=><section className="answer-project" key={g.id}>{g.name&&<h3>{g.name}</h3>}{g.points.map((p,i)=><article key={i}><p>{p.text}</p><details className="answer-evidence"><summary>근거 회의록 {(p.sources||[]).length}개</summary><div className="answer-sources">{(p.sources||[]).map(id=>{const s=answer.sources?.find(x=>x.id===id);return s&&<button key={id} onClick={()=>show(id)}><FileText size={13}/><span>{s.title}<small>{s.date}</small></span></button>})}</div></details></article>)}</section>)}{answer.kind==='clarification'&&<div className="question-choices">{answer.projects?.map(p=><Button key={p.id} onClick={()=>submit(null,p.id)}>{p.name}</Button>)}</div>}{answer.kind==='projects'&&<div className="question-projects">{answer.projects?.map(p=><button key={p.id} onClick={()=>onOpenProject(p.id)}><span><small>{p.id} · PM {p.pm}</small><b>{p.name}</b></span><span className="project-open">프로젝트 열기 <ArrowUpRight size={16}/></span></button>)}</div>}{answer.notice&&<p className="answer-notice">{answer.notice}</p>}{answer.omitted_projects?.length>0&&<p className="muted">답변에 포함되지 않은 프로젝트: {answer.omitted_projects.map(p=>p.name).join(', ')}</p>}</>}
   </section>
   {(preview||sourceBusy)&&<aside className="search-preview" aria-label="답변 원문 근거"><div className="section-head"><h2>원문 근거</h2><button className="icon-button" aria-label="원문 닫기" onClick={()=>{sourceSeq.current++;setPreview(null);setSourceBusy(false)}}><X size={17}/></button></div>{sourceBusy?<p role="status">불러오는 중…</p>:<><p className="muted">{preview.project_name} · {preview.date}</p><h3>{preview.title}</h3><div className="search-source-lines" ref={sourceBox}>{preview.lines?.map(l=><p key={l.id} className={preview.highlight?.includes(l.id)?'highlight':''}>{l.text}</p>)}</div></>}</aside>}
  </div>
 </Modal>
}
