import React,{useState,useEffect}from'react';
import{Plus,Search,Sparkles,ArrowRight,FileText,History,ChevronDown,Loader2}from'lucide-react';
import{useApp,api,Button,Modal,PageHead,Empty,dateText,Status}from'./app';
import{SourceView}from'./evidence';
import{MeetingChangeReview}from'./change_review';
import{changeGroups,filterChangeGroups}from'./change_groups';

export function MeetingChangeStatus({meeting:m}){
 const{nav,setPid}=useApp(),[scan,setScan]=useState({state:m.change_scan_state||'idle'});
 useEffect(()=>{
  let stopped=false,timer;
  const poll=async()=>{
   try{
    const next=await api('/changes/meetings/'+m.id+'/status');
    if(stopped)return;
    setScan(next);
    if(['queued','running'].includes(next.state))timer=setTimeout(poll,2500);
   }catch{if(!stopped)timer=setTimeout(poll,5000)}
  };
  poll();return()=>{stopped=true;clearTimeout(timer)};
 },[m.id,m.revision,m.version]);
 if(scan.state==='idle')return null;
 const pending=['queued','running'].includes(scan.state),failed=['failed','stale'].includes(scan.state);
 const text=scan.state==='queued'?'변경사항 자동 분석 대기 중 · 회의록 등록은 완료되었습니다.':scan.state==='running'?'변경사항을 자동으로 찾고 있습니다. 다른 업무를 계속할 수 있습니다.':scan.state==='stale'?'본문이 변경되었습니다. 최신 내용으로 변경사항을 다시 찾아주세요.':failed?'변경사항 자동 분석을 완료하지 못했습니다. 회의록은 등록되어 있습니다.':scan.pending>0?'검토할 변경 후보 '+scan.pending+'건이 있습니다. PM이 확인하면 이력에 반영됩니다.':scan.total>0?'이 회의록의 변경 후보 검토가 끝났습니다.':'자동 분석이 완료되었습니다. 이 회의록에서 찾은 변경 후보가 없습니다.';
 return <div className="change-scan-note" role="status">{pending&&<Loader2 size={15} className="spin"/>}<span>{text}</span><button className="text-link" onClick={()=>{setPid(m.project_id);nav('changes',scan.pending>0||pending?'pending':'history')}}>{scan.pending>0?'변경 후보 확인':'변경 이력 보기'}</button></div>;
}

