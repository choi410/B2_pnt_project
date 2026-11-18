import React from 'react';

// Keep one reading area; preserve user text and render only the lines that exist.
export function TaskDescription({text,title='',className=''}){
 const lines=(text||'').split(/\r?\n/).map(s=>s.replace(/^\s*[-•]\s*/,'').trim()).filter(Boolean);
 if(!lines.length)return <p className={'task-description '+className}>{title}</p>;
 return lines.length===1?<p className={'task-description '+className}>{lines[0]}</p>:<ul className={'task-description '+className}>{lines.map((line,i)=><li key={i}>{line}</li>)}</ul>;
}
