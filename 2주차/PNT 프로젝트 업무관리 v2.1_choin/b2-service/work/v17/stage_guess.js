/* 회의록 본문으로 프로젝트 단계를 추정한다 (규칙 기반, AI 미사용).
   - 단계별 핵심어가 회의록에 나온 횟수를 점수로 센다.
   - '결정 사항'·'후속 조치' 아래 문장은 2배, 회의명·안건은 1.5배로 본다.
   - "납품일", "시운전 투입일", "공급 일정"처럼 날짜·일정만 언급한 경우는 그 단계의 활동으로 치지 않는다.
   - 후속 조치 끝의 "/ 2026-11-05까지" 같은 기한 표기는 제외한다.
   - 점수가 3 미만이거나 1·2위 차이가 작으면 추정하지 않는다. */
export const STAGE_KEYWORDS={
 '수주':['수주','계약','견적','입찰','제안서','킥오프','착수','PO'],
 '설계 및 변경':['승인도','설계','도면','사양','규격','공차','배치도','레이아웃','변경 요청','설계 변경','Rev.','검토 의견'],
 '구매':['구매','발주','자재','부품','구성품','업체 선정','견적 비교'],
 '제작':['제작','가공','조립','용접','배선','도장','제관'],
 '검수':['검수','FAT','출하 검사','성능 시험','성능 확인','공장 시운전'],
 '납품':['납품','출하','운송','반입','장비 인도'],
 '현장':['현장 설치','설치','SAT','시운전','셋업','안정화','현장'],
 '종료':['종료','완료 보고','하자 보수','하자 처리','정산','인수인계','최종 승인','클로징'],
};
const SCHEDULE=/^\s?(일|일정|일자|날짜|예정일|투입일|기한|시점)/;
const HEADS={'결정사항':2,'합의사항':2,'후속조치':2,'향후조치':2,'actionitem':2,'actionitems':2,'회의안건':1.5,'안건':1.5,'논의내용':1,'논의사항':1,'추가확인사항':1,'확인사항':1,'확인필요사항':1,'참고사항':.5};

// 모든 단계의 핵심어를 긴 것부터 한 번씩만 매칭한다 (예: '승인도' 안의 '인도', '배치도' 안의 '배치'를 다시 세지 않음)
function scoreAll(text,table){
 const used=new Array(text.length).fill(false),out={};
 const words=Object.entries(table).flatMap(([stage,list])=>list.map(word=>({stage,word}))).sort((a,b)=>b.word.length-a.word.length);
 for(const{stage,word}of words){
  let from=0;
  while(true){
   const i=text.indexOf(word,from);if(i<0)break;from=i+word.length;
   if(used.slice(i,i+word.length).some(Boolean))continue;
   for(let k=i;k<i+word.length;k++)used[k]=true; // 날짜 언급이어도 자리는 차지한다
   if(SCHEDULE.test(text.slice(i+word.length)))continue; // 날짜·일정 언급은 점수 제외
   (out[stage]||(out[stage]={total:0,hits:[]})).total++;out[stage].hits.push(word);
  }
 }
 return out;
}

export function inferStage(meeting,stages){
 const names=(stages&&stages.length?stages:Object.keys(STAGE_KEYWORDS));
 const table=Object.fromEntries(names.map(s=>[s,STAGE_KEYWORDS[s]||[s]]));
 const result=Object.fromEntries(names.map(s=>[s,{score:0,hits:[]}]));
 const add=(text,weight)=>{
  const clean=String(text||'').replace(/\s*\/\s*[^/]*$/,m=>/\d{4}-\d{2}-\d{2}|까지|차주|중$/.test(m)?'':m);
  const found=scoreAll(clean,table);for(const s of names)if(found[s]){result[s].score+=found[s].total*weight;result[s].hits.push(...found[s].hits)}
 };
 add(meeting?.title,1.5);
 let weight=1;
 for(const line of meeting?.lines||[]){
  const text=String(line?.text||'').trim();if(!text)continue;
  const key=text.replace(/[\s:：\[\]]/g,'').toLowerCase();
  if(key in HEADS){weight=HEADS[key];continue}
  if(/^(회의록|meetingminutes|회의명|프로젝트명|일시|참석자|작성자)/i.test(key.replace(/\|.*/,'')))continue; // 머리글 표
  add(text,weight);
 }
 const ranked=names.map(s=>({stage:s,score:Math.round(result[s].score*10)/10,hits:[...new Set(result[s].hits)]})).sort((a,b)=>b.score-a.score);
 const [top,second]=ranked;
 const confident=!!top&&top.score>=3&&(!second||top.score>=second.score*1.5);
 return{stage:confident?top.stage:null,top,second,ranked,meetingId:meeting?.id,meetingTitle:meeting?.title,meetingDate:meeting?.date};
}
