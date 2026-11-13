import React,{useState,useEffect,useRef,useContext,createContext} from 'react';
import{createRoot}from'react-dom/client';
import{createPortal}from'react-dom';
import{Home,ListTodo,Files,Inbox,Search,Plus,ArrowUpRight,ArrowRight,ArrowLeft,ChevronDown,ChevronLeft,ChevronRight,PanelLeftClose,PanelLeftOpen,Check,CheckCheck,X,Bell,Upload,FileText,CalendarDays,Clock,Users,LogOut,HelpCircle,SlidersHorizontal,LayoutList,Columns3,MoreHorizontal,Sparkles,Paperclip,History,Trash2,RotateCcw,CheckCircle2,AlertCircle,FolderOpen,Building2,Menu,ExternalLink,Save,Send,Pencil,Loader2,Download,CornerDownRight}from'lucide-react';
import logo from './logo';
import{SortHeader,sortByColumn,dateValue}from'./table_sort';
import{ChangeHistory}from'./change_history';
import{CooperationInbox,ProjectMembers}from'./controls';
queueMicrotask(()=>createRoot(document.getElementById('root')).render(<App/>));
import{TaskDialog,MeetingLibrary,MeetingPage}from'./details';
import{HomePage}from'./home';
import{DashboardPage}from'./dashboard_v2';
import{Sidebar as SidebarV3}from'./sidebar_v3';
import{Reports}from'./reports';
import{Composer,CandidateEditor}from'./registration';
import{Projects,NewProject,NewTask,FieldReport,Notifications,SearchDialog,Trash,Drafts}from'./extras';
export{useApp,api,Status,Empty,Button,IconButton,Avatar,Person,PeoplePicker,Modal,PageHead,TaskRows,RecentMeetings,label,day,dateText,norm,TaskAttentionDot,hasTaskAttention};
const C=createContext(null),useApp=()=>useContext(C);
const statuses=['미착수','진행중','검토대기','보완요청','확인필요','완료'];
const label=s=>({'진행중':'진행 중','검토대기':'검토 대기','보완요청':'보완 요청','확인필요':'추가 확인','작성 중':'작성 중','확정':'검토 완료'}[s]||s);
const day=s=>s?s.slice(5,10).replace('-','.'):'미정';
const dateText=s=>s?String(s).slice(0,16).replace('T',' '):'';
const norm=s=>(s||'').toLocaleLowerCase();
async function api(path,method='GET',body){const form=body instanceof FormData;const res=await fetch('/api'+path,{method,headers:{'X-B2-Request':'workspace',...(!form&&body?{'Content-Type':'application/json'}:{})},body:body?(form?body:JSON.stringify(body)):undefined});const data=await res.json();if(!res.ok){let e=new Error(typeof data.detail==='string'?data.detail:data.detail?.message||'요청을 처리하지 못했습니다. 입력 내용을 확인해 주세요.');e.status=res.status;throw e}return data}
const Status=({value})=><span className={'status s-'+(statuses.indexOf(value)>=0?statuses.indexOf(value):value==='확정'?5:value==='검토 대기'?2:value==='보완 요청'?3:0)}><i/>{label(value)}</span>;
const Empty=({title='표시할 내용이 없습니다',text='프로젝트나 검색 조건을 바꿔 보세요.',action})=><div className="empty"><FolderOpen size={34}/><h3>{title}</h3><p>{text}</p>{action}</div>;
const Button=({children,primary,small,danger,icon:Icon,...props})=><button className={'btn '+(primary?'primary ':'')+(small?'small ':'')+(danger?'danger ':'')} {...props}>{Icon&&<Icon size={16}/>} {children}</button>;
const IconButton=({label:lbl,icon:Icon,...p})=><button className="icon-btn" title={lbl} aria-label={lbl} {...p}><Icon size={19}/></button>;
function Avatar({id,large}){const{person}=useApp();const p=person(id);return <span className={'avatar '+(large?'large ':'')+'a'+((id||'').charCodeAt(0)%4)}>{p?.name?.slice(-2)||'—'}</span>}
function Person({id,plain=false}){const{person}=useApp();return <span className="person">{!plain&&<Avatar id={id}/>}<span>{person(id)?.name||'미지정'}</span></span>}
function Modal({title,children,close,wide,footer,variant=''}){const titleId=React.useId();const ref=useRef();const ctx=useApp();useEffect(()=>{const node=ref.current;node.showModal();ctx?.setModalLayers(layers=>[...layers,node]);return()=>{node.close();ctx?.setModalLayers(layers=>layers.filter(layer=>layer!==node))}},[]);return <dialog ref={ref} aria-labelledby={titleId} className={'modal '+(wide?'wide ':'')+(variant?'modal-'+variant:'')} onCancel={e=>{e.preventDefault();close()}} onClick={e=>{if(e.target===e.currentTarget){e.preventDefault();e.stopPropagation();close()}}}><div className="modal-inner"><header><h2 id={titleId}>{title}</h2><IconButton icon={X} label="닫기" onClick={close}/></header><div className="modal-body">{children}</div>{footer&&<footer>{footer}</footer>}</div></dialog>}
function PeoplePicker({value,onChange,ids,placeholder='사람 선택',exclude,required=false,broaden=false}){const{D,person}=useApp(),[open,setOpen]=useState(false),[q,setQ]=useState(''),[all,setAll]=useState(false);const list=D.people.filter(p=>(!ids||all&&broaden||ids.includes(p.id))&&p.id!==exclude&&norm(p.name+' '+p.department+' '+p.position).includes(norm(q)));return <div className="people-picker"><button className="person-select" onClick={()=>setOpen(true)} type="button" aria-expanded={open}>{value?<Person plain id={value}/>:<span className="muted">{placeholder}</span>}<ChevronDown size={15}/></button>{open&&<Modal variant="people" title={placeholder} close={()=>setOpen(false)}><label className="search"><Search size={16}/><input autoFocus value={q} onChange={e=>setQ(e.target.value)} placeholder="이름·부서·직책 검색" aria-label="사람 검색"/></label>{broaden&&ids&&<div className="tabs"><button className={!all?'active':''} onClick={()=>setAll(false)}>프로젝트 구성원</button><button className={all?'active':''} onClick={()=>setAll(true)}>전체 구성원 검색</button></div>}<div className="people-search-results">{!required&&<button type="button" onClick={()=>{onChange(null);setOpen(false)}}>지정하지 않음</button>}{list.map(p=><button type="button" key={p.id} onClick={()=>{onChange(p.id);setOpen(false);setQ('')}}><span><b>{p.name}</b><small>{p.department} · {p.position}</small></span>{p.id===value&&<Check size={16}/>}</button>)}{!list.length&&<p className="notice">선택 가능한 사람 중 검색 결과가 없습니다.</p>}</div>{!broaden&&ids&&<p className="field-note">이 업무 또는 프로젝트에서 선택 권한이 있는 구성원입니다.</p>}</Modal>}</div>}
const sidebarSections = [
  ['업무 공간', [[Home, 'home', '홈'], [ListTodo, 'work', '업무']]],
  ['기록과 문서', [[Files, 'minutes', '회의록'], [History, 'changes', '변경 이력'], [FileText, 'reports', '보고서 작성']]],
];

