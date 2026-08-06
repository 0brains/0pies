import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os"; import { join } from "node:path";
const CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const BASE="http://localhost:8748";
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const profile=mkdtempSync(join(tmpdir(),"sp-"));
const chrome=spawn(CHROME,["--remote-debugging-port=0","--headless=new","--no-first-run",`--user-data-dir=${profile}`,"about:blank"],{stdio:"ignore"});
let ws,id=0; const pending=new Map(); const errs=[];
const send=(m,p={})=>new Promise(res=>{const i=++id;pending.set(i,res);ws.send(JSON.stringify({id:i,method:m,params:p}))});
const ev=async e=>{const r=await send("Runtime.evaluate",{expression:e,returnByValue:true});
  if(r?.result?.exceptionDetails) errs.push(r.result.exceptionDetails.exception?.description||"eval threw");
  return r?.result?.result?.value};
try{
 let port; for(let i=0;i<60;i++){try{port=readFileSync(join(profile,"DevToolsActivePort"),"utf8").split("\n")[0].trim(); if(port)break;}catch{} await sleep(250);}
 const list=await(await fetch(`http://localhost:${port}/json/list`)).json();
 ws=new WebSocket(list.find(t=>t.type==="page").webSocketDebuggerUrl);
 await new Promise(r=>ws.addEventListener("open",r));
 ws.addEventListener("message",e=>{const m=JSON.parse(e.data);
  if(m.id&&pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}
  if(m.method==="Runtime.exceptionThrown")errs.push(m.params.exceptionDetails.text)});
 await send("Runtime.enable"); await send("Page.enable");
 let pass=0, fail=0;
 const ok=(name,v)=>{ v?pass++:fail++; if(!v)console.log("FAIL",name); };
 for(const p of ["AI%20Concepts.html","2026%20AIGP.html","2026%20AIF-C01.html","AI-901.html","Legislation%20%26%20Regulatory.html"]){
   await send("Page.navigate",{url:`${BASE}/${p}`}); await sleep(2000);
   await ev(`start(GAMES[0].id)`); await sleep(300);
   ok(`${p} share button in bar`, await ev(`!!document.getElementById("share-game")`));
   await ev(`document.getElementById("share-game").click()`); await sleep(300);
   ok(`${p} modal opens`, await ev(`document.getElementById("share-root").classList.contains("open")`));
   ok(`${p} 3 tones`, await ev(`document.querySelectorAll(".share-tone").length === 3`));
   ok(`${p} preview has game title`, await ev(`document.getElementById("share-preview").textContent.includes(GAMES[0].title)`));
   ok(`${p} preview has deep link`, await ev(`document.getElementById("share-preview").textContent.includes("#g/"+encodeURIComponent(GAMES[0].id))`));
   ok(`${p} 8 networks + copy`, await ev(`document.querySelectorAll("#share-nets a").length === 8 && !!document.getElementById("share-copy")`));
   // switch to "crap" tone, check text changes and chips re-encode
   const before = await ev(`document.getElementById("share-preview").textContent`);
   await ev(`document.querySelector('[data-tone="crap"]').click()`); await sleep(200);
   const after = await ev(`document.getElementById("share-preview").textContent`);
   ok(`${p} tone switches text`, before !== after);
   ok(`${p} X chip carries encoded url`, await ev(`document.querySelector("#share-nets a").href.includes(encodeURIComponent("#g/"))||document.querySelector("#share-nets a").href.includes("url=")`));
   // reroll changes the take
   const r1 = await ev(`document.getElementById("share-preview").textContent`);
   await ev(`document.getElementById("share-reroll").click()`); await sleep(150);
   const r2 = await ev(`document.getElementById("share-preview").textContent`);
   ok(`${p} reroll rerolls`, r1 !== r2);
   // escape closes
   await ev(`document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape"}))`); await sleep(150);
   ok(`${p} escape closes`, await ev(`!document.getElementById("share-root").classList.contains("open")`));
 }
 console.log(`\n${pass} passed, ${fail} failed`);
 console.log(errs.length?`PAGE ERRORS:\n${[...new Set(errs)].join("\n")}`:"no page errors");
 process.exitCode = fail||errs.length?1:0;
}finally{try{ws?.close()}catch{}; chrome.kill()}
