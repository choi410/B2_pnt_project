import React,{useMemo,useState} from 'react';
import {Search,ArrowRight,ArrowUpRight,Pencil,ChevronLeft,ChevronRight,AlertCircle} from 'lucide-react';
import {api,Button,Modal,Empty} from './app';
import {describeRequirement,trackingLabel,trackingStates} from './requirement_display';

const business=s=>s==='확정'?'합의':s;
function RequirementDetailTable({row}){
 const description=describeRequirement(row);
 return <table className="requirement-detail-table" aria-label="요구사항 상세 정보"><colgroup><col className="detail-label-column"/><col/><col className="detail-label-column"/><col/></colgroup><tbody>
  <tr><th scope="row">요구 내용</th><td colSpan={3}><strong>{row.title}</strong><p className="requirement-current-value">{description.value}</p></td></tr>
  {description.source.length>0&&<tr><th scope="row">회의 내용</th><td colSpan={3}><p>{description.source[0].text}</p></td></tr>}
  <tr><th scope="row">관련 후속 조치</th><td colSpan={3}>{description.followups.length?description.followups.map(q=><p key={q.id}>{q.text}</p>):<span className="muted">현재 연결된 후속 조치가 없습니다.</span>}</td></tr>
  <tr><th scope="row">요구 상태</th><td><span className={'status '+(['요청','보류'].includes(row.business_state)?'warning':'')}>{business(row.business_state)}</span></td><th scope="row">처리 상태</th><td title="필요할 때 직접 기록하는 상태입니다."><span className={trackingLabel(row.state)==='미등록'?'muted':''}>{trackingLabel(row.state)}</span></td></tr>
  <tr><th scope="row">담당자</th><td className={!row.owner?'warning':''}>{row.owner||'미정'}</td><th scope="row">기한</th><td className={!row.due?'warning':''}>{row.due||'미정'}</td></tr>
  <tr><th scope="row">확인할 사항</th><td colSpan={3}>{row.risks.length?<span className="warning">{row.risks.join(' · ')}</span>:<span className="muted">현재 표시된 확인 사항이 없습니다.</span>}</td></tr>
  {row.result&&<tr><th scope="row">처리 메모</th><td colSpan={3} className="requirement-note-text">{row.result}</td></tr>}
  <tr><th scope="row">근거 회의록</th><td colSpan={3}>{row.meeting_title}<small className="requirement-source-date">{row.meeting_date||'회의일 미정'}</small></td></tr>
 </tbody></table>
}
export function RequirementNotice({rows,onOpen}){
 const attention=rows.filter(r=>r.risk),missing=attention.filter(r=>!r.owner||!r.due).length,overdue=attention.filter(r=>r.risks.includes('기한 경과')).length,updated=attention.filter(r=>r.risks.includes('새 기록 확인 필요')).length;
 if(!attention.length)return null;
 const reasons=[missing&&`담당자·기한 확인 ${missing}건`,overdue&&`기한 경과 ${overdue}건`,updated&&`새 기록 확인 ${updated}건`].filter(Boolean).join(' · ');
 return <button className="requirement-notice" onClick={onOpen}><span className="requirement-notice-main"><AlertCircle size={19}/><strong>확인할 요구사항 <b>{attention.length}</b></strong></span><span className="muted">{reasons}</span><span className="requirement-notice-link">목록 보기 <ArrowRight size={16}/></span></button>
}

