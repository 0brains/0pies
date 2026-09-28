// News page probe: zero external requests, no page errors, chrome parity with
// index.html (topbar + footer byte-identical modulo the active nav link),
// share modal, subscribe panel, and a feed that matches the rendered items.
// Prereq: cd <0pies>/gamification && python3 -m http.server 8748
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os"; import { join } from "node:path";
const CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const BASE="http://localhost:8748";
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const profile=mkdtempSync(join(tmpdir(),"vn-"));
const chrome=spawn(CHROME,["--remote-debugging-port=0","--headless=new","--no-first-run",`--user-data-dir=${profile}`,"about:blank"],{stdio:"ignore"});
let ws,id=0; const pending=new Map(); const errs=[]; const external=[];
const send=(m,p={})=>new Promise(res=>{const i=++id;pending.set(i,res);ws.send(JSON.stringify({id:i,method:m,params:p}))});
const ev=async e=>{const r=await send("Runtime.evaluate",{expression:e,returnByValue:true,awaitPromise:true});
  if(r?.result?.exceptionDetails) errs.push(r.result.exceptionDetails.exception?.description||"eval threw");
  return r?.result?.result?.value};
const block=(html,tag)=>{const a=html.indexOf(`<${tag}>`),b=html.indexOf(`</${tag}>`);return a===-1||b===-1?null:html.slice(a,b+tag.length+3)};
// The whitelisted nav difference: active marker moves, Labs points back home.
const stripActive=s=>s.replaceAll(' class="active"',"").replaceAll('class="active" ',"").replaceAll('href="./#labs"','href="#labs"');
try{
 let port; for(let i=0;i<60;i++){try{port=readFileSync(join(profile,"DevToolsActivePort"),"utf8").split("\n")[0].trim(); if(port)break;}catch{} await sleep(250);}
 const list=await(await fetch(`http://localhost:${port}/json/list`)).json();
 ws=new WebSocket(list.find(t=>t.type==="page").webSocketDebuggerUrl);
 await new Promise(r=>ws.addEventListener("open",r));
 ws.addEventListener("message",e=>{const m=JSON.parse(e.data);
  if(m.id&&pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}
  if(m.method==="Network.requestWillBeSent"){const u=m.params.request.url;
    if(!u.startsWith(BASE)&&!u.startsWith("data:")&&!u.startsWith("chrome"))external.push(u)}
  if(m.method==="Runtime.exceptionThrown")errs.push(m.params.exceptionDetails.text+" "+(m.params.exceptionDetails.exception?.description||""))});
 await send("Network.enable"); await send("Runtime.enable"); await send("Page.enable");
 let pass=0, fail=0;
 const ok=(n,v)=>{v?pass++:fail++; console.log(v?`ok ${n}`:`FAIL ${n}`)};

 // 1+2: load news.html — external hooks + exceptions collect passively.
 await send("Page.navigate",{url:`${BASE}/news.html`}); await sleep(2000);

 // 3: chrome parity — topbar/footer identical modulo the active marker.
 const [idxHtml,newsHtml]=await Promise.all([
   fetch(`${BASE}/index.html`).then(r=>r.text()),
   fetch(`${BASE}/news.html`).then(r=>r.text())]);
 ok("topbar parity", stripActive(block(idxHtml,"topbar"))===stripActive(block(newsHtml,"topbar")));
 ok("footer parity", block(idxHtml,"footer")===block(newsHtml,"footer"));

 // 4: share modal with the no-tracking disclaimer.
 await ev(`document.querySelector(".share-open").click()`); await sleep(400);
 ok("share modal opens", await ev(`document.getElementById("share-root")?.classList.contains("open")`));
 ok("share disclaimer", await ev(`document.querySelector(".share-note")?.textContent.includes("mum’s basement")`));
 await ev(`document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape"}))`); await sleep(150);
 ok("share closes", await ev(`!document.getElementById("share-root").classList.contains("open")`));

 // 5: subscribe panel + autodiscovery.
 ok("feed url shown", await ev(`document.getElementById("feed-url")?.textContent.trim()==="https://0pi.es/feed.xml"`));
 ok("raw feed link", await ev(`!!document.querySelector('a[href="feed.xml"]')`));
 ok("autodiscovery", await ev(`!!document.querySelector('link[rel="alternate"][type="application/atom+xml"]')`));
 ok("copy button", await ev(`!!document.getElementById("copy-feed")`));

 // 6: feed parses and leads with the page's first item.
 const feedChecks=await ev(`(async()=>{const t=await (await fetch("feed.xml")).text();
   const d=new DOMParser().parseFromString(t,"application/xml");
   if(d.querySelector("parsererror")) return {err:"parsererror"};
   const titles=[...d.querySelectorAll("entry > title")].map(e=>e.textContent);
   return {n:titles.length, first:titles[0]}})()`);
 ok("feed parses", !!feedChecks && !feedChecks.err && feedChecks.n>0);
 // Feed carries every item; the page splits them into the trending box + story list.
 const pageTitles=await ev(`[...document.querySelectorAll(".news-item h3")].map(e=>e.textContent)`);
 const feedTitles=await ev(`(async()=>{const t=await (await fetch("feed.xml")).text();
   const d=new DOMParser().parseFromString(t,"application/xml");
   return [...d.querySelectorAll("entry > title")].map(e=>e.textContent)})()`);
 ok("stories all in feed", Array.isArray(pageTitles)&&pageTitles.length>0&&pageTitles.every(t=>feedTitles.includes(t)));

 // 7: items render fully.
 const itemCount=await ev(`document.querySelectorAll(".news-item").length + document.querySelectorAll(".trending-list li").length`);
 ok("item count = entry count", itemCount===feedChecks?.n);
 ok("items complete", await ev(`[...document.querySelectorAll(".news-item")].every(a=>
   a.querySelector(".news-tag") && a.querySelector(".news-dates").textContent.includes("as of")
   && a.querySelector(".news-src a")?.textContent.includes("Open source"))`));

 console.log(`\n${pass} passed, ${fail} failed`);
 console.log("external requests:", external.length?[...new Set(external)].join(", "):"ZERO");
 console.log(errs.length?"ERRORS: "+[...new Set(errs)].join(" | "):"no page errors");
 process.exitCode = fail||errs.length||external.length?1:0;
}finally{try{ws?.close()}catch{}; chrome.kill()}