export function ChangeHistory(){
 const{D,pid,pm,project,person,run,setConfirm,changeStartTab}=useApp(),[data,setData]=useState(null),[q,setQ]=useState(''),[tab,setTab]=useState(changeStartTab||'history'),[editor,setEditor]=useState(null),[batch,setBatch]=useState(null),[reviewMeeting,setReviewMeeting]=useState(null),[evidence,setEvidence]=useState(null),[error,setError]=useState('');
 const refresh=()=>api('/changes'+(pid?'?project_id='+encodeURIComponent(pid):'')).then(setData).catch(e=>setError(e.message));useEffect(()=>{refresh()},[pid]);
 const running=data?.scans.some(x=>['running','queued'].includes(x.state));useEffect(()=>{if(!running)return;const timer=setInterval(refresh,2500);return()=>clearInterval(timer)},[running,pid]);
 const events=(data?.events||[]).map(e=>{const m=D.meetings.find(m=>m.id===e.meeting_id);return {...e,meeting_title:e.meeting_title||m?.title||'회의록 제목 확인 필요',meeting_created_at:e.meeting_created_at||m?.created_at||''}});
 const pending=events.filter(e=>e.review_state==='검토 전');
 const historyCount=events.filter(e=>e.review_state==='확인됨').length;
 const batchScans=(batch?.jobs||[]).map(j=>data?.scans.find(s=>s.id===j.id&&s.job===j.job)||(data?{state:'unavailable',added:0}:null));
 const batchDone=batchScans.filter(s=>s&&!['running','queued'].includes(s.state)).length;
 const batchFailed=batchScans.filter(s=>s&&['failed','stale','unavailable'].includes(s.state)).length;
 const batchAdded=batchScans.reduce((n,s)=>n+(s?.state==='ready'?s.added||0:0),0);
 const startScan=()=>run(async()=>{const result=await api('/changes/analyze-scope','POST',{project_id:pid||null});setBatch(result);await refresh();setTab('pending')});
 const excludedCount=events.filter(e=>e.review_state==='제외').length;
 const groups=filterChangeGroups(changeGroups(events,data?.topics||[],tab),q,id=>project(id)?.name||'');
 const excluded=events.filter(e=>e.review_state==='제외'&&(e.title+' '+e.before+' '+e.after+' '+e.meeting_title).toLowerCase().includes(q.toLowerCase()));
 const openEvidence=e=>run(async()=>{const m=await api('/meetings/'+e.meeting_id);const rev=m.revisions.find(r=>r.number===e.source_revision);setEvidence({m:{...m,source:rev?.body||m.source,lines:null,view_revision:e.source_revision},e})});
 const row=e=><article className="business-event" key={e.id} data-change-id={e.id}>
  <div><span className={'business-state state-'+e.business_state}>{e.business_state}</span><time>{e.effective_date}</time><small>{e.origin}{e.review_state==='확인됨'?' · 대조 확인 '+person(e.confirmed_by)?.name:' · '+e.review_state}</small></div>
  <button className="change-source-title" onClick={()=>openEvidence(e)}><FileText size={14}/><span>{e.meeting_title}</span><small>근거 회의록 v{e.source_revision}</small></button>
  <div className="before-after"><span><small>변경 전</small>{e.before||'원문에 명시되지 않음'}</span><ArrowRight size={17}/><span><small>{e.business_state==='확정'?'확정 내용':e.business_state==='철회'?'철회 내용':'논의 내용'}</small>{e.after}</span></div>
  <div className="event-foot">{e.source_deleted&&<small>휴지통에 보관된 원문</small>}{e.source_changed&&<small>당시 버전 보관</small>}
   {e.review_state==='검토 전'&&pm(e.project_id)&&<><Button small onClick={()=>setReviewMeeting(e.meeting_id)}>회의록과 함께 검토</Button><button className="text-link" onClick={()=>setEditor(e)}>대조·수정</button><button className="text-link" onClick={()=>setConfirm({title:'변경 후보 제외',text:'이 후보를 이력에서 제외할까요? 제외 목록에서 다시 확인할 수 있습니다.',action:async()=>{await api('/changes/'+e.id+'/decision','POST',{version:e.version,action:'exclude'});await refresh()}})}>제외</button></>}
   {e.review_state==='제외'&&pm(e.project_id)&&<Button small onClick={()=>setConfirm({title:'변경 후보 복원',text:'이 후보를 검토할 변경 목록으로 돌릴까요? 이력에 반영하려면 다시 확인해야 합니다.',action:async()=>{await api('/changes/'+e.id+'/decision','POST',{version:e.version,action:'restore'});await refresh();setTab('pending')}})}>검토할 변경으로 복원</Button>}
  </div>
 </article>;
 return <><PageHead eyebrow="PROJECT CHANGES" title="변경 이력" text="회의록의 변경 제안을 원문과 대조하고, 확인한 내용을 프로젝트별로 모아 봅니다.">{D.projects.some(p=>pm(p.id)&&(!pid||pid===p.id))&&<><Button icon={Sparkles} onClick={startScan}>변경사항 다시 찾기</Button><Button primary icon={Plus} onClick={()=>setEditor({})}>변경 기록</Button></>}</PageHead><div className="workbar"><div className="tabs">{[['history','확인된 변경 '+historyCount],['pending','검토할 변경 '+pending.length],['excluded','제외한 후보 '+excludedCount]].map(([key,l])=><button key={key} className={tab===key?'active':''} onClick={()=>setTab(key)}>{l}</button>)}</div><label className="search"><Search size={17}/><input aria-label="변경 이력 검색" placeholder="변경 대상·내용 검색" value={q} onChange={e=>setQ(e.target.value)}/></label></div>{batch&&<p className="notice" role="status">{batch.total?<>재분석 {batchDone} / {batch.total}건 완료 · 새 후보 {batchAdded}건{batchFailed>0&&<> · 실패·본문 변경·범위 이탈 {batchFailed}건</>}</>:<>새로 분석할 회의록이 없습니다.</>} · 변경 없는 분석 완료본과 진행 중인 회의록 {batch.skipped}건 제외</p>}{running&&<p className="notice"><Loader2 size={15} className="spin"/> 변경 후보를 분석하고 있습니다. 결과는 검토할 변경 목록에 표시됩니다.</p>}{data?.scans.filter(x=>x.error||x.state==='stale').map(x=><p className="warning" key={x.id}>{x.title} · {x.state==='stale'?'본문이 변경되었습니다. 최신 내용으로 변경사항 다시 찾기를 실행해 주세요.':x.error}</p>)}{!running&&data?.scans.some(x=>x.state==='ready')&&tab==='pending'&&pending.length===0&&<p className="notice">분석이 완료되었습니다. 검토할 변경 후보가 없습니다. 누락된 내용은 원문을 확인해 직접 기록할 수 있습니다.</p>}{error&&<p className="warning">{error}</p>}
 {data===null?<p>이력을 불러오는 중…</p>:tab==='excluded'?excluded.length?excluded.map(e=><section className="pending-change" key={e.id}><h3>{e.title}<small>{project(e.project_id)?.name} · {e.category}</small></h3>{row(e)}</section>):<Empty title="제외한 후보가 없습니다" text="제외한 후보는 이곳에 보관되며, 검토할 변경으로 복원할 수 있습니다."/>:groups.length?<>
  <div className="change-list-meta"><span>변경 대상 <b>{groups.length}개</b> · {tab==='pending'?'검토할 기록':'확인한 기록'} <b>{groups.reduce((n,g)=>n+g.events.length,0)}건</b></span><small>항목을 펼치면 회의별 기록을 볼 수 있습니다.</small></div>
  <div className="change-group-list">{groups.map(g=><ChangeGroup key={tab+g.key} group={g} mode={tab} projectName={project(g.project_id)?.name} renderEvent={row}/>)}</div>
 </>:q?<Empty title="검색 결과가 없습니다" text="변경 대상이나 회의 제목으로 다시 검색해 주세요."/>:tab==='history'?<Empty title="아직 확인된 변경 이력이 없습니다" text="새 회의록을 등록하면 변경 후보를 자동으로 찾습니다. 검토할 변경에서 원문과 대조한 뒤 이력에 반영하세요. 기존 회의록은 변경사항 다시 찾기를 사용할 수 있습니다."/>:<Empty title="검토할 변경 후보가 없습니다" text="AI는 변경 내용을 제안하며, PM의 확인 전에는 확정 이력에 반영되지 않습니다."/>}
 {editor&&<ChangeEditor item={editor} topics={data?.topics||[]} close={()=>setEditor(null)} saved={async()=>{setEditor(null);await refresh();setTab('history')}}/>}
 {reviewMeeting&&<MeetingChangeReview meetingId={reviewMeeting} close={()=>setReviewMeeting(null)} saved={refresh}/>}
 {evidence&&<Modal wide title={evidence.m.title} close={()=>setEvidence(null)}><SourceView record={evidence.m} selected={evidence.e.evidence} focusKey={evidence.e.id}/></Modal>}
 </>;
}

