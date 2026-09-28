#!/usr/bin/env node
// Verify the mobile placement sheet in headless Chrome over CDP.
//
//     node tools/verify_mobile_sheet.mjs <component|board|grid|map|fine> [--port 8732]
//
// Requires: python3 -m http.server 8732 -d gamification   (running separately)
//
// Coarse-pointer mode is emulated via Emulation.setTouchEmulationEnabled, which is
// why the template checks matchMedia live instead of caching it at load. (Verified
// empirically against Chrome 150: Emulation.setEmulatedMedia's "features" list does
// NOT support "pointer"/"hover" — only prefers-color-scheme, prefers-reduced-motion,
// forced-colors, etc. Touch emulation is what flips matchMedia(pointer:coarse) true.)
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
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const port = Number(process.argv[process.argv.indexOf("--port") + 1]) || 8732;

const sleep = ms => new Promise(r => setTimeout(r, ms));

const profile = mkdtempSync(join(tmpdir(), "sheetverify-"));
const chrome = spawn(CHROME, [
  "--headless=new", "--remote-debugging-port=9223", `--user-data-dir=${profile}`,
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

async function connect() {
  for (let i = 0; i < 60; i++) {
    try {
      const list = await fetch(`http://127.0.0.1:9223/json/list`).then(r => r.json());
      const page = list.find(t => t.type === "page");
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

const scenario = process.argv[2];
const PAGES = {
  component: "2026 AIGP.html", board: "2026 AIGP.html",
  grid: "Legislation & Regulatory.html", map: "Legislation & Regulatory.html",
  fine: "2026 AIGP.html",
};
if (!PAGES[scenario]) { console.error("unknown scenario"); process.exit(2); }

if (scenario !== "fine") {
  await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
}
await send("Page.navigate", { url: `http://localhost:${port}/${encodeURIComponent(PAGES[scenario])}` });
await sleep(1200);
await evaluate(`
  window.__errs = [];
  window.addEventListener("error", e => window.__errs.push(e.message));
  window.addEventListener("unhandledrejection", e => window.__errs.push("rejection: " + e.reason));
  true;
`);

const checks = { component: checkComponent, board: checkBoard, grid: checkGrid,
                 map: checkMap, fine: checkFine };
let exitCode = 1;
try {
  const result = await checks[scenario]();
  const errs = await evaluate(`window.__errs`);
  const failures = [...result.failures, ...errs, ...consoleErrors];
  console.log(JSON.stringify({ scenario, passed: result.passed, failures }, null, 2));
  exitCode = failures.length ? 1 : 0;
} finally {
  chrome.kill();
}
process.exit(exitCode);

async function checkComponent() {
  return await evaluate(`(async () => {
    const out = { passed: [], failures: [] };
    const ok = (cond, msg) => (cond ? out.passed : out.failures).push(msg);
    ok(matchMedia("(pointer: coarse)").matches, "media emulation active");
    ok(typeof isCoarse === "function" && isCoarse(), "isCoarse() true under emulation");
    let picked = null, closed = false;
    openSheet({ title: 'Place "Test card" in:',
      targets: [{ key: "z1", label: "Zone one", sub: "def one", icon: null },
                { key: "z2", label: "Zone two", sub: "", icon: null }],
      onPick: k => { picked = k; }, onClose: () => { closed = true; } });
    const root = document.querySelector(".sheet-root");
    ok(!!root, "sheet mounts on body");
    ok(root && root.querySelectorAll(".sheet-row").length === 2, "one row per target");
    ok(root && root.querySelector(".sheet-title").textContent.includes("Test card"), "title names the card");
    const row = root && root.querySelector('.sheet-row[data-key="z2"]');
    ok(row && row.getBoundingClientRect().height >= 44, "row is >=44px");
    if (row) row.click();
    ok(picked === "z2", "onPick receives the row key");
    closeSheet();
    ok(!document.querySelector(".sheet-root"), "closeSheet removes the sheet");
    openSheet({ title: "t", targets: [{ key: "a", label: "A", sub: "", icon: null }],
      onPick: () => {}, onClose: () => { closed = true; } });
    document.querySelector(".sheet-backdrop").click();
    ok(closed && !document.querySelector(".sheet-root"), "backdrop dismisses and calls onClose");
    return out;
  })()`);
}
async function checkBoard() {
  return await evaluate(`(async () => {
    const out = { passed: [], failures: [] };
    const ok = (cond, msg) => (cond ? out.passed : out.failures).push(msg);
    const g = GAMES.find(x => x.runner === "board");
    start(g.id);
    ok(document.querySelector(".hint").textContent.trim()
       === "Tap a card, then choose where it belongs.", "touch hint swapped in");
    document.querySelector(".bank [data-tok]").click();
    let root = document.querySelector(".sheet-root");
    ok(!!root, "tapping a bank card opens the sheet");
    ok(root && root.querySelectorAll(".sheet-row").length === state.board.zones.length,
       "one row per zone");
    const z0 = state.board.zones[0];
    if (z0.def) ok(root && root.querySelector(".sheet-row em").textContent.includes(z0.def.slice(0, 20)),
       "zone definition shown in row");
    // Sweep the whole bank: each placement is tap-card -> pick-target, and the
    // sheet must CLOSE after every pick (close-on-place; the auto-advance sweep
    // was reverted after real-phone feedback). The tapped card is always the
    // first bank token, so the current card is derivable without test hooks.
    // Every 3rd card is placed wrong to exercise the miss path.
    const total = state.board.items.length;
    let closedEveryTime = true, titledEveryTime = true;
    for (let n = 0; n < total; n++) {
      if (n > 0) {
        document.querySelector(".bank [data-tok]").click();
        await new Promise(r => setTimeout(r, 30));
      }
      root = document.querySelector(".sheet-root");
      if (!root) { out.failures.push("sheet did not open at card " + n); break; }
      const cur = state.board.items.find(i => !state.placed[i.id]);
      if (!root.querySelector(".sheet-title").textContent.includes(cur.label.slice(0, 30)))
        titledEveryTime = false;
      const wrong = state.board.zones.map(z => z.key).find(k => k !== cur.answer);
      const key = (n % 3 === 0 && wrong) ? wrong : cur.answer;
      root.querySelector('.sheet-row[data-key="' + key + '"]').click();
      await new Promise(r => setTimeout(r, 30));
      if (document.querySelector(".sheet-root")) closedEveryTime = false;
    }
    ok(titledEveryTime, "sheet titled for the tapped card on every open");
    ok(closedEveryTime, "sheet closes after every placement");
    ok(Object.keys(state.placed).length === total, "all cards placed");
    const chk = document.getElementById("check");
    ok(chk && !chk.disabled, "Check enabled");
    chk.click();
    ok(!!document.querySelector(".reveal"), "reveal renders after check");
    // Returning a placed card: replay, place one card, tap it in its zone.
    document.getElementById("retry").click();
    document.querySelector(".bank [data-tok]").click();
    const cur = state.board.items.find(i => !state.placed[i.id]);
    document.querySelector('.sheet-row[data-key="' + cur.answer + '"]').click();
    await new Promise(r => setTimeout(r, 30));
    ok(!document.querySelector(".sheet-root"), "sheet closed itself after the replay pick");
    const placedTok = document.querySelector(".zone [data-tok]");
    placedTok.click();
    ok(Object.keys(state.placed).length === 0, "tapping a placed card returns it to the bank");
    return out;
  })()`);
}
async function checkGrid() {
  return await evaluate(`(async () => {
    const out = { passed: [], failures: [] };
    const ok = (cond, msg) => (cond ? out.passed : out.failures).push(msg);
    const g = GAMES.find(x => x.runner === "grid3x3");
    start(g.id);
    ok(document.querySelector(".hint").textContent.trim()
       === "Tap a card, then choose where it belongs.", "touch hint swapped in");
    document.querySelector(".bank [data-tok]").click();
    let root = document.querySelector(".sheet-root");
    ok(!!root, "tapping a grid card opens the sheet");
    ok(root && root.querySelectorAll(".sheet-row").length === 6, "6 rows (3 domains x 2 sides)");
    // Sweep all 6 with close-on-place: tap card -> pick -> sheet closes. The
    // first card is deliberately placed in a wrong cell so a later correct
    // placement bumps it back to the bank via placeInCell.
    let closedEveryTime = true;
    for (let n = 0; n < 6; n++) {
      if (n > 0) {
        document.querySelector(".bank [data-tok]").click();
        await new Promise(r => setTimeout(r, 30));
      }
      root = document.querySelector(".sheet-root");
      if (!root) { out.failures.push("sheet did not open at card " + n); break; }
      const cur = state.gridItems.find(i => state.gridPlaced[i.id] === undefined);
      const right = cur.domainId + ":" + cur.side;
      const keys = [...root.querySelectorAll(".sheet-row")].map(r => r.dataset.key);
      const key = n === 0 ? keys.find(k => k !== right) : right;
      root.querySelector('.sheet-row[data-key="' + key + '"]').click();
      await new Promise(r => setTimeout(r, 30));
      if (document.querySelector(".sheet-root")) closedEveryTime = false;
    }
    ok(closedEveryTime, "sheet closes after every placement");
    // 6 placements but a guaranteed bump means 7 are needed (card 0 twice +
    // the other 5), so exactly one card is always back in the bank now.
    const bank = document.querySelectorAll(".bank [data-tok]");
    ok(bank.length === 1, "bumped card is back in the bank after 6 placements");
    if (bank.length) {
      bank[0].click();
      await new Promise(r => setTimeout(r, 30));
      root = document.querySelector(".sheet-root");
      ok(!!root, "sheet reopens for the bumped card");
      const occ = root ? [...root.querySelectorAll(".sheet-row em")] : [];
      ok(occ.length > 0, "occupied cells show their occupant in the sheet");
      const cur = state.gridItems.find(i => state.gridPlaced[i.id] === undefined);
      root.querySelector('.sheet-row[data-key="' + cur.domainId + ':' + cur.side + '"]').click();
      await new Promise(r => setTimeout(r, 30));
    }
    ok(!document.querySelector(".sheet-root"), "sheet closed after the final placement");
    const chk = document.getElementById("check");
    ok(chk && !chk.disabled, "Check enabled");
    chk.click();
    ok(!!document.querySelector(".reveal"), "reveal renders after check");
    return out;
  })()`);
}
async function checkMap() {
  return await evaluate(`(async () => {
    const out = { passed: [], failures: [] };
    const ok = (cond, msg) => (cond ? out.passed : out.failures).push(msg);
    const g = GAMES.find(x => x.runner === "map");
    start(g.id);
    ok(document.querySelector(".hint").textContent.trim()
       === "Tap a card, then choose where it belongs.", "touch hint swapped in");
    const js = g.payload().jurisdictions;
    document.querySelector(".bank [data-tok]").click();
    let root = document.querySelector(".sheet-root");
    ok(!!root, "tapping an instrument opens the sheet");
    ok(root && root.querySelectorAll(".sheet-row").length === js.length,
       "one row per jurisdiction (" + js.length + ")");
    const total = state.board.items.length;
    let closedEveryTime = true;
    for (let n = 0; n < total; n++) {
      if (n > 0) {
        document.querySelector(".bank [data-tok]").click();
        await new Promise(r => setTimeout(r, 30));
      }
      root = document.querySelector(".sheet-root");
      if (!root) { out.failures.push("sheet did not open at card " + n); break; }
      const cur = state.board.items.find(i => !state.placed[i.id]);
      root.querySelector('.sheet-row[data-key="' + cur.answer + '"]').click();
      await new Promise(r => setTimeout(r, 30));
      if (document.querySelector(".sheet-root")) closedEveryTime = false;
    }
    ok(closedEveryTime, "sheet closes after every placement");
    ok(Object.keys(state.placed).length === total, "all instruments placed");
    const chk = document.getElementById("check");
    ok(chk && !chk.disabled, "Check enabled");
    chk.click();
    ok(!!document.querySelector(".reveal"), "reveal renders after check");
    return out;
  })()`);
}
async function checkFine() {
  return await evaluate(`(async () => {
    const out = { passed: [], failures: [] };
    const ok = (cond, msg) => (cond ? out.passed : out.failures).push(msg);
    ok(!matchMedia("(pointer: coarse)").matches, "no coarse emulation in this scenario");
    const g = GAMES.find(x => x.runner === "board");
    start(g.id);
    const spec = state.board.spec;
    ok(document.querySelector(".hint").textContent.trim() === spec.hint.trim(),
       "desktop keeps the deck's drag hint");
    const tok = document.querySelector(".bank [data-tok]");
    ok(typeof tok.ondragstart === "function", "ondragstart still wired");
    ok(typeof document.querySelector("[data-zone]").ondrop === "function", "ondrop still wired");
    tok.click();
    ok(!document.querySelector(".sheet-root"), "no sheet mounts on fine pointer");
    ok(state.sel !== null, "click still selects (tap-tap path intact)");
    document.querySelector("[data-zone]").click();
    ok(Object.keys(state.placed).length === 1, "tap-tap place still works");
    return out;
  })()`);
}
