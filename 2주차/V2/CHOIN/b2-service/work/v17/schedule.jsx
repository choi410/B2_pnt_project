import React,{useState,useEffect,useMemo,useRef,useLayoutEffect}from'react';
import{Plus,Upload,Download,FileSpreadsheet,ChevronDown,ChevronRight,Pencil,Trash2,RefreshCw,RotateCcw,Search,Check,Loader2,TriangleAlert,ChartGantt,Table,History,ArrowRight}from'lucide-react';
import{useApp,api,Button,IconButton,Modal,PageHead,Empty,Person,PeoplePicker,day,dateText,norm}from'./app';
import{SortHeader,sortByColumn,dateValue}from'./table_sort';

const DAY=86400000,ROW=34,HEAD=52,LEFT=300;
const toDate=s=>new Date(s+'T00:00:00Z');
const iso=d=>d.toISOString().slice(0,10);
const addDays=(s,n)=>iso(new Date(toDate(s).getTime()+n*DAY));
const diffDays=(a,b)=>Math.round((toDate(b)-toDate(a))/DAY);
const FIELD_LABELS={start:'시작일',end:'종료일',due:'종료일',progress:'진행률',phase:'단계',title:'항목명',owner_id:'담당자',owner_name:'담당자',kind:'구분',key:'핵심',note:'비고',depends_on:'선행작업',code:'프로젝트 번호',customer:'고객사',equipment:'장비·호기',done_at:'완료일'};
const STATUS_ORDER=['예정','진행중','지연','완료'];
const kindLabel=k=>k==='마일스톤'?'마일스톤':k==='업무'?'업무':'항목';
const textW=(t,size=10.5)=>[...String(t)].reduce((n,ch)=>n+(ch.charCodeAt(0)>255?size:size*.56),0);
const fitText=(t,maxPx,size=10.5)=>{if(textW(t,size)<=maxPx)return t;let out='';for(const ch of String(t)){if(textW(out+ch+'…',size)>maxPx)break;out+=ch}return out?out+'…':''};
function PHASE_COLOR(phases,name){return phases.find(p=>p.name===name)?.color||'#8a97a8'}

function SchedStatus({value}){return <span className={'sched-status st-'+STATUS_ORDER.indexOf(value)}>{value}</span>}
function PhaseChip({name,phases}){return name?<span className="phase-chip" style={{'--phase':PHASE_COLOR(phases,name)}}><i/>{name}</span>:<span className="phase-chip none"><i/>미분류</span>}
function valueText(k,v,person){if(v===null||v===undefined||v==='')return '미정';if(k==='owner_id')return person(v)?.name||v;if(k==='key')return v?'핵심':'일반';if(k==='progress')return v+'%';if(k==='done_at')return dateText(v);return String(v)}

