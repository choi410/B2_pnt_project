import React,{useState} from 'react';
import {Loader2} from 'lucide-react';
import {api,Button,Modal} from './app';

export function HistoryEditor({event,meeting,close,onSaved}){
 const [draft,setDraft]=useState({title:event.title,business_state:event.business_state,before:event.before||'',after:event.after,evidence:[...event.evidence]}),[choosing,setChoosing]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState('');
 const lines=meeting.lines||[],selected=lines.filter(line=>draft.evidence.includes(line.id));
 const update=(key,value)=>setDraft(old=>({...old,[key]:value}));
 const valid=draft.title.trim().length>=2&&draft.after.trim()&&selected.length>0&&selected.length<=20;
 const changed=['title','business_state','before','after'].some(key=>draft[key]!==String(event[key]||''))||draft.evidence.join('|')!==event.evidence.join('|');
 const dismiss=()=>{if(!saving)close()};
 async function save(){
  if(!valid||!changed||saving)return;
  setSaving(true);setError('');
  try{const saved=await api('/v3/changes/'+event.id,'PATCH',{...draft,version:event.version,source_revision:event.source_revision});onSaved(saved)}
  catch(e){setError(e.message)}finally{setSaving(false)}
 }
 return <Modal title="변경 기록 수정" className="history-edit-modal" close={dismiss} footer={<><Button disabled={saving} onClick={dismiss}>취소</Button><Button primary disabled={saving||!valid||!changed} onClick={save}>{saving&&<Loader2 size={16} className="spin"/>}{saving?'저장 중':'변경 저장'}</Button></>}>
  <div className="history-editor">
   <p className="history-edit-source">{meeting.title} · {meeting.date||'날짜 미정'}</p>
   <div className="history-edit-heading">
    <label>항목명<input autoFocus maxLength={160} value={draft.title} disabled={saving} onChange={e=>update('title',e.target.value)}/></label>
    <label>상태<select value={draft.business_state} disabled={saving} onChange={e=>update('business_state',e.target.value)}>{[['요청','요청'],['확정','합의'],['보류','보류'],['철회','철회']].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
   </div>
   <div className="history-edit-values">
    <label><span>변경 전 <small>(선택)</small></span><textarea rows={3} maxLength={1500} value={draft.before} disabled={saving} placeholder="이전 내용이 없으면 비워 두세요." onChange={e=>update('before',e.target.value)}/></label>
    <label>변경 내용<textarea rows={3} maxLength={1500} value={draft.after} disabled={saving} onChange={e=>update('after',e.target.value)}/></label>
   </div>
   <section className="history-edit-evidence"><div className="section-head"><h3>원문 근거 <small>{selected.length}개</small></h3><button type="button" disabled={saving} onClick={()=>setChoosing(!choosing)}>{choosing?'선택 마침':'근거 변경'}</button></div>
    {choosing?<div className="history-evidence-options" role="group" aria-label="원문 근거 선택">{lines.map(line=><label key={line.id}><input type="checkbox" checked={draft.evidence.includes(line.id)} disabled={saving||(!draft.evidence.includes(line.id)&&selected.length>=20)} onChange={e=>update('evidence',e.target.checked?[...draft.evidence,line.id]:draft.evidence.filter(id=>id!==line.id))}/><span>{line.text}</span></label>)}</div>:<div className="history-evidence-quotes">{selected.map(line=><blockquote key={line.id}>{line.text}</blockquote>)}</div>}
   </section>
   <p className="history-edit-note">선택한 기록만 수정합니다. 회의록 원문과 수정 전 기록은 보관됩니다.</p>
   {error&&<p role="alert" className="history-edit-error">{error}</p>}
  </div>
 </Modal>
}
