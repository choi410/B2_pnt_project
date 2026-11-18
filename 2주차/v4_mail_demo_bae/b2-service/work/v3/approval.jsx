// Customer approval mail: PM send dialog, state shown beside a meeting, and the customer page.
import React,{useState,useEffect} from 'react';
import {Mail,Check,AlertCircle} from 'lucide-react';
import {api,Button,Modal} from './app';
import logo from './assets/pnt-logo.png';

const labels={sent:'고객 승인 대기',approved:'고객 승인',rejected:'고객 반려',expired:'승인 링크 만료',canceled:'요청 취소'};
const when=s=>s?s.slice(0,16).replace('T',' '):'';
// The mail link is /#/approval/<token>; it opens without the workspace or a login.
export const approvalToken=()=>{const m=window.location.hash.match(/^#\/approval\/([\w-]+)$/);return m?m[1]:''};

export function ApprovalBadge({approval}){
 if(!approval||!labels[approval.status])return null;
 return <span className={'status approval-'+approval.status}>{labels[approval.status]}</span>;
}

export function ApprovalLine({approval}){
 if(!approval||!labels[approval.status])return null;
 return <p className="approval-line"><ApprovalBadge approval={approval}/><span>{approval.email} · {when(approval.sent_at)} 발송{approval.responded_at?' · '+when(approval.responded_at)+' 응답':''}{approval.outdated?' · 이전 본문 기준':''}</span>{approval.comment&&<span className="approval-comment">고객 의견: {approval.comment}</span>}</p>;
}

export function SendApprovalDialog({meeting,approval,close,onSent}){
 const[form,setForm]=useState({email:approval?.email||'',name:'',message:''}),[history,setHistory]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[sent,setSent]=useState(null);
 useEffect(()=>{api('/v3/meetings/'+meeting.id+'/approval-requests').then(setHistory).catch(()=>setHistory([]))},[meeting.id]);
 const waiting=history.some(h=>h.status==='sent');
 async function submit(){
  setBusy(true);setError('');
  try{const result=await api('/v3/meetings/'+meeting.id+'/approval-requests','POST',form);setSent(result);onSent(result)}
  catch(e){setError(e.message)}
  finally{setBusy(false)}
 }
 if(sent)return <Modal title="승인 요청을 보냈습니다" close={close} footer={<Button primary onClick={close}>닫기</Button>}>
  {sent.mode==='smtp'?<p>{sent.email} 주소로 승인 요청 메일을 보냈습니다.</p>:<><p>테스트 모드(MAIL_MODE=console)라 메일은 보내지 않고 서버 실행 창에 내용을 출력했습니다.</p><p className="approval-link">승인 링크: <a href={sent.link} target="_blank" rel="noreferrer">{sent.link}</a></p></>}
  <p className="muted">링크는 {when(sent.expires_at)}까지 한 번만 사용할 수 있습니다.</p>
 </Modal>;
 return <Modal title="고객 승인 메일 보내기" close={()=>{if(!busy)close()}} footer={<><Button onClick={close} disabled={busy}>취소</Button><Button primary icon={Mail} disabled={busy||!form.email.trim()} onClick={submit}>{busy?'보내는 중…':'메일 보내기'}</Button></>}>
  <h3>{meeting.title}</h3>
  <label>받는 사람 이메일<input autoFocus type="email" placeholder="customer@example.com" value={form.email} onChange={e=>setForm({...form,email:e.target.value})}/></label>
  <label>받는 사람 이름 (선택)<input maxLength={50} placeholder="예: 홍길동 책임" value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label>
  <label>전달 메시지 (선택)<textarea maxLength={1000} rows={3} placeholder="예: 11/12 회의 내용입니다. 확인 후 승인 부탁드립니다." value={form.message} onChange={e=>setForm({...form,message:e.target.value})}/></label>
  <p className="muted">고객은 메일의 링크에서 지금 본문을 확인하고 승인 또는 반려합니다.</p>
  {waiting&&<p className="error-box">응답을 기다리는 요청이 있습니다. 다시 보내면 이전 메일의 링크는 쓸 수 없게 됩니다.</p>}
  {error&&<p role="alert" className="error-box">{error}</p>}
  {history.length>0&&<div className="approval-history"><h4>이전 요청</h4>{history.map(h=><p key={h.id}><ApprovalBadge approval={h}/><span>{h.email} · {when(h.sent_at)}</span>{h.comment&&<small>고객 의견: {h.comment}</small>}</p>)}</div>}
 </Modal>;
}

const closedText={expired:'링크의 유효 기간이 지났습니다. 담당자에게 다시 요청해 주세요.',canceled:'더 이상 사용할 수 없는 링크입니다. 새로 받은 메일의 링크를 사용해 주세요.'};

export function ApprovalPage({token}){
 const[view,setView]=useState(null),[loadError,setLoadError]=useState(''),[comment,setComment]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const load=()=>api('/v3/approvals/'+token).then(setView).catch(e=>setLoadError(e.message));
 useEffect(()=>{load()},[token]);
 async function respond(decision){
  if(decision==='rejected'&&!comment.trim()&&!window.confirm('의견 없이 반려할까요? 반려 사유를 적어 주시면 담당자가 확인하기 쉽습니다.'))return;
  setBusy(true);setError('');
  try{await api('/v3/approvals/'+token,'POST',{decision,comment})}
  catch(e){setError(e.message)}
  // Reload either way: another click or an expiry may already have settled it.
  finally{await load();setBusy(false)}
 }
 const head=<span className="brand"><img src={logo} alt="PNT"/></span>;
 if(loadError)return <div className="approval-page"><section className="approval-card">{head}<h1>회의록 승인 요청</h1><p role="alert" className="error-box">{loadError}</p></section></div>;
 if(!view)return <div className="approval-page"><section className="approval-card">{head}<p className="muted">불러오는 중…</p></section></div>;
 const done=view.status==='approved'||view.status==='rejected';
 return <div className="approval-page">
  <section className="approval-card">{head}<h1>회의록 승인 요청</h1>
   <dl><dt>프로젝트</dt><dd>{view.project_name}</dd><dt>회의록</dt><dd>{view.title}{view.date?' ('+view.date+')':''}</dd>{view.requested_by_name&&<><dt>요청자</dt><dd>{view.requested_by_name} · {when(view.sent_at)}</dd></>}</dl>
   {view.message&&<p className="approval-message">{view.message}</p>}
   {closedText[view.status]&&<p className="error-box">{closedText[view.status]}</p>}
   {done&&<div className={'approval-result '+view.status}>{view.status==='approved'?<Check size={18}/>:<AlertCircle size={18}/>}<div><b>{view.status==='approved'?'승인 처리되었습니다.':'반려 처리되었습니다.'}</b> <small>{when(view.responded_at)}</small>{view.comment&&<p>남기신 의견: {view.comment}</p>}<p className="muted">이 창은 닫으셔도 됩니다.</p></div></div>}
   {view.status==='sent'&&<div className="approval-form"><p className="muted">아래 회의록 내용을 확인한 뒤 승인 또는 반려를 선택해 주세요. {when(view.expires_at)}까지 한 번만 처리할 수 있습니다.</p><label>의견 (선택, 반려 시 사유를 적어 주세요)<textarea rows={3} maxLength={1000} value={comment} onChange={e=>setComment(e.target.value)}/></label>{error&&<p role="alert" className="error-box">{error}</p>}<div className="actions"><Button primary disabled={busy} onClick={()=>respond('approved')}>승인</Button><Button className="reject" disabled={busy} onClick={()=>respond('rejected')}>반려</Button></div></div>}
  </section>
  {view.lines&&<article className="paper source-lines">{view.lines.map((text,i)=><p key={i}>{text}</p>)}</article>}
 </div>;
}