export function SchedulePage(){
 const{D,pid,setPid,pm,project,person,run,busy,openTask,setConfirm,setToast,reload}=useApp();
 const[data,setData]=useState(null),[error,setError]=useState(''),[tab,setTab]=useState('gantt'),[zoom,setZoom]=useState('fit'),[collapsed,setCollapsed]=useState({}),[editor,setEditor]=useState(null),[importer,setImporter]=useState(false),[info,setInfo]=useState(false),[q,setQ]=useState(''),[hist,setHist]=useState('all'),[sort,setSort]=useState({key:'start',direction:'asc'});
 const refresh=()=>api('/schedule'+(pid?'?project_id='+encodeURIComponent(pid):'')).then(d=>{setData(d);setError('')}).catch(e=>setError(e.message));
 useEffect(()=>{setData(null);refresh()},[pid]);
 const p=pid?project(pid):null,isPm=!!(pid&&pm(pid)),card=data?.projects.find(x=>x.id===pid);
 const canImport=pid?isPm:(D.can_create_project||D.projects.some(x=>pm(x.id)));
 const imported=async r=>{if(r.project_id!==pid){await reload();setPid(r.project_id)}else await refresh()};
 const phases=data?.phases||[];
 const rows=useMemo(()=>data&&pid?buildRows(data,collapsed,phases):[],[data,collapsed,pid]);
 const searchText=x=>norm(x.title+' '+(x.phase||'')+' '+(person(x.owner_id)?.name||x.owner_name||'')+' '+(x.note||'')).includes(norm(q));
 const tableRows=useMemo(()=>{if(!data)return [];const all=[...data.items.map(x=>({...x,type:'item'})),...data.tasks.map(t=>({...t,type:'task',kind:'업무',progress:t.status==='완료'?100:null,status:t.status==='완료'?'완료':t.end&&t.end<data.today?'지연':t.start&&t.start<=data.today?'진행중':'예정'}))];return sortByColumn(all.filter(searchText),sort,{phase:x=>phases.findIndex(ph=>ph.name===x.phase)<0?99:phases.findIndex(ph=>ph.name===x.phase),title:x=>x.title,owner:x=>person(x.owner_id)?.name||x.owner_name||'',start:x=>dateValue(x.start),end:x=>dateValue(x.end),progress:x=>x.progress??-1,status:x=>STATUS_ORDER.indexOf(x.status)})},[data,q,sort]);
 const changes=useMemo(()=>(data?.changes||[]).filter(c=>(hist==='all'||c.source===hist)&&norm(c.title+' '+(c.phase||'')+' '+c.action+' '+(c.note||'')+' '+(person(c.actor)?.name||'')).includes(norm(q))),[data,hist,q]);
 const markDone=(it)=>run(async()=>{await api('/schedule/items/'+it.id,'PATCH',{version:it.version,progress:it.progress>=100?0:100});await refresh()},it.progress>=100?'완료를 취소했습니다.':'완료로 표시했습니다.');
 const remove=(it)=>setConfirm({title:'항목 삭제',text:`"${it.title}" 항목을 삭제할까요? 변경 이력에는 남습니다.`,button:'삭제',action:async()=>{await api('/schedule/items/'+it.id+'/delete','POST',{version:it.version,reason:'화면에서 삭제'});setEditor(null);await refresh()}});
 const exportHref='/api/schedule/export'+(pid?'?project_id='+encodeURIComponent(pid):''),templateHref='/api/schedule/template'+(pid?'?project_id='+encodeURIComponent(pid):'');
 return <>
  <PageHead eyebrow="PROJECT SCHEDULE" title={p?p.name+' 일정':'전체 프로젝트 일정'} text={p?'수주부터 종료까지 8단계 마일스톤과 일정 항목, 기한이 있는 업무를 한 화면에서 봅니다.':'프로젝트별 전체 기간과 핵심 마일스톤을 비교합니다. 프로젝트를 선택하면 단계별 상세 일정을 볼 수 있습니다.'}>
   <a className="btn" href={templateHref} download><FileSpreadsheet size={16}/> 엑셀 양식</a>
   <a className="btn" href={exportHref} download><Download size={16}/> 엑셀 내보내기</a>
   {canImport&&<Button icon={Upload} primary={!pid} onClick={()=>setImporter(true)}>엑셀 올리기</Button>}
   {isPm&&<Button primary icon={Plus} onClick={()=>setEditor({project_id:pid,kind:'항목',phase:phases[0]?.name||'수주',title:'',owner_id:null,owner_name:'',start:data?.today||'',end:data?.today||'',progress:0,key:false,depends_on:'',note:''})}>항목 추가</Button>}
  </PageHead>
  {card&&<ProjectCard card={card} phases={phases} isPm={isPm} onEdit={()=>setInfo(true)}/>}
  <div className="schedule-tools"><div className="tabs">{[['gantt','간트차트',ChartGantt],['table','일정표',Table],['history','변경 이력',History]].map(([k,l,I])=><button key={k} className={tab===k?'active':''} onClick={()=>setTab(k)}><I size={14}/>{l}{k==='history'&&data?<em>{data.changes.length}</em>:null}</button>)}</div>
   <div className="work-tools">{tab==='gantt'&&pid&&<div className="zoom-group" role="group" aria-label="시간 축 확대"><button className={zoom==='fit'?'active':''} onClick={()=>setZoom('fit')}>전체</button><button className={zoom==='month'?'active':''} onClick={()=>setZoom('month')}>월</button><button className={zoom==='week'?'active':''} onClick={()=>setZoom('week')}>주</button></div>}
   {tab!=='gantt'&&<label className="search"><Search size={16}/><input aria-label="일정 검색" placeholder={tab==='table'?'항목·담당자 검색':'변경 내용 검색'} value={q} onChange={e=>setQ(e.target.value)}/></label>}
   {tab==='history'&&<select aria-label="변경 출처" value={hist} onChange={e=>setHist(e.target.value)}><option value="all">모든 출처</option><option value="직접">직접 수정</option><option value="엑셀">엑셀 업로드</option><option value="업무">업무 관리</option><option value="기본">기본 생성</option></select>}
   <IconButton icon={RefreshCw} label="새로고침" onClick={refresh}/></div></div>
  {error&&<p className="warning">{error}</p>}
  {!data&&!error&&<p className="muted" role="status"><Loader2 size={14} className="spin"/> 일정을 불러오고 있습니다.</p>}
  {data&&tab==='gantt'&&(pid?<Gantt rows={rows} data={data} phases={phases} zoom={zoom} collapsed={collapsed} toggle={ph=>setCollapsed({...collapsed,[ph]:!collapsed[ph]})} onItem={it=>isPm?setEditor(it):null} onTask={t=>openTask(t.id)} person={person}/>:<Portfolio data={data} phases={phases} zoom={zoom} person={person} onProject={id=>setPid(id)} onImport={canImport?()=>setImporter(true):null}/>)}
  {data&&tab==='table'&&<ScheduleTable rows={tableRows} phases={phases} sort={sort} onSort={setSort} person={person} isPm={isPm} onEdit={x=>x.type==='task'?openTask(x.id):isPm&&setEditor(x)} onDone={markDone} today={data.today} showProject={!pid} projects={data.projects}/>}
  {data&&tab==='history'&&<ChangeList changes={changes} phases={phases} person={person} projects={data.projects} showProject={!pid}/>}
  {editor&&<ItemDialog item={editor} phases={phases} members={p?.members||[]} close={()=>setEditor(null)} saved={async()=>{setEditor(null);await refresh()}} onDelete={editor.id?()=>remove(editor):null}/>}
  {importer&&<ImportDialog pid={pid} close={()=>setImporter(false)} done={imported} templateHref={templateHref}/>}
  {info&&card&&<ProjectInfoDialog card={card} close={()=>setInfo(false)} saved={async()=>{setInfo(false);await refresh()}}/>}
 </>;
}

