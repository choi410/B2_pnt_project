import React from 'react';

const collator=new Intl.Collator('ko',{numeric:true,sensitivity:'base'});
export const dateValue=value=>{const time=value?Date.parse(value):NaN;return Number.isFinite(time)?time:null};
export const nextSort=(current,key,initial='asc')=>({key,direction:current.key===key&&current.direction==='asc'?'desc':current.key===key?'asc':initial});

export function sortByColumn(items,sort,columns){
 const get=columns[sort.key];
 if(!get)return [...items];
 return [...items].sort((a,b)=>{
  const x=get(a),y=get(b),missingX=x===null||x===undefined||x==='',missingY=y===null||y===undefined||y==='';
  // Unknown dates/people stay last in both directions.
  if(missingX||missingY)return Number(missingX)-Number(missingY);
  const result=typeof x==='number'&&typeof y==='number'?x-y:collator.compare(String(x),String(y));
  return sort.direction==='asc'?result:-result;
 });
}

export function SortHeader({label,column,sort,onSort,initial='asc',hint}){
 const active=sort.key===column,next=nextSort(sort,column,initial);
 const direction=active?(sort.direction==='asc'?'오름차순':'내림차순'):'정렬 안 됨';
 return <button type="button" className={'column-sort '+(active?'sorted':'')} aria-label={label+' · '+direction} title={(hint?hint+' · ':'')+(next.direction==='asc'?'오름차순으로 정렬':'내림차순으로 정렬')} onClick={()=>onSort(next)}><span>{label}</span><span className="sort-indicator" aria-hidden="true">{active?(sort.direction==='asc'?'▴':'▾'):<><i>▴</i><i>▾</i></>}</span></button>;
}
