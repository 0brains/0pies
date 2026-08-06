// Verify the index-page footer: run a static server in gamification/ first
//
//     cd gamification && python3 -m http.server 8748 &
//     node tools/verify_footer.mjs
//
// Verify the index footer: Terms modal opens/closes, Privacy still works, and
// the GitHub/Reddit links point where they should. Errors are collected
// out-of-band (see verify_labs.mjs) because exceptions inside a click handler
// never reach .click().
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 8747;
const URL_ = "http://localhost:8748/index.html";
const sleep = ms => new Promise(r => setTimeout(r, ms));

const profile = mkdtempSync(join(tmpdir(), "vf-"));
const chrome = spawn(CHROME, [
  `--remote-debugging-port=${PORT}`, "--headless=new", "--no-first-run",
  `--user-data-dir=${profile}`, "about:blank",
], { stdio: "ignore" });

let ws, id = 0;
const pending = new Map();
const errors = [];
const send = (method, params = {}) => new Promise(res => {
  const msgId = ++id;
  pending.set(msgId, res);
  ws.send(JSON.stringify({ id: msgId, method, params }));
});
const evalJs = async expr => {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  return r?.result?.result?.value;
};

try {
  for (let i = 0; i < 40; i++) {
    try { await fetch(`http://localhost:${PORT}/json/version`); break; } catch { await sleep(250); }
  }
  const targets = await (await fetch(`http://localhost:${PORT}/json/list`)).json();
  const page = targets.find(t => t.type === "page" && t.webSocketDebuggerUrl);
  if (!page) { console.error("no page target:", targets.map(t => t.type)); process.exit(2); }
  ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(r => ws.addEventListener("open", r));
  ws.addEventListener("message", e => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    if (m.method === "Runtime.exceptionThrown") errors.push(JSON.stringify(m.params.exceptionDetails?.text));
    if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error")
      errors.push(m.params.args.map(a => a.value).join(" "));
  });
  await send("Runtime.enable");
  await send("Page.enable");
  await send("Page.navigate", { url: URL_ });
  await sleep(2500);
  console.log("loaded:", await evalJs(`location.href`), "|", await evalJs(`document.title`));

  const checks = {};
  checks.termsClosedInitially = await evalJs(`!document.getElementById("terms-overlay").classList.contains("open")`);
  await evalJs(`document.getElementById("terms-link").click()`);
  await sleep(300);
  checks.termsOpensOnClick = await evalJs(`document.getElementById("terms-overlay").classList.contains("open")`);
  checks.termsMentionsLicence = await evalJs(`/PolyForm Noncommercial/.test(document.getElementById("terms-overlay").innerText)`);
  checks.termsMentionsNoResale = await evalJs(`/don't sell it/i.test(document.getElementById("terms-overlay").innerText)`);
  await evalJs(`document.getElementById("terms-close").click()`);
  await sleep(300);
  checks.termsClosesOnX = await evalJs(`!document.getElementById("terms-overlay").classList.contains("open")`);

  await evalJs(`document.getElementById("privacy-link").click()`);
  await sleep(300);
  checks.privacyStillOpens = await evalJs(`document.getElementById("cookie-overlay").classList.contains("open")`);
  await evalJs(`document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape"}))`);
  await sleep(300);
  checks.escapeClosesPrivacy = await evalJs(`!document.getElementById("cookie-overlay").classList.contains("open")`);

  checks.githubLinkCorrect = await evalJs(`!!document.querySelector('a[href="https://github.com/0brains/0pies"]')`);
  checks.redditLinkCorrect = await evalJs(`!!document.querySelector('a[href="https://www.reddit.com/r/0pi/"]')`);
  checks.iconsRendered = await evalJs(`document.querySelectorAll('.footer-nav svg').length >= 3`);

  let pass = 0, fail = 0;
  for (const [k, v] of Object.entries(checks)) { v ? pass++ : fail++; console.log(`${v ? "PASS" : "FAIL"}  ${k}`); }
  console.log(`\n${pass} passed, ${fail} failed`);
  console.log(errors.length ? `PAGE ERRORS:\n${errors.join("\n")}` : "no page errors");
  process.exitCode = fail || errors.length ? 1 : 0;
} finally {
  try { ws?.close(); } catch {}
  chrome.kill();
}