function ChangeGroup({group:g,mode,projectName,renderEvent}){
 const latest=g.events.at(-1),pending=mode==='pending',flow=g.events.slice(-3);
 return <details className="change-topic grouped-change"><summary>
  <span className="change-topic-name"><b>{g.title}</b><small>{projectName} · {g.category}</small></span>
  <span className="change-group-flow"><small>{pending?'원문에서 추출한 상태 · 검토 전':'확인한 기록의 흐름'}</small><span>{g.events.length>3&&<span className="earlier-events">이전 {g.events.length-3}건 · </span>}{flow.map((e,i)=><React.Fragment key={e.id}>{i>0&&<ArrowRight size={13}/>}<span className={'business-state state-'+e.business_state} title={e.effective_date+' · '+e.meeting_title}>{e.business_state}</span></React.Fragment>)}</span></span>
  <span className={'change-group-value '+(pending?'candidate-value':'current-value')}><small>{pending?'최근 후보 내용':'현재 확인된 확정 내용'}</small><span>{pending?latest.after:g.topic?.current_value||'확정된 변경 없음'}</span></span>
  <span className="change-group-count">기록 {g.events.length}건</span><ChevronDown className="group-chevron" size={17}/>
 </summary><div className="topic-events"><p className="change-order-note" title="같은 변경 기준일의 기록은 회의록 등록순으로 표시합니다.">변경 기준일순 · 오래된 기록부터</p>{g.events.map(renderEvent)}</div></details>;
}

