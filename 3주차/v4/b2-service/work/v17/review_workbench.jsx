import React,{useState}from'react';
import{Plus,Sparkles,Loader2,TriangleAlert,X}from'lucide-react';
import{useApp,Button,IconButton,PeoplePicker,Modal}from'./app';
import{SourceView}from'./evidence';
import{CandidateEditor}from'./registration';

export function ReviewWorkbench({draft,source,bundle,project,analyzing,target,evidence,marks,focus,editEvidence,setEditEvidence,onTarget,onClear,onLine,onUpdate,onAdd,onRemove,onOverall,onBody,onAnalyze,overall}){
 const{busy,person}=useApp(),[original,setOriginal]=useState(false),[editing,setEditing]=useState(null);
 const lines=source.split(/\r?\n/).map(t=>t.trim()).filter(Boolean).map((text,i)=>({id:'L'+String(i+1).padStart(3,'0'),text}));
 const item=target?bundle[target.key]?.[target.index]:null;
 const missing=bundle.candidates.map((c,i)=>({c,i,owner:c.kind==='확인사항'?c.reviewer_id:c.owner_id})).filter(x=>!x.owner||!x.c.due);
 const active=(key,i)=>target?.key===key&&target.index===i?'selected':'';
 const show=(key,i)=>{setOriginal(false);onTarget(key,i)};
 const patch=(key,i,k,v)=>onUpdate(key,i,{...bundle[key][i],[k]:v});
 return <div className="reference-review">
  <section className="ref-panel ref-original"><header><h2>원문</h2><div className="ref-tools"><button className="text-link" disabled={analyzing} onClick={onBody}>본문 수정</button>{draft.preview_pages>0&&<button className="text-link" aria-pressed={original} onClick={()=>setOriginal(!original)}>{original?'본문 대조':'원본 파일'}</button>}</div></header>
   <dl className="ref-meta"><dt>회의명</dt><dd>{draft.title||'회의 제목 미입력'}</dd><dt>프로젝트</dt><dd>{project?.name||'선택 전'}</dd><dt>회의일</dt><dd>{draft.meeting_date||'미정'}</dd></dl>
   <div className="ref-source-scroll source-scroll"><SourceView record={{...draft,source,lines:null}} type="meeting-imports" linesMode={!original||editEvidence} selected={evidence} marks={target?null:marks} focusKey={focus} onLine={editEvidence&&target?onLine:undefined}/></div>
   <footer className="ref-legend"><span><i className="req"/>요구·변경 근거</span><span><i className="task"/>할 일 근거</span></footer>
  </section>
  <section className="ref-panel ref-extraction"><header><h2>AI 정리 결과</h2><Button small primary disabled={busy||analyzing||!project} onClick={onAnalyze}>{analyzing?<Loader2 className="spin" size={14}/>:<Sparkles size={14}/>} {analyzing?'분석 중':'AI로 정리'}</Button></header>
   {analyzing?<div className="ref-wait" role="status"><Loader2 className="spin"/><p>요약·요구사항·할 일을 정리하고 있습니다.</p><small>임시 저장본에서 이어갈 수 있습니다.</small></div>:<>
    {!project&&<p className="ref-inline-note">위에서 프로젝트를 선택하면 AI 정리를 시작할 수 있습니다.</p>}
    {draft.analysis_error&&<p className="warning">{draft.analysis_error}</p>}
    <details className="ref-summary" open={undefined}><summary>전체 요약·결정사항 <span>{bundle.summary.length+bundle.decisions.length}건</span></summary><div><label>전체 요약<textarea aria-label="전체 요약" rows={3} value={bundle.overall??overall} onChange={e=>onOverall(e.target.value)} placeholder="AI 정리 후 요약을 확인할 수 있습니다."/></label>{['summary','decisions'].map(key=><section key={key}><h3>{key==='summary'?'핵심 요약':'결정사항'}<button className="text-link" onClick={()=>onAdd(key)}><Plus size={13}/>추가</button></h3>{bundle[key].map((x,i)=><div className="ref-summary-line" key={i}><textarea aria-label={(key==='summary'?'핵심 요약':'결정사항')+' '+(i+1)} rows={2} value={x.text} onChange={e=>patch(key,i,'text',e.target.value)}/><button className="text-link" onClick={()=>show(key,i)}>근거</button><IconButton icon={X} label={'항목 '+(i+1)+' 삭제'} onClick={()=>onRemove(key,i)}/></div>)}</section>)}</div></details>
    <div className="ref-subheading"><h3>요구사항·변경 <span>{bundle.changes?bundle.changes.length+'건':'미분석'}</span></h3></div>
    <div className="ref-table-scroll"><table className="ref-table extraction-table"><thead><tr><th>주제</th><th>이전 → 이번 회의</th><th>원문 상태</th></tr></thead><tbody>{bundle.changes?.map((c,i)=><tr key={i} className={active('changes',i)} onClick={()=>show('changes',i)}><td><button className="ref-row-title" onClick={()=>show('changes',i)}>{c.title}</button><small>{c.category}</small></td><td>{c.before&&<del>{c.before}</del>}<input aria-label={c.title+' 이번 회의 내용'} value={c.after} onChange={e=>patch('changes',i,'after',e.target.value)}/></td><td><select aria-label={c.title+' 원문 상태'} value={c.business_state} onChange={e=>patch('changes',i,'business_state',e.target.value)}>{['요청','확정','보류','철회'].map(s=><option key={s}>{s}</option>)}</select></td></tr>)}{!bundle.changes?.length&&<tr><td colSpan={3} className="ref-empty-cell">{bundle.changes?'추출된 요구·변경사항이 없습니다.':'AI 정리 후 요구·변경사항이 표시됩니다.'}</td></tr>}</tbody></table></div>
    <div className="ref-subheading"><h3>할 일·확인사항 <span>{bundle.candidates.length}건</span></h3><button className="text-link" onClick={()=>onAdd('candidates')}><Plus size={13}/>추가</button></div>
    <div className="ref-table-scroll"><table className="ref-table extraction-table ref-task-table"><thead><tr><th>내용</th><th>담당</th><th>기한</th></tr></thead><tbody>{bundle.candidates.map((c,i)=>{const owner=c.kind==='확인사항'?'reviewer_id':'owner_id';return <tr key={c.id} className={active('candidates',i)} onClick={()=>show('candidates',i)}><td><textarea rows={2} aria-label={'할 일 '+(i+1)} value={c.title} onChange={e=>patch('candidates',i,'title',e.target.value)}/><div className="ref-task-sub"><small>{c.kind==='확인사항'?'추가 확인':'업무'}</small><button className="text-link" onClick={()=>setEditing(i)}>상세 수정</button><button className="text-link" onClick={()=>show('candidates',i)}>근거</button></div></td><td className={!c[owner]?'ref-missing':''}><PeoplePicker value={c[owner]} ids={project?.members||[]} projectId={project?.id} placeholder="담당 미정" onChange={id=>patch('candidates',i,owner,id)}/></td><td className={!c.due?'ref-missing':''}><input type="date" aria-label={'기한 '+(i+1)} value={c.due||''} onInput={e=>patch('candidates',i,'due',e.currentTarget.value||null)}/></td></tr>})}{!bundle.candidates.length&&<tr><td colSpan={3} className="ref-empty-cell">추출된 할 일이 없습니다.</td></tr>}</tbody></table></div>
    <footer className="ref-inline-note">항목을 누르면 왼쪽 원문과 오른쪽 근거가 함께 표시됩니다.</footer>
   </>}
  </section>
  <aside className="ref-panel ref-evidence"><header><h2>근거·미정사항</h2></header>
   <section className="ref-alert"><h3>{missing.length>0?<><TriangleAlert size={15}/>담당·기한 미정 {missing.length}건</>:'담당·기한 확인'}</h3>{missing.length?<><ul>{missing.map(({c,i,owner})=><li key={c.id}><button onClick={()=>show('candidates',i)}>{c.title||'새 업무'}</button><small>{[!owner&&'담당',!c.due&&'기한'].filter(Boolean).join('·')} 미정</small></li>)}</ul><p>정해지지 않은 값은 비워 두어도 됩니다.</p></>:<p>{bundle.candidates.length?'모든 할 일에 담당자와 기한이 있습니다.':'AI 정리 후 확인할 항목을 표시합니다.'}</p>}</section>
   <section className="ref-quotes"><h3>{item?.title||'선택한 항목의 근거'}</h3>{item?<>{evidence.length?evidence.map(id=><blockquote key={id}><small>{id}</small>{lines.find(l=>l.id===id)?.text||'현재 본문에서 해당 문장을 찾을 수 없습니다.'}</blockquote>):<p>연결된 근거가 없습니다. 원문에서 선택해 주세요.</p>}<div className="ref-tools"><button className="text-link" onClick={()=>{setOriginal(false);setEditEvidence(!editEvidence)}}>{editEvidence?'근거 선택 끝내기':'근거 선택·수정'}</button><button className="text-link" onClick={onClear}>선택 해제</button></div>{editEvidence&&<p>왼쪽 원문에서 해당 문장을 눌러 주세요.</p>}</>:<p>가운데 표의 항목을 누르면 근거 문장을 볼 수 있습니다.</p>}</section>
   <p className="ref-inline-note">회의록 등록과 프로젝트 기준 반영은 별개입니다. 확정 사양은 변경 이력에서 확인합니다.</p>
  </aside>
  {editing!==null&&bundle.candidates[editing]&&<Modal wide title="할 일 상세 수정" close={()=>setEditing(null)} footer={<Button primary onClick={()=>setEditing(null)}>수정 마치기</Button>}><CandidateEditor candidate={bundle.candidates[editing]} project={project} defaultOpen onChange={c=>onUpdate('candidates',editing,c)} onEvidence={()=>{show('candidates',editing);setEditing(null)}}/></Modal>}
 </div>;
}
