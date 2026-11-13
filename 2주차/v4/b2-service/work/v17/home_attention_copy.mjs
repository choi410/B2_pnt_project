// Display copy only: leave the stored meeting, AI draft and evidence unchanged.
const clean=value=>String(value||'').trim().replace(/\s+/g,' ');
const escape=value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const actions='작성|개정|수정|확인|검토|요청|전달|공유|제출|보완|취합|정리|발송';
const actionObject=new RegExp('^(.+?)(?:을|를)\\s*(?:\\S+(?:에게|에)\\s+)?('+actions+')(?:한다|합니다|하기로|할 예정|해|하여|하고|하며)');

function withoutLeadingMetadata(text,owner,due){
 let result=clean(text);
 if(owner)result=result.replace(new RegExp('^'+escape(owner)+'(?:(?:이|가|은|는)\\s+|\\s*[:：]\\s*)'),'');
 if(due)result=result.replace(new RegExp('^'+escape(due)+'\\s*까지\\s*'),'');
 return result||clean(text);
}

function actionTitle(text){
 // A shortened action must not turn a condition, cancellation or an unknown
 // outcome into an instruction. Keep the sentence when its meaning is unclear.
 const sentence=text.split(/(?<=[다요])\.\s+|\n/)[0];
 const pending=sentence.match(/,\s*(?:\S+\s+)?(\S+?)(?:은|는|이|가)\s*미정(?:이다|입니다)\.?$/);
 const first=pending?sentence.slice(0,pending.index):sentence;
 if(/않|아니|불가|금지|철회|취소|보류|중단|완료|미정|여부에 따라|경우|한다면|해야만|승인\s*(?:후|전|시)|확인\s*(?:후|전|시)/.test(first))return text;
 const match=first.match(actionObject);
 if(!match)return text;
 let object=match[1];
 // Retain the deliverable, while its detailed design conditions stay in the body.
 object=object.split(/(?:반영한|반영해|반영하여|고려한|포함한)\s+/).at(-1);
 object=object.replace(/^\S+(?:에게|에)\s+/,'').trim();
 if(!object||object.length>44||/(?:한다|하며|하고|했으나|지만)/.test(object))return text;
 const verb=match[2],tail=first.slice(match[0].length);
 const delivery=tail.match(/(?:에게|에)\s*(공유|전달|제출|발송)(?:한다|합니다|하기로|할 예정)/);
 return object+' '+verb+(delivery&&delivery[1]!==verb?'·'+delivery[1]:'')+(pending?' · '+pending[1]+' 미정':'');
}

export function attentionCopy(item,ownerName=''){
 const title=clean(item.title),body=clean(item.description||item.title);
 if(item.origin!=='회의록')return {title,description:body};
 const description=withoutLeadingMetadata(body,ownerName,item.due);
 // Preserve a separately authored title; derive one only from sentence-like
 // titles or a title that simply repeats/truncates the description.
 const repeated=title===body||(title.length>=60&&body.startsWith(title));
 const sentence=/[.。]$|(?:한다|합니다|미정이다|예정이다)$/.test(title);
 const heading=repeated||sentence?actionTitle(description):withoutLeadingMetadata(title,ownerName,item.due);
 return {title:heading||title,description};
}
