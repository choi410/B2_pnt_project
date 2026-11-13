import{requirementGroups}from'./project_story';
import{compareChangeEvents}from'./change_groups';

const normalize=s=>String(s||'').normalize('NFKC').trim().replace(/\s+/g,' ').toLocaleLowerCase('ko');
const scopeOf=e=>[...new Set([e.title,e.before,e.after,...(e.quotes||[])].join(' ').match(/\d+\s*(?:호기|라인)|롤프레스|코터|슬리터|코팅기/g)||[])].map(normalize).sort().join(' · ');
// Display-only aliases. Keep original events, topic IDs and approval state intact.
// Only recognize a small set of evidenced synonyms; never use fuzzy title matching.
function alias(group){
 const title=normalize(group.title),texts=group.events.map(e=>[e.before,e.after,...(e.quotes||[])].join(' '));
 let name='';
 if(group.category==='사양'&&/^점검 커버 (방식|형식|구조|개폐 방식)$/.test(title)&&
    texts.every(t=>/여닫이|슬라이드|개폐/.test(t)))name='점검 커버 개폐 방식';
 if(group.category==='납기'&&/^(납기|납품일|장비 납품일)$/.test(title)&&
    texts.every(t=>/납품/.test(t)||title.includes('납품'))&&
    !texts.some(t=>/(부품|자재|소모품)\s*(납품|납기)/.test(t)))name='장비 납품일';
 if(!name)return null;
 // Explicit machine numbers/types remain distinct, including unqualified records.
 return{name,scope:group.scope};
}

export function historyGroups(events,topics,mode='all'){
 const buckets=new Map();
 for(const e of events){const scope=scopeOf(e);if(!buckets.has(scope))buckets.set(scope,[]);buckets.get(scope).push(e)}
 const sources=[...buckets].flatMap(([scope,items])=>requirementGroups(items,topics,mode==='excluded'?'excluded':'all').map(g=>({...g,scope}))),result=new Map();
 for(const source of sources){
  const target=alias(source),key=target?JSON.stringify([source.project_id,source.category,'subject',target.name,target.scope]):source.scope?JSON.stringify([source.key,source.scope]):source.key;
  if(!result.has(key))result.set(key,{...source,key,title:target?target.name+(target.scope?' · '+target.scope:''):source.title,events:[],titles:[],originalKeys:[],baselines:[],needsAttention:0});
  const group=result.get(key);
  group.events.push(...source.events);group.titles.push(...source.titles);group.originalKeys.push(source.key);
  group.baselines.push(...source.baselines);group.needsAttention+=source.needsAttention;
 }
 return [...result.values()].map(group=>{
  group.events=[...new Map(group.events.map(e=>[e.id,e])).values()].sort(compareChangeEvents);
  group.titles=[...new Set(group.titles)];group.latest=group.events.at(-1);
  const bases=[...new Map(group.baselines.map(e=>[e.id,e])).values()].sort(compareChangeEvents),last=bases.at(-1);
  group.conflicting=last?bases.filter(e=>e.effective_date===last.effective_date):[];
  group.conflict=new Set(group.conflicting.map(e=>normalize(e.after))).size>1;
  group.current=group.conflict?null:last||null;group.grouped=group.titles.length>1;
  return group;
 }).filter(g=>mode!=='attention'||g.needsAttention||g.conflict)
 .sort((a,b)=>a.title.localeCompare(b.title,'ko')||compareChangeEvents(b.latest,a.latest));
}

// Highlight only potentially conflicting source records, never unreviewed status.
export function decisionComparisonIds(group){
 const dates=new Map();
 for(const e of group?.events||[]){
  if(e.business_state!=='확정'||e.review_state==='제외'||e.superseded_by_revision)continue;
  if(!dates.has(e.effective_date))dates.set(e.effective_date,[]);
  dates.get(e.effective_date).push(e);
 }
 return new Set([...dates.values()].filter(items=>new Set(items.map(e=>normalize(e.after))).size>1).flatMap(items=>items.map(e=>e.id)));
}

export function missingRecordSeed(group,projectId=''){
 if(!group)return {project_id:projectId};
 return {project_id:group.project_id,title:group.titles[0]||group.title,category:group.category,topic_id:group.topic?.id||null};
}