function ProjectCard({card,phases,isPm,onEdit}){
 const{person}=useApp();
 const pct=card.milestones_total?Math.round(card.milestones_done/card.milestones_total*100):0;
 return <section className="schedule-card"><div className="schedule-card-main"><span className="eyebrow">{card.code}</span><h2>{card.name}</h2><dl><dt>고객사</dt><dd>{card.customer||'미등록'}</dd><dt>장비·호기</dt><dd>{card.equipment||'미등록'}</dd><dt>착수일</dt><dd>{card.planned_start||'미정'}</dd><dt>납기일</dt><dd>{card.planned_end||'미정'}</dd><dt>PM</dt><dd><Person plain id={card.pm}/></dd></dl>{isPm&&<Button small icon={Pencil} onClick={onEdit}>정보 수정</Button>}</div>
  <div className="schedule-card-phases"><div className="phase-track">{phases.map(ph=>{const idx=phases.findIndex(x=>x.name===card.current_phase);const i=phases.indexOf(ph);return <span key={ph.name} className={'phase-step '+(i<idx?'done ':'')+(ph.name===card.current_phase?'current':'')} style={{'--phase':ph.color}}><i/><b>{ph.name}</b></span>})}</div><div className="schedule-card-stats"><span><b>{card.milestones_done}</b>/{card.milestones_total} 마일스톤 완료 ({pct}%)</span>{card.late>0&&<span className="late-badge"><TriangleAlert size={13}/> 기한 지난 항목 {card.late}건</span>}<span>현재 단계 <b>{card.current_phase||'미정'}</b></span></div></div></section>;
}

function buildRows(data,collapsed,phases){
 const rows=[];const groups=phases.map(ph=>ph.name);const tasks=data.tasks;
 const unassigned=tasks.filter(t=>!t.phase||!groups.includes(t.phase));
 for(const ph of [...groups,...(unassigned.length?['미분류']:[])]){
  const items=ph==='미분류'?[]:data.items.filter(x=>x.phase===ph);
  const ts=ph==='미분류'?unassigned:tasks.filter(t=>t.phase===ph);
  const children=[...items.map(x=>({...x,type:'item'})),...ts.map(t=>({...t,type:'task',kind:'업무',progress:t.status==='완료'?100:0,status:t.status==='완료'?'완료':t.end&&t.end<data.today?'지연':t.start&&t.start<=data.today?'진행중':'예정'}))].sort((a,b)=>(a.start||'9999').localeCompare(b.start||'9999')||(a.kind==='마일스톤'?-1:1));
  const dated=children.filter(c=>c.start);
  const start=dated.length?dated.reduce((m,c)=>c.start<m?c.start:m,dated[0].start):null,end=dated.length?dated.reduce((m,c)=>(c.end||c.start)>m?(c.end||c.start):m,dated[0].end||dated[0].start):null;
  rows.push({type:'phase',phase:ph,start,end,count:children.length,done:children.filter(c=>c.status==='완료').length,late:children.filter(c=>c.status==='지연').length,collapsed:!!collapsed[ph]});
  if(!collapsed[ph])rows.push(...children.map(c=>({...c,type:c.type,phase:ph})));
 }
 return rows;
}

function useWidth(ref){const[w,setW]=useState(900);useLayoutEffect(()=>{if(!ref.current)return;const ro=new ResizeObserver(e=>setW(e[0].contentRect.width));ro.observe(ref.current);setW(ref.current.clientWidth);return()=>ro.disconnect()},[ref]);return w}

function timeRange(dates,today,cardStart,cardEnd){
 const all=[...dates,cardStart,cardEnd].filter(Boolean);
 let min=all.length?all.reduce((m,d)=>d<m?d:m):addDays(today,-30),max=all.length?all.reduce((m,d)=>d>m?d:m):addDays(today,150);
 if(today<min)min=today;if(today>max)max=today;
 min=addDays(min,-7);max=addDays(max,24);
 if(diffDays(min,max)<60)max=addDays(min,60);
 return {min,max,days:diffDays(min,max)};
}

function Axis({range,ppd,width}){
 const months=[];let d=toDate(range.min);d.setUTCDate(1);
 while(iso(d)<=range.max){const s=iso(d);const n=new Date(d);n.setUTCMonth(n.getUTCMonth()+1);const e=iso(n);months.push({start:s<range.min?range.min:s,end:e>range.max?range.max:e,label:`${d.getUTCFullYear()}.${String(d.getUTCMonth()+1).padStart(2,'0')}`});d=n}
 const weeks=[];if(ppd>=5){let w=toDate(range.min);w.setUTCDate(w.getUTCDate()+((8-w.getUTCDay())%7));while(iso(w)<range.max){weeks.push(iso(w));w=new Date(w.getTime()+7*DAY)}}
 const x=s=>diffDays(range.min,s)*ppd;
 return <g className="gantt-axis">
  {months.map(m=><g key={m.label+m.start}><rect x={x(m.start)} y={0} width={Math.max(0,x(m.end)-x(m.start))} height={HEAD} fill={months.indexOf(m)%2?'#f6f8fb':'#fff'}/><line x1={x(m.start)} x2={x(m.start)} y1={0} y2={HEAD} stroke="#d9e1ea"/>{x(m.end)-x(m.start)>34&&<text x={x(m.start)+6} y={16} fontSize="11" fontWeight="700" fill="#4a5d73">{m.label}</text>}</g>)}
  {weeks.map(wk=><g key={wk}><line x1={x(wk)} x2={x(wk)} y1={HEAD-20} y2={HEAD} stroke="#e3e9f0"/>{ppd>=5&&<text x={x(wk)+3} y={HEAD-7} fontSize="9.5" fill="#8a99ad">{wk.slice(5).replace('-','/')}</text>}</g>)}
  <line x1={0} x2={width} y1={HEAD-.5} y2={HEAD-.5} stroke="#c9d3df"/>
 </g>;
}

