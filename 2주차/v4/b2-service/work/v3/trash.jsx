import React,{useState,useEffect} from 'react';
import {api,Button,Modal,Empty} from './app';

export function TrashPanel({close,onChanged}){
 const[data,setData]=useState(null),[tab,setTab]=useState('meetings'),[confirm,setConfirm]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const load=async()=>setData(await api('/v3/trash'));
 useEffect(()=>{let active=true;api('/v3/trash').then(d=>{if(active)setData(d)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[]);
 async function run(fn){setBusy(true);setError('');setMessage('');try{await fn()}catch(e){setError(e.message)}finally{setBusy(false)}}
 async function restore(item){await api(item.kind==='project'?'/projects/'+item.id+'/restore':'/v3/meetings/'+item.id+'/restore','POST',item.kind==='project'?{version:item.version}:undefined);await load();await onChanged();setMessage('복원했습니다.')}
 async function purge(){await api('/v3/trash/'+confirm.kind+'/'+confirm.id,'DELETE',{version:confirm.version,confirmed:true});setConfirm(null);await load();await onChanged();setMessage('영구 삭제했습니다.')}
 return <Modal title={confirm?'영구 삭제 확인':'휴지통'} close={()=>{if(!busy)close()}} footer={confirm?<><Button disabled={busy} onClick={()=>{setConfirm(null);setError('')}}>취소</Button><Button className="danger-button" disabled={busy||!!confirm.blocked} onClick={()=>run(purge)}>영구 삭제</Button></>:null}>
  {error&&<p className="error-box" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
  {confirm?<><h3>{confirm.title}</h3><p className="muted">{confirm.kind==='project'?confirm.id:confirm.project_name}</p><p>{confirm.kind==='project'?'프로젝트와 그 안의 회의록 '+confirm.counts.meeting+'개':'이 회의록'}, 연결된 변경 기록 {confirm.counts.change_event}개와 해당 원본 파일을 삭제합니다.{confirm.counts.task>0&&` 업무 ${confirm.counts.task}개도 포함됩니다.`}{confirm.counts.report>0&&` 보고서 ${confirm.counts.report}개도 포함됩니다.`}</p><p className="warning">삭제 후에는 복원할 수 없습니다.</p>{confirm.blocked&&<p role="alert">{confirm.blocked}</p>}</>:<><div className="tabs trash-tabs" role="tablist" aria-label="휴지통 종류">{[['meetings','회의록'],['projects','프로젝트']].map(([key,label])=><button role="tab" aria-selected={tab===key} key={key} className={tab===key?'active':''} onClick={()=>{setTab(key);setError('');setMessage('')}}>{label} <small>{data?.[key]?.length??0}</small></button>)}</div>{!data?<p role="status">불러오는 중…</p>:!data[tab].length?<Empty>휴지통이 비어 있습니다.</Empty>:data[tab].map(item=><div className="trash-row" key={item.id}><div><b>{item.title}</b><p className="muted">{item.kind==='meeting'?item.project_name:item.id} · {item.deleted_at.slice(0,10)}</p>{item.blocked&&<small className="muted">{item.blocked}</small>}</div><div className="trash-actions"><Button disabled={busy} onClick={()=>run(()=>restore(item))}>복원</Button><Button disabled={busy||!!item.blocked} onClick={()=>run(async()=>setConfirm(await api('/v3/trash/'+item.kind+'/'+item.id)))}>영구 삭제</Button></div></div>)}</>}
 </Modal>
}
