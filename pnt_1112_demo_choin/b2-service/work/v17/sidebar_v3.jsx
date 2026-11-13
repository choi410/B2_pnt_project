import React,{useState,useEffect,useRef}from'react';
import{PanelLeftClose,PanelLeftOpen,HelpCircle,LogOut,Search,Sun,SquareCheckBig,CheckCheck,CircleHelp,UserPlus,Inbox,Star,ChevronDown}from'lucide-react';
import{useApp}from'./app';
import logo from './logo';
import{assignmentWaitingCount}from'./assignment_queue';

/* 사이드바 v3: 프로필 · 나의 업무 · 즐겨찾기 · 메뉴
   즐겨찾기는 사용자별로 이 브라우저(localStorage)에 저장된다. */

const favKey=userId=>'pnt-favs:'+userId;
function readFavorites(userId){
 try{const value=JSON.parse(localStorage.getItem(favKey(userId))||'[]');return Array.isArray(value)?value:[]}catch{return[]}
}
function toggleFavorite(userId,projectId){
 const current=readFavorites(userId),next=current.includes(projectId)?current.filter(id=>id!==projectId):[...current,projectId];
 try{localStorage.setItem(favKey(userId),JSON.stringify(next))}catch{}
 window.dispatchEvent(new CustomEvent('pnt-favs'));
}
function useFavorites(userId){
 const[favorites,setFavorites]=useState(()=>readFavorites(userId));
 useEffect(()=>{
  const refresh=()=>setFavorites(readFavorites(userId));refresh();
  window.addEventListener('pnt-favs',refresh);window.addEventListener('storage',refresh);
  return()=>{window.removeEventListener('pnt-favs',refresh);window.removeEventListener('storage',refresh)};
 },[userId]);
 return favorites;
}
function greeting(){
 const hour=new Date().getHours();
 return hour<6?'늦은 시간까지 수고 많아요':hour<12?'좋은 아침이에요':hour<18?'좋은 오후예요':'좋은 저녁이에요';
}

/* 프로젝트 목록 행 안에 들어가는 ☆ 버튼 (행 자체가 button이라 span role=button으로 둔다) */
export function FavoriteStar({id,label}){
 const{D}=useApp(),favorites=useFavorites(D.user.id),on=favorites.includes(id),text=on?'즐겨찾기 해제':'즐겨찾기 추가';
 const toggle=event=>{event.stopPropagation();event.preventDefault();toggleFavorite(D.user.id,id)};
 return <span role="button" tabIndex={0} className={'pnt-star'+(on?' on':'')} title={text} aria-label={(label||id)+' '+text} aria-pressed={on}
  onClick={toggle} onKeyDown={event=>{if(event.key==='Enter'||event.key===' ')toggle(event)}}><Star size={18} fill={on?'currentColor':'none'}/></span>;
}

/* 사이드바: 프로필 · 메뉴(업무 하위 목록: 마우스를 올리거나 ▾로 펼침) · 즐겨찾기 */
const NARROW='(max-width:760px)';
function useNarrow(){
 const[narrow,setNarrow]=useState(()=>typeof matchMedia==='function'&&matchMedia(NARROW).matches);
 useEffect(()=>{if(typeof matchMedia!=='function')return;const q=matchMedia(NARROW),f=()=>setNarrow(q.matches);f();q.addEventListener('change',f);return()=>q.removeEventListener('change',f)},[]);
 return narrow;
}

function Item({active,icon,label,title,onClick,className,children}){
 return <button type="button" className={'pnt-item'+(className?' '+className:'')+(active?' active':'')} title={title||label} aria-label={title||label} aria-current={active?'page':undefined} onClick={onClick}>
  <span className="pnt-ico">{icon}</span><span className="pnt-lbl">{label}</span>{children}</button>;
}

function WorkSubList({rows,style,isActive,onPick,onEnter,onLeave}){
 return <div className={'pnt-group-sub'+(style?' fly':'')} style={style} role="group" aria-label="업무 바로가기" onMouseEnter={onEnter} onMouseLeave={onLeave}>
  {style&&<span className="pnt-fly-title">업무</span>}
  {rows.map(([key,label,Icon,count,dest,tone,pmOnly])=><Item key={key} className="sub" label={label} title={label+' '+count+'건'} icon={<Icon size={16}/>} active={isActive(key)} onClick={()=>onPick(key,dest)}>
   {pmOnly&&<span className="pnt-tag">PM</span>}<span className={'pnt-count'+(count>0?' hot '+tone:'')}>{count}</span></Item>)}
 </div>;
}

