import React,{useState,useEffect}from'react';
import{ArrowRight,FileText,Loader2}from'lucide-react';
import{api,Button,Modal}from'./app';
import{SourceView}from'./evidence';

export function changeProblem(x){
 if(x.source_deleted)return '근거 회의록이 휴지통에 있습니다. 복구 후 확인하세요.';
 if(x.source_changed)return '본문이 바뀌었습니다. 변경 이력의 대조·수정에서 최신 근거를 선택하세요.';
 if((x.title||'').trim().length<2)return '변경 대상 이름을 2자 이상 입력하세요.';
 if(!(x.after||'').trim())return '변경 내용을 입력하세요.';
 if(!x.evidence?.length)return '근거 선택·수정에서 원문 문장을 선택하세요.';
 return '';
}
export function ChangeReviewList({items,onChange,onEvidence,isPM=true,topics=[]}){
 return <div className="change-review-list">{items.map((x,i)=>{
  const patch=(k,v)=>onChange(i,{...x,[k]:v}),action=x.review_action||'record',problem=changeProblem(x);
  return <article key={x.id||i} className={'review-change '+(action==='record'?'':'deferred')}>
   <div className="review-change-heading"><b>{x.title}</b><span className={'business-state state-'+x.business_state}>{x.business_state}</span></div>
   <div className="before-after"><span><small>변경 전</small>{x.before||'원문에 명시되지 않음'}</span><ArrowRight size={16}/><span><small>변경 내용</small>{x.after}</span></div>
   <div className="review-change-controls"><button type="button" className="text-link" onClick={()=>onEvidence(i)}><FileText size={14}/>원문 대조</button>{isPM&&<select aria-label={x.title+' 처리'} value={action} onChange={e=>patch('review_action',e.target.value)}><option value="record">이력에 기록</option><option value="defer">나중에 확인</option><option value="exclude">제외</option></select>}</div>
   {problem&&<p className="warning">{problem}</p>}
   {!x.source_changed&&!x.source_deleted&&<details className="review-change-edit"><summary>내용 수정</summary><div className="edit-grid">
    {topics.length>0&&<label className="span2">변경 대상 연결<select value={x.topic_id||''} onChange={e=>{const t=topics.find(t=>t.id===e.target.value);onChange(i,{...x,topic_id:t?.id||null,title:t?.title||x.title,category:t?.category||x.category})}}><option value="">동일 이름·구분 연결 또는 새 대상</option>{topics.map(t=><option key={t.id} value={t.id}>{t.title} · {t.category}</option>)}</select></label>}
    <label className="span2">변경 대상<input aria-label="변경 대상 이름" disabled={!!x.topic_id} maxLength={160} value={x.title} onChange={e=>patch('title',e.target.value)}/></label>
    <label>구분<select disabled={!!x.topic_id} value={x.category} onChange={e=>patch('category',e.target.value)}>{['요구사항','사양','납기'].map(v=><option key={v}>{v}</option>)}</select></label>
    <label>원문에서의 상태<select value={x.business_state} onChange={e=>patch('business_state',e.target.value)}>{['요청','확정','철회','보류'].map(v=><option key={v}>{v}</option>)}</select></label>
    <label className="span2">변경 전<textarea maxLength={1500} value={x.before} onChange={e=>patch('before',e.target.value)}/></label>
    <label className="span2">변경 내용<textarea maxLength={1500} value={x.after} onChange={e=>patch('after',e.target.value)}/></label>
   </div></details>}
  </article>
 })}</div>
}