function ChangeEditor({item,topics,close,saved}){
 const{D,pid,pm,run,busy,setConfirm}=useApp(),[m,setM]=useState(null),[persisted,setPersisted]=useState(item),[data,setData]=useState({meeting_id:item.meeting_id||'',source_revision:item.source_revision||1,topic_id:item.topic_id||null,title:item.title||'',category:item.category||'요구사항',before:item.before||'',after:item.after||'',business_state:item.business_state||'요청',evidence:item.evidence||[],effective_date:item.effective_date||D.today}),[verified,setVerified]=useState(false),[editEvidence,setEditEvidence]=useState(false),[sourceNotice,setSourceNotice]=useState('');
 const patch=(key,v)=>{setData(x=>({...x,[key]:v}));setVerified(false)};
 const load=async mid=>{const next=await api('/meetings/'+mid);setM(next);let evidence=[];
  if(mid===item.meeting_id&&next.revision===item.source_revision)evidence=item.evidence||[];
  else if(mid===item.meeting_id&&item.quotes?.length){const matches=item.quotes.map(quote=>next.lines.filter(l=>l.text===quote));if(matches.every(xs=>xs.length===1))evidence=matches.map(xs=>xs[0].id)}
  setSourceNotice(mid===item.meeting_id&&next.revision!==item.source_revision?(evidence.length?'본문이 새 버전으로 변경되었습니다. 동일한 근거 문장을 연결했습니다. 최신 문맥과 변경 상태를 다시 확인해 주세요.':'본문이 새 버전으로 변경되어 이전 근거를 그대로 사용할 수 없습니다. 오른쪽 최신 원문에서 근거 문장을 눌러 선택해 주세요.'):'');
  setEditEvidence(!evidence.length);setData(x=>({...x,meeting_id:mid,source_revision:next.revision,evidence,effective_date:mid===item.meeting_id?x.effective_date:next.date||D.today}));setVerified(false)};

 useEffect(()=>{if(item.meeting_id)run(()=>load(item.meeting_id))},[]);
 const selectedTopics=topics.filter(t=>t.project_id===m?.project_id),allowed=D.meetings.filter(x=>pm(x.project_id)&&(!pid||x.project_id===pid));
 const save=async confirm=>{const payload={...data,...(persisted.id?{version:persisted.version}:{})};const result=await api('/changes'+(persisted.id?'/'+persisted.id:''),persisted.id?'PATCH':'POST',payload);setPersisted(result);if(confirm)await api('/changes/'+result.id+'/decision','POST',{version:result.version,action:'confirm'});await saved()};
 const reason=!m?'근거 회의록을 선택하세요.':data.title.trim().length<2?'변경 대상 이름을 2자 이상 입력하세요.':!data.after.trim()?'변경 내용을 입력하세요.':!data.evidence.length?'오른쪽 원문에서 근거 문장을 선택하세요.':data.business_state==='확정'&&m.document_status!=='확정'?'회의록을 먼저 확정하거나, 원문에서의 상태를 확인하세요.':!verified?'하단의 원문 대조 확인 표시를 해 주세요.':'';
 return <Modal wide title={item.id?'변경 후보 대조·수정':'변경 기록'} close={close} footer={<><div className="change-disabled-reason" role="status">{reason}</div><label className="check-line"><input type="checkbox" checked={verified} onChange={e=>setVerified(e.target.checked)}/>원문·연결 대상·변경 상태를 확인했습니다.</label><Button primary disabled={!!reason||busy} onClick={()=>run(()=>save(true))}>이력에 반영</Button></>}>
 {sourceNotice&&<p className="warning">{sourceNotice}</p>}<label className="field">근거 회의록<select aria-label="변경 근거 회의록" value={data.meeting_id} onChange={e=>{patch('topic_id',null);run(()=>load(e.target.value))}}><option value="">회의록 선택</option>{allowed.map(x=><option key={x.id} value={x.id}>{x.date} · {x.title}</option>)}</select></label>{m&&<div className="change-editor-grid"><section><div className="edit-grid"><label className="span2">변경 대상 연결<select value={data.topic_id||''} onChange={e=>{const t=selectedTopics.find(x=>x.id===e.target.value);setData({...data,topic_id:t?.id||null,title:t?.title||data.title,category:t?.category||data.category});setVerified(false)}}><option value="">새 변경 대상</option>{selectedTopics.map(t=><option key={t.id} value={t.id}>{t.title}</option>)}</select></label><label className="span2">변경 대상 이름<input value={data.title} disabled={!!data.topic_id} onChange={e=>patch('title',e.target.value)} placeholder="예: 점검 커버 개폐 방식"/></label><label>구분<select value={data.category} disabled={!!data.topic_id} onChange={e=>patch('category',e.target.value)}>{['요구사항','사양','납기'].map(x=><option key={x}>{x}</option>)}</select></label><label>원문에서의 상태<select value={data.business_state} onChange={e=>patch('business_state',e.target.value)}>{['요청','확정','철회','보류'].map(x=><option key={x}>{x}</option>)}</select></label><label className="span2">변경 전<textarea value={data.before} onChange={e=>patch('before',e.target.value)} placeholder="원문에 없으면 비워 두세요."/></label><label className="span2">변경·논의 내용<textarea value={data.after} onChange={e=>patch('after',e.target.value)}/></label><label>변경 기준일<input type="date" value={data.effective_date} onChange={e=>patch('effective_date',e.target.value)}/></label></div>{data.business_state==='확정'&&m.document_status!=='확정'&&<p className="warning">확정 변경으로 기록하려면 근거 회의록을 먼저 확정해야 합니다.</p>}<p className="field-note">요청·보류·철회 기록은 현재 확정 내용을 덮어쓰지 않습니다.</p></section><section><div className="section-title"><h3>원문 대조</h3><Button small onClick={()=>setEditEvidence(!editEvidence)}>{editEvidence?'원본으로 보기':'근거 선택·수정'}</Button></div><SourceView record={m} selected={data.evidence} linesMode={editEvidence} onLine={editEvidence?id=>patch('evidence',data.evidence.includes(id)?data.evidence.filter(x=>x!==id):[...data.evidence,id]):undefined}/></section></div>}
 </Modal>;
}
