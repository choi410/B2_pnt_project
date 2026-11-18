export function duration(seconds){
 const n=Math.max(0,Math.floor(seconds));
 if(n<60)return n+'초';
 const minutes=Math.floor(n/60),rest=n%60;
 return minutes+'분'+(rest?' '+rest+'초':'');
}
export function timingText(progress,delta=0,queued=false){
 if(!progress)return {elapsed:'',remaining:'예상 시간 계산 중'};
 const elapsed=Number.isFinite(progress.elapsed_seconds)?(queued?'대기 ':'')+duration(progress.elapsed_seconds+Math.max(0,delta))+' 경과':'';
 if(delta>12)return {elapsed,remaining:'진행 상태를 다시 확인 중'};
 const range=progress.remaining_seconds;
 if(range){
  const low=Math.max(0,range[0]-delta),high=range[1]-delta;
  if(high<=0)return {elapsed,remaining:'예상보다 오래 걸리고 있습니다.'};
  const hi=Math.max(5,Math.ceil(high/5)*5),lo=Math.max(0,Math.floor(low/5)*5);
  return {elapsed,remaining:lo>0?'예상 남은 시간 약 '+duration(lo)+'~'+duration(hi):'예상 남은 시간 약 '+duration(hi)+' 이내'};
 }
 return {elapsed,remaining:progress.estimate_status==='overdue'?'예상보다 오래 걸리고 있습니다.':progress.estimate_status==='loading'?'모델 준비 후 예상 시간 표시':progress.estimate_status==='retrying'?'추가 분석 중 · 예상 시간 계산 중':'예상 시간 계산 중'};
}

export function uploadImports(form,onProgress,createXHR=()=>new XMLHttpRequest()){
 return new Promise((resolve,reject)=>{
  const xhr=createXHR();xhr.open('POST','/api/v3/imports');xhr.withCredentials=true;xhr.responseType='json';xhr.setRequestHeader('X-B2-Request','workspace');
  xhr.upload.onprogress=e=>onProgress({stage:'uploading',percent:e.lengthComputable&&e.total>0?Math.min(100,Math.floor(e.loaded/e.total*100)):null});
  xhr.upload.onload=()=>onProgress({stage:'reading',percent:null});
  xhr.onload=()=>{
   const data=xhr.response;
   if(xhr.status<200||xhr.status>=300){reject(Error(typeof data?.detail==='string'?data.detail:'파일을 불러오지 못했습니다. 다시 시도해 주세요.'));return}
   if(!data||!Array.isArray(data.items)||!Array.isArray(data.errors)){reject(Error('서버 응답을 읽지 못했습니다.'));return}
   resolve(data);
  };
  xhr.onerror=()=>reject(Error('파일 전송 중 연결이 끊어졌습니다. 다시 시도해 주세요.'));
  xhr.onabort=()=>reject(Error('파일 전송이 취소되었습니다.'));
  xhr.send(form);
 });
}
