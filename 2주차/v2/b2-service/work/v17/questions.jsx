import React,{useState,useEffect,useRef}from'react';
import{Search,ArrowRight,Loader2,FileText,X,RefreshCw,Folder}from'lucide-react';
import{useApp,api,Button,IconButton,Status,dateText}from'./app';

const progress={queued:'질문을 접수했습니다.',searching:'프로젝트 자료에서 관련 근거를 찾고 있습니다.',waiting_model:'다른 AI 처리가 끝나면 답변을 작성합니다.',answering:'찾은 근거를 바탕으로 답변을 작성하고 있습니다.'};

export function ProjectQuestion(){
 const{D,pid}=useApp();
 const[projectId,setProjectId]=useState(pid||''),[question,setQuestion]=useState(''),[job,setJob]=useState(null),[posting,setPosting]=useState(false),[error,setError]=useState(''),[source,setSource]=useState(null),[sourceBusy,setSourceBusy]=useState(false),[sourceError,setSourceError]=useState('');
 const generation=useRef(0),sourceGeneration=useRef(0),evidenceRef=useRef(null);
 const pending=posting||(job&&!['done','failed'].includes(job.state));
 const result=job?.state==='done'?job.result:null;
 useEffect(()=>()=>{generation.current++;sourceGeneration.current++},[]);
 useEffect(()=>{
  if(!job?.id||['done','failed'].includes(job.state))return;
  let active=true,timer;
  const poll=async()=>{try{const next=await api('/questions/'+job.id);if(active){setJob(next);if(!['done','failed'].includes(next.state))timer=setTimeout(poll,1400)}}catch(e){if(active){setError(e.message);setJob(j=>({...j,state:'failed'}))}}};
  timer=setTimeout(poll,250);return()=>{active=false;clearTimeout(timer)};
 },[job?.id,job?.state]);
 useEffect(()=>{const box=evidenceRef.current,row=box?.querySelector('.source-highlight');if(row)box.scrollTop=Math.max(0,row.offsetTop-24)},[source]);
 const reset=()=>{generation.current++;sourceGeneration.current++;setJob(null);setError('');setSource(null);setSourceError('');setSourceBusy(false)};
 const ask=async()=>{
  const seq=++generation.current;sourceGeneration.current++;setPosting(true);setError('');setSource(null);setSourceError('');setSourceBusy(false);setJob(null);
  try{const next=await api('/questions','POST',{project_id:projectId||null,question:question.trim()});if(seq===generation.current)setJob({...next,question:question.trim()})}
  catch(e){if(seq===generation.current)setError(e.message)}finally{if(seq===generation.current)setPosting(false)}
 };
 const showSource=async id=>{
  const seq=++sourceGeneration.current;setSourceBusy(true);setSourceError('');setSource(null);
  try{const data=await api('/questions/'+job.id+'/sources/'+id);if(seq===sourceGeneration.current)setSource(data)}
  catch(e){if(seq===sourceGeneration.current)setSourceError(e.message)}finally{if(seq===sourceGeneration.current)setSourceBusy(false)}
 };
 const examples=projectId?['고객이 요청한 변경사항은 무엇이야?','납기 변경 이유가 뭐야?','내 미완료 업무가 몇 개야?']:['내 미완료 업무가 몇 개야?','기한 지난 업무를 보여줘','납기 변경이 논의된 프로젝트는?'];
 const chooseProject=id=>{setProjectId(id);reset()};
 const group=items=>Object.values((items||[]).reduce((groups,item)=>{const id=item.project_id||'current';(groups[id]??={id,name:item.project_name||D.projects.find(p=>p.id===id)?.name||'',items:[]}).items.push(item);return groups},{}));
 const projectChoices=projects=><div className="question-project-choices">{projects.map(p=><button key={p.id} onClick={()=>chooseProject(p.id)}><b>{p.name}</b><small>{p.id} · 이 프로젝트로 질문 범위 변경</small></button>)}</div>;
 return <div className="project-question">
  <div className="question-controls"><label>질문 범위<select aria-label="질문 범위" value={projectId} disabled={pending} onChange={e=>chooseProject(e.target.value)}><option value="">전체 프로젝트</option>{D.projects.map(p=><option key={p.id} value={p.id}>{p.id} · {p.name}</option>)}</select></label><span className="field-note">{!projectId&&<>조회 권한이 있는 프로젝트 전체를 검색합니다.<br/></>}회의 내용은 확정본에서, 현재 업무는 저장된 상태에서 확인합니다.</span></div>
  <form className="question-input" onSubmit={e=>{e.preventDefault();if(question.trim().length>=2&&!pending)ask()}}><textarea aria-label="프로젝트 질문" placeholder={projectId?'예: 안전커버 방식이 어떻게 변경됐어?':'예: 납기 변경이 논의된 프로젝트는?'} maxLength={500} value={question} disabled={pending} onChange={e=>setQuestion(e.target.value)} rows={2}/><Button primary disabled={question.trim().length<2||pending} type="submit">{pending?<Loader2 className="spin" size={17}/>:<Search size={17}/>}질문하기</Button></form>
  {!job&&!error&&<><div className="question-example-label"><b>예시 질문</b><small>누르면 입력창에 들어갑니다</small></div><div className="question-examples">{examples.map(q=><button key={q} disabled={pending} onClick={()=>setQuestion(q)}>{q}</button>)}</div></>}
  {pending&&<div className="question-progress" role="status"><Loader2 className="spin" size={18}/>{posting?'질문을 보내고 있습니다.':progress[job.state]}</div>}
  {(error||job?.error)&&<div className="question-error" role="alert">{error||job.error}<Button small disabled={pending} onClick={ask} icon={RefreshCw}>다시 질문</Button></div>}
  {!job&&!pending&&!error&&<div className="question-empty"><FileText size={29}/><h3>프로젝트 자료에 질문해 보세요</h3><p>답변의 근거를 선택하면 이 창에서 본문과 나란히 확인할 수 있습니다.</p><small>담당자 변경이나 업무 완료는 실행하지 않습니다.</small></div>}
  {result&&<div className={'question-output '+(source||sourceBusy||sourceError?'with-source':'')}>
   <section className="question-answer" aria-label="질문 답변"><div className="question-answer-heading"><h3>{result.kind==='tasks'?'현재 업무 조회':result.kind==='clarification'?'질문 범위 선택':'회의록 근거 답변'}</h3><small>{job.seconds!=null?job.seconds+'초':''}</small></div><p className="asked-question">{job.question}</p>
    {!result.answerable&&<p className="question-unanswered">{result.message}</p>}
    {result.kind==='clarification'&&projectChoices(result.projects)}
    {result.kind==='documents'&&group(result.points).map(g=><section className="question-project-group" key={g.id}>{g.name&&<h4 className="question-project-heading"><Folder size={18}/><span>{g.name}<small>{g.id}</small></span><em>답변 {g.items.length}건</em></h4>}{g.items.map((point,i)=><article className="answer-point" key={i}><p>{point.text}</p><div className="answer-citations">{point.sources.map(id=>{const s=result.sources.find(s=>s.id===id);return s&&<button key={id} onClick={()=>showSource(id)} aria-label={'근거 보기 · '+s.title}><FileText size={14}/><span>{s.title}<small>{s.project_name&&s.project_name+' · '}{s.date||'회의일 미정'} · 확정본 v{s.revision}{s.has_draft?' · 수정 중인 새 버전 있음':''}</small></span><ArrowRight size={14}/></button>})}</div></article>)}</section>)}
    {result.kind==='documents'&&<><p className="field-note">{result.searched_projects!=null&&<>조회 범위: {result.searched_projects}개 프로젝트 · 확정 회의록 {result.searched_meetings}건<br/></>}검색된 근거를 바탕으로 작성한 답변입니다. 모든 관련 항목을 빠짐없이 나열한 결과는 아닙니다.</p>{result.omitted_projects?.length>0&&<><p className="field-note">관련 자료가 많아 아래 프로젝트는 이번 답변에서 빠졌습니다. 선택해서 따로 확인할 수 있습니다.</p>{projectChoices(result.omitted_projects)}</>}</>}
    {result.kind==='tasks'&&<><p className="task-query-conditions">{result.conditions.join(' · ')}<small>{dateText(result.checked_at)} 조회 기준</small></p>{result.answerable&&<p><b>{result.message}</b></p>}{group(result.tasks).map(g=><section className="question-project-group" key={g.id}>{g.name&&<h4 className="question-project-heading"><Folder size={18}/><span>{g.name}<small>{g.id}</small></span><em>업무 {g.items.length}건</em></h4>}<div className="question-task-list">{g.items.map(t=><button key={t.id} onClick={()=>{sourceGeneration.current++;setSourceBusy(false);setSourceError('');setSource({task:t})}}><span><b>{t.title}</b><small>담당 {t.owner} · 기한 {t.due||'미정'}</small></span><Status value={t.status}/></button>)}</div></section>)}</>}
   </section>
   {(source||sourceBusy||sourceError)&&<aside className="question-source" aria-label="답변 근거 본문"><div className="question-source-heading"><h3>{source?.task?'현재 업무 정보':'근거 본문'}</h3><IconButton icon={X} label="근거 닫기" onClick={()=>{sourceGeneration.current++;setSource(null);setSourceError('');setSourceBusy(false)}}/></div>{sourceBusy&&<p role="status">근거를 불러오고 있습니다.</p>}{sourceError&&<p role="alert">{sourceError}</p>}
    {source?.task?<><h4>{source.task.title}</h4><p className="field-note">{source.task.project_id} · {source.task.project_name}</p><dl className="question-task-facts"><dt>담당자</dt><dd>{source.task.owner}</dd><dt>검토자</dt><dd>{source.task.reviewer}</dd><dt>상태</dt><dd><Status value={source.task.status}/></dd><dt>완료 목표일</dt><dd>{source.task.due||'미정'}</dd></dl><h4>해야 할 일</h4><p className="source-task-text">{source.task.description||'등록된 설명이 없습니다.'}</p><h4>저장된 처리 내용</h4><p className="source-task-text">{source.task.result||'등록된 처리 내용이 없습니다.'}</p></>:source&&<><h4>{source.title}</h4><p className="field-note">{source.project_id} · {source.project_name}<br/>{source.date||'회의일 미정'} · 확정본 v{source.revision}{source.has_draft?' · 새 수정본은 미확정':''}</p><div ref={evidenceRef} className="question-source-lines">{source.lines.map(line=><p className={source.highlight.includes(line.id)?'source-highlight':''} key={line.id}><small>{line.id}</small><span>{line.text}</span></p>)}</div></>}
   </aside>}
  </div>}
 </div>
}