export function MeetingChangeReview({meetingId,action=null,note='',close,saved}){
 const[m,setM]=useState(null),[items,setItems]=useState([]),[topics,setTopics]=useState([]),[scan,setScan]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[target,setTarget]=useState(null),[editEvidence,setEditEvidence]=useState(false),[loaded,setLoaded]=useState(false);
 const load=async(preserve=false)=>{
  try{const next=await api('/meetings/'+meetingId),data=await api('/changes?project_id='+encodeURIComponent(next.project_id));setM(next);setTopics(data.topics);setScan(data.scans.find(x=>x.id===meetingId));setItems(previous=>data.events.filter(x=>x.meeting_id===meetingId&&x.review_state==='검토 전').sort((a,b)=>(a.evidence?.[0]||'').localeCompare(b.evidence?.[0]||'')).map(x=>{const edited=preserve&&previous.find(p=>p.id===x.id&&p.version===x.version&&!x.source_changed);return edited||{...x,review_action:x.source_changed||x.source_deleted||x.deferred_by?'defer':'record'}}));setError('');setLoaded(true)}catch(e){setError(e.message)}
 };
 useEffect(()=>{load()},[meetingId]);
 const waiting=['queued','running'].includes(scan?.state);
 useEffect(()=>{if(!waiting)return;let alive=true;const timer=setInterval(async()=>{try{const next=await api('/changes/meetings/'+meetingId+'/status');if(alive&&!['queued','running'].includes(next.state))load(true)}catch{}},2500);return()=>{alive=false;clearInterval(timer)}},[waiting,meetingId]);
 const update=(i,next)=>setItems(xs=>xs.map((x,n)=>n===i?next:x));
 const count=items.filter(x=>x.review_action==='record').length;
 const blocker=items.find(x=>x.review_action==='record'&&(changeProblem(x)||(!action&&x.business_state==='확정'&&m?.document_status!=='확정')));
 const compact=!!action&&loaded&&!items.length;
 const label=action?(count?'회의록 확정 · 변경 '+count+'건 기록':'회의록 확정'):'변경 '+count+'건 이력에 반영';
 const submit=async()=>{
  setBusy(true);setError('');
  try{const choices=items.map(x=>({id:x.id,version:x.version,action:x.review_action,...(x.review_action==='record'?{change:Object.fromEntries(['meeting_id','source_revision','topic_id','title','category','before','after','business_state','evidence','effective_date'].map(k=>[k,x[k]??(k==='topic_id'?null:'')]))}:{})}));
   if(action)await api('/meetings/'+m.id+'/document-action','POST',{version:m.version,action,note,changes:choices});
   else await api('/changes/meetings/'+m.id+'/review','POST',{version:m.version,items:choices});
   await saved();close();
  }catch(e){setError(e.message)}finally{setBusy(false)}
 };
 return <Modal wide={!compact} title={compact?'회의록 확정':action?'회의록과 변경사항 검토':'회의록별 변경 검토'} close={busy?()=>{}:close} footer={<div className="joint-review-footer">{error&&<p className="warning" role="alert">{error} <button className="text-link" disabled={busy} onClick={()=>load()}>최신 내용 다시 불러오기</button></p>}{blocker&&<p className="warning">{blocker.title} · {changeProblem(blocker)||'회의록 확정이 필요합니다. 지금은 나중에 확인으로 남겨 주세요.'}</p>}{items.length>0&&<span>{items.filter(x=>x.review_action==='defer').length}건 나중에 확인 · {items.filter(x=>x.review_action==='exclude').length}건 제외</span>}<Button primary disabled={!loaded||busy||!!blocker||(!action&&!items.length)} onClick={submit}>{busy?'저장 중…':label}</Button></div>}>
 {!m?<p role="status">회의록과 변경사항을 불러오는 중…</p>:compact?<div className="meeting-confirm-copy"><h3>{m.title}</h3><p>검토한 회의록 내용을 확정할까요?</p>{scan?.state==='ready'?<p className="notice">변경 분석이 완료됐으며, 현재 검토할 변경 제안이 없습니다.</p>:<p className="warning">변경 분석 미완료{waiting?' · 분석 중입니다.':''} 회의록을 먼저 확정할 수 있으며, 변경사항은 이후 별도로 확인해야 합니다.</p>}<p className="field-note">회의록 확정과 업무 배정·완료 처리는 별개입니다.</p></div>:<div className="joint-review-grid">
  <section className="joint-source source-scroll"><div className="section-title"><h3>{m.title}</h3><small>근거 회의록 v{m.revision}</small></div>{target!==null&&<div className="evidence-banner"><span>{items[target]?.title}</span><Button small onClick={()=>setEditEvidence(!editEvidence)}>{editEvidence?'대조로 돌아가기':'근거 선택·수정'}</Button></div>}<SourceView record={m} selected={target!==null?items[target]?.evidence||[]:[]} focusKey={target} linesMode={editEvidence} onLine={editEvidence&&target!==null?id=>{const x=items[target];update(target,{...x,evidence:x.evidence.includes(id)?x.evidence.filter(y=>y!==id):[...x.evidence,id]})}:undefined}/></section>
  <section className="joint-changes"><h3>변경사항 {items.length}건</h3><p className="field-note">원문과 함께 확인하고 틀린 항목만 수정하세요. 요청은 요청으로 기록되며 변경 승인으로 바뀌지 않습니다.</p>
   {waiting?<p className="notice"><Loader2 size={15} className="spin"/>변경 분석 중입니다. 회의록을 먼저 확정하면 변경사항은 나중에 검토합니다.</p>:['failed','stale','idle'].includes(scan?.state||'idle')?<p className="warning">변경 분석이 완료되지 않았습니다. 회의록을 먼저 확정할 수 있으며 변경사항은 나중에 확인하세요.</p>:!items.length&&<p className="notice">검토할 변경 제안이 없습니다.</p>}
   <ChangeReviewList items={items} topics={topics} onChange={update} onEvidence={i=>{setTarget(i);setEditEvidence(false)}}/>
  </section>
 </div>}
 </Modal>
}
