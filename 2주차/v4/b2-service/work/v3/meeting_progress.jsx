import React,{useEffect,useMemo,useState} from 'react';
import {Check,ChevronRight} from 'lucide-react';
import {meetingProgress} from './meeting_list';
import {duration,timingText} from './progress_time';

function useTick(){const [now,setNow]=useState(()=>performance.now());useEffect(()=>{const timer=setInterval(()=>setNow(performance.now()),1000);return()=>clearInterval(timer)},[]);return now}

function AnalysisTiming({snapshot,queued}){
 const received=useMemo(()=>performance.now(),[snapshot?.measured_at]);
 const now=useTick(),text=timingText(snapshot,Math.max(0,(now-received)/1000),queued);
 return <div className="analysis-timing">{text.elapsed&&<span>{text.elapsed}</span>}<span>{text.remaining}</span></div>
}

export function TransferProgress({transfer}){
 const now=useTick();
 if(!transfer)return null;
 const uploading=transfer.stage==='uploading',label=uploading?'파일 업로드 중':transfer.stage==='saving'?'회의록 저장 중':'파일 내용 확인 중';
 const percent=uploading?transfer.percent:null;
 return <section className="transfer-progress" aria-label="회의록 등록 진행"><div className="meeting-progress-label"><strong>{label}{percent!==null?' · '+percent+'%':''}</strong><span>{duration(Math.max(0,(now-transfer.startedAt)/1000))} 경과</span></div><div className={'meeting-progress-track '+(percent!==null?'determinate':'')} role="progressbar" aria-label={label} aria-valuenow={percent??undefined} aria-valuemin={percent!==null?0:undefined} aria-valuemax={percent!==null?100:undefined} aria-valuetext={percent!==null?percent+'%':label}><span style={percent!==null?{width:percent+'%'}:undefined}/></div><small>{uploading?'파일 전송량 기준입니다.':transfer.stage==='saving'?'저장 후 AI 분석이 시작됩니다.':'전송한 파일의 내용을 읽고 프로젝트를 확인하고 있습니다.'}</small></section>
}

export function BatchProgress({batch}){
 if(!batch||batch.total<2||(!batch.pending&&!batch.failed))return null;
 return <p className="registration-batch" role="status">최근 등록 · 전체 {batch.total}개 중 <b>{batch.completed}개 완료</b>{batch.failed>0&&<span className="warning"> · {batch.failed}개 실패</span>}{batch.removed>0&&<span> · {batch.removed}개 삭제됨</span>}</p>
}

export function MeetingProgress({meeting}){
 const progress=meetingProgress(meeting);
 if(!progress)return null;
 return <div className={'meeting-progress '+progress.stage}>
  <div className="meeting-progress-label"><strong>{progress.label}</strong><span>{progress.detail}</span></div>
  <div className="meeting-progress-track" role="progressbar" aria-label={meeting.title+' 진행 상황'} aria-valuetext={progress.label+' · '+progress.detail}><span/></div>
  <AnalysisTiming snapshot={meeting.progress} queued={progress.stage==='queued'}/>
  <ol className="meeting-progress-steps" aria-label="처리 단계">
   <li className="complete"><Check size={13} aria-hidden="true"/>저장 완료</li>
   <li className={progress.stage==='analyzing'?'current':progress.stage==='applying'?'complete':''}>{progress.stage==='applying'&&<Check size={13} aria-hidden="true"/>}AI 분석</li>
   <li className={progress.stage==='applying'?'current':''}>결과 반영</li>
  </ol>
 </div>
}

export function ProcessingMeetings({meetings,projectName,onOpen}){
 if(!meetings.length)return null;
 return <section className="processing-meetings" aria-label="등록·분석 중인 회의록">
  <div className="section-head"><h2>등록·분석 중 <small>{meetings.length}</small></h2><span>완료되면 아래 목록으로 이동합니다.</span></div>
  <div className="processing-meeting-list">{meetings.map(m=><button key={m.id} className="processing-meeting" onClick={()=>onOpen(m.id)}>
   <div className="processing-meeting-heading"><div><b>{m.title}</b><small>{projectName(m.project_id)}</small></div><ChevronRight size={17} aria-hidden="true"/></div>
   <MeetingProgress meeting={m}/>
  </button>)}</div>
 </section>
}
