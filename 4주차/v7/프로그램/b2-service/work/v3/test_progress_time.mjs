import assert from 'node:assert/strict';
import {duration,timingText,uploadImports} from './progress_time.js';
assert.equal(duration(65),'1분 5초');
assert.equal(duration(-2),'0초');
const snapshot={elapsed_seconds:15,remaining_seconds:[10,30],estimate_status:'available'};
assert.equal(timingText(snapshot,5).elapsed,'20초 경과');
assert.equal(timingText(snapshot,5).remaining,'예상 남은 시간 약 5초~25초');
assert.equal(timingText({...snapshot,remaining_seconds:[0,2]},3).remaining,'예상보다 오래 걸리고 있습니다.');
assert.equal(timingText(snapshot,13).remaining,'진행 상태를 다시 확인 중');
assert.equal(timingText(null).remaining,'예상 시간 계산 중');
assert.equal(timingText({elapsed_seconds:2,estimate_status:'loading'},0).remaining,'모델 준비 후 예상 시간 표시');
assert.equal(timingText(snapshot,0,true).elapsed,'대기 15초 경과');

class XHR{
 upload={};status=200;response={items:[],errors:[]};headers={};
 open(method,url){this.method=method;this.url=url}
 setRequestHeader(k,v){this.headers[k]=v}
 send(form){this.form=form}
}
const xhr=new XHR(),updates=[],promise=uploadImports('form',x=>updates.push(x),()=>xhr);
xhr.upload.onprogress({lengthComputable:true,loaded:25,total:100});
assert.deepEqual(updates.at(-1),{stage:'uploading',percent:25});
xhr.upload.onprogress({lengthComputable:false,loaded:25});
assert.equal(updates.at(-1).percent,null);
xhr.upload.onload();assert.equal(updates.at(-1).stage,'reading');
xhr.onload();assert.deepEqual(await promise,{items:[],errors:[]});
assert.equal(xhr.headers['X-B2-Request'],'workspace');
assert.equal(xhr.withCredentials,true);
const failed=new XHR(),failure=uploadImports('form',()=>{},()=>failed);failed.onerror();
await assert.rejects(failure,/연결이 끊어졌습니다/);
console.log('Elapsed time, honest ETA, upload byte progress and connection-error checks passed');
