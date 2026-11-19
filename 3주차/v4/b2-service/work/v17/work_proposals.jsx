import React,{useState,useEffect}from'react';
import{ArrowLeft,ArrowRight,FileText,Search,X}from'lucide-react';
import{useApp,api,Button,Empty,Person,Modal,TaskRows,Status}from'./app';
import{CandidateEditor}from'./registration';
import{SourceView}from'./evidence';
import{unassignedFieldIssues}from'./assignment_queue';

export function WorkProposals(){
 const{D,pid,tasks,person,openTask,project,pm,workMeeting,setWorkMeeting,openMeeting,setConfirm,run,busy,reload,setFormDirty}=useApp();
 const[groups,setGroups]=useState([]),[m,setM]=useState(null),[items,setItems]=useState([]),[selected,setSelected]=useState([]),[target,setTarget]=useState(null),[error,setError]=useState(''),[q,setQ]=useState(''),[dirty,setDirty]=useState(false),[loading,setLoading]=useState(false);
 useEffect(()=>{setFormDirty(dirty);return()=>setFormDirty(false)},[dirty]);
 const loadGroups=()=>api('/work-proposals'+(pid?'?project_id='+encodeURIComponent(pid):'')).then(setGroups).catch(e=>setError(e.message));
 useEffect(()=>{loadGroups()},[pid,D.meetings]);
 const load=async id=>{const next=await api('/meetings/'+id);setM(next);setItems(next.candidates||[]);setSelected([]);setDirty(false);setError('');return next};
 useEffect(()=>{let live=true;if(!workMeeting){setM(null);setItems([]);return}setLoading(true);api('/meetings/'+workMeeting).then(next=>{if(live){setM(next);setItems(next.candidates||[]);setSelected([]);setDirty(false);setError('')}}).catch(e=>live&&setError(e.message)).finally(()=>live&&setLoading(false));return()=>{live=false}},[workMeeting]);
 const choose=id=>{if(dirty)setConfirm({title:'저장하지 않은 제안',text:'수정한 제안을 저장하지 않고 이동할까요?',button:'이동',action:()=>{setDirty(false);setWorkMeeting(id)}});else setWorkMeeting(id)};
 const p=m&&project(m.project_id),isPM=p&&pm(p.id),canEdit=m&&(isPM||m.author===D.user.id),drafts=items.filter(x=>x.state==='draft'),linked=m?D.tasks.filter(t=>t.meeting_id===m.id):[];
 const save=async send=>{const path=send&&!isPM?'/assignment-request':'/review';await api('/meetings/'+m.id+path,'POST',{version:m.version,candidates:items,selected:send?selected:[]});await load(m.id);await reload();await loadGroups()};
 const fieldIssues=unassignedFieldIssues(tasks).filter(t=>(t.title+' '+(project(t.project_id)?.name||'')).toLowerCase().includes(q.toLowerCase()));
 const shownGroups=groups.filter(g=>(g.title+' '+(project(g.project_id)?.name||'')+' '+g.candidates.map(x=>x.title).join(' ')).toLowerCase().includes(q.toLowerCase()));
 const source=items.find(x=>x.id===target);
 if(loading)return <p role="status">이 회의의 업무를 불러오고 있습니다.</p>;
 return <section className="work-proposals">{error&&<p className="warning" role="alert">{error}</p>}{!m?<>
 <div className="home-list-tools"><p className="muted">회의에서 나온 제안과 담당자 지정이 필요한 현장 이슈를 모았습니다.</p><label className="search"><Search size={16}/><input aria-label="업무 제안 검색" placeholder="회의·업무·프로젝트 검색" value={q} onChange={e=>setQ(e.target.value)}/></label></div>
 <section className="proposal-queue-section"><h3>회의에서 나온 업무 제안 <small>배정 전 초안 · {shownGroups.reduce((n,g)=>n+g.pending,0)}건</small></h3><div className="proposal-meetings">{shownGroups.map(g=><button className="proposal-meeting-row" key={g.id} onClick={()=>choose(g.id)}><FileText size={20}/><span><b>{g.title}</b><small>{project(g.project_id)?.name} · {g.date||'회의일 미정'}</small><span className="proposal-preview">{g.candidates.slice(0,2).map(x=>x.title).join(' · ')}{g.pending>2?' 외 '+(g.pending-2)+'건':''}</span></span><span className="proposal-row-count">제안 {g.pending}건{g.requested>0&&<strong>배정 요청 {g.requested}건</strong>}</span><ArrowRight size={16}/></button>)}</div>{!shownGroups.length&&<p className="queue-empty">{q?'검색 조건에 맞는 제안이 없습니다.':'대기 중인 업무 제안이 없습니다.'}</p>}</section>
 <section className="proposal-queue-section"><h3>현장 이슈 · 담당자 지정 필요 <small>등록된 업무 · {fieldIssues.length}건</small></h3><div className="field-assignment-list">{fieldIssues.map(t=><div className="field-assignment-row" key={t.id}><div><b>{t.title}</b><small>{project(t.project_id)?.name} · 접수 {person(t.created_by)?.name||'미정'} · {(t.created_at||'').slice(0,10)}</small></div><Status value={t.status}/><Button small onClick={()=>openTask(t.id,pm(t.project_id)?'settings':'action')}>{pm(t.project_id)?'담당자 지정':'내용 보기'}</Button></div>)}</div>{!fieldIssues.length&&<p className="queue-empty">{q?'검색 조건에 맞는 현장 이슈가 없습니다.':'담당자를 지정할 현장 이슈가 없습니다.'}</p>}</section>
 </>:<>
 <button className="back-link" onClick={()=>choose('')}><ArrowLeft size={16}/>업무 제안 목록</button><div className="section-title"><div><h2>{m.title}</h2><p>{p?.name} · {m.date||'회의일 미정'}</p></div><Button small onClick={()=>openMeeting(m.id)}>회의록 보기</Button></div>
 {linked.length>0&&<section className="proposal-linked"><h3>등록된 업무 {linked.length}건</h3><TaskRows items={linked}/></section>}
 <div className="section-title"><h3>아직 배정하지 않은 제안 {drafts.length}건</h3>{!canEdit&&<span>작성자와 PM이 내용을 수정할 수 있습니다.</span>}</div>
 {!drafts.length&&<Empty title="남은 업무 제안이 없습니다" text="등록된 업무의 진행 상황을 위에서 확인할 수 있습니다."/>}
 {drafts.map(c=><div key={c.id}>{(c.assignment_requested_by||m.requested_task_ids?.includes(c.id))&&<p className="proposal-requested">배정 요청됨 · <Person plain id={c.assignment_requested_by||m.author}/></p>}<CandidateEditor candidate={c} project={p} readonly={!canEdit} selected={selected.includes(c.id)} onSelected={canEdit?v=>setSelected(s=>v?[...s,c.id]:s.filter(id=>id!==c.id)):undefined} onChange={next=>{setItems(xs=>xs.map(x=>x.id===c.id?next:x));setDirty(true)}} onEvidence={()=>setTarget(c.id)}/></div>)}
 {canEdit&&drafts.length>0&&<div className="candidate-actions"><span>{selected.length}건 선택</span><Button disabled={busy} onClick={()=>run(()=>save(false),'제안을 저장했습니다.')}>제안 저장</Button><Button primary disabled={!selected.length||busy} onClick={()=>setConfirm({title:isPM?'선택 업무 배정':'업무 배정 요청',text:isPM?'선택한 '+selected.length+'건을 담당자에게 배정할까요?':'선택한 '+selected.length+'건의 배정을 PM에게 요청할까요?',button:isPM?'배정':'요청',action:()=>save(true)})}>{isPM?'선택 업무 배정':'선택 업무 배정 요청'}</Button></div>}
 {target&&source&&<Modal wide title="업무의 원문 근거" close={()=>setTarget(null)} footer={<Button onClick={()=>{if(canEdit){setItems(xs=>xs.map(x=>x.id===target?{...x,rechecked:true}:x));setDirty(true)}setTarget(null)}}>확인</Button>}><p className="field-note">{canEdit?'원문을 대조하고 필요한 근거 문장을 선택하세요.':'선택된 문장이 이 업무의 근거입니다.'}</p><SourceView record={m} linesMode selected={source.evidence||[]} onLine={canEdit?id=>{setItems(xs=>xs.map(x=>x.id===target?{...x,evidence:(x.evidence||[]).includes(id)?x.evidence.filter(y=>y!==id):[...(x.evidence||[]),id]}:x));setDirty(true)}:undefined}/></Modal>}
 </>}</section>;
}
