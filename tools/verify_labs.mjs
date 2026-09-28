#!/usr/bin/env node
// Drive every game in a lab through a full play cycle in headless Chrome and
// report any error the page throws.
//
//     cd gamification && python3 -m http.server 8731 &
//     node tools/verify_labs.mjs "AI Concepts.html" [--port 8731]
//
// It does NOT start the static server for you — point --port at one you started
// in gamification/. Without it Chrome loads an error page and the sweep fails
// with something unhelpful about LAB being undefined.
//
// Why this exists in this shape:
//
// Exceptions raised inside a click handler never propagate to whatever called
// .click(). A harness that wraps clicks in try/catch therefore reports success
// while the app is throwing on every board — that happened once here and hid 48
// exceptions behind a "0 failures" result. So the only trustworthy signals are
// window.onerror, unhandledrejection, and the console itself, all collected
// out-of-band and read at the end.
//
// Chrome is driven over the DevTools Protocol directly. node has a global
// WebSocket, so this needs no dependencies.

import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const file = process.argv[2];
const port = Number(process.argv[process.argv.indexOf("--port") + 1]) || 8731;
if (!file) { console.error("usage: verify_labs.mjs <lab file name> [--port N]"); process.exit(2); }

const sleep = ms => new Promise(r => setTimeout(r, ms));

const profile = mkdtempSync(join(tmpdir(), "labverify-"));
// Port 0 makes Chrome pick a free port and write it to DevToolsActivePort in the
// profile. A hardcoded 9222 silently attaches to any *other* Chrome already
// holding that port — a stale instance from an earlier run, or the browser you
// happen to be debugging in — and then the sweep drives the wrong browser and
// reports nonsense about a page it never loaded.
const chrome = spawn(CHROME, [
  "--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profile}`,
  "--no-first-run", "--no-default-browser-check", "--disable-gpu",
  "--window-size=1280,2000", "about:blank",
], { stdio: "ignore" });

let ws, msgId = 0;
const pending = new Map();
const consoleErrors = [];

function send(method, params = {}) {
  const id = ++msgId;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((res, rej) => pending.set(id, { res, rej }));
}
async function evaluate(expression) {
  const r = await send("Runtime.evaluate", {
    expression, awaitPromise: true, returnByValue: true,
  });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || "eval threw");
  return r.result.value;
}

async function devtoolsPort() {
  const portFile = join(profile, "DevToolsActivePort");
  for (let i = 0; i < 60; i++) {
    try {
      const port = readFileSync(portFile, "utf8").split("\n")[0].trim();
      if (port) return port;
    } catch {}
    await sleep(250);
  }
  throw new Error("Chrome never wrote DevToolsActivePort");
}

async function connect() {
  const cdpPort = await devtoolsPort();
  for (let i = 0; i < 60; i++) {
    try {
      const list = await fetch(`http://127.0.0.1:${cdpPort}/json/list`).then(r => r.json());
      const page = list.find(t => t.type === "page" && t.webSocketDebuggerUrl);
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(250);
  }
  throw new Error("Chrome did not expose a debugging target");
}

const wsUrl = await connect();
ws = new WebSocket(wsUrl);
await new Promise(r => ws.addEventListener("open", r, { once: true }));
ws.addEventListener("message", ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const { res, rej } = pending.get(m.id);
    pending.delete(m.id);
    m.error ? rej(new Error(m.error.message)) : res(m.result);
  } else if (m.method === "Runtime.exceptionThrown") {
    consoleErrors.push("exception: " + (m.params.exceptionDetails.exception?.description
      || m.params.exceptionDetails.text));
  } else if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") {
    consoleErrors.push("console.error: " + m.params.args.map(a => a.value ?? a.description).join(" "));
  }
});
await send("Runtime.enable");
await send("Page.enable");

const url = `http://localhost:${port}/${encodeURIComponent(file)}`;
await send("Page.navigate", { url });

