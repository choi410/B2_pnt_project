import React,{useState,useEffect}from'react';
import{Plus,Search,ChevronLeft,ChevronRight}from'lucide-react';
import{useApp,Button,IconButton,PageHead,TaskRows,Empty,Status,Person,TaskAttentionDot,hasTaskAttention,day,dateText,norm}from'./app';
import{SortHeader,sortByColumn,dateValue}from'./table_sort';
import{WorkProposals}from'./work_proposals';
import{assignmentWaitingCount}from'./assignment_queue';
import{calendarEntries,calendarWeeks,eventsOn}from'./calendar_layout';
const statuses=['미착수','진행중','검토대기','보완요청','확인필요','완료'];

export function HomePage(){
 const{D,pid,tasks,meetings,reviewTask,mine,pm,overdue,filter,setFilter,setDialog,person,project,openTask,openMeeting,setWorkMeeting,guardLeave}=useApp();
 const[q,setQ]=useState(''),[limit,setLimit]=useState(30),[history,setHistory]=useState(false),[sort,setSort]=useState({key:'due',direction:'asc'}),[reviewSort,setReviewSort]=useState({key:'requested',direction:'asc'});
 useEffect(()=>{setLimit(30)},[q,filter]);
 const relevant=t=>pm(t.project_id)||mine(t)||t.created_by===D.user.id;
 const groups={mine:tasks.filter(t=>mine(t)&&t.status!=='완료'),review:tasks.filter(reviewTask),late:tasks.filter(t=>overdue(t)),missing:tasks.filter(t=>t.status!=='완료'&&(t.kind==='확인사항'||!(t.kind==='확인사항'?t.reviewer_id:t.owner_id)||!t.due)),all:tasks};
 const waitingDocs=meetings.filter(m=>pm(m.project_id)&&m.document_status==='검토 대기');
 const canReview=D.projects.some(p=>pm(p.id))||D.tasks.some(t=>t.reviewer_id===D.user.id&&t.owner_id!==D.user.id);
 const select=k=>guardLeave(()=>{setFilter(k);setWorkMeeting('');setHistory(false);setLimit(30)});
 const searchText=x=>norm(x.title+' '+(x.description||'')+' '+(project(x.project_id)?.name||'')).includes(norm(q));
 const shown=sortByColumn((groups[filter]||tasks).filter(searchText),sort,{title:t=>t.title,owner:t=>person(t.kind==='확인사항'?t.reviewer_id:t.owner_id)?.name,due:t=>dateValue(t.due),status:t=>statuses.indexOf(t.status)});
 const reviewTasks=history?tasks.filter(t=>(t.events||[]).some(e=>e.actor===D.user.id&&e.action==='완료 확인')):groups.review;
 const reviewDocs=history?meetings.filter(m=>pm(m.project_id)&&m.document_status==='확정'):waitingDocs;
 const reviews=sortByColumn([...reviewTasks.map(t=>({...t,type:'task',requester:t.owner_id,requested:t.submitted_at})),...reviewDocs.map(m=>({...m,type:'meeting',requester:m.author,requested:[...(m.document_events||[])].reverse().find(e=>e.action==='회의록 검토 요청')?.at||m.created_at}))].filter(searchText),reviewSort,{title:x=>x.title,requester:x=>person(x.requester)?.name,requested:x=>dateValue(x.requested),status:x=>x.type==='task'?x.status:x.document_status});
 return <><PageHead title="업무" text="내 업무를 처리하고, 요청받은 결과를 확인하세요."><Button icon={Plus} onClick={()=>setDialog({type:'field'})}>현장 이슈</Button>{D.projects.some(p=>pm(p.id))&&<Button primary icon={Plus} onClick={()=>setDialog({type:'new-task'})}>업무 등록</Button>}</PageHead>
 <div className="work-layout"><section className="main-list">
 <div className="tabs home-tabs">{[['mine','내 업무',groups.mine.length],['review','검토 요청',groups.review.length+waitingDocs.length],['late','기한 지남',groups.late.length],['missing','추가 확인',groups.missing.length],['all','전체',tasks.length],['proposals','업무 제안',assignmentWaitingCount(meetings,tasks)]].filter(([k])=>k!=='review'||canReview).map(([k,l,n])=><button key={k} className={(filter===k?'active ':'')+'task-attention-tab'} onClick={()=>select(k)}>{l}<em>{n}</em>{((k==='mine'&&groups.mine.some(t=>hasTaskAttention(t,'mine')))||(k==='review'&&groups.review.some(t=>hasTaskAttention(t,'review'))))&&<TaskAttentionDot tab/>}</button>)}</div>
 {filter!=='proposals'&&<div className="home-list-tools"><span className="muted">{filter==='review'?reviews.length+'건의 검토':shown.length+'건의 업무'}</span><div className="work-tools"><label className="search"><Search size={16}/><input aria-label="업무·검토 검색" placeholder="제목·프로젝트 검색" value={q} onChange={e=>setQ(e.target.value)}/></label></div></div>}

 {filter==='proposals'?<WorkProposals/>:filter==='review'?<><div className="review-list-meta"><span>업무 결과와 회의록 내용은 각각 검토합니다.</span><label className="check-line"><input type="checkbox" checked={history} onChange={e=>{setHistory(e.target.checked);setLimit(30)}}/>확인한 내역 보기</label></div>{reviews.length?<div className="task-table home-reviews"><div className="table-head">{[['title','검토할 내용'],['requester','요청자'],['requested','요청일'],['status','상태']].map(([k,l])=><SortHeader key={k} label={l} column={k} sort={reviewSort} onSort={setReviewSort}/>)}<span/></div>{reviews.slice(0,limit).map(x=><button className="task-row" key={x.type+x.id} onClick={()=>x.type==='task'?openTask(x.id):openMeeting(x.id)}><span className="task-main"><span><span className={'review-kind '+x.type}>{x.type==='task'?'업무':'회의록'}</span><b className="task-title-with-dot">{x.type==='task'&&hasTaskAttention(x)&&<TaskAttentionDot/>}<span>{x.title}</span></b><small>{project(x.project_id)?.name}</small></span></span><Person plain id={x.requester}/><span title={dateText(x.requested)}>{day(x.requested)}</span><Status value={x.type==='task'?x.status:x.document_status}/><ChevronRight size={16}/></button>)}</div>:<Empty title={history?'확인한 내역이 없습니다':'검토를 기다리는 항목이 없습니다'} text="업무 완료 요청과 회의록 승인 요청이 여기에 표시됩니다."/>}</>:shown.length?<TaskRows items={shown.slice(0,limit)} sort={sort} onSort={setSort}/>:<Empty title={q?'검색 결과가 없습니다':({mine:'내게 배정된 미완료 업무가 없습니다',late:'기한이 지난 업무가 없습니다',missing:'추가 확인할 업무가 없습니다',all:'등록된 업무가 없습니다'}[filter]||'표시할 업무가 없습니다')} text={q?'다른 제목이나 프로젝트 이름으로 검색해 보세요.':filter==='mine'?'배정받은 업무는 여기에 표시됩니다. 전체 탭에서 프로젝트 업무를 볼 수 있습니다.':'새 업무와 처리 상태가 여기에 표시됩니다.'}/>}
 {filter!=='proposals'&&(filter==='review'?reviews.length:shown.length)>limit&&<div className="load-more"><Button onClick={()=>setLimit(limit+30)}>30건 더 보기</Button></div>}</section></div></>;
}

export {HomeCalendar as PeriodCalendar}from'./home_calendar';