function Sidebar({collapsed, toggle, logout}) {
  const {page, nav, setDialog} = useApp();
  const ToggleIcon = collapsed ? PanelLeftOpen : PanelLeftClose;
  const toggleLabel = collapsed ? '사이드바 펼치기' : '사이드바 접기';

  return <aside className="rail" aria-label="PNT 사이드바">
    <div className="rail-brand">
      <img src={logo} alt="PNT"/>
      <button type="button" className="rail-toggle" aria-label={toggleLabel} title={toggleLabel}
        aria-expanded={!collapsed} aria-controls="primary-navigation" onClick={toggle}>
        <ToggleIcon size={18}/>
      </button>
    </div>
    <button type="button" className="rail-action rail-search" aria-label="회의록·업무 검색" title="회의록·업무 검색"
      onClick={() => setDialog({type: 'search'})}>
      <Search size={18}/><span>회의록·업무 검색</span>
    </button>
    <nav id="primary-navigation" aria-label="주 메뉴">
      {sidebarSections.map(([group, items]) => <div className="nav-section" key={group}>
        <span className="nav-section-label">{group}</span>
        {items.map(([Icon, key, title]) => {
          const active = page === key || (key === 'minutes' && page === 'compose');
          return <button type="button" key={key} className={active ? 'active' : ''}
            aria-label={title} aria-current={active ? 'page' : undefined} title={title} onClick={() => nav(key)}>
            <Icon size={19}/><span>{title}</span>
          </button>;
        })}
      </div>)}
    </nav>
    <div className="rail-bottom">
      <button type="button" className="rail-action" aria-label="사용 도움말" title="사용 도움말"
        onClick={() => setDialog({type: 'help'})}>
        <HelpCircle size={18}/><span>사용 도움말</span>
      </button>
      <button type="button" className="rail-action" aria-label="로그아웃" title="로그아웃" onClick={logout}>
        <LogOut size={18}/><span>로그아웃</span>
      </button>
    </div>
  </aside>;
}