// Wait for the page's own script to have run rather than guessing at a delay.
// A fixed sleep here used to be enough and silently stopped being enough, which
// surfaces as a baffling "LAB is not defined" from the sweep below rather than
// as a timeout — so poll for the binding the sweep actually needs.
for (let i = 0; ; i++) {
  const ready = await evaluate(`typeof LAB !== "undefined" && typeof render === "function"`);
  if (ready) break;
  if (i >= 60) { console.error(`page never finished loading: ${url}`); process.exit(2); }
  await sleep(250);
}

// Collected out-of-band, because a handler that throws never fails the caller.
await evaluate(`
  window.__errs = [];
  window.addEventListener("error", e => window.__errs.push(e.message));
  window.addEventListener("unhandledrejection", e => window.__errs.push("rejection: " + e.reason));
  true;
`);

// The sweep itself runs in the page: it walks every filter x every game, plays
// each board to a reveal deliberately answering some cards wrong, exercises the
// clear and replay controls, and steps to the next round.
const report = await evaluate(`(async () => {
  const out = { combos: 0, played: 0, games: [], notes: [] };
  const click = sel => { const el = document.querySelector(sel); if (el) { el.click(); return true; } return false; };
  const home = () => { state.game = null; render(); };

  // Sweep every enabled tab, and within each tab only the filters that tab
  // actually offers — iterating every filter regardless of tab would "test"
  // states the UI cannot reach and quietly miss the games on other tabs.
  const tabs = (LAB.tabs || [{ id: "all", enabled: true }]).filter(t => t.enabled !== false);
  for (const tab of tabs) {
    state.domain = tab.id;
    const scoped = (LAB.filters || []).filter(f => !f.tab || f.tab === tab.id);
    const filters = ["all"].concat(scoped.map(f => f.id));
    for (const area of filters) {
    state.area = area; home();
    const cards = [...document.querySelectorAll("[data-game]")].map(b => b.dataset.game);
    for (const id of cards) {
      out.combos++;
      start(id);
      const g = GAMES.find(x => x.id === id);
      try {
        if (g.runner === "board") {
          // Place every token; get roughly a third deliberately wrong so the
          // miss path, the confident-miss sweep and the deep-dive links render.
          const items = state.board.items;
          items.forEach((it, i) => {
            const zones = state.board.zones.map(z => z.key);
            const wrong = zones.find(z => z !== it.answer);
            state.placed[it.id] = (i % 3 === 0 && wrong) ? wrong : it.answer;
          });
          render();
          if (!click("#check")) out.notes.push(id + ": check button missing");
          if (!document.querySelector(".reveal")) out.notes.push(id + ": no reveal after check");
          const cw = document.querySelector("[data-cw]");
          if (cw) cw.click();
          click("#retry");
          click("#next");
        } else if (g.runner === "pairs") {
          const p = g.payload().filter(x => state.area === "all" || (x.area||"").startsWith(state.area))[0];
          state.pairPick = { a: p.buckets[0], b: p.buckets[1] };
          render();
          click("#check");
          if (!document.querySelector(".reveal")) out.notes.push(id + ": no reveal after check");
          click("#retry"); click("#next");
        } else if (g.runner === "grid3x3") {
          for (let round = 0; round < 3; round++) {
            const items = state.gridItems;
            // Each cell holds exactly one item, so "deliberately wrong"
            // placements must stay a bijection onto the 6 cells (unlike the
            // board runner's zones, which can hold many items each). Swap
            // adjacent pairs of target keys instead of redirecting several
            // items at the same single cell, which would just bump one
            // permanently back to the bank and block #check forever.
            const targets = items.map(it => it.domainId + ":" + it.side);
            for (let i = 0; i + 1 < targets.length; i += 3) {
              const tmp = targets[i]; targets[i] = targets[i + 1]; targets[i + 1] = tmp;
            }
            items.forEach((it, i) => {
              const tokBtn = document.querySelector('[data-tok="' + it.id + '"]');
              if (tokBtn) tokBtn.click();
              // Re-query: the token click re-renders the DOM, so any element
              // reference captured before it is now detached.
              const cellEl = document.querySelector('[data-cell="' + targets[i] + '"]');
              if (cellEl) cellEl.click();
            });
            if (!click("#check")) out.notes.push(id + ": check button missing (round " + (round + 1) + ")");
            if (!document.querySelector(".reveal")) out.notes.push(id + ": no reveal after check (round " + (round + 1) + ")");
            click("#next");
          }
          if (state.game) out.notes.push(id + ": did not return home after finishing round 3");
        } else if (g.runner === "ladders") {
          click("[data-l]");
          let guard = 0;
          while (document.querySelector("[data-step]") && guard++ < 40) {
            document.querySelector("[data-step]").click();
          }
          if (!document.querySelector(".reveal")) out.notes.push(id + ": ladder never completed");
          click("#reset"); click("#pick");
        } else if (g.runner === "desk") {
          const c = g.payload()[0];
          c.steps.forEach(s => state.deskPick[s.id] = s.options[0]);
          render(); click("#check"); click("#retry"); click("#next");
        } else if (g.runner === "map") {
          state.board.items.forEach(i => state.placed[i.id] = i.answer);
          render(); click("#check"); click("#retry"); click("#next");
        } else if (g.runner === "briefs") {
          const b = g.payload()[0];
          state.brief = b; render();
          b.fields.forEach(f => {
            const el = document.getElementById("f-" + f.key);
            if (el) { el.value = "Test response for verification purposes only."; el.dispatchEvent(new Event("input")); }
          });
          click("#reveal");
        }
        out.played++;
      } catch (e) {
        out.notes.push(id + " [" + area + "]: threw " + e.message);
      }
      home();
    }
    out.games.push({ tab: tab.id, area, count: cards.length });
    }
  }
  return out;
})()`);