function Gantt({rows,data,phases,zoom,toggle,onItem,onTask,person}){
 const ref=useRef(null),width=useWidth(ref);
 const card=data.projects[0];
 const range=timeRange(rows.flatMap(r=>[r.start,r.end]),data.today,card?.planned_start,card?.planned_end);
 const avail=Math.max(300,width-LEFT-2);const ppd=zoom==='week'?22:zoom==='month'?7:Math.max(1.2,avail/range.days);
 const chartW=Math.max(avail,Math.ceil(range.days*ppd));
 const x=s=>diffDays(range.min,s)*ppd;
 const height=HEAD+rows.length*ROW+10;
 const todayX=x(data.today);
 const undated=rows.filter(r=>r.type!=='phase'&&!r.start);
 return <div className="gantt" ref={ref}>
  {!rows.length&&<Empty title="일정 항목이 없습니다" text="PM이 항목을 추가하거나 엑셀을 올리면 여기에 표시됩니다."/>}
  {rows.length>0&&<div className="gantt-scroll"><div className="gantt-inner" style={{width:LEFT+chartW}}>
   <div className="gantt-labels" style={{width:LEFT}}>
    <div className="gantt-label-head"><span>단계 · 항목</span><span>담당</span></div>
    {rows.map((r,i)=>r.type==='phase'?<button key={'p'+r.phase} className="gantt-phase-row" style={{'--phase':PHASE_COLOR(phases,r.phase)}} onClick={()=>toggle(r.phase)} aria-expanded={!r.collapsed}>{r.collapsed?<ChevronRight size={14}/>:<ChevronDown size={14}/>}<i/><b>{r.phase}</b><small>{r.count}건{r.done?` · 완료 ${r.done}`:''}{r.late?<em> · 지연 {r.late}</em>:null}</small></button>
     :<button key={r.type+r.id} className={'gantt-item-row '+(r.status==='완료'?'done ':'')+(r.status==='지연'?'late ':'')} onClick={()=>r.type==='task'?onTask(r):onItem(r)} title={r.title}><span className={'kind-mark k-'+r.kind}>{r.kind==='마일스톤'?'◆':r.kind==='업무'?'■':'▬'}</span><span className="gantt-item-title">{r.title}{r.key&&<small className="key-tag">핵심</small>}{r.kind==='업무'&&<small className="task-tag">업무</small>}</span><span className="gantt-item-owner">{person(r.owner_id)?.name||r.owner_name||''}</span></button>)}
   </div>
   <svg className="gantt-svg" width={chartW} height={height} role="img" aria-label="간트차트">
    <Axis range={range} ppd={ppd} width={chartW}/>
    {rows.map((r,i)=><rect key={'bg'+i} x={0} y={HEAD+i*ROW} width={chartW} height={ROW} fill={r.type==='phase'?'#f3f6f9':i%2?'#fcfdfe':'#fff'}/>)}
    {rows.map((r,i)=><line key={'ln'+i} x1={0} x2={chartW} y1={HEAD+(i+1)*ROW-.5} y2={HEAD+(i+1)*ROW-.5} stroke="#edf1f5"/>)}
    {card?.planned_start&&card?.planned_end&&<rect x={x(card.planned_start)} y={HEAD} width={Math.max(2,x(card.planned_end)-x(card.planned_start))} height={rows.length*ROW} fill="#174a8b" opacity=".035"/>}
    {rows.map((r,i)=>{const y=HEAD+i*ROW;const color=PHASE_COLOR(phases,r.phase);
     if(r.type==='phase'){if(!r.start)return null;const x1=x(r.start),x2=Math.max(x1+6,x(r.end||r.start)+(r.end===r.start?ppd:0));return <g key={'ph'+i}><rect x={x1} y={y+12} width={x2-x1} height={10} rx={5} fill={color} opacity=".28"/><rect x={x1} y={y+12} width={Math.max(0,(x2-x1)*(r.count?r.done/r.count:0))} height={10} rx={5} fill={color} opacity=".85"/></g>}
     if(!r.start)return <text key={'u'+i} x={8} y={y+21} fontSize="10" fill="#a0adbd">날짜 미정</text>;
     const done=r.status==='완료',late=r.status==='지연';
     if(r.kind==='마일스톤'){const cx=x(r.start)+ppd/2,cy=y+ROW/2,s=r.key?9:7;return <g key={'ms'+i} className="gantt-ms" onClick={()=>onItem(r)}><polygon points={`${cx},${cy-s} ${cx+s},${cy} ${cx},${cy+s} ${cx-s},${cy}`} fill={done?color:late?'#fff':'#fff'} stroke={late?'#c0392b':color} strokeWidth={r.key?2.4:1.8}/>{done&&<path d={`M${cx-3.5},${cy} l2.5,2.5 l4.5,-5`} stroke="#fff" strokeWidth="1.8" fill="none"/>}<text x={cx+s+6} y={cy+4} fontSize="10.5" fill={late?'#b03a2e':'#3b4a5c'} fontWeight={r.key?700:500}>{r.title}{done?'':late?' · 지연':''}</text></g>}
     const x1=x(r.start),x2=Math.max(x1+4,x(r.end||r.start)+ppd);const w=x2-x1;const isTask=r.kind==='업무';
     return <g key={'it'+i} className="gantt-bar" onClick={()=>isTask?onTask(r):onItem(r)}>
      <rect x={x1} y={y+8} width={w} height={18} rx={4} fill={isTask?'#fff':color} stroke={late?'#c0392b':isTask?color:'none'} strokeWidth={isTask?1.6:late?1.6:0} strokeDasharray={isTask?'4 3':undefined} opacity={done&&!isTask?.55:1}/>
      {!isTask&&r.progress>0&&r.progress<100&&<rect x={x1} y={y+8} width={Math.max(0,w*r.progress/100)} height={18} rx={4} fill="#0d2440" opacity=".28"/>}
      <title>{r.title} · {r.start}{r.end&&r.end!==r.start?' ~ '+r.end:''}{!isTask?` · ${r.progress||0}%`:''} · {r.status}</title>
      {(()=>{const suffix=!isTask&&r.progress?` ${r.progress}%`:'';const inner=fitText(r.title,w-14-textW(suffix));return inner&&(inner===r.title||w>=170)?<text x={x1+7} y={y+21} fontSize="10.5" fill={isTask?'#2f3f52':'#fff'} fontWeight="600">{inner}{suffix}</text>:<text x={x2+6} y={y+21} fontSize="10.5" fill="#3b4a5c">{r.title}{suffix}</text>})()}
     </g>})}
    <line x1={todayX} x2={todayX} y1={HEAD-4} y2={height} stroke="#d9534f" strokeWidth="1.5"/><rect x={todayX-25} y={HEAD-21} width={50} height={17} rx={8.5} fill="#d9534f"/><text x={todayX} y={HEAD-9} fontSize="9.5" textAnchor="middle" fill="#fff" fontWeight="700">오늘 {data.today.slice(5).replace('-','/')}</text>
   </svg></div></div>}
  <div className="gantt-legend">{phases.map(ph=><span key={ph.name}><i style={{background:ph.color}}/>{ph.name}</span>)}<span><i className="legend-ms"/>마일스톤 (굵은 테두리 = 핵심)</span><span><i className="legend-task"/>업무 관리의 업무</span><span><i className="legend-today"/>오늘</span>{undated.length>0&&<span className="muted">날짜 미정 {undated.length}건은 왼쪽 목록에서 확인</span>}</div>
 </div>;
}

