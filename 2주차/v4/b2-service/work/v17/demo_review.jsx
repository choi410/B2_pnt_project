import React,{useState,useEffect}from'react';
import{Plus,FileText,Pencil}from'lucide-react';
import{Button,IconButton}from'./app';
import{FollowupEditor}from'./demo_followup';

import{orderedNotes}from'./demo_note_order.mjs';

const labels={summary:'논의',decisions:'결정',candidates:'후속 조치',changes:'요구·변경'};
export function ReviewNotes({bundle,source,mode='reading',readonly=false,onUpdate,onRemove,onAdd,selection,onPreview,changesPending=false,changeError='',analyzed=false}){
 const[active,setActive]=useState(null),[editing,setEditing]=useState(false);
 const narrative=true;
 useEffect(()=>{if(!selection?.pinned){setActive(null);setEditing(false)}},[selection?.pinned]);
 const choose=(e,item,key,index)=>{setActive({key,index});setEditing(false);onPreview({key,index,pinned:true})};
 const add=()=>{const selection=onAdd(active);setActive(selection);setEditing(true);onPreview({...selection,pinned:true})};
 const close=()=>{setActive(null);setEditing(false);onPreview(null)};
 function itemRow(item,key,index,id){
  const chosen=active?.key===key&&active.index===index,edit=chosen&&editing&&!readonly,text=key==='candidates'?(item.description||item.title):item.text;
  return <article className={'demo-review-row '+(chosen?'selected ':'')+(key==='changes'?'is-change':'')} key={id||item.id||key+index}>
   {edit?<div className="demo-inline-edit">{key==='candidates'?<FollowupEditor candidate={item} onChange={next=>onUpdate(key,index,next)}/>:<label>내용 수정<textarea autoFocus aria-label="내용 수정" value={text} onChange={e=>onUpdate(key,index,{...item,text:e.target.value})}/></label>}</div>:<button type="button" className="demo-review-sentence" aria-expanded={chosen} aria-label={(key==='changes'?item.title:text||'내용을 입력하세요.')} onClick={e=>choose(e,item,key,index)} onMouseEnter={()=>onPreview({key,index,pinned:false})} onFocus={()=>onPreview({key,index,pinned:false})}>
    {key==='changes'?<><span className="demo-change-heading"><b>{item.title}</b><span className={'business-state state-'+item.business_state}>{item.business_state}</span></span><span className="demo-change-value">{item.before&&<><span className="demo-before">{item.before}</span><span aria-label="변경 내용"> → </span></>}{item.after}</span></>:<><span className={'demo-line-label label-'+key}>{labels[key]}</span><span className="demo-sentence-text">{text||'내용을 입력하세요.'}</span></>}
   </button>}
   {chosen&&<div className="demo-selected-actions">{key!=='changes'&&!readonly&&<button type="button" className="text-link" onClick={()=>{setEditing(!editing)}}><Pencil size={13}/>{edit?'수정 마침':'수정'}</button>}{edit&&<button type="button" className="text-link" onClick={()=>{onRemove(key,index);close()}}>항목 삭제</button>}<button type="button" className="text-link" onClick={()=>{close()}}>선택 해제</button></div>}
  </article>;
 }
 const notes=orderedNotes(bundle),notesCount=notes.length;
 return <div className={'demo-review-document '+(narrative?'narrative':'')}>
  <section className="demo-notes-section"><div className="demo-section-heading"><h3>회의 핵심 내용</h3>{!readonly&&<div className="demo-add"><button className="text-link" onClick={add}><Plus size={14}/>내용 추가</button></div>}</div>
  <p className="demo-reading-hint">문장을 선택하면 원문 근거를 확인할 수 있습니다.</p>
  {notes.map(({item,key,index,id})=>itemRow(item,key,index,id))}
  {!notesCount&&<p className="demo-empty-notes">{analyzed?'AI가 정리한 핵심 내용이 없습니다. 필요한 내용을 직접 추가할 수 있습니다.':'AI 정리하기를 누르면 이곳에서 회의 내용을 확인할 수 있습니다.'}</p>}</section>
  <section className="demo-changes-section"><div className="demo-section-heading"><h3>요구·변경사항</h3>{bundle.changes&&<span className="demo-section-count">{bundle.changes.length}건</span>}</div>
   {changesPending?<p className="demo-reading-hint" role="status">변경사항을 분석 중입니다. 위의 핵심 내용부터 읽어보세요.</p>:bundle.changes?(bundle.changes.length?bundle.changes.map((x,i)=>itemRow(x,'changes',i)):<p className="demo-empty-notes">추출된 요구·변경사항이 없습니다.</p>):<p className="demo-empty-notes">{changeError||'분석 후 요청·합의·보류·철회를 구분해 표시합니다.'}</p>}
   {bundle.changes?.length>0&&<p className="demo-reading-hint demo-change-footnote">등록하면 변경이력에 기록됩니다. 프로젝트 기준 확정은 별도입니다.</p>}
  </section>

 </div>;
}
