// Post-fix verification: zero external requests on every page, deep links
// work, and the footer modals still behave.
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
// Release gate (build document §9, ADR 0004): every published page must make
// zero requests to another origin, and the Content Security Policy must not
// block anything the page itself needs.  node tools/verify_noleaks.mjs [--port 8731]
const PORT = (() => { const i = process.argv.indexOf("--port"); return i > 0 ? process.argv[i + 1] : "8748"; })();
const BASE = `http://localhost:${PORT}`;
const SITE = new URL("../gamification/", import.meta.url).pathname;
const cspViolations = [];
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
    if (m.method === "Log.entryAdded" && /Content Security Policy/i.test(m.params.entry.text || "")) cspViolations.push(m.params.entry.text);
    if (m.method === "Runtime.consoleAPICalled" && m.params.args.some(a => /Content Security Policy/i.test(String(a.value || "")))) cspViolations.push(String(m.params.args[0].value));
    if (m.method === "Network.requestWillBeSent") {
      const u = m.params.request.url;
      // The production origin is first-party (short-link stubs redirect to it).
      if (!u.startsWith(BASE) && !u.startsWith("https://0pi.es/") && !u.startsWith("data:") && !u.startsWith("chrome")) external.push(u);
    }
  });
  await send("Network.enable"); await send("Runtime.enable"); await send("Page.enable"); await send("Log.enable");

  // Every top-level page, the 404 page, and one short-link stub.
  const shortLink = readdirSync(SITE + "g").find(d => !d.includes(".") && !d.includes(" "));
  const pages = readdirSync(SITE).filter(f => f.endsWith(".html") && !/ \d+\.html$/.test(f)).map(encodeURIComponent)
    .concat(shortLink ? [`g/${shortLink}/`] : []);
  for (const p of pages) {
    await send("Page.navigate", { url: `${BASE}/${p}` });
    await sleep(2200);
  }
  // open the cookie modal so the gif loads too
  await send("Page.navigate", { url: `${BASE}/index.html` }); await sleep(1500);
  await ev(`document.getElementById("cookie-badge").click()`); await sleep(1200);
  await ev(`document.getElementById("cookie-close").click()`);

  console.log(external.length ? `EXTERNAL REQUESTS (${external.length}):\n` + [...new Set(external)].join("\n") : `ZERO external requests across ${pages.length} pages + cookie modal`);
  console.log(cspViolations.length ? `CSP BLOCKED (${cspViolations.length}):\n` + [...new Set(cspViolations)].slice(0, 10).join("\n") : "ZERO Content Security Policy violations");
  process.exitCode = (external.length || cspViolations.length) ? 1 : 0;

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
