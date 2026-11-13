import React,{useEffect,useRef,useState}from'react';
import{useApp,api,Button,Modal}from'./app';
import{SourceView}from'./evidence';

export function ChangeEditor({item,topics,close,saved}){
 const{D,pid,pm,run,busy}=useApp();
 const[projectId,setProjectId]=useState(item.project_id||pid||''),[m,setM]=useState(null),[persisted,setPersisted]=useState(item),[loading,setLoading]=useState(false);
 const[data,setData]=useState({meeting_id:item.meeting_id||'',source_revision:item.source_revision||1,topic_id:item.topic_id||null,title:item.title||'',category:item.category||'요구사항',before:item.before||'',after:item.after||'',business_state:item.business_state||'요청',evidence:item.evidence||[],effective_date:item.effective_date||D.today});
 const[editEvidence,setEditEvidence]=useState(false),[sourceNotice,setSourceNotice]=useState('');
 const request=useRef(0);
 useEffect(()=>()=>{request.current++},[]);
 const patch=(key,value)=>setData(d=>({...d,[key]:value,...(['title','category'].includes(key)?{topic_id:null}:{})}));
 const projects=D.projects.filter(p=>pm(p.id)&&!p.deleted_at);
 const allowed=D.meetings.filter(x=>pm(x.project_id)&&x.project_id===projectId&&!x.deleted_at).sort((a,b)=>(b.date||'').localeCompare(a.date||''));
 const load=async mid=>{
  const seq=++request.current;setM(null);setLoading(!!mid);setSourceNotice('');
  setData(d=>({...d,meeting_id:mid,evidence:[]}));
  if(!mid)return;
  try{
   const next=await api('/meetings/'+mid);if(seq!==request.current)return;
   let evidence=[];
   if(mid===item.meeting_id&&next.revision===item.source_revision)evidence=item.evidence||[];
   else if(mid===item.meeting_id&&item.quotes?.length){
    const matches=item.quotes.map(q=>next.lines.filter(l=>l.text===q));
    if(matches.every(xs=>xs.length===1))evidence=matches.map(xs=>xs[0].id);
   }
   setSourceNotice(mid===item.meeting_id&&next.revision!==item.source_revision?(evidence.length?'본문이 수정되어 동일한 근거 문장을 다시 연결했습니다. 문맥을 확인해 주세요.':'본문이 수정되었습니다. 최신 원문에서 근거 문장을 선택해 주세요.'):'');
   setM(next);setEditEvidence(!evidence.length);
   setData(d=>({...d,meeting_id:mid,source_revision:next.revision,evidence,effective_date:mid===item.meeting_id?d.effective_date:next.date||D.today}));
  }finally{if(seq===request.current)setLoading(false)}
 };
 useEffect(()=>{if(item.meeting_id)run(()=>load(item.meeting_id))},[]);
 const changeProject=id=>{
  request.current++;setProjectId(id);setM(null);setLoading(false);setSourceNotice('');
  setData(d=>({...d,meeting_id:'',topic_id:null,title:'',category:'요구사항',evidence:[],before:'',after:'',effective_date:D.today}));
 };
 const selectTopic=id=>{const t=topics.find(t=>t.id===id&&t.project_id===projectId);setData(d=>({...d,topic_id:t?.id||null,title:t?.title||d.title,category:t?.category||d.category}))};
 const save=async()=>{
  const result=await api('/changes'+(persisted.id?'/'+persisted.id:''),persisted.id?'PATCH':'POST',{...data,...(persisted.id?{version:persisted.version}:{})});
  setPersisted(result);await saved(result.id);
 };
 const reason=!projectId?'프로젝트를 선택하세요.':loading?'회의록을 불러오고 있습니다.':!m?'근거 회의록을 선택하세요.':data.title.trim().length<2?'변경 대상을 입력하세요.':!data.after.trim()?'추가할 내용을 입력하세요.':!data.evidence.length?'원문에서 근거 문장을 선택하세요.':!(m.registered_revision===m.revision||m.approved_revision===m.revision)?'현재 본문을 먼저 등록해 주세요.':'';
 return <Modal wide title={item.id?'기록 수정':'누락된 내용 추가'} close={close} footer={<><span className="change-disabled-reason" role="status">{reason}</span><Button primary disabled={!!reason||busy} onClick={()=>run(save)}>{item.id?'수정 저장':'기록 추가'}</Button></>}>
 <p className="field-note">회의록에 기록된 내용을 근거와 함께 남깁니다.</p>
 <div className="history-editor-context">
  <label className="field">프로젝트<select aria-label="기록 프로젝트" disabled={!!item.id} value={projectId} onChange={e=>changeProject(e.target.value)}><option value="">프로젝트 선택</option>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
  <label className="field">근거 회의록<select aria-label="변경 근거 회의록" disabled={!projectId||loading} value={data.meeting_id} onChange={e=>run(()=>load(e.target.value))}><option value="">회의록 선택</option>{allowed.map(x=><option key={x.id} value={x.id}>{x.date} · {x.title}</option>)}</select></label>
 </div>
 {sourceNotice&&<p className="warning">{sourceNotice}</p>}
 <div className="change-editor-grid history-editor-grid"><section>
  <label className="field">변경 대상<input aria-label="변경 대상" value={data.title} onChange={e=>patch('title',e.target.value)} placeholder="예: 점검 커버 개폐 방식"/></label>
  <label className="field">회의에서의 상태<select aria-label="회의에서의 상태" value={data.business_state} onChange={e=>patch('business_state',e.target.value)}>{[['요청','요청'],['확정','결정'],['보류','보류'],['철회','철회']].map(([v,label])=><option key={v} value={v}>{label}</option>)}</select></label>
  <label className="field">내용<textarea aria-label="기록 내용" value={data.after} onChange={e=>patch('after',e.target.value)} placeholder="회의에서 요청하거나 결정한 내용을 입력하세요."/></label>
  <details className="history-editor-options"><summary>추가 정보</summary><div className="edit-grid">
   <label>구분<select value={data.category} onChange={e=>patch('category',e.target.value)}>{['요구사항','사양','납기'].map(x=><option key={x}>{x}</option>)}</select></label>
   <label>기록 날짜<input type="date" value={data.effective_date} onChange={e=>patch('effective_date',e.target.value)}/></label>
   <label className="span2">이전 내용 · 선택<textarea value={data.before} onChange={e=>patch('before',e.target.value)} placeholder="원문에 이전 값이 있을 때만 입력하세요."/></label>
   {topics.some(t=>t.project_id===projectId)&&<label className="span2">기존 대상 연결 · 선택<select value={data.topic_id||''} onChange={e=>selectTopic(e.target.value)}><option value="">입력한 대상 이름 사용</option>{topics.filter(t=>t.project_id===projectId).map(t=><option key={t.id} value={t.id}>{t.title}</option>)}</select></label>}
  </div></details>
 </section><section className="history-editor-source">
  {m?<><div className="section-title"><h3>원문 근거 <small>{data.evidence.length}개 선택</small></h3><Button small onClick={()=>setEditEvidence(!editEvidence)}>{editEvidence?'원본 보기':'근거 선택'}</Button></div>{editEvidence&&<p className="field-note">관련 문장을 누르면 선택하거나 해제할 수 있습니다.</p>}<SourceView record={m} selected={data.evidence} linesMode={editEvidence} onLine={editEvidence?id=>patch('evidence',data.evidence.includes(id)?data.evidence.filter(x=>x!==id):[...data.evidence,id]):undefined}/></>:<p className="history-source-placeholder">{loading?'회의록을 불러오고 있습니다.':'회의록을 선택하면 여기에서 근거 문장을 고를 수 있습니다.'}</p>}
 </section></div></Modal>;
}
