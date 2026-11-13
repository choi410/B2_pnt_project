import React,{useState,useEffect,useRef}from'react';
import{Plus,Search,Sparkles,FileText,Loader2,RotateCcw,ChevronDown,ChevronUp}from'lucide-react';
import{useApp,api,Button,Modal,PageHead,Empty}from'./app';
import{SourceView}from'./evidence';
import{ChangeEditor}from'./change_editor';
import{filterChangeGroups,changeStateLabel}from'./change_groups';
import{categoryLabel}from'./project_story';
import{historyGroups,decisionComparisonIds,missingRecordSeed}from'./change_subjects';

export function MeetingChangeStatus({meeting:m}){
 const{nav}=useApp(),[scan,setScan]=useState({state:m.change_scan_state||'idle'});
 useEffect(()=>{let live=true,timer;const poll=async()=>{try{const next=await api('/changes/meetings/'+m.id+'/status');if(!live)return;setScan(next);if(['queued','running'].includes(next.state))timer=setTimeout(poll,2500)}catch{if(live)timer=setTimeout(poll,5000)}};poll();return()=>{live=false;clearTimeout(timer)}},[m.id,m.revision,m.version]);
 if(scan.state==='idle')return null;
 const waiting=['queued','running'].includes(scan.state),failed=['failed','stale'].includes(scan.state);
 const text=waiting?'요구·변경사항을 자동으로 찾고 있습니다.':failed?'요구·변경 분석에 확인이 필요합니다. 흐름 화면의 분석 관리에서 다시 시도할 수 있습니다.':scan.total>0?'이 회의의 요구·변경 기록 '+scan.total+'건을 흐름에서 볼 수 있습니다.':'이 회의에서 추출된 요구·변경사항이 없습니다.';
 return <div className="change-scan-note" role="status">{waiting&&<Loader2 size={15} className="spin"/>}<span>{text}</span><button className="text-link" onClick={()=>nav('changes','all',m.project_id)}>변경 흐름 보기</button></div>;
}

