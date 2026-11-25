import React,{useState}from'react';
import{PeoplePicker,Person,Button,useApp}from'./app';

export function assignmentProblem(item){
 if(item.kind==='업무'&&item.owner_id&&item.requires_review!==false){
  if(item.owner_id===item.reviewer_id)return '직접 완료를 선택하거나, 담당자와 다른 검토자를 지정하세요.';
  if(!item.reviewer_id)return '검토 후 완료할 업무입니다. 완료 검토자를 지정하세요.';
 }
 return '';
}

export function AssignmentFields({value,onChange,project,readonly=false,showDue=true}){
 const confirmation=value.kind==='확인사항',ownerKey=confirmation?'reviewer_id':'owner_id';
 const owner=value[ownerKey],review=value.requires_review!==false;
 const{simple}=useApp();
 const patch=(key,next)=>onChange({...value,[key]:next});
 const problem=assignmentProblem(value);
 return <div className="assignment-fields">
  <div className="assignment-field"><span>{confirmation?'확인 담당자':'담당자'}</span>{readonly?<Person plain id={owner}/>:<PeoplePicker projectId={project?.id} value={owner} ids={project?.members||[]} placeholder="담당자 미정" onChange={v=>patch(ownerKey,v)}/>}</div>
  {showDue&&<label className="assignment-field">완료 목표일<input type="date" disabled={readonly} value={value.due||''} onChange={e=>patch('due',e.target.value||null)}/></label>}
  {!simple&&!confirmation&&<div className="assignment-field completion-field"><span>완료 방식</span><div className="completion-choice" role="group" aria-label="완료 방식">
   <button type="button" disabled={readonly} aria-pressed={!review} onClick={()=>onChange({...value,requires_review:false,reviewer_id:null})}>직접 완료</button>
   <button type="button" disabled={readonly} aria-pressed={review} onClick={()=>onChange({...value,requires_review:true,reviewer_id:value.reviewer_id||(project?.pm!==value.owner_id?project?.pm:null)})}>검토 후 완료</button>
  </div></div>}
  {!simple&&!confirmation&&review&&<div className="assignment-field"><span>완료 검토자</span>{readonly?<Person plain id={value.reviewer_id}/>:<PeoplePicker projectId={project?.id} value={value.reviewer_id} ids={project?.members||[]} exclude={value.owner_id} placeholder="검토자 선택" onChange={v=>patch('reviewer_id',v)}/>}</div>}
  {simple?null:problem?<p className="assignment-hint error" role="status">{problem}</p>:!owner?<p className="assignment-hint">담당자 미정으로 등록하고, 업무 제안에서 나중에 지정할 수 있습니다.</p>:!confirmation&&!review?<p className="assignment-hint">담당자가 처리 결과를 남기고 직접 완료합니다.</p>:null}
 </div>;
}

export function BatchAssignment({items,selected,onChange,project,disabled=false}){
 const[owner,setOwner]=useState(null),[message,setMessage]=useState('');
 const{person}=useApp();
 if(selected.length<2)return null;
 return <div className="batch-assignment"><b>선택한 {selected.length}건</b><div><PeoplePicker projectId={project?.id} value={owner} ids={project?.members||[]} placeholder="같은 담당자 선택" onChange={v=>{setOwner(v);setMessage('')}}/></div><Button small disabled={!owner||disabled} onClick={()=>{onChange(items.map(c=>selected.includes(c.id)?{...c,[c.kind==='확인사항'?'reviewer_id':'owner_id']:owner}:c));setMessage(person(owner)?.name+' · '+selected.length+'건에 적용했습니다.')}}>담당자 일괄 적용</Button>{message&&<span role="status">{message}</span>}</div>;
}