export function RequirementsPage({D,pid,setPid,initialFilter='all',onOpenMeeting,onOpenHistory,onEditContent,onChanged}){
 const[query,setQuery]=useState(''),[filter,setFilter]=useState(initialFilter),[sort,setSort]=useState('latest'),[page,setPage]=useState(0),[selected,setSelected]=useState(null),[editing,setEditing]=useState(false),[form,setForm]=useState(null),[saving,setSaving]=useState(false),[error,setError]=useState('');
 const rows=(D.requirements||[]).filter(r=>!pid||r.project_id===pid);
 const selectedRow=(D.requirements||[]).find(r=>r.id===selected);
 const counts={all:rows.length,risk:rows.filter(r=>r.risk).length,done:rows.filter(r=>r.state==='조치 완료').length};
 const filtered=useMemo(()=>{
  let result=rows.filter(r=>(filter==='all'||filter==='risk'&&r.risk||filter==='done'&&r.state==='조치 완료')&&(!query||[describeRequirement(r).title,r.content,r.project_name,r.owner,...r.risks,...(r.quotes||[]).map(q=>q.text)].join(' ').toLowerCase().includes(query.toLowerCase())));
  return result.sort((a,b)=>sort==='due'?(a.due||'9999').localeCompare(b.due||'9999'):sort==='title'?a.title.localeCompare(b.title,'ko'):(b.meeting_date||'').localeCompare(a.meeting_date||''));
 },[D.requirements,pid,query,filter,sort]);
 const currentPage=Math.min(page,Math.max(0,Math.ceil(filtered.length/10)-1)),offset=currentPage*10;
 const close=()=>{setSelected(null);setEditing(false);setForm(null);setError('')};
 function beginEdit(){setForm({version:selectedRow.version,signature:selectedRow.signature,owner:selectedRow.owner,due:selectedRow.due,state:trackingLabel(selectedRow.state),result:selectedRow.result});setEditing(true);setError('')}
 async function save(){setSaving(true);setError('');try{await api('/v3/requirements/'+selectedRow.id,'PATCH',form);await onChanged();setEditing(false);setForm(null)}catch(e){setError(e.message)}finally{setSaving(false)}}
 return <>
  <div className="page-heading"><div><h1>요구사항</h1><p>회의에서 나온 요구와 담당자·기한을 함께 확인합니다.</p></div><select aria-label="요구사항 프로젝트" value={pid} onChange={e=>{setPid(e.target.value);setPage(0)}}><option value="">전체 프로젝트</option>{D.projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></div>
  <div className="requirements-toolbar"><div className="tabs requirements-tabs" aria-label="요구사항 필터">{[['all','전체'],['risk','확인 필요'],['done','조치 완료']].map(([key,label])=><button key={key} className={filter===key?'active':''} onClick={()=>{setFilter(key);setPage(0)}}>{label} <span>{counts[key]}</span></button>)}</div><div className="actions"><label className="requirement-search"><Search size={17}/><input type="search" aria-label="요구사항 검색" placeholder="요구사항·담당자 검색" value={query} onChange={e=>{setQuery(e.target.value);setPage(0)}}/></label><select aria-label="요구사항 정렬" value={sort} onChange={e=>{setSort(e.target.value);setPage(0)}}><option value="latest">최근 회의순</option><option value="due">기한 임박순</option><option value="title">요구사항 이름순</option></select></div></div>
  <div className="requirement-table-wrap"><table className="requirement-table" aria-label="요구사항 목록"><thead><tr><th scope="col">요구사항 / 프로젝트</th><th scope="col">요구 내용</th><th scope="col">담당자</th><th scope="col">기한</th><th scope="col">확인할 사항</th><th scope="col">처리 상태</th></tr></thead><tbody>{filtered.slice(offset,offset+10).map(r=>{const description=describeRequirement(r);return <tr key={r.id}><td><button className="requirement-title" onClick={()=>{setSelected(r.id);setEditing(false);setError('')}}>{description.title}<ArrowUpRight size={14}/></button><small className="requirement-project-name">{r.project_name}</small><div className="requirement-labels"><span className={'status '+(['요청','보류'].includes(r.business_state)?'warning':'')}>{business(r.business_state)}</span><small>{r.change_kind}</small>{r.edited&&<small>수정됨</small>}</div></td><td><p className="requirement-table-value">{description.value}</p>{description.source[0]&&<p className="requirement-context-preview">{description.source[0].text}</p>}</td><td className={!r.owner?'warning':''}>{r.owner||'미정'}</td><td className={!r.due?'warning':''}>{r.due||'미정'}</td><td><div className="requirement-risks">{r.risks.length?r.risks.map(reason=><span key={reason} className="warning">{reason}</span>):<span className="muted">—</span>}</div></td><td><span title={trackingLabel(r.state)==='미등록'?'처리 상태를 아직 기록하지 않았습니다.':''} className={trackingLabel(r.state)==='미등록'?'muted':'status '+(r.state==='조치 완료'?'requirement-complete':'')}>{trackingLabel(r.state)}</span></td></tr>})}</tbody></table></div>
  {!filtered.length&&<Empty>{rows.length?'조건에 맞는 요구사항이 없습니다.':D.meetings.some(m=>(!pid||m.project_id===pid)&&['queued','running'].includes(m.analysis_state))?'분석이 완료되면 요구사항이 자동으로 표시됩니다.':'아직 추출된 요구사항이 없습니다. 회의록을 등록하고 AI 분석 결과를 확인해 주세요.'}</Empty>}
  <div className="pager"><span>{filtered.length?offset+1:0}–{Math.min(offset+10,filtered.length)} / {filtered.length}</span><button aria-label="이전 요구사항" disabled={!currentPage} onClick={()=>setPage(currentPage-1)}><ChevronLeft/></button><button aria-label="다음 요구사항" disabled={offset+10>=filtered.length} onClick={()=>setPage(currentPage+1)}><ChevronRight/></button></div>
  {selected&&!selectedRow&&<Modal title="요구사항이 갱신되었습니다" close={close}><p>회의록의 수정·삭제 또는 재분석으로 목록이 바뀌었습니다. 목록에서 다시 선택해 주세요.</p></Modal>}
  {selectedRow&&<Modal title={describeRequirement(selectedRow).title} close={close} className="requirement-detail" footer={editing?<><Button disabled={saving} onClick={()=>{setEditing(false);setError('')}}>취소</Button><Button primary disabled={saving} onClick={save}>{saving?'저장 중…':'저장'}</Button></>:<><Button onClick={()=>onOpenHistory(selectedRow)}>변경 이력 {selectedRow.event_count}건</Button><Button primary onClick={()=>onOpenMeeting(selectedRow.meeting_id,selectedRow.evidence)}>근거 회의록 보기</Button></>}>
   <p className="muted requirement-detail-project">{selectedRow.project_name}</p>
   {editing?<div className="requirement-edit"><label>담당자<input aria-label="요구사항 담당자" list="requirement-people" maxLength={60} placeholder="미정이면 비워 두세요" value={form.owner} onChange={e=>setForm({...form,owner:e.target.value})}/><datalist id="requirement-people">{D.people.map(p=><option key={p.id} value={p.name}/>)}</datalist></label><label>기한<input aria-label="요구사항 기한" type="date" value={form.due} onChange={e=>setForm({...form,due:e.target.value})}/></label><label>처리 상태 <small className="muted">선택 기록</small><select aria-label="요구사항 처리 상태" value={form.state} onChange={e=>setForm({...form,state:e.target.value})}>{trackingStates.map(v=><option key={v}>{v}</option>)}</select><small className="tracking-help">필요할 때만 기록합니다.</small></label><label className="full">처리 메모 <small className="muted">선택</small><textarea aria-label="요구사항 처리 메모" value={form.result} maxLength={2000} onChange={e=>setForm({...form,result:e.target.value})}/></label></div>:<><RequirementDetailTable row={selectedRow}/>{selectedRow.can_edit&&<div className="actions requirement-detail-actions">{selectedRow.business_state!=='철회'&&<Button icon={Pencil} onClick={beginEdit}>담당자·기한·처리 수정</Button>}<Button onClick={()=>onEditContent(selectedRow)}>요구 내용 수정</Button></div>}</>}
   {error&&<p role="alert" className="error-box">{error}</p>}
   <details className="requirement-evidence"><summary>원문 근거 {selectedRow.quotes.length}개</summary><p className="muted">{selectedRow.meeting_title}</p>{selectedRow.quotes.map(q=><blockquote key={q.id}><small>{q.kind}</small>{q.text}</blockquote>)}</details>
  </Modal>}
 </>
}
