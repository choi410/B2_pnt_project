const normalize=text=>String(text||'').trim().replace(/\s+/g,' ');

// Resolve quotes against the displayed document, not line IDs from a different
// revision. Changed wording, numbers and negation must never match approximately.
export function quoteFocus(source,quotes=[]){
 const lines=String(source||'').split(/\r?\n/).map(text=>text.trim()).filter(Boolean)
  .map((text,index)=>({id:'L'+String(index+1).padStart(3,'0'),text}));
 const wanted=[...new Set(quotes.map(normalize).filter(Boolean))];
 return {
  selected:lines.filter(line=>wanted.includes(normalize(line.text))).map(line=>line.id),
  missing:wanted.filter(quote=>!lines.some(line=>normalize(line.text)===quote))
 };
}