function Portfolio({data,phases,zoom,person,onProject,onImport}){
 const ref=useRef(null),width=useWidth(ref);
 const ps=data.projects;
 if(!ps.length)return <Empty title="참여 중인 프로젝트가 없습니다" text={onImport?'일정 엑셀을 올리면 "프로젝트" 시트의 이름·번호·기간으로 프로젝트를 만들고 일정을 채웁니다.':'PM이 프로젝트를 만들면 여기에 표시됩니다.'} action={onImport&&<Button primary icon={Upload} onClick={onImport}>엑셀로 프로젝트 만들기</Button>}/>;
 const range=timeRange(ps.flatMap(p=>[p.start,p.end]),data.today);
 const avail=Math.max(300,width-LEFT-2);const ppd=zoom==='week'?22:zoom==='month'?7:Math.max(1.2,avail/range.days);
 const chartW=Math.max(avail,Math.ceil(range.days*ppd));const x=s=>diffDays(range.min,s)*ppd;
 const PR=44;const height=HEAD+ps.length*PR+10;const todayX=x(data.today);
 const keyMs=data.items.filter(it=>it.kind==='마일스톤'&&it.key&&it.start);
 return <div className="gantt portfolio" ref={ref}><div className="gantt-scroll"><div className="gantt-inner" style={{width:LEFT+chartW}}>
  <div className="gantt-labels" style={{width:LEFT}}><div className="gantt-label-head"><span>프로젝트</span><span>PM</span></div>
   {ps.map(p=><button key={p.id} className="gantt-project-row" onClick={()=>onProject(p.id)} style={{height:PR,'--phase':PHASE_COLOR(phases,p.current_phase)}}><span className="gantt-item-title"><b>{p.name}</b><small>{p.code}{p.customer?' · '+p.customer:''} · <i/>{p.current_phase||'단계 미정'}{p.late?<em> · 지연 {p.late}</em>:null}</small></span><span className="gantt-item-owner">{person(p.pm)?.name}</span></button>)}
  </div>
  <svg className="gantt-svg" width={chartW} height={height} role="img" aria-label="프로젝트별 일정">
   <Axis range={range} ppd={ppd} width={chartW}/>
   {ps.map((p,i)=><rect key={'bg'+p.id} x={0} y={HEAD+i*PR} width={chartW} height={PR} fill={i%2?'#fcfdfe':'#fff'}/>)}
   {ps.map((p,i)=><line key={'ln'+p.id} x1={0} x2={chartW} y1={HEAD+(i+1)*PR-.5} y2={HEAD+(i+1)*PR-.5} stroke="#edf1f5"/>)}
   {ps.map((p,i)=>{const y=HEAD+i*PR;if(!p.start)return <text key={'u'+p.id} x={8} y={y+26} fontSize="10" fill="#a0adbd">착수일·납기일 미정</text>;const x1=x(p.start),x2=Math.max(x1+6,x(p.end||p.start)+ppd);const color=PHASE_COLOR(phases,p.current_phase);const pct=p.milestones_total?p.milestones_done/p.milestones_total:0;
    return <g key={'bar'+p.id} className="gantt-bar" onClick={()=>onProject(p.id)}><rect x={x1} y={y+13} width={x2-x1} height={18} rx={5} fill={color} opacity=".25"/><rect x={x1} y={y+13} width={Math.max(0,(x2-x1)*pct)} height={18} rx={5} fill={color} opacity=".9"/>
     {keyMs.filter(m=>m.project_id===p.id).map(m=>{const cx=x(m.start)+ppd/2,cy=y+22,s=6;const done=m.status==='완료';return <polygon key={m.id} points={`${cx},${cy-s} ${cx+s},${cy} ${cx},${cy+s} ${cx-s},${cy}`} fill={done?'#132f52':'#fff'} stroke="#132f52" strokeWidth="1.6"><title>{m.title} · {m.start}{done?' · 완료':''}</title></polygon>})}
     <title>{p.name} · {p.planned_start||p.start} ~ {p.planned_end||p.end}</title><text x={x2+8} y={y+26} fontSize="10.5" fill="#3b4a5c" fontWeight="600">{(p.planned_start||p.start).slice(2)} ~ {(p.planned_end||p.end).slice(2)}</text></g>})}
   <line x1={todayX} x2={todayX} y1={HEAD-4} y2={height} stroke="#d9534f" strokeWidth="1.5"/><rect x={todayX-25} y={HEAD-21} width={50} height={17} rx={8.5} fill="#d9534f"/><text x={todayX} y={HEAD-9} fontSize="9.5" textAnchor="middle" fill="#fff" fontWeight="700">오늘 {data.today.slice(5).replace('-','/')}</text>
  </svg></div></div>
  <div className="gantt-legend"><span><i style={{background:'#132f52',opacity:.25}}/>프로젝트 기간 (진한 부분 = 마일스톤 완료 비율)</span><span><i className="legend-ms"/>핵심 마일스톤 (승인도·입고·FAT·출하·SAT)</span><span><i className="legend-today"/>오늘</span></div></div>;
}