export function Sidebar({sections,collapsed,toggle,logout}){
 const app=useApp(),{page,nav,setDialog,D,filter,pid,pm,mine,reviewTask,person}=app,tasks=app.tasks||[],meetings=app.meetings||[];
 const user=D.user,favorites=useFavorites(user.id),[lastKey,setLastKey]=useState(''),[hover,setHover]=useState(false),[pinned,setPinned]=useState(false),[fly,setFly]=useState(null),timer=useRef(null);
 const narrow=useNarrow(),compact=collapsed||narrow;
 useEffect(()=>setFly(null),[compact]);
 const isPm=D.projects.some(p=>pm(p.id)),open=tasks.filter(t=>t.status!=='완료'),mineOpen=open.filter(t=>mine(t));
 const rows=[
  ['today','오늘 할 일',Sun,mineOpen.filter(t=>t.due&&t.due<=D.today).length,'mine','blue'],
  ['mine','내 미완료 업무',SquareCheckBig,mineOpen.length,'mine','blue'],
  ['review','검토 요청',CheckCheck,tasks.filter(reviewTask).length+meetings.filter(m=>pm(m.project_id)&&m.document_status==='검토 대기').length,'review','blue'],
  ['check','추가 확인 필요',CircleHelp,open.filter(t=>t.kind==='확인사항'||t.status==='확인필요').length,'missing','violet'],
  ...(isPm?[['unassigned','담당 미정 업무',UserPlus,open.filter(t=>pm(t.project_id)&&!(t.kind==='확인사항'?t.reviewer_id:t.owner_id)).length,'missing','red',true]]:[]),
  ['proposals','배정할 업무 제안',Inbox,assignmentWaitingCount(meetings,tasks),'proposals','blue'],
 ];
 const attention=rows.some(r=>r[3]>0),expanded=!compact&&(hover||pinned);
 const isActive=key=>{const r=rows.find(x=>x[0]===key);return page==='work'&&filter===r[4]&&(lastKey?lastKey===key:key===r[4])};
 const pick=(key,dest)=>{setLastKey(key);setFly(null);nav('work',dest)};
 const enter=event=>{clearTimeout(timer.current);if(compact){const r=event.currentTarget.getBoundingClientRect(),rail=(event.currentTarget.closest('.pnt-rail')||event.currentTarget).getBoundingClientRect();setFly({top:Math.max(8,Math.min(r.top-6,innerHeight-rows.length*36-24)),left:rail.right+8})}else setHover(true)};
 const leave=()=>{clearTimeout(timer.current);timer.current=setTimeout(()=>{setHover(false);setFly(null)},180)};
 const favoriteProjects=favorites.map(id=>D.projects.find(p=>p.id===id)).filter(Boolean);
 const ToggleIcon=collapsed?PanelLeftOpen:PanelLeftClose,toggleLabel=collapsed?'사이드바 펼치기':'사이드바 접기';
 const department=user.department||person?.(user.id)?.department||'';

 return <aside className="rail pnt-rail" aria-label="PNT 사이드바">
  <div className="rail-brand"><img src={logo} alt="PNT"/>
   <button type="button" className="rail-toggle" aria-label={toggleLabel} title={toggleLabel} aria-expanded={!collapsed} aria-controls="primary-navigation" onClick={toggle}><ToggleIcon size={18}/></button></div>
  <div className="pnt-me">
   <span className="pnt-avatar" title={user.name}>{(user.name||'').slice(-2)}</span>
   <span className="pnt-me-txt"><small>{greeting()}</small><b>{user.name}<em>{[user.position,department].filter(Boolean).join(' · ')}</em></b></span>
   <button type="button" className="pnt-search" aria-label="회의록·업무 검색" title="회의록·업무 검색" onClick={()=>setDialog({type:'search'})}><Search size={17}/></button>
  </div>
  <nav id="primary-navigation" aria-label="주 메뉴" className="pnt-scroll">
   <div className="pnt-sec"><span className="pnt-sec-label">메뉴</span>
    {sections.flatMap(([,items])=>items).map(([Icon,key,title])=>key==='work'
     ?<div key={key} className={'pnt-group'+(expanded?' open':'')} onMouseEnter={enter} onMouseLeave={leave}>
       <div className="pnt-group-row">
        <Item label={title} icon={<Icon size={19}/>} active={page===key&&(!expanded||!rows.some(r=>isActive(r[0])))} onClick={()=>{setLastKey('');nav(key)}}>{!expanded&&attention&&<span className="pnt-dot" aria-hidden="true"/>}</Item>
        {!compact&&<button type="button" className="pnt-chev" aria-label={expanded?'업무 하위 메뉴 접기':'업무 하위 메뉴 펼치기'} aria-expanded={expanded}
          onClick={event=>{event.stopPropagation();setPinned(!(pinned||hover));setHover(false)}}><ChevronDown size={16}/></button>}
       </div>
       {compact
        ?fly&&<WorkSubList rows={rows} style={{top:fly.top+'px',left:fly.left+'px'}} isActive={isActive} onPick={pick} onEnter={()=>clearTimeout(timer.current)} onLeave={leave}/>
        :<WorkSubList rows={rows} isActive={isActive} onPick={pick}/>}
      </div>
     :<Item key={key} label={title} icon={<Icon size={19}/>} active={page===key||(key==='minutes'&&page==='compose')} onClick={()=>nav(key)}/>)}
   </div>
   <div className="pnt-divider"/>
   <div className="pnt-sec"><span className="pnt-sec-label">즐겨찾기</span>
    {favoriteProjects.length?favoriteProjects.map(p=><Item key={'fav-'+p.id} label={p.name} title={p.name+' 프로젝트 흐름 보기'} icon={<FavoriteStar id={p.id} label={p.name}/>}
      active={page==='home'&&pid===p.id} onClick={()=>nav('home',undefined,p.id)}/>)
     :<p className="pnt-empty">프로젝트 목록의 ☆를 누르면 여기에 고정됩니다.</p>}
   </div>
  </nav>
  <div className="rail-bottom">
   <button type="button" className="rail-action" aria-label="사용 도움말" title="사용 도움말" onClick={()=>setDialog({type:'help'})}><HelpCircle size={18}/><span>사용 도움말</span></button>
   <button type="button" className="rail-action" aria-label="로그아웃" title="로그아웃" onClick={logout}><LogOut size={18}/><span>로그아웃</span></button>
  </div>
 </aside>;
}