function App(){const[D,setD]=useState(null),[accounts,setAccounts]=useState([]),[booting,setBooting]=useState(true),[page,setPage]=useState('home'),[workMeeting,setWorkMeeting]=useState(''),[changeStartTab,setChangeStartTab]=useState('history'),[changeFocus,setChangeFocus]=useState(''),[pid,setPid]=useState(''),[filter,setFilter]=useState('mine'),[meeting,setMeeting]=useState(null),[dialog,setDialog]=useState(null),[confirm,setConfirm]=useState(null),[toast,setToast]=useState(null),[modalLayers,setModalLayers]=useState([]),[notices,setNotices]=useState({items:[],unread:0}),[globalQ,setGlobalQ]=useState(''),[busy,setBusy]=useState(false),[collapsed,setCollapsed]=useState(false),[formDirty,setFormDirty]=useState(false);
const reload=async()=>{const d=await api('/bootstrap');setD(d);setNotices(await api('/notifications'));return d};
useEffect(()=>{reload().catch(async e=>{if(e.status===401)setAccounts(await api('/demo-accounts'));else setToast({error:true,text:e.message})}).finally(()=>setBooting(false))},[]);
useEffect(()=>{if(!D?.user.id)return;let live=true,loading=false;const timer=setInterval(async()=>{if(loading)return;loading=true;try{const[d,n]=await Promise.all([api('/bootstrap'),api('/notifications')]);if(live){setD(d);setNotices(n)}}catch{}finally{loading=false}},8000);return()=>{live=false;clearInterval(timer)}},[D?.user.id]);
useEffect(()=>{if(!toast)return;const t=setTimeout(()=>setToast(null),toast.error?10000:4500);return()=>clearTimeout(t)},[toast]);
const run=async(fn,msg)=>{setBusy(true);try{const r=await fn();if(msg)setToast({text:msg});return r}catch(e){setToast({error:true,text:e.message});return null}finally{setBusy(false)}};
const person=id=>D?.people.find(p=>p.id===id),project=id=>D?.projects.find(p=>p.id===id),pm=id=>project(id)?.pm===D?.user.id;
const reviewTask=t=>t.kind==='업무'&&t.status==='검토대기'&&t.owner_id!==D?.user.id&&(t.reviewer_id===D?.user.id||pm(t.project_id));
const mine=t=>t.owner_id===D?.user.id||(t.kind==='확인사항'&&t.reviewer_id===D?.user.id);
const overdue=t=>t.status!=='완료'&&t.due&&t.due<D.today;
const tasks=D?.tasks.filter(t=>!pid||t.project_id===pid)||[],meetings=D?.meetings.filter(m=>!pid||m.project_id===pid)||[];
const nav=(p,f,targetProject)=>{const destination=p==='review'?'work':p,nextFilter=p==='review'?'review':f||(destination==='work'?'mine':null);const go=()=>{if(targetProject!==undefined)setPid(targetProject);setPage(destination);setMeeting(null);setWorkMeeting('');if(p==='changes'){setChangeStartTab(f==='pending'?'pending':'history');setChangeFocus('')}else if(nextFilter)setFilter(nextFilter);setFormDirty(false);window.scrollTo({top:0})};if(formDirty)setConfirm({title:'저장하지 않은 변경 내용',text:'임시 저장하지 않은 변경 내용이 있습니다. 저장하지 않고 이동할까요?',button:'이동',action:go});else go()};
const guardLeave=action=>{if(formDirty)setConfirm({title:'저장하지 않은 변경 내용',text:'수정한 내용을 저장하지 않고 이동할까요?',button:'이동',action:()=>{setFormDirty(false);return action()}});else return action()};
const selectProject=id=>guardLeave(()=>{setPid(id);setWorkMeeting('');setMeeting(null)});
const openMeeting=id=>guardLeave(()=>run(async()=>{const m=await api('/meetings/'+id);setMeeting(m);setPage('minutes');setDialog(null);window.scrollTo({top:0})}));
const openTask=(id,initialTab='action')=>{const task=D?.tasks.find(t=>t.id===id);setDialog({type:'task',id,initialTab,seenTokens:{...(task?.unseen||{})}})};
const showMeetingWork=id=>guardLeave(()=>{const m=D?.meetings.find(x=>x.id===id);if(m)setPid(m.project_id);setWorkMeeting(id);setFilter('proposals');setPage('work');setMeeting(null);setDialog(null);setFormDirty(false);window.scrollTo({top:0})});
const openChangeTopic=(key,id)=>guardLeave(()=>{setPid(id);setChangeFocus(key);setPage('changes');setMeeting(null);setDialog(null);window.scrollTo({top:0})});
const logout = () => guardLeave(() => run(async()=>{await api('/logout','POST');setD(null);setDialog(null);setPage('home');setFilter('mine');setPid('');setAccounts(await api('/demo-accounts'))}));
const ctx={D,setD,changeFocus,openChangeTopic,formDirty,workMeeting,setWorkMeeting,showMeetingWork,person,project,pm,reviewTask,mine,overdue,openTask,tasks,meetings,pid,setPid:selectProject,page,nav,changeStartTab,filter,setFilter,meeting,setMeeting,dialog,setDialog,confirm,setConfirm,toast,setToast,modalLayers,setModalLayers,notices,setNotices,reload,run,busy,openMeeting,setFormDirty,guardLeave};
if(booting)return <div className="boot"><Loader2 className="spin"/> 업무 공간을 불러오고 있습니다.</div>;
return <C.Provider value={ctx}>{!D?<Login accounts={accounts} login={id=>run(async()=>{await api('/demo-login','POST',{username:id});await reload()})}/>:<div className={'workspace design-v20 '+(collapsed?'compact-nav':'')}><SidebarV3 sections={sidebarSections} collapsed={collapsed} toggle={() => setCollapsed(value => !value)} logout={logout}/><div className="main-shell"><header className="topbar"><div className="context"><button className="project-switch" aria-haspopup="dialog" title="프로젝트 선택" onClick={()=>setDialog({type:'projects'})}><FolderOpen size={19}/><span>{pid?project(pid)?.name:'전체 프로젝트'}</span><ChevronDown size={16}/></button></div><div className="top-tools"><button className="notification-btn icon-btn" aria-label={'알림 '+notices.unread+'건'} onClick={()=>setDialog({type:'notifications'})}><Bell size={20}/>{notices.unread>0&&<i/>}</button><button aria-label={D.user.name+' 계정 메뉴'} className="profile-btn" onClick={()=>setDialog({type:'account'})}><Avatar id={D.user.id}/><span>{D.user.name}<small>{D.user.position}</small></span><ChevronDown size={14}/></button></div></header><main className={'content page-'+page}>{page==='home'?<DashboardPage/>:page==='work'?<HomePage/>:page==='minutes'?(meeting?<MeetingPage key={meeting.id}/>:<MeetingLibrary/>):page==='compose'?<Composer/>:page==='changes'?<ChangeHistory/>:page==='reports'?<Reports/>:null}</main></div></div>}
{D&&dialog?.type==='members'&&<ProjectMembers id={dialog.id}/>}
{D&&dialog?.type==='cooperation'&&<CooperationInbox initialId={dialog.id}/>}
{D&&dialog?.type==='task'&&<TaskDialog key={dialog.id} id={dialog.id} seenTokens={dialog.seenTokens} initialTab={dialog.initialTab}/>}
{D&&dialog?.type==='projects'&&<Projects/>}{D&&dialog?.type==='new-project'&&<NewProject/>}
{D&&dialog?.type==='new-task'&&<NewTask/>}{D&&dialog?.type==='field'&&<FieldReport/>}
{D&&dialog?.type==='notifications'&&<Notifications/>}{D&&dialog?.type==='search'&&<SearchDialog/>}{D&&dialog?.type==='trash'&&<Trash/>}{D&&dialog?.type==='drafts'&&<Drafts/>}
{D&&dialog?.type==='account'&&<Modal title="내 계정" close={()=>setDialog(null)}><div className="account-info"><Avatar id={D.user.id} large/><div><h3>{D.user.name}</h3><p>{D.user.department} · {D.user.position}</p></div></div><p className="notice">가상 데이터로 사용하는 v2.0 디자인 프리뷰입니다. 기존 공동 테스트 데이터를 이어서 사용합니다.</p><Button icon={LogOut} onClick={logout}>로그아웃·사용자 바꾸기</Button></Modal>}
{D&&dialog?.type==='help'&&<Modal title="업무 공간 사용 안내" close={()=>setDialog(null)}><ol className="help-steps"><li><b>회의록을 등록하세요</b><p>Word 파일을 올리거나 글을 붙여 넣고, 프로젝트를 선택합니다.</p></li><li><b>원문과 AI 정리 내용을 대조하세요</b><p>요약·결정사항·업무 제안을 확인하고 수정합니다. 미정인 담당자나 기한은 추측하지 않습니다.</p></li><li><b>필요한 업무를 선택해 배정합니다</b><p>PM은 선택한 업무를 배정하고, 일반 팀원은 배정을 요청할 수 있습니다. 회의록만 등록하고 업무 탭에서 나중에 처리해도 됩니다.</p></li><li><b>담당자가 처리하고 검토를 요청합니다</b><p>검토가 필요한 업무는 지정 검토자가 확인합니다. 직접 완료 업무는 담당자가 결과를 기록하고 완료합니다.</p></li></ol><p className="notice">추출 결과와 데이터는 별도 검증이 필요합니다. 상단 검색의 AI 질문에서 등록된 회의 내용과 현재 업무를 조회할 수 있습니다. 요구·변경 기록은 변경 이력에서 자동으로 이어집니다. 합의로 추출된 내용은 원문 확인 후 현재 기준에 반영합니다. 확정 사양·납기는 이 기준으로 답합니다. 답변의 근거를 눌러 본문을 함께 확인하세요.</p></Modal>}
{confirm&&<Modal title={confirm.title||'내용을 확인해 주세요'} close={()=>!busy&&setConfirm(null)} footer={<><Button disabled={busy} onClick={()=>setConfirm(null)}>취소</Button><Button primary disabled={busy} onClick={()=>run(async()=>{await confirm.action();setConfirm(null)})}>{busy?'처리 중…':confirm.button||'확인'}</Button></>}><p className="confirm-copy">{confirm.text}</p></Modal>}
{toast&&createPortal(<div className={'toast '+(toast.error?'error':'')} role={toast.error?'alert':'status'}>{toast.error?<AlertCircle size={18}/>:<CheckCircle2 size={18}/>}<span>{toast.text}</span><IconButton icon={X} label="메시지 닫기" onClick={()=>setToast(null)}/></div>,modalLayers[modalLayers.length-1]||document.body)}
</C.Provider>}
function Login({accounts,login}){const[q,setQ]=useState(''),[selected,setSelected]=useState('');const{busy}=useApp();return <div className="login-page"><section className="login-intro"><img src={logo} alt="PNT"/><span className="eyebrow">PROJECT WORKSPACE / 2.0</span><h1>회의에서 나온 일,<br/>완료까지 이어지도록.</h1><p>흩어진 회의록과 업무를 연결하고<br/>담당자·기한·처리 결과를 한곳에서 확인하세요.</p><div className="login-journey"><span><Files/>회의록</span><ArrowRight/><span><ListTodo/>업무</span><ArrowRight/><span><CheckCircle2/>완료 확인</span></div><small>PNT 업무 서비스 · 별도 시험 버전</small></section><section className="login-form"><span className="eyebrow">WELCOME BACK</span><h2>업무 공간에 들어가기</h2><p>테스트할 사용자를 선택하세요. 비밀번호는 필요하지 않습니다.</p><label className="search"><Search size={17}/><input aria-label="사용자 검색" placeholder="이름 또는 부서 검색" value={q} onChange={e=>setQ(e.target.value)}/></label><div className="accounts">{accounts.filter(p=>norm(p.name+p.department).includes(norm(q))).map(p=><button className={selected===p.id?'selected':''} key={p.id} onClick={()=>setSelected(p.id)}><span className="avatar">{p.name.slice(-2)}</span><span><b>{p.name}</b><small>{p.department} · {p.position}</small></span>{selected===p.id&&<Check size={18}/>}</button>)}</div><Button primary disabled={!selected||busy} onClick={()=>login(selected)}>{busy?'접속 중…':(accounts.find(p=>p.id===selected)?.name||'사용자')+'님으로 시작'}<ArrowRight size={17}/></Button></section></div>}
function PageHead({eyebrow,title,text,children}){return <div className="page-head"><div>{eyebrow&&<div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1>{text&&<p>{text}</p>}</div><div className="head-actions">{children}</div></div>}
function hasTaskAttention(t,bucket){return bucket?!!t.unseen?.[bucket]:!!(t.unseen?.mine||t.unseen?.review)}
function TaskAttentionDot({tab=false}){return <span className={'task-unseen-dot'+(tab?' tab-unseen-dot':'')} role="img" aria-label="아직 확인하지 않은 내용" title="목록에서 아직 확인하지 않은 내용이 있습니다."/>}
function TaskRows({items,compact=false,sort,onSort}){const{project,overdue,openTask}=useApp();return !items.length?<Empty/>:<div className={'task-table '+(compact?'condensed':'')}><div className="table-head">{sort&&onSort?[["title","업무"],["owner","담당자"],["due","완료 목표"],["status","상태"]].map(([key,title])=><SortHeader key={key} label={title} column={key} sort={sort} onSort={onSort} hint={key==='status'?'미착수 → 진행 중 → 검토 대기 → 보완 요청 → 추가 확인 → 완료':undefined}/>):<><span>업무</span><span>담당자</span><span>완료 목표</span><span>상태</span></>}<span/></div>{items.map(t=><button className="task-row" key={t.id} onClick={()=>openTask(t.id)}><span className="task-main"><span><b className="task-title-with-dot">{hasTaskAttention(t)&&<TaskAttentionDot/>}<span>{t.title}</span></b><small>{project(t.project_id)?.name}{t.kind==='확인사항'?' · 추가 확인':''}</small></span></span><Person plain id={t.kind==='확인사항'?t.reviewer_id:t.owner_id}/><span className={overdue(t)?'overdue':''}>{day(t.due)}{overdue(t)&&<small>기한 지남</small>}</span><Status value={t.status}/><ChevronRight size={16}/></button>)}</div>}
function RecentMeetings({list}){const{project,openMeeting}=useApp();return <div className="recent-meetings">{list.map(m=><button key={m.id} onClick={()=>openMeeting(m.id)}><span className="file-icon"><FileText size={21}/></span><span><b>{m.title}</b><small>{project(m.project_id)?.name} · {m.date}</small></span><Status value={m.document_status}/><ChevronRight size={16}/></button>)}{!list.length&&<Empty title="등록된 회의록이 없습니다"/>}</div>}