function ScheduleTable({rows,phases,sort,onSort,person,isPm,onEdit,onDone,today,showProject,projects}){
 if(!rows.length)return <Empty title="표시할 일정이 없습니다"/>;
 const cols=[['phase','단계'],['title','항목'],['owner','담당'],['start','시작'],['end','종료'],['progress','진행률'],['status','상태']];
 return <div className={'task-table schedule-table '+(showProject?'with-project':'')}><div className="table-head">{showProject&&<span>프로젝트</span>}{cols.map(([k,l])=><SortHeader key={k} label={l} column={k} sort={sort} onSort={onSort}/>)}<span>기간</span><span/></div>
  {rows.map(r=>{const dur=r.start&&r.end?diffDays(r.start,r.end)+1:null;const dday=r.end&&r.status!=='완료'?diffDays(today,r.end):null;
   return <div className={'task-row schedule-row '+(r.status==='지연'?'late ':'')+(r.status==='완료'?'done':'')} key={r.type+r.id}>
    {showProject&&<span className="muted">{projects.find(p=>p.id===r.project_id)?.name}</span>}
    <PhaseChip name={r.phase} phases={phases}/>
    <button className="schedule-title" onClick={()=>onEdit(r)}><span className={'kind-mark k-'+r.kind}>{r.kind==='마일스톤'?'◆':r.kind==='업무'?'■':'▬'}</span><span><b>{r.title}</b><small>{kindLabel(r.kind)}{r.key?' · 핵심':''}{r.note?' · '+r.note:''}</small></span></button>
    <span>{person(r.owner_id)?.name||r.owner_name||<span className="muted">미지정</span>}</span>
    <span>{r.start?day(r.start):'미정'}</span>
    <span>{r.end?day(r.end):'미정'}{dday!==null&&<small className={dday<0?'overdue-note':'dday-note'}>{dday<0?`${-dday}일 지남`:dday===0?'오늘':`D-${dday}`}</small>}</span>
    <span className="progress-cell">{r.progress===null||r.progress===undefined?<span className="muted">—</span>:<><i style={{width:r.progress+'%'}}/><small>{r.progress}%</small></>}</span>
    <SchedStatus value={r.status}/>
    <span className="muted">{dur?dur+'일':'—'}</span>
    <span className="row-actions">{isPm&&r.type==='item'&&<IconButton icon={r.status==='완료'?RotateCcw:Check} label={r.status==='완료'?'완료 취소':'완료 표시'} onClick={()=>onDone(r)}/>}{r.type==='task'?<ChevronRight size={15}/>:isPm&&<IconButton icon={Pencil} label="수정" onClick={()=>onEdit(r)}/>}</span>
   </div>})}
 </div>;
}

function ChangeList({changes,phases,person,projects,showProject}){
 if(!changes.length)return <Empty title="변경 이력이 없습니다" text="항목을 추가·수정하거나 엑셀을 올리면 변경 내용이 시간순으로 쌓입니다."/>;
 const groups=[];for(const c of changes){const d=c.at.slice(0,10);const g=groups.find(x=>x.date===d);if(g)g.items.push(c);else groups.push({date:d,items:[c]})}
 return <div className="schedule-history">{groups.map(g=><section key={g.date}><h3>{g.date} <small>{g.items.length}건</small></h3>{g.items.map(c=><article className="schedule-change" key={c.id}>
  <div className="change-meta"><time>{c.at.slice(11,16)}</time><span className={'source-chip src-'+c.source}>{c.source}</span>{showProject&&<span className="muted">{projects.find(p=>p.id===c.project_id)?.name}</span>}<PhaseChip name={c.phase} phases={phases}/><span className="muted">{c.target_type}</span></div>
  <div className="change-body"><b>{c.title}</b><span className={'change-action act-'+c.action}>{c.action}</span>
   {(()=>{const ch={...(c.changes||{})};if(ch.start&&ch.end&&ch.start.before===ch.end.before&&ch.start.after===ch.end.after){ch['날짜']=ch.start;delete ch.start;delete ch.end}return Object.entries(ch)})().filter(([k])=>k!=='done_at'||c.action==='완료').map(([k,v])=><span className="change-diff" key={k}><small>{FIELD_LABELS[k]||k}</small>{c.action==='추가'||c.action==='업무 등록'?<em>{valueText(k,v.after,person)}</em>:c.action==='삭제'?<s>{valueText(k,v.before,person)}</s>:<><s>{valueText(k,v.before,person)}</s><ArrowRight size={11}/><em>{valueText(k,v.after,person)}</em></>}</span>)}
   {c.note&&<p className="change-note">{c.note}</p>}</div>
  <div className="change-actor"><Person plain id={c.actor}/></div>
 </article>)}</section>)}</div>;
}

