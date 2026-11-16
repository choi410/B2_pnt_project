import React,{useState,useEffect}from'react';
import{Pencil,ChevronDown,FileText}from'lucide-react';
import{useApp,api,Button,Modal,day}from'./app';
const DEFAULT_STAGES=['수주','설계 및 변경','구매','제작','검수','납품','현장','종료'];

export function FocusEditor({project:p,close}){
 const{run,busy,reload,openMeeting}=useApp(),o=p.overview||{};
 const[form,setForm]=useState({version:o.version||1,current_stage:o.current_stage||'',next_goal:o.next_goal||'',next_goal_date:o.next_goal_date||''});
 const[custom,setCustom]=useState(false),[proposals,setProposals]=useState(null),[error,setError]=useState(''),[chosen,setChosen]=useState({}),[confirmClose,setConfirmClose]=useState(false);
 const stages=[...new Set([...(o.stages?.length?o.stages:DEFAULT_STAGES),...(o.current_stage?[o.current_stage]:[])])];
 const dirty=['current_stage','next_goal','next_goal_date'].some(k=>form[k]!==String(o[k]||''));
 const requestClose=()=>dirty?setConfirmClose(true):close();
 const refresh=()=>{setError('');api('/projects/'+p.id+'/focus-suggestions').then(setProposals).catch(e=>setError(e.message))};
 useEffect(()=>{let live=true;api('/projects/'+p.id+'/focus-suggestions').then(x=>live&&setProposals(x)).catch(e=>live&&setError(e.message));return()=>{live=false}},[p.id]);
 const patch=(key,value)=>{setForm(f=>({...f,[key]:value}));setChosen(c=>({...c,[key==='next_goal_date'?'next_goal':key]:null}));setConfirmClose(false)};
 const useSuggestion=item=>{setForm(f=>({...f,[item.field]:item.value,...(item.field==='next_goal'?{next_goal_date:item.due||''}:{})}));setChosen(c=>({...c,[item.field]:item.id}));if(item.field==='current_stage')setCustom(false)};
 return <Modal title="현재 단계 · 다음 목표" close={requestClose} variant="project-focus" footer={<><Button disabled={busy} onClick={requestClose}>취소</Button><Button primary disabled={busy||!dirty} onClick={()=>run(async()=>{await api('/projects/'+p.id+'/focus','PATCH',{...form,suggestion_ids:Object.values(chosen).filter(Boolean)});await reload();close()},'프로젝트 단계와 목표를 저장했습니다.')}>저장</Button></>}>
  <p className="focus-project-name">{p.name}</p>
  <div className="focus-form"><label>현재 단계<select aria-label="현재 단계" value={custom?'__custom':form.current_stage} onChange={e=>{if(e.target.value==='__custom'){setCustom(true);patch('current_stage','')}else{setCustom(false);patch('current_stage',e.target.value)}}}><option value="">미지정</option>{stages.map(s=><option key={s}>{s}</option>)}<option value="__custom">직접 입력 · 병행 단계</option></select></label>
   {custom&&<label>단계 이름<input aria-label="단계 이름" maxLength={80} value={form.current_stage} placeholder="예: 설계·구매 병행" onChange={e=>patch('current_stage',e.target.value)}/></label>}
   <label>다음 목표<input aria-label="다음 목표" maxLength={2000} value={form.next_goal} placeholder="예: 고객 도면 승인 받기" onChange={e=>patch('next_goal',e.target.value)}/></label>
   <label className="focus-goal-date">목표일 <small>선택</small><input aria-label="목표일" type="date" value={form.next_goal_date} onChange={e=>patch('next_goal_date',e.target.value)}/></label>
  </div>
  <details className="focus-proposals"><summary>회의록에서 참고할 제안 {proposals?.items.length>0&&<span>{proposals.items.length}건</span>}<ChevronDown size={15}/></summary>
   <p className="field-note">최근 회의록의 명시된 단계와 등록 시 정리한 후속 조치입니다. 적용 후 저장하면 반영됩니다.</p>
   {error?<p role="alert">{error}<button type="button" className="text-link" onClick={refresh}>다시 확인</button></p>:!proposals?<p role="status">최근 회의록 확인 중…</p>:proposals.stale?<p className="muted">최근 회의록 본문이 바뀌어 제안을 표시하지 않습니다.</p>:!proposals.items.length?<p className="muted">최근 회의록에 제안할 단계·목표가 없습니다. 직접 입력할 수 있습니다.</p>:proposals.items.map(item=><section key={item.id} className="focus-proposal"><small>{item.field==='current_stage'?'현재 단계':'다음 목표'} 제안 · {item.origin}</small><div><b>{item.value}</b><Button small disabled={chosen[item.field]===item.id} onClick={()=>useSuggestion(item)}>{chosen[item.field]===item.id?'입력됨':'적용'}</Button></div>{item.due&&<small>목표일 {item.due}</small>}<details><summary>원문 근거</summary>{item.evidence.map(e=><blockquote key={e.id}>{e.text}</blockquote>)}<button type="button" className="text-link" onClick={()=>{if(dirty){setConfirmClose(true);return}close();openMeeting(item.meeting.id)}}><FileText size={14}/>{item.meeting.title} · {day(item.meeting.date)}</button></details></section>)}
  </details>
  {confirmClose&&<div className="focus-discard" role="alert"><span>저장하지 않은 내용을 닫을까요?</span><Button small onClick={()=>setConfirmClose(false)}>계속 수정</Button><Button small onClick={close}>저장하지 않고 닫기</Button></div>}
 </Modal>;
}

export function ProjectFocus({project:p,compact=false}){
 const{pm,person}=useApp(),[edit,setEdit]=useState(false),o=p.overview||{};
 return <><section className={'project-direction '+(compact?'compact':'')} aria-label={p.name+' 현재 단계와 다음 목표'}>
  <div className="direction-stage"><small>현재 단계</small><strong className={!o.current_stage?'is-empty':''}>{o.current_stage||'미지정'}</strong></div>
  <div className="direction-goal"><small>다음 목표</small><strong className={!o.next_goal?'is-empty':''}>{o.next_goal||'아직 정하지 않았습니다'}</strong>{o.next_goal&&o.next_goal_date&&<time dateTime={o.next_goal_date}>목표일 {o.next_goal_date}</time>}</div>
  {pm(p.id)&&<button className="direction-edit" type="button" aria-label={p.name+' 단계·목표 수정'} onClick={()=>setEdit(true)}><Pencil size={14}/>수정</button>}
  {!compact&&o.focus_updated_at&&<p className="direction-updated">{person(o.focus_updated_by)?.name||'PM'} · {day(o.focus_updated_at)} 확인</p>}
 </section>{edit&&<FocusEditor project={p} close={()=>setEdit(false)}/>}</>;
}
