import React from'react';
import{Check,ChevronRight}from'lucide-react';
export const PROJECT_STAGES=['수주','설계 및 변경','구매','제작','검수','납품','현장','종료'];
export function projectStages(o={}){
 return [...new Set([...(o.stages?.length?o.stages:PROJECT_STAGES),...(o.current_stage?[o.current_stage]:[])])];
}
export function ProjectStageRail({stages,current,onSelect,busy}){
 const currentIndex=stages.indexOf(current);
 return <>
  <div className="project-stepper-scroll" tabIndex={0} aria-label="프로젝트 단계 가로 스크롤">
  <ol className="project-stepper" aria-label="프로젝트 단계">
   {stages.map((stage,index)=>{
    const state=index===currentIndex?'current':currentIndex>index?'past':'upcoming';
    const status=state==='current'?'현재 단계':state==='past'?'이전 단계':'예정';
    return <li key={stage} className={state} aria-current={state==='current'?'step':undefined}>
     <button type="button" className="project-step-button" disabled={!onSelect||busy||state==='current'}
      aria-label={stage+' · '+status+(onSelect&&state!=='current'?' · 현재 단계로 설정':'')}
      onClick={()=>onSelect?.(stage)}>
      <span className="project-step-node" aria-hidden="true">{state==='past'?<Check size={16}/>:index+1}</span>
      <span className="project-step-name">{stage}</span>
      <small>{status}</small>
     </button>
    </li>;
   })}
  </ol>
 </div></>;
}

const DIGEST_HEADS={"결정사항":"decisions","합의사항":"decisions","추가확인사항":"checks","확인사항":"checks","확인필요사항":"checks","후속조치":"followups","향후조치":"followups","actionitem":"followups","actionitems":"followups"},DIGEST_STOP=new Set(["회의안건","안건","논의내용","논의사항","참고사항","기타","첨부"]);
function parseMinutes(lines){let o={decisions:[],checks:[],followups:[]},c=null;for(const l of lines||[]){const t=String(l&&l.text||"").trim();if(!t)continue;const k=t.replace(/[\s:：\[\]]/g,"").toLowerCase();if(DIGEST_HEADS[k]){c=DIGEST_HEADS[k];continue}if(DIGEST_STOP.has(k)){c=null;continue}if(c&&o[c].length<6)o[c].push(t.replace(/^\s*(?:\d+[.)]|[-•·])\s*/,""))}return o}


export function MinutesDigest({meeting,detail,error,onMeeting}){
 if(!meeting)return <p className="sv-quiet">등록된 회의록이 없습니다.</p>;
 const ready=detail?.id===meeting.id&&detail?.revision===meeting.revision&&detail?.version===meeting.version;
 const digest=ready?parseMinutes(detail.lines):null;
 const groups=[['결정 사항',digest?.decisions],['추가 확인 사항',digest?.checks],['후속 조치',digest?.followups]].filter(([,items])=>items?.length);
 return <section className="sv-minutes-digest" aria-label="회의록 요약">
  <div className="sv-digest-head"><span>회의록 요약</span><button type="button" className="sv-link" onClick={()=>onMeeting?.(meeting.id)}>{(meeting.date?meeting.date+' · ':'')+meeting.title}<ChevronRight size={13}/></button></div>
  {error?<p className="sv-quiet" role="alert">{error}</p>:!digest?<p className="sv-quiet" role="status">회의록을 불러오는 중입니다.</p>:groups.length?groups.map(([title,items])=><div key={title} className="sv-digest-group"><h3>{title}</h3><ul>{items.map((text,index)=><li key={index}>{text}</li>)}</ul></div>):<p className="sv-quiet">회의록에서 결정 사항·후속 조치 항목을 찾지 못했습니다. 회의록을 열어 확인해 주세요.</p>}
 </section>;
}
