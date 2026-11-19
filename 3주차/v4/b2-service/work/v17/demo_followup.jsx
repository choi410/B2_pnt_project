import React from 'react';
import {useApp} from './app';

// These are statements extracted from a meeting, not task assignments.
export function FollowupEditor({candidate:c,onChange}){
 const{person}=useApp();
 const patch=(key,value)=>onChange({...c,[key]:value,selected_for_assignment:false});
 return <div className="demo-followup-editor">
  <label>후속 조치 제목<input aria-label="후속 조치 제목" value={c.title||''} onChange={e=>patch('title',e.target.value)}/></label>
  <label>내용<textarea aria-label="후속 조치 내용" value={c.description||''} onChange={e=>patch('description',e.target.value)}/></label>
  <label>구분<select aria-label="후속 조치 구분" value={c.kind} onChange={e=>patch('kind',e.target.value)}><option value="업무">후속 조치</option><option value="확인사항">추가 확인</option></select></label>
  {(c.owner_id||c.start||c.due)&&<p className="field-note">원문에서 추출한 정보: {[c.owner_id&&person(c.owner_id)?.name,c.start&&'시작 '+c.start,c.due&&'기한 '+c.due].filter(Boolean).join(' · ')}</p>}
 </div>;
}