export function ChangeHistory(){
 const{D,pid,pm,project,person,run,setConfirm,busy,changeFocus,openTask}=useApp();
 const[data,setData]=useState(null),[query,setQuery]=useState(''),[mode,setMode]=useState('all'),[selected,setSelected]=useState(changeFocus||''),[focusEvent,setFocusEvent]=useState(''),[editor,setEditor]=useState(null),[evidence,setEvidence]=useState(null),[error,setError]=useState(''),[batch,setBatch]=useState(null),[expanded,setExpanded]=useState(false);
 const requestSeq=useRef(0),mounted=useRef(true),scope=useRef(pid),eventNodes=useRef({});scope.current=pid;
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[]);
 const refresh=async()=>{const seq=++requestSeq.current,target=pid;try{const next=await api('/changes'+(target?'?project_id='+encodeURIComponent(target):''));if(mounted.current&&scope.current===target&&seq===requestSeq.current){setData(next);setError('')}return next}catch(e){if(mounted.current&&scope.current===target&&seq===requestSeq.current)setError(e.message)}};
 useEffect(()=>{setData(null);setSelected(changeFocus||'');setFocusEvent('');setQuery('');setMode('all');setBatch(null);setExpanded(false);refresh();const timer=setInterval(refresh,8000);return()=>{clearInterval(timer);requestSeq.current++}},[pid]);
 useEffect(()=>{if(changeFocus){setSelected(changeFocus);setMode('all');setQuery('')}},[changeFocus]);
 const events=(data?.events||[]).map(e=>({...e,meeting_title:e.meeting_title||D.meetings.find(m=>m.id===e.meeting_id)?.title||'회의록'}));
 const all=historyGroups(events,data?.topics||[]),excluded=events.filter(e=>e.review_state==='제외'&&!e.superseded_by_revision);
 const groups=filterChangeGroups(historyGroups(events,data?.topics||[],mode),query,id=>project(id)?.name||'');
 const chosen=groups.find(g=>g.key===selected||g.originalKeys.includes(selected))||groups.find(g=>g.events.some(e=>e.id===focusEvent))||groups[0];
 useEffect(()=>{if(expanded&&focusEvent)eventNodes.current[focusEvent]?.scrollIntoView({block:'nearest',behavior:'smooth'})},[focusEvent,expanded,chosen?.key]);
 const canManage=D.projects.some(p=>pm(p.id)&&(!pid||p.id===pid));
 const scans=data?.scans||[],running=scans.filter(s=>['running','queued'].includes(s.state)),failed=scans.filter(s=>s.error||s.state==='stale');
 const select=g=>{setSelected(g.key);setFocusEvent('');setExpanded(false)};
 const openEvidence=e=>run(async()=>{const m=await api('/meetings/'+e.meeting_id),rev=m.revisions.find(r=>r.number===e.source_revision);if(!rev)throw new Error('이 기록의 원문 버전을 찾을 수 없습니다.');setEvidence({m:{...m,source:rev.body,title:rev.title,lines:null,view_revision:e.source_revision},e})});
 const decide=async(e,action)=>{await api('/changes/'+e.id+'/decision','POST',{version:e.version,action});setFocusEvent(e.id);setSelected(action==='exclude'?chosen?.key||'':'');await refresh()};
 const exclude=e=>setConfirm({title:'기록 제외',text:'잘못 추출되었거나 중복된 기록인가요? 흐름에서 제외하고, 제외 목록에서 복원할 수 있습니다.',button:'제외',action:()=>decide(e,'exclude')});
 const startScan=()=>run(async()=>{setBatch(await api('/changes/analyze-scope','POST',{project_id:pid||null}));await refresh()});
 const compareIds=decisionComparisonIds(chosen),categories=[...new Set(groups.map(g=>g.category))].sort((a,b)=>['사양','납기','요구사항'].indexOf(a)-['사양','납기','요구사항'].indexOf(b));
 const related=chosen?D.tasks.filter(t=>chosen.events.some(e=>e.meeting_id===t.meeting_id)):[];
 return <div className="change-flow-page history-simple"><PageHead title="요구·변경 이력" text="대상을 선택하면 회의마다 달라진 내용을 볼 수 있습니다."/>
 <div className="flow-toolbar"><div className="tabs" aria-label="변경 흐름 필터">{[['all','전체 대상',all.length],['excluded','제외한 기록',excluded.length]].map(([key,label,count])=><button key={key} className={mode===key?'active':''} aria-pressed={mode===key} onClick={()=>{setMode(key);setSelected('');setFocusEvent('');setExpanded(false)}}>{label}<em>{count}</em></button>)}</div><label className="search"><Search size={16}/><input aria-label="변경 흐름 검색" placeholder="대상·회의·내용 검색" value={query} onChange={e=>setQuery(e.target.value)}/></label></div>
 {error&&<p className="warning" role="alert">{error}</p>}
 {running.length>0&&<p className="field-note" role="status"><Loader2 className="spin" size={14}/> 회의록 {running.length}건 분석 중 · 완료되면 자동으로 표시됩니다.</p>}
 {data===null?<p role="status">변경 이력을 불러오고 있습니다.</p>:groups.length?<div className="flow-workspace"><nav className="flow-topics" aria-label="변경 대상"><span className="flow-topics-label">변경 대상 <b>{groups.length}</b></span>{categories.map(category=><section className="flow-topic-section" key={category}><h3>{categoryLabel(category)}</h3>{groups.filter(g=>g.category===category).map(g=><button key={g.key} className={'flow-topic-item '+(chosen?.key===g.key?'selected':'')} aria-current={chosen?.key===g.key?'true':undefined} onClick={()=>select(g)}><b>{g.title}</b><span className="subject-count">{g.events.length}<span className="sr-only">건의 기록</span></span>{!pid&&new Set(all.map(g=>g.project_id)).size>1&&<small>{project(g.project_id)?.name}</small>}</button>)}</section>)}</nav>
 <section className="flow-detail" aria-label={chosen.title+' 변경 흐름'}><div className="flow-detail-head"><div><small>{project(chosen.project_id)?.name} · {categoryLabel(chosen.category)}</small><h2>{chosen.title}</h2></div><span>{chosen.events.length}건의 기록</span></div>
 <div className="history-reading-hint"><span>시간순 변화</span><small>기록을 누르면 원문 근거와 상세 내용을 볼 수 있습니다.</small></div>
 <ol className="subject-history" aria-label="시간순 변화">{chosen.events.map((e,index)=>{
  const isExcluded=e.review_state==='제외',canEdit=pm(e.project_id)&&!isExcluded;
  const notice=e.source_deleted?'근거 회의록이 휴지통에 있습니다.':e.source_changed?'회의록 본문이 바뀌었습니다. 수정에서 최신 근거를 대조해 주세요.':!e.evidence?.length?'원문 근거를 연결해 주세요.':compareIds.has(e.id)?'같은 날짜에 다른 결정 내용이 있습니다. 각 기록의 조건과 원문을 비교해 주세요.':'';
  const opened=expanded&&focusEvent===e.id;
  return <li key={e.id} ref={el=>{eventNodes.current[e.id]=el}} className={'history-step '+(isExcluded?'excluded ':'')+(opened?'opened':'')} data-change-id={e.id}><time>{e.effective_date}</time><span className="history-dot" aria-hidden="true"/><article><button className="history-step-toggle" aria-expanded={opened} aria-controls={'history-record-'+e.id} onClick={()=>{setFocusEvent(e.id);setExpanded(!opened)}}><span className="history-step-label"><span className={'business-state state-'+e.business_state}>{changeStateLabel(e)}</span>{isExcluded&&<small>제외됨</small>}{!isExcluded&&notice&&<small>{compareIds.has(e.id)&&!e.source_changed&&!e.source_deleted?'결정 내용 비교':'근거 확인 필요'}</small>}</span><strong>{e.after}</strong><ChevronDown size={16}/></button>
 {opened&&<section className="history-record" id={'history-record-'+e.id}>
 {e.before&&<p className="history-before"><b>이전 내용</b>{e.before}</p>}
 <div className="history-source-head"><span>원문 근거</span><button className="text-link" onClick={()=>openEvidence(e)}><FileText size={14}/>원문 보기</button></div>
 <p className="history-meeting-name">{e.meeting_title}{e.source_changed?' · 당시 원문 v'+e.source_revision:''}</p>
 {e.quotes?.length?e.quotes.map((quote,i)=><blockquote key={i}>{quote}</blockquote>):<p>근거 회의록에서 해당 내용을 확인해 주세요.</p>}
 {chosen.grouped&&<small className="history-original-title">추출 당시 항목명: {e.title}</small>}
 {!isExcluded&&notice&&<p className="timeline-warning">{notice}</p>}
 <div className="history-record-actions">{canEdit&&<><button className="text-link" onClick={()=>setEditor(e)}>수정</button><button className="text-link" onClick={()=>exclude(e)}>제외</button></>}{isExcluded&&pm(e.project_id)&&<Button small disabled={busy} icon={RotateCcw} onClick={()=>run(async()=>{await decide(e,'restore');setMode('all')},'변경 흐름에 복원했습니다.')}>흐름으로 복원</Button>}<button type="button" className="text-link history-collapse" aria-label="변경 기록 접기" aria-controls={'history-record-'+e.id} aria-expanded={true} onClick={()=>{setExpanded(false);eventNodes.current[e.id]?.querySelector('.history-step-toggle')?.focus({preventScroll:true})}}>접기<ChevronUp size={14}/></button></div>
 </section>}</article></li>;
 })}</ol>
 {related.length>0&&<section className="flow-related-tasks"><h3>같은 회의에서 등록한 업무 <small>{related.length}건</small></h3><p>회의 단위로 연결된 업무입니다. 이 주제의 해결 여부와는 별개입니다.</p>{related.map(t=><button key={t.id} onClick={()=>openTask(t.id)}><span>{t.title}</span><small>{person(t.kind==='확인사항'?t.reviewer_id:t.owner_id)?.name||'미정'} · {t.status}</small></button>)}</section>}
 </section></div>:<Empty title={query?'검색 결과가 없습니다':mode==='excluded'?'제외한 기록이 없습니다':'아직 요구·변경 기록이 없습니다'} text={mode==='all'?'회의록에서 찾은 최초 요구와 변경 기록이 자동으로 쌓입니다. 대상을 선택하면 시간순 흐름을 볼 수 있습니다.':'검색어나 필터를 바꿔 보세요.'}/>}
 {data&&mode==='all'&&(chosen?pm(chosen.project_id):canManage)&&<div className="history-add-record"><button className="text-link" onClick={()=>setEditor(missingRecordSeed(chosen,pid))}><Plus size={14}/>누락된 내용 추가</button></div>}
 {data&&canManage&&<details className="flow-analysis-tools"><summary>분석 관리{failed.length>0?' · 확인 필요 '+failed.length+'건':''}</summary><p className="field-note">새 회의록은 자동 분석합니다. 실패했거나 이전 분석 기준으로 처리한 회의록은 다시 찾기를 사용할 수 있습니다.</p>{failed.map(s=><p className="timeline-warning" key={s.id}>{s.title} · {s.error||'최신 본문·분석 기준 확인 필요'}</p>)}<Button small icon={Sparkles} disabled={busy||running.length>0} onClick={startScan}>변경사항 다시 찾기</Button>{batch&&<p role="status">재분석 요청 {batch.total}건 · 이미 분석했거나 처리 중인 회의록 {batch.skipped}건 제외</p>}</details>}
 {editor&&<ChangeEditor item={editor} topics={data?.topics||[]} close={()=>setEditor(null)} saved={async id=>{setEditor(null);setFocusEvent(id);setSelected('');setQuery('');setMode('all');setExpanded(true);await refresh()}}/>}
 {evidence&&<Modal wide title={evidence.m.title} close={()=>setEvidence(null)}>{evidence.m.view_revision!==evidence.m.revision&&<p className="field-note">이 기록을 추출한 당시 본문 v{evidence.m.view_revision}입니다.</p>}<SourceView record={evidence.m} linesMode={evidence.m.view_revision!==evidence.m.revision} selected={evidence.e.evidence} focusKey={evidence.e.id}/></Modal>}
 </div>;
}
