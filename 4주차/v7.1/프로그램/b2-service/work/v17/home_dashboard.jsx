import React,{useEffect,useState}from'react';
import{ChevronLeft,ChevronRight,FileText,ArrowRight}from'lucide-react';
import{useApp,api,Modal,Empty}from'./app';
import{registered}from'./project_story';
import{pendingChanges,orderAttention}from'./home_attention';
import{attentionCopy}from'./home_attention_copy.mjs';

export function HomeDashboard({groups=[],changesLoading,changesError,calendar}){
 const{D,pid,person,project,nav,openMeeting,openChangeTopic}=useApp();
 const[items,setItems]=useState(null),[error,setError]=useState(''),[selected,setSelected]=useState(null),[paging,setPaging]=useState({scope:pid,page:0});
 useEffect(()=>{let live=true,running=false;const refresh=async()=>{if(running)return;running=true;try{const data=await api('/home/attention');if(live){setItems(data.items);setError('')}}catch(e){if(live)setError(e.message)}finally{running=false}};refresh();const timer=setInterval(refresh,8000);return()=>{live=false;clearInterval(timer)}},[D.user.id]);
 useEffect(()=>{setPaging({scope:pid,page:0});setSelected(null)},[pid]);
 const all=orderAttention([...(items||[]),...pendingChanges(groups,D.meetings)]).map(i=>({...i,...attentionCopy(i,person(i.owner_id)?.name||'')}));
 const shown=all.filter(i=>!pid||i.project_id===pid),pageSize=5,pageCount=Math.ceil(shown.length/pageSize);
 const page=paging.scope===pid?Math.min(paging.page,Math.max(0,pageCount-1)):0,pageItems=shown.slice(page*pageSize,(page+1)*pageSize);
 const turnPage=delta=>setPaging({scope:pid,page:Math.max(0,Math.min(page+delta,pageCount-1))});
 const recent=D.meetings.filter(m=>registered(m)&&(!pid||m.project_id===pid)).sort((a,b)=>(b.date||'').localeCompare(a.date||'')||(b.created_at||'').localeCompare(a.created_at||'')).slice(0,3);
 const ready=items!==null&&!changesLoading;
 const owner=i=>person(i.owner_id)?.name||'담당자 미정';
 const contact=i=>person(project(i.project_id)?.pm)?.name||'미정';
 const openSource=i=>{setSelected(null);openMeeting(i.meeting_id,i.project_id,{key:i.id,quotes:i.quotes||[]})};
 return <div className="home-attention-dashboard">
  <header className="overview-heading"><div><h1>프로젝트 대시보드</h1></div></header>
  <div className="home-attention-grid">
   <section className="surface home-attention-panel" aria-label="확인할 사항">
    <header><div><h2>확인할 사항 <small>{ready?shown.length:'—'}</small></h2><p>{pid?project(pid)?.name:'전체 프로젝트'}</p></div>{pid&&<button className="text-link" onClick={()=>nav('project',undefined,pid)}>프로젝트 보기<ChevronRight size={15}/></button>}</header>
    <p className="home-attention-note">회의록의 후속 사항과 요청·보류 기록을 모았습니다. 처리 결과가 연결되지 않은 항목은 담당자 확인이 필요합니다.</p>
    {(error||changesError)&&<p className="warning" role="alert">{error||changesError}</p>}
    <div className="home-attention-body">{!ready?<p className="home-attention-empty" role="status">확인할 사항을 불러오는 중입니다.</p>:!shown.length?<Empty title="표시할 확인 사항이 없습니다" text="등록된 회의록과 요구·변경 기록을 기준으로 표시합니다."/>:<>
     <div className="home-attention-columns" aria-hidden="true"><span>확인할 항목 · 프로젝트</span><span>관련자</span><span>기한</span><span>확인 이유</span><span/></div>
     <div className="home-attention-rows" id="home-attention-rows">{pageItems.map(i=><button className="home-attention-row" key={i.id} onClick={()=>setSelected(i)} aria-label={i.title+' 확인 내용 보기'}>
      <span className="home-attention-title"><b>{i.title}</b><small>{project(i.project_id)?.name} · {i.meeting_date||i.origin}</small></span>
      <span className="home-attention-owner"><b>{owner(i)}</b>{!i.owner_id&&<small>문의 · PM {contact(i)}</small>}</span>
      <span className="home-attention-due">{i.due||'미정'}</span>
      <span className="home-attention-reasons">{i.reasons.map(r=><span key={r} className={r.includes('기한')?'late':r.includes('담당')?'unassigned':''}>{r}</span>)}</span><ChevronRight size={16}/>
     </button>)}</div>
    </>}</div>
    <footer className="home-attention-pagination"><span>{ready&&shown.length?`${shown.length}건 중 ${page*pageSize+1}–${Math.min((page+1)*pageSize,shown.length)}건`:ready?'0건':'불러오는 중'}</span><nav aria-label="확인할 사항 페이지"><button type="button" aria-label="이전 확인 사항" aria-controls="home-attention-rows" disabled={!ready||page===0} onClick={()=>turnPage(-1)}><ChevronLeft size={17}/></button><span aria-live="polite" aria-atomic="true">{ready&&pageCount?page+1:0} / {ready?pageCount:0}</span><button type="button" aria-label="다음 확인 사항" aria-controls="home-attention-rows" disabled={!ready||page+1>=pageCount} onClick={()=>turnPage(1)}><ChevronRight size={17}/></button></nav></footer>
   </section>
   <aside className="home-attention-side" aria-label="일정과 최근 기록">
   <section className="surface overview-calendar" aria-label="회의 일정">{calendar}</section>
   <section className="surface overview-recent" aria-label="최근 회의록"><header className="surface-heading"><h2>최근 회의록</h2><button className="text-link" onClick={()=>nav('minutes')}>전체 보기<ArrowRight size={14}/></button></header>{recent.map(m=><button className="overview-meeting-row" key={m.id} onClick={()=>openMeeting(m.id,m.project_id)}><span className="document-symbol"><FileText size={18}/></span><span><strong>{m.title}</strong><small>{project(m.project_id)?.name} · {m.date||'날짜 미정'}</small></span><ChevronRight size={15}/></button>)}{!recent.length&&<p className="overview-empty">등록된 회의록이 없습니다.</p>}</section>
   </aside>
  </div>
  {selected&&<Modal title={selected.title} close={()=>setSelected(null)} variant="home-attention" footer={<><button className="btn" onClick={()=>setSelected(null)}>닫기</button>{selected.topic_key&&<button className="btn" onClick={()=>{setSelected(null);openChangeTopic(selected.topic_key,selected.project_id)}}>변경 이력 보기</button>}{selected.meeting_id&&<button className="btn primary" onClick={()=>openSource(selected)}>근거 회의록 보기</button>}</>}>
   <p className="home-attention-detail-project">{project(selected.project_id)?.name} · {selected.origin}</p>
   <dl className="home-attention-meta"><div><dt>관련자</dt><dd>{owner(selected)}</dd></div><div><dt>기한</dt><dd>{selected.due||'미정'}</dd></div><div><dt>프로젝트 PM</dt><dd>{contact(selected)}</dd></div></dl>
   {selected.description!==selected.title&&<p className="home-attention-description">{selected.description}</p>}{selected.origin!=='회의록'&&selected.note&&<p className="notice">{selected.note}</p>}
   {selected.result&&<section><h3>처리 결과</h3><p>{selected.result}</p></section>}
   {!!selected.quotes?.length&&<details key={selected.id} className="home-attention-evidence"><summary>원문 근거 보기</summary>{selected.quotes.map((q,index)=><blockquote key={index}>{q}</blockquote>)}</details>}
   {selected.meeting_title&&<p className="field-note">{selected.meeting_date} · {selected.meeting_title}</p>}
  </Modal>}
 </div>;
}
