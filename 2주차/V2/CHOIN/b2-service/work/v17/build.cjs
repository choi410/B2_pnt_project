const esbuild=require('esbuild');const fs=require('fs');const path=require('path');
const folder=__dirname;
esbuild.buildSync({entryPoints:[path.join(folder,'app.jsx')],bundle:true,minify:true,format:'iife',target:['es2020'],outfile:path.join(folder,'app.bundle.js'),define:{'process.env.NODE_ENV':'"production"'}});
const js=fs.readFileSync(path.join(folder,'app.bundle.js'),'utf8').replace(/<\/script/gi,'<\\/script');
const css=fs.readFileSync(path.join(folder,'theme.css'),'utf8');
const html=`<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PNT · 업무 공간 1.8.0</title><style>${css}</style></head><body><div id="root"></div><script>${js}</script></body></html>`;
fs.writeFileSync(path.join(folder,'workspace.html'),html);
console.log('Built v1.8.0 independent React interface');
