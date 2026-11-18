const esbuild=require('esbuild'),fs=require('fs'),path=require('path');
const dir=__dirname;
esbuild.buildSync({entryPoints:[path.join(dir,'app.jsx')],bundle:true,minify:true,format:'iife',target:['es2020'],loader:{'.png':'dataurl'},outfile:path.join(dir,'app.bundle.js'),define:{'process.env.NODE_ENV':'"production"'}});
const js=fs.readFileSync(path.join(dir,'app.bundle.js'),'utf8').replace(/<\/script/gi,'<\\/script');
const css=fs.readFileSync(path.join(dir,'style.css'),'utf8');
fs.writeFileSync(path.join(dir,'workspace.html'),`<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark light"><title>PNT 회의록 서비스</title><script>try{var p=JSON.parse(localStorage.getItem('pnt-v3-display-preferences')||'{}');document.documentElement.dataset.theme=p&&p.theme==='light'?'light':'dark';document.documentElement.dataset.textSize=p&&['small','normal','large'].includes(p.size)?p.size:'normal'}catch(e){}</script><style>${css}</style></head><body><div id="root"></div><script>${js}</script></body></html>`);
console.log('Built connected B2 interface');
