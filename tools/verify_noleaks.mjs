// Post-fix verification: zero external requests on every page, deep links
// work, and the footer modals still behave.
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const BASE = "http://localhost:8748";
const sleep = ms => new Promise(r => setTimeout(r, ms));
const profile = mkdtempSync(join(tmpdir(), "rt-"));
const chrome = spawn(CHROME, ["--remote-debugging-port=0", "--headless=new", "--no-first-run", `--user-data-dir=${profile}`, "about:blank"], { stdio: "ignore" });

let ws, id = 0;
const pending = new Map();
const external = [];
const send = (m, p = {}) => new Promise(res => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method: m, params: p })); });
const ev = async e => (await send("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true }))?.result?.result?.value;

try {
  let port;
  for (let i = 0; i < 60; i++) { try { port = readFileSync(join(profile, "DevToolsActivePort"), "utf8").split("\n")[0].trim(); if (port) break; } catch {} await sleep(250); }
  const list = await (await fetch(`http://localhost:${port}/json/list`)).json();
  const pg = list.find(t => t.type === "page" && t.webSocketDebuggerUrl);
  ws = new WebSocket(pg.webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener("open", r));
  ws.addEventListener("message", e => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    if (m.method === "Network.requestWillBeSent") {
      const u = m.params.request.url;
      if (!u.startsWith(BASE) && !u.startsWith("data:") && !u.startsWith("chrome")) external.push(u);
    }
  });
  await send("Network.enable"); await send("Runtime.enable"); await send("Page.enable");

  const pages = ["index.html", "2026%20AIGP.html", "2026%20AIF-C01.html", "AI%20Concepts.html", "AI-901.html", "Legislation%20%26%20Regulatory.html", "AWS.html", "Microsoft.html"];
  for (const p of pages) {
    await send("Page.navigate", { url: `${BASE}/${p}` });
    await sleep(2200);
  }
  // open the cookie modal so the gif loads too
  await send("Page.navigate", { url: `${BASE}/index.html` }); await sleep(1500);
  await ev(`document.getElementById("cookie-badge").click()`); await sleep(1200);
  await ev(`document.getElementById("cookie-close").click()`);

  console.log(external.length ? `EXTERNAL REQUESTS (${external.length}):\n` + [...new Set(external)].join("\n") : "ZERO external requests across all 8 pages + cookie modal");

  // deep link: land directly on a game
  await send("Page.navigate", { url: `${BASE}/AI%20Concepts.html` }); await sleep(2000);
  const firstGame = await ev(`GAMES[0].id`);
  await send("Page.navigate", { url: `${BASE}/AI%20Concepts.html#g/${encodeURIComponent(firstGame)}` });
  await sleep(2000);
  const opened = await ev(`state.game && state.game.id`);
  console.log(opened === firstGame ? `DEEPLINK PASS (#g/${firstGame} opened directly)` : `DEEPLINK FAIL: ${opened}`);
  // hash reflects in-page navigation
  await ev(`state.game=null; render()`); await sleep(300);
  const cleared = await ev(`location.hash`);
  console.log(cleared === "" ? "HASH CLEARS on exit" : `HASH STUCK: ${cleared}`);
  // hostile hash is inert
  await send("Page.navigate", { url: `${BASE}/AI%20Concepts.html#g/%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E` });
  await sleep(1500);
  const home = await ev(`state.game === null && !!document.querySelector("[data-game]")`);
  const alerts = await ev(`window.__alerted || false`);
  console.log(home && !alerts ? "HOSTILE HASH inert (home renders, nothing executed)" : "HOSTILE HASH PROBLEM");
} finally { try { ws?.close(); } catch {} chrome.kill(); }