function ItemDialog({item,phases,members,close,saved,onDelete}){
 const{run,busy}=useApp(),[d,setD]=useState({...item,reason:''}),patch=(k,v)=>setD({...d,[k]:v});
 const isNew=!item.id,ms=d.kind==='마일스톤';
 const save=()=>run(async()=>{
  if(isNew){await api('/schedule/items','POST',{project_id:d.project_id,kind:d.kind,phase:d.phase,title:d.title.trim(),owner_id:d.owner_id||null,owner_name:d.owner_id?'':(d.owner_name||''),start:d.start||null,end:ms?(d.end||d.start||null):(d.end||null),progress:Number(d.progress)||0,key:!!d.key,depends_on:d.depends_on||'',note:d.note||''})}
  else{const body={version:item.version,reason:d.reason||''};for(const k of ['kind','phase','title','owner_id','owner_name','start','end','progress','key','depends_on','note']){if(JSON.stringify(d[k]??null)!==JSON.stringify(item[k]??null))body[k]=k==='progress'?Number(d[k])||0:k==='key'?!!d[k]:(d[k]===''?(k==='start'||k==='end'||k==='owner_id'?null:''):d[k])}
   if(d.owner_id&&!('owner_name' in body)&&item.owner_name)body.owner_name='';
   await api('/schedule/items/'+item.id,'PATCH',body)}
  await saved()},isNew?'항목을 추가했습니다.':'항목을 수정했습니다.');
 return <Modal title={isNew?'일정 항목 추가':'일정 항목 수정'} close={close} footer={<>{onDelete&&<Button danger icon={Trash2} onClick={onDelete} disabled={busy}>삭제</Button>}<Button onClick={close}>취소</Button><Button primary disabled={busy||!d.title.trim()||!d.phase} onClick={save}>{isNew?'추가':'저장'}</Button></>}>
  <div className="edit-grid">
   <label>구분<select value={d.kind} onChange={e=>patch('kind',e.target.value)}><option>항목</option><option>마일스톤</option></select></label>
   <label>단계<select value={d.phase} onChange={e=>patch('phase',e.target.value)}>{phases.map(ph=><option key={ph.name}>{ph.name}</option>)}</select></label>
   <label className="span2">{ms?'마일스톤 이름':'항목명'}<input autoFocus value={d.title} onChange={e=>patch('title',e.target.value)} placeholder={ms?'예: 승인도 승인':'예: 롤 소재 발주·입고'}/></label>
   <label>담당자 (참여자)<PeoplePicker value={d.owner_id} onChange={v=>setD({...d,owner_id:v,owner_name:v?'':d.owner_name})} ids={members} placeholder="참여자 선택"/></label>
   <label>담당자 이름 (직접 입력)<input value={d.owner_id?'':(d.owner_name||'')} disabled={!!d.owner_id} onChange={e=>patch('owner_name',e.target.value)} placeholder="참여자가 아니면 이름만 입력"/></label>
   {ms?<label className="span2">날짜<input type="date" value={d.end||d.start||''} onChange={e=>setD({...d,start:e.target.value,end:e.target.value})}/></label>
   :<><label>시작일<input type="date" value={d.start||''} onChange={e=>patch('start',e.target.value)}/></label><label>종료일<input type="date" value={d.end||''} onChange={e=>patch('end',e.target.value)}/></label></>}
   <label>진행률 (%)<input type="number" min="0" max="100" value={d.progress??0} onChange={e=>patch('progress',e.target.value)}/></label>
   <label className="check-line inline-check"><input type="checkbox" checked={!!d.key} onChange={e=>patch('key',e.target.checked)}/>핵심 마일스톤 (승인도·입고·FAT·출하·SAT 등)</label>
   <label className="span2">선행작업<input value={d.depends_on||''} onChange={e=>patch('depends_on',e.target.value)} placeholder="예: 핵심 부품 입고"/></label>
   <label className="span2">비고 · 완료 기준<textarea value={d.note||''} onChange={e=>patch('note',e.target.value)} placeholder="완료로 보는 기준이나 참고 사항"/></label>
   {!isNew&&<label className="span2">변경 사유 (변경 이력에 남습니다)<input value={d.reason} onChange={e=>patch('reason',e.target.value)} placeholder="예: 협력사 열처리 재작업으로 입고 지연"/></label>}
  </div>
  {!isNew&&<p className="field-note">출처: {item.source} · 마지막 수정 {dateText(item.updated_at)}</p>}
 </Modal>;
}

