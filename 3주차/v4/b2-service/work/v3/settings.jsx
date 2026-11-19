import React,{useState,useLayoutEffect,useEffect,useRef} from 'react';
import {Settings,Sun,Moon,X} from 'lucide-react';

const STORAGE_KEY='pnt-v3-display-preferences';
function loadPreferences(){
 try{const p=JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}');return {theme:p?.theme==='light'?'light':'dark',size:['small','normal','large'].includes(p?.size)?p.size:'normal'}}catch{return {theme:'dark',size:'normal'}}
}
export function DisplaySettings(){
 const[prefs,setPrefs]=useState(loadPreferences),[open,setOpen]=useState(false);
 const box=useRef(),trigger=useRef();
 useLayoutEffect(()=>{document.documentElement.dataset.theme=prefs.theme;document.documentElement.dataset.textSize=prefs.size;try{localStorage.setItem(STORAGE_KEY,JSON.stringify(prefs))}catch{}},[prefs]);
 useEffect(()=>{if(!open)return;const outside=e=>{if(!box.current?.contains(e.target))setOpen(false)};const escape=e=>{if(e.key==='Escape'){setOpen(false);trigger.current?.focus()}};document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape)}},[open]);
 return <div className="display-settings" ref={box}><button ref={trigger} className="icon-button settings-trigger" aria-label="화면 설정" title="화면 설정" aria-expanded={open} aria-controls="display-settings-panel" onClick={()=>setOpen(v=>!v)}><Settings size={21}/></button>{open&&<section id="display-settings-panel" role="dialog" aria-label="화면 설정" className="settings-panel"><div className="section-head"><h2>화면 설정</h2><button className="icon-button" aria-label="설정 닫기" onClick={()=>{setOpen(false);trigger.current?.focus()}}><X size={17}/></button></div><fieldset><legend>테마</legend><div className="setting-options">{[['light','밝게',Sun],['dark','어둡게',Moon]].map(([value,label,Icon])=><button key={value} type="button" aria-pressed={prefs.theme===value} onClick={()=>setPrefs(p=>({...p,theme:value}))}><Icon size={17}/>{label}</button>)}</div></fieldset><fieldset><legend>글자 크기</legend><div className="setting-options">{[['small','작게'],['normal','기본'],['large','크게']].map(([value,label])=><button key={value} type="button" aria-pressed={prefs.size===value} onClick={()=>setPrefs(p=>({...p,size:value}))}>{label}</button>)}</div></fieldset><p className="settings-note">이 브라우저에 설정이 저장됩니다.</p></section>}</div>
}
