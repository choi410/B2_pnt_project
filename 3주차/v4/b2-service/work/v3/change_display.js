// Only compact whole values. Conditions such as '최대' or '이상' remain intact.
export function displayChange(e){
 const before=(e.before||'').trim(),after=(e.after||'').trim();
 const transition=!!before&&['확정','요청'].includes(e.business_state)&&before!==after;
 const quantity=s=>s.match(/^([\d,]+(?:\.\d+)?)\s*(m\/min|mm|cm|kg|kW|rpm|℃|°C|%)(?:(?:으)?로\s*변경\s*(?:합의|확정)(?:했다|함)?\.?)?$/i);
 const a=quantity(before),b=quantity(after);
 return {transition,before:transition&&a&&b&&a[2]===b[2]?a[1]:before,after:transition&&a&&b&&a[2]===b[2]?b[1]:after,unit:transition&&a&&b&&a[2]===b[2]?b[2]:'',label:e.business_state==='요청'?'요청':e.business_state==='확정'?'합의':e.business_state};
}

const sentences=text=>String(text||'').trim().split(/(?<=[.!?])\s+/).filter(Boolean);
const withoutPeriod=text=>text.replace(/[.]$/,'').trim();

// Compact only complete, recognized phrases. Negations and qualifiers stay visible.
function shortValue(text){
 const s=withoutPeriod(text);
 for(const pattern of [
  /^(.+?)(?:을|를)\s*(?:기본\s*(?:설계\s*)?사양으로\s*)?(?:합의했다|합의함|합의|확정했다|확정함|확정)$/,
  /^(.+?)(?:으)?로\s*(?:변경(?:하기로)?\s*)?(?:합의했다|합의함|합의|확정했다|확정함|확정)$/,
  /^(.+?)(?:을|를)\s*유지(?:한다|하기로 했다|함)?$/
 ]){
  const m=s.match(pattern);
  if(m&&!/않|아니|미정|보류|철회|요청|조건|검토/.test(m[1]))return m[1].trim()+(pattern.source.includes('유지')?' 유지':'');
 }
 return s;
}

export function cardSummary(event){
 const parts=sentences(event.after);
 const state=event.business_state;
 let index=0;
 if(state==='보류')index=Math.max(0,parts.findIndex(s=>s.includes('보류')));
 if(state==='철회')index=Math.max(0,parts.findIndex(s=>/철회|취소/.test(s)));
 const headline=parts[index]||'';
 const after=['요청','확정'].includes(state)?shortValue(headline):withoutPeriod(headline);
 const before=shortValue(event.before||'');
 const v=displayChange({...event,before,after});
 const details=parts.filter((s,i)=>i!==index).map(withoutPeriod);
 const context=withoutPeriod(event.context||'');
 if(context&&!details.length&&!parts.some(s=>s.includes(context)))details.push(context);
 const q=v.after.match(/^((?:(?:최대|최소|상한|하한|약)\s*)?[\d,]+(?:\.\d+)?)\s*(m\/min|mm|cm|kg|kW|rpm|℃|°C|%)(\s*(?:이상|이하|미만|초과))?$/i);
 const numeric=!v.transition&&!!q;
 return {...v,after:numeric?q[1]:v.after,unit:numeric?q[2]+(q[3]||''):v.unit,numeric:numeric||!!v.unit,detail:details.join(' · ')};
}
