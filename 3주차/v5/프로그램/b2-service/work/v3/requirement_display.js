const clean=s=>String(s||'').replace(/\s+/g,' ').trim();
const comparable=s=>clean(s).replace(/\s/g,'');
export const trackingLabel=state=>!state||['처리 결과 미확인','미확인'].includes(state)?'미등록':state;
export const trackingStates=['미등록','진행 중','조치 완료'];

// Presentation only. Keep the stored request, business state and evidence intact.
export function describeRequirement(row){
 const state=row.business_state, before=clean(row.before),after=clean(row.content);
 const changed=!!before&&comparable(before)!==comparable(after);
 const action=state==='요청'?(changed?'변경 요청':'요청'):state==='확정'?(changed?'변경 합의':'합의'):state==='보류'?'검토 보류':state==='철회'?'요청 철회':'기록';
 const suffix=clean(row.title).endsWith(action)?'':' '+action;
 const quotes=row.quotes||[];
 const primary=quotes.filter(q=>q.kind==='요구사항 근거');
 const followups=quotes.filter(q=>q.kind==='담당·기한 관련 근거');
 const unique=items=>items.filter((q,i)=>items.findIndex(x=>comparable(x.text)===comparable(q.text))===i);
 // A held/withdrawn value is never rendered as an approved before -> after.
 const value=changed&&['요청','확정'].includes(state)&&before.length<80&&after.length<100?before+' → '+after:after;
 return {title:clean(row.title)+suffix,value,action,source:unique(primary),followups:unique(followups)};
}
