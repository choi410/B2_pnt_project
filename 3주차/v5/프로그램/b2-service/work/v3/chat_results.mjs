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
