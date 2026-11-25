export function groupedMeetings(result){
 const grouped=new Map();
 for(const item of result.meetings||[]){
  const key=result.group_by==='month'?(item.group_date||item.date||'').slice(0,7)||'날짜 미정':result.group_by==='project'?item.project_id:'전체';
  if(!grouped.has(key))grouped.set(key,{key,label:result.group_by==='project'?item.project_name:key,items:[]});
  grouped.get(key).items.push(item);
 }
 const groups=[...grouped.values()];
 if(result.group_by==='month')groups.sort((a,b)=>a.key==='날짜 미정'?1:b.key==='날짜 미정'?-1:a.key.localeCompare(b.key)*(result.direction==='oldest'?1:-1));
 return groups;
}

export function matchingProjects(projects, query) {
 const compact = text => text.normalize('NFKC').toLowerCase().replace(/[\s-]+/g, '');
 const terms = query.trim().split(/\s+/).map(compact).filter(Boolean);
 return projects.filter(project => {
  const text = compact(project.name + ' ' + project.id);
  return terms.every(term => text.includes(term));
 });
}

export function groupedChanges(result) {
 const newestFirst = result.direction === 'newest' || (!result.direction && result.notice?.includes('회의일 최신순'));
 const items = result.change_items || [];
 const chronological = newestFirst ? [...items].reverse() : items;
 const groups = new Map();
 for (const item of chronological) {
  const title = item.title.normalize('NFKC').toLowerCase().replace(/[\s·_().-]/g, '');
  const key = JSON.stringify([item.project_id, item.topic_id || [item.category || '', title]]);
  if (!groups.has(key)) groups.set(key, {key, items:[]});
  groups.get(key).items.push(item);
 }
 return [...groups.values()].map(group => {
  const dated = group.items.filter(item => item.date);
  const latest = dated.at(-1);
  const confirmed = dated.filter(item => item.state === '합의' && item.after);
  const lastAgreement = confirmed.at(-1);
  const agreementConflict = lastAgreement && confirmed.some(item => item.date === lastAgreement.date && item.after !== lastAgreement.after);
  const timeline = newestFirst ? [...dated].reverse() : dated;
  return {...group, title:(latest || group.items.at(-1)).title,
   projectName:group.items[0].project_name, latest, lastAgreement, agreementConflict,
   items:[...timeline, ...group.items.filter(item => !item.date)]};
 }).sort((a,b) => (b.latest?.date || '').localeCompare(a.latest?.date || ''));
}