// Horizontal overflow at the narrowest supported width.
await send("Emulation.setDeviceMetricsOverride",
  { width: 430, height: 900, deviceScaleFactor: 1, mobile: true });
await sleep(400);
const overflow = await evaluate(`(() => {
  state.area = "all"; state.game = null; render();
  const w = document.documentElement.scrollWidth, c = document.documentElement.clientWidth;
  const wide = [...document.querySelectorAll("body *")]
    .filter(el => el.scrollWidth > el.clientWidth + 2 && getComputedStyle(el).overflowX === "visible")
    .slice(0, 5).map(el => el.className || el.tagName);
  return { scrollWidth: w, clientWidth: c, overflows: w > c + 1, wide };
})()`);

const pageErrors = await evaluate("window.__errs");

console.log(`\n${file}`);
console.log(`  ${report.combos} game x filter combinations, ${report.played} played through`);
for (const g of report.games) console.log(`    tab ${g.tab} / filter "${g.area}": ${g.count} games offered`);
console.log(`  page errors:    ${pageErrors.length}`);
console.log(`  console errors: ${consoleErrors.length}`);
console.log(`  430px overflow: ${overflow.overflows ? "YES — " + overflow.scrollWidth + "px in " + overflow.clientWidth : "none"}`);
if (overflow.wide.length) console.log(`    wide elements: ${overflow.wide.join(", ")}`);
for (const n of report.notes) console.log(`  ! ${n}`);
for (const e of pageErrors) console.log(`  ✗ ${e}`);
for (const e of consoleErrors) console.log(`  ✗ ${e}`);

const failed = pageErrors.length + consoleErrors.length + report.notes.length
  + (overflow.overflows ? 1 : 0);
console.log(failed ? `\nFAIL — ${failed} problem(s)` : `\nPASS`);

ws.close();
chrome.kill();
process.exit(failed ? 1 : 0);
