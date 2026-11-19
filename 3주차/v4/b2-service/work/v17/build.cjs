const esbuild=require('esbuild');const fs=require('fs');const path=require('path');
const folder=__dirname;
const output=process.env.B2_BUILD_DIR||folder;fs.mkdirSync(output,{recursive:true});
esbuild.buildSync({entryPoints:[path.join(folder,'app.jsx')],bundle:true,minify:true,format:'iife',target:['es2020'],outfile:path.join(output,'app.bundle.js'),define:{'process.env.NODE_ENV':'"production"'}});
const js=fs.readFileSync(path.join(output,'app.bundle.js'),'utf8').replace(/<\/script/gi,'<\\/script');
const css=['theme.css','design-v18.css','design-v181.css','design-v182.css','design-v19.css','reports.css','dashboard.css','design-v2.css','reports-layout.css','demo.css','home-calendar.css','project-home-reference.css'].map(file=>fs.readFileSync(path.join(folder,file),'utf8')).join('\n');
const html=`<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PNT 회의록 서비스</title><style>${css}</style></head><body><div id="root"></div><script>${js}</script></body></html>`;
fs.writeFileSync(path.join(output,'workspace.html'),html);
console.log('Built v2.0 independent React interface');