function ImportDialog({pid,close,done,templateHref}){
 const{D,pm,run,busy}=useApp(),[file,setFile]=useState(null),[mode,setMode]=useState('merge'),[result,setResult]=useState(null),[drag,setDrag]=useState(false),[target,setTarget]=useState(pid||'');
 const mine=D.projects.filter(x=>pm(x.id));
 const upload=()=>run(async()=>{const form=new FormData();form.append('project_id',pid||target);form.append('mode',mode);form.append('file',file);const r=await api('/schedule/import','POST',form);setResult(r);await done(r)},'엑셀 일정을 반영했습니다.');
 return <Modal title="엑셀 일정 올리기" close={close} footer={<><Button onClick={close}>{result?'닫기':'취소'}</Button>{!result&&<Button primary disabled={!file||busy} icon={Upload} onClick={upload}>{busy?'반영 중…':'반영'}</Button>}</>}>
  {!result?<>
   {!pid&&<label className="field">반영할 프로젝트<select value={target} onChange={e=>setTarget(e.target.value)}><option value="">엑셀의 "프로젝트" 시트 기준 (같은 번호가 있으면 반영, 없으면 새로 만들기)</option>{mine.map(x=><option key={x.id} value={x.id}>{x.name} ({x.code||x.id})</option>)}</select></label>}
   <p className="notice">양식의 <b>일정</b> 시트를 읽습니다. 같은 단계·같은 항목명이 이미 있으면 그 항목을 갱신하고, 바뀐 내용은 변경 이력에 남습니다. <a className="text-link" href={templateHref} download>현재 일정이 채워진 양식 내려받기</a></p>
   <div className={'xl-drop '+(drag?'drag':'')} onDragOver={e=>{e.preventDefault();setDrag(true)}} onDragLeave={()=>setDrag(false)} onDrop={e=>{e.preventDefault();setDrag(false);const f=e.dataTransfer.files[0];if(f)setFile(f)}}>
    <FileSpreadsheet size={28}/><p>{file?<b>{file.name}</b>:'여기에 .xlsx 파일을 끌어다 놓거나'}</p><label className="btn small">{file?'다른 파일 선택':'파일 선택'}<input type="file" accept=".xlsx,.xlsm" hidden onChange={e=>setFile(e.target.files[0]||null)}/></label>
   </div>
   <div className="xl-modes"><label className={mode==='merge'?'on':''}><input type="radio" name="mode" checked={mode==='merge'} onChange={()=>setMode('merge')}/><span><b>추가·갱신만</b><small>엑셀에 없는 기존 항목은 그대로 둡니다.</small></span></label><label className={mode==='replace'?'on':''}><input type="radio" name="mode" checked={mode==='replace'} onChange={()=>setMode('replace')}/><span><b>엑셀 기준으로 맞추기</b><small>이전에 엑셀로 올린 항목 중 이번 파일에 없는 것은 삭제합니다. 기본 마일스톤과 직접 입력 항목은 남습니다.</small></span></label></div>
  </>:<div className="import-result"><h3>반영 결과 · {result.project_name}</h3>{result.project_created&&<p className="notice">엑셀의 프로젝트 정보로 새 프로젝트를 만들었습니다. 참여자는 프로젝트 선택 화면의 "참여자 추가"에서 넣을 수 있습니다.</p>}<div className="import-stats"><span><b>{result.added}</b>추가</span><span><b>{result.changed}</b>변경</span><span><b>{result.removed}</b>삭제</span><span><b>{result.unchanged}</b>변동 없음</span></div>
   {result.project_updated?.length>0&&<p className="notice">프로젝트 정보 갱신: {result.project_updated.map(k=>FIELD_LABELS[k]||k).join(', ')}</p>}
   {result.problems?.length>0&&<div className="warning"><b>확인이 필요한 행 {result.problems.length}건</b><ul>{result.problems.map((x,i)=><li key={i}>{x}</li>)}</ul></div>}
   {!result.problems?.length&&<p className="muted">모든 행을 문제 없이 읽었습니다.</p>}</div>}
 </Modal>;
}

function ProjectInfoDialog({card,close,saved}){
 const{run,busy}=useApp(),[d,setD]=useState({code:card.code||'',customer:card.customer||'',equipment:card.equipment||'',start:card.planned_start||'',end:card.planned_end||'',reason:''}),patch=(k,v)=>setD({...d,[k]:v});
 return <Modal title="프로젝트 정보" close={close} footer={<><Button onClick={close}>취소</Button><Button primary disabled={busy} onClick={()=>run(async()=>{await api('/projects/'+card.id+'/info','PATCH',{code:d.code,customer:d.customer,equipment:d.equipment,start:d.start||null,end:d.end||null,reason:d.reason});await saved()},'프로젝트 정보를 저장했습니다.')}>저장</Button></>}>
  <div className="edit-grid"><label>프로젝트 번호<input value={d.code} onChange={e=>patch('code',e.target.value)} placeholder="예: P-2606"/></label><label>고객사<input value={d.customer} onChange={e=>patch('customer',e.target.value)} placeholder="예: D사"/></label>
   <label className="span2">장비·호기<input value={d.equipment} onChange={e=>patch('equipment',e.target.value)} placeholder="예: 전극 롤프레스 1호기"/></label>
   <label>착수일<input type="date" value={d.start} onChange={e=>patch('start',e.target.value)}/></label><label>납기일<input type="date" value={d.end} onChange={e=>patch('end',e.target.value)}/></label>
   <label className="span2">변경 사유<input value={d.reason} onChange={e=>patch('reason',e.target.value)} placeholder="납기 변경 등 사유 (변경 이력에 남습니다)"/></label></div>
  <p className="field-note">착수일·납기일을 처음 입력하면 날짜가 없던 기본 마일스톤에 단계별 예정일이 자동 배분됩니다. 이후에는 각 마일스톤에서 직접 조정합니다.</p>
 </Modal>;
}
