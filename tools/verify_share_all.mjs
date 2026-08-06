// Share coverage: index, both vendor hubs, and a lab game — modal, tones,
// context, the mum's-basement disclaimer, and zero external requests.
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os"; import { join } from "node:path";
const CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const BASE="http://localhost:8748";
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const profile=mkdtempSync(join(tmpdir(),"sa-"));
const chrome=spawn(CHROME,["--remote-debugging-port=0","--headless=new","--no-first-run",`--user-data-dir=${profile}`,"about:blank"],{stdio:"ignore"});
let ws,id=0; const pending=new Map(); const errs=[]; const external=[];
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
  if(m.method==="Network.requestWillBeSent"){const u=m.params.request.url;
    if(!u.startsWith(BASE)&&!u.startsWith("data:")&&!u.startsWith("chrome"))external.push(u)}
  if(m.method==="Runtime.exceptionThrown")errs.push(m.params.exceptionDetails.text)});
 await send("Network.enable"); await send("Runtime.enable"); await send("Page.enable");
 let pass=0, fail=0;
 const ok=(n,v)=>{v?pass++:fail++; if(!v)console.log("FAIL",n)};
 const checkModal=async(page,openExpr,ctxWord)=>{
   await send("Page.navigate",{url:`${BASE}/${page}`}); await sleep(2000);
   await ev(openExpr); await sleep(400);
   ok(`${page} modal opens`, await ev(`document.getElementById("share-root")?.classList.contains("open")`));
   ok(`${page} 3 tones`, await ev(`document.querySelectorAll(".share-tone").length===3`));
   ok(`${page} context in preview`, await ev(`document.getElementById("share-preview").textContent.includes(${JSON.stringify(ctxWord)})`));
   ok(`${page} 8 nets + copy`, await ev(`document.querySelectorAll("#share-nets a").length===8 && !!document.getElementById("share-copy")`));
   ok(`${page} basement disclaimer`, await ev(`document.querySelector(".share-note").textContent.includes("mum’s basement")`));
   await ev(`document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape"}))`); await sleep(150);
   ok(`${page} escape closes`, await ev(`!document.getElementById("share-root").classList.contains("open")`));
 };
 await checkModal("index.html", `document.querySelector(".share-open").click()`, "AI governance");
 await checkModal("AWS.html", `document.querySelector(".share-open").click()`, "AWS");
 await checkModal("Microsoft.html", `document.querySelector(".share-open").click()`, "Microsoft");
 await checkModal("AI%20Concepts.html", `start(GAMES[0].id); document.getElementById("share-game").click()`, "");
 console.log(`\n${pass} passed, ${fail} failed`);
 console.log("external requests:", external.length?[...new Set(external)].join(", "):"ZERO");
 console.log(errs.length?"ERRORS: "+[...new Set(errs)].join(" | "):"no page errors");
 process.exitCode = fail||errs.length||external.length?1:0;
}finally{try{ws?.close()}catch{}; chrome.kill()}
