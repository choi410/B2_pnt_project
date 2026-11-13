import React,{useState,useEffect}from'react';
import{Trash2,RotateCcw,ArrowLeft}from'lucide-react';
import{useApp,api,Button,Modal,Empty,dateText}from'./app';

export function ProjectTrashButton({project,onDone,compactMenu=false,onPrompt}){
 const{D,run,busy,setConfirm,setDialog,reload,nav}=useApp();
 if(project.pm!==D.user.id)return null;
 return <Button small className={compactMenu?'project-card-trash':'btn small project-trash-button'} icon={Trash2} disabled={busy} onClick={()=>run(async()=>{
  const info=await api('/projects/'+project.id+'/trash-preview');
  setConfirm({title:'프로젝트를 휴지통으로 이동',text:'‘'+project.name+'’을 휴지통으로 옮길까요?\n회의록 '+info.meetings+'건 · 임시 저장본 '+info.drafts+'건 · 변경 기록 '+info.changes+'건도 함께 숨겨집니다.\n프로젝트 선택 → 프로젝트 휴지통에서 복구할 수 있습니다.',button:'휴지통으로 이동',action:async()=>{
   await api('/projects/'+project.id+'/trash','POST',{version:info.version});onDone?.();setDialog(null);await reload();nav('home',undefined,'');
  }});onPrompt?.();
 })}>{compactMenu?'휴지통으로 이동':'프로젝트 삭제'}</Button>;
}
export function ProjectTrash(){
 const{run,busy,setDialog,setConfirm,reload}=useApp(),[items,setItems]=useState([]),[loading,setLoading]=useState(true),[error,setError]=useState('');
 const load=async()=>setItems(await api('/project-trash'));
 useEffect(()=>{let live=true;api('/project-trash').then(data=>live&&setItems(data)).catch(e=>live&&setError(e.message)).finally(()=>live&&setLoading(false));return()=>{live=false}},[]);
 return <Modal wide title="프로젝트 휴지통" close={()=>setDialog(null)}><Button small icon={ArrowLeft} onClick={()=>setDialog({type:'projects'})}>프로젝트 선택으로</Button><p className="notice">PM으로 관리하는 프로젝트를 복구할 수 있습니다. 연결 기록도 다시 표시되며, 이전에 개별 삭제한 회의록은 휴지통에 남습니다.</p>{loading?<p role="status">불러오는 중…</p>:error?<p className="warning">{error}</p>:items.length?items.map(p=><div className="trash-row" key={p.id}><Trash2 size={20}/><span><b>{p.name}</b><small>{dateText(p.deleted_at)} · {p.id}</small></span><Button small icon={RotateCcw} disabled={busy} onClick={()=>setConfirm({title:'프로젝트 복구',text:'‘'+p.name+'’과 연결 기록을 다시 표시할까요?',button:'복구',action:async()=>{await api('/projects/'+p.id+'/restore','POST',{version:p.version});await load();await reload()}})}>복구</Button></div>):<Empty title="휴지통에 프로젝트가 없습니다"/>}</Modal>;
}

