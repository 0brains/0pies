# Regulatory Risk — adversarial playtest log

Plan Task 14 Step 4. One iteration per wave: probe findings → controller adjudication →
fixes applied to `tools/templates/lab.html` (engine/CSS) and
`data/aigp/knowledge/domain-ii.json` (label nudges only) → rebuild → re-probe.

## Iteration 1 — 2026-08-03 (5 agents, 46 probes, 9 findings)

### Probe table

| Probe | Agent | Result | Evidence (one line) |
|---|---|---|---|
| full-win-campaign | core-loop | PASS | 15-turn all-correct run: debrief arithmetic `32 market + 6 capital − 0 − 2×0 = 38, A+` matches hand-recompute; all 46 submits recorded on `ii-rr-*` ids only |
| deliberate-bust | core-loop | PASS | All-wrong play busts end of turn 3 at capital 0; reload lands on debrief; replay CTA clears `rr-campaign-v1`, bumps `rr-meta-v1` campaignCount |
| mid-gate-reload-resume | core-loop | PASS | Reload mid-gate on map-uk/us/eu: pending `{cardIds,qIndex,correctSoFar}` byte-identical, resumes at exactly cardIds[qIndex], no re-roll |
| debrief-arithmetic-fuzz | core-loop | PASS | 3 injected end-states match ADD §1.6 hand-computes (suspended-EU excluded, bust forced, A+ boundary inclusive); only cosmetic `+ -1` double sign (finding 5) |
| withdraw-exploit | exploits | PASS | Free withdraw only at intro; post-stem withdraw = fail with capital/notice/turn consequences; consolidate withdraw still spends the slot — no farming |
| consolidate-farm | exploits | PASS | rrConsLimit = min(2, pool) enforced at commit; counter increments at stem-commit so withdrawn consolidates spend the slot |
| one-action-per-turn | exploits | FAIL | UI buttons disable, but forced `state.rr.action` + `render()` resolved 3 fully-scored actions in turn 1 — no mutation-layer guard (finding 2) |
| state-corruption | exploits | FAIL | Garbage/scalar/v:99 discard cleanly, but v:1 with pending:7 or `{action:'expand'}` crash-loops board↔action to stack overflow (finding 3); turn:-5 / capital:1e15 accepted verbatim (finding 6) |
| capital-overflow | exploits | PASS | Every reward path clamps at capitalCap 8; injected capital 100 clamps down on next consolidate pass |
| notice-L3-suspension | regulator | PASS | L1→L2 at age 2, L2→L3 at age 4 with −2 capital, sanction, suspended flag, hatch, market excluded from score, `SUSPENDED (L3)` in print |
| role-shift-path | regulator | PASS | ev-05 deployer→provider at t5; defends re-draw for new role; no re-fire after roleShiftMax; reshuffle never re-fires fired shifts |
| event-weight-sanity | regulator | PASS | 700 draws: zero violations — audits only on held/noticed, hat gating honoured, no roleShift before t5 or to current role; weight-5 drew ~6× weight-1 |
| event-without-replacement | regulator | PASS | 20 full campaigns: zero duplicate event ids pre-reshuffle; exhaustion reshuffles deckDrawn minus fired role-shifts without crash |
| scheduler-id-audit | regulator | PASS | 254 DOM-driven steps: 64 submits = 64 record() calls, all keys `ii-rr-*`, none `-map`, only the 3 expected localStorage keys |
| layouts-horizontal-scroll | ui | PASS | hscroll 0 and zero out-of-viewport elements across 7 screens × 375/1800 × light/dark × media/attr; data-theme attr beats opposite media query |
| layouts-44px-touch-targets | ui | FAIL | `.rr-hit` map targets 44×44, but house-kit `.btn` 42–43px and debrief ai-links 38×38 on every screen (finding 9) |
| screenshots-board | ui | PASS | Board captured 375/1800 light/dark; CoE ring + SG dot legible; EU/COE/CH label pile-up at 1800 filed as finding 8 |
| greyscale-channel | ui | PASS | Held/open/notice distinguishable with hue removed: luminance deltas 22.9–76.1, plus stroke-width and glyph channels |
| interstitial-order | ui | PASS | 5 consecutive regulator phases: `.rr-aging` DOM-precedes `.rr-event` every time |
| print-report | ui | PASS | All 5 §2.7 sections present, single page at 96dpi, screen panel hidden under print emulation, storage untouched |
| accessibility-quick | ui | PASS | All six coverage letters render as badges in both themes; 22 rows carry letter badges (dark T chip ~3.5:1 at 12px, observation only) |
| card ii-rr-any-n03 | content | PASS | Art. 25(1)(c) purpose-change role shift accurate |
| card ii-rr-tx-d02 | content | PASS | TRAIGA gov-only bans + intent-based private rules match FACTS |
| card ii-rr-cn-c02 | content | PASS | CSL amendment dates + no-unified-statute match corrected FACTS |
| card ii-rr-ae-s01 | content | PASS | DIFC Reg 10 full enforcement 2026-01-01; June 2026 body is a regulator, not a statute |
| card ii-rr-co-s02 | content | PASS | SB 26-189 signed 2026-05-14, narrower ADMT regime eff. 2027-01-01 |
| card ii-rr-eu-k01 | content | PASS | Art. 57 sandbox deadline 2026-08-02 unchanged by Omnibus; 2026/1744 citation matches |
| card ii-rr-nyc-n02 | content | PASS | LL144 independent-auditor + one-year currency; vendor self-review fails both |
| card ii-rr-ke-s01 | content | PASS | Kenya bill first reading 2026-04-02, at ICT committee |
| card ii-rr-co-c02 | content | PASS | CAIA machinery dropped, disclosure kept — consistent with FACTS |
| card ii-rr-usca-d02 | content | PASS | B.O.T. Act vs SB 942 provenance correctly distinguished |
| card ii-rr-il-c01 | content | PASS | Subpart J withdrawn 2026-06-02; HB 3773 binds without final regs |
| card ii-rr-any-k01 | content | PASS | ISO 42001 certifiable AIMS; 42005/RMF non-certifiable — uniquely best |
| card ii-rr-uk-s02 | content | PASS | DUAA s.80/Sch.6 in force 2026-02-05, permission-with-safeguards default |
| card ii-rr-us-s04 | content | PASS | NIST RMF voluntary, no certification scheme |
| card ii-rr-in-c02 | content | PASS | Private member's bill 17 Dec 2025, not enacted |
| card ii-rr-in-s01 | content | PASS | MeitY Guidelines non-binding; binding layer is DPDP/IT Rules |
| card ii-rr-in-c01 | content | PASS | India regime layering matches corrected FACTS |
| card ii-rr-tw-s01 | content | PASS | Taiwan AI Basic Act promulgated + effective 2026-01-14 |
| card ii-rr-eu-p05 | content | PASS | Art. 55(1)(c) GPAI incident duty live; Art. 73 deferred with Annex III |
| card ii-rr-au-c01 | content | PASS | DTA 2026-12-15 full-compliance date; Privacy Act ADM date separated |
| event ii-rr-ev-09 | content | PASS | Colorado goalposts (SB 24-205 never effective → SB 26-189) accurate |
| event ii-rr-ev-33 | content | PASS | Kenya committee status accurate |
| event ii-rr-ev-35 | content | PASS | Swiss consultation timeline accurate |
| event ii-rr-ev-36 | content | PASS | Digital Omnibus deadlines + binding-today list accurate |
| event ii-rr-ev-37 | content | PASS | EU CoE accession effective 2026-09-01, treaty-binds-states framing |

**Content spot-check summary:** 20 cards + 5 info events sampled (seed 20260803), **25/25 clean** —
every checked card matches the corrected FACTS layer, answers uniquely best, distractors accurately wrong.

### Findings and dispositions

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | major | Empty role-filtered gate pool: begin silently no-ops, locking 7 role/territory combos out of expansion (importer: KR/CN/TX/NYC/CA; deployer: CN; provider: NYC) | **fixed** — `rrDrawGate` falls back to the territory's full gate pool when the role pool is empty, and tops a short role pool up from the unfiltered remainder before the ADD §3.3 due/LRU fallback; empty draw now renders the bad-state "No gate available…" screen instead of a silent bounce |
| 2 | major | One-action-per-turn enforced only in board button rendering — forced screen state allows unlimited scored actions per turn | **fixed** — `acted` re-derived from the log at the mutation layer (rrRenderAction stage 1 AND the `#rr-begin` handler, before `camp.pending` is set) → "Action already taken this turn" bad-state; audits/checks stay exempt (guard keyed to expand/defend/consolidate only) |
| 3 | major | v:1 campaign with invalid pending crash-loops (board↔action stack overflow), bricking the game until localStorage is hand-cleared | **fixed** — `rrValidCampaign()` on load validates shape (log Array, held plain object, pending null or `{action:string, cardIds:Array, qIndex:number}`), discarding failures to the stale-note fresh start; belt-and-braces: rrRenderBoard drops an unresolvable pending + rrSave() instead of redirecting |
| 4 | major | Debrief/print hard-crash (TypeError in rrFactText) when a saved answer's card id no longer resolves | **fixed** — `rrFactText` hardened to `String(card.fact \|\| card.id \|\| card.q \|\| "?")`; all answer-review fallback objects now carry the original id |
| 5 | minor | Debrief renders `+ -1 capital` (double sign) on negative capital | **fixed** — formatted as `− N capital` in both rrRenderDebrief and the print report arithmetic |
| 6 | minor | No numeric sanitation on load: negative turns render, injected capital mints an instant A+ | **fixed** — load-time clamp: turn to [1, turns+1], capital above capitalCap clamped to cap, \|capital\| > 99 rejected as corrupt (stale path); legitimate negative capital (bust) left intact |
| 7 | minor | Consolidate button stays enabled at limit, opening a dead-end screen | **fixed** — button disabled + relabelled "Consolidated ✓" in board rows and the US inset rows when `consolidates >= rrConsLimit` |
| 8 | minor | Europe pin-label pile-up at desktop (COE↔EU 12×3px, COE↔CH 19×5px overlap) | **fixed** — RR board pin labels now consume the same labelDx/labelDy nudges (map-%) the Jurisdiction Map uses, converted to px at the capped desktop map width; map-coe labelDx 5→6, map-ch labelDx −4→−5 in domain-ii.json |
| 9 | minor | Interactive elements below the 44px touch bar everywhere except `.rr-hit` | **fixed (RR-scoped)** — `.rr-mode` class stamped on `<main>` for the risk runner only; scoped CSS bumps `.btn`, `.pick button` and `.ai-link` to min 44px within Regulatory Risk screens |

### Accepted items (with rationale)

- **kr-i01 authoring gap** — the addendum's worked example `ii-rr-kr-i01` (KR importer gate card) is
  absent from the source material, and CN/NYC carry no shared `*` gate cards. Accepted for this wave: the
  engine fallback in finding 1 covers play for every role/territory combo, so no card is authored
  here (content authoring is out of scope for a playtest-fix pass). Left open for a future content wave.
- **house-kit 42px baseline** — the shared house kit's `.btn` is 42–43px across all labs. Bumping it
  globally would restyle every other lab that shares the kit, so the 44px fix is scoped to Regulatory
  Risk via `.rr-mode` only. The kit-wide baseline stays as-is (accepted).

### Re-probe results (post-fix, build + headless Chrome/CDP on :8746)

| Re-probe | Result | Evidence |
|---|---|---|
| (a) provider expand NYC | PASS | Full-pool gate drawn (`ii-rr-nyc-d04`, `ii-rr-nyc-d03`), question 1 renders, no bounce |
| (a) importer KR / TX / CA | PASS | KR 3-Q (`kr-d03/kr-p01/kr-d02`), TX 3-Q, CA 2-Q — all draw and render |
| (b) forced double-act | PASS | Stage-1 render AND rr-begin click both route to "Action already taken this turn"; no pending created, log unchanged |
| (c) pending:7 / `{action:'expand'}` | PASS | Both → stale-note + clean role screen, zero window errors (no recursion) |
| (d) unresolvable answer id | PASS | Debrief + print render the row with the raw id / "?" — no TypeError |
| (e) negative capital | PASS | Debrief and print both show `− 1 capital`; no `+ -1` anywhere |
| (f) consolidate at limit | PASS | Canada (2/2) and TX inset (1/1) disabled + "Consolidated ✓"; US (1/2) still enabled |
| (g) 1800px labels | PASS | COE↔EU and EU↔CH zero overlap; COE↔CH zero x-overlap — screenshot verified |
| (h) 375px | PASS | hscroll 0 on board/role/debrief; every visible RR `.btn`/picker ≥44px; all 6 debrief ai-links ≥44×44 |

## Iteration 2 — independent adversarial re-verify (post-83fda4b)

Fresh read-only verifier, instructed to distrust the fixer. All 5 probe groups PASS, no new defects:

| Probe | Result | Evidence |
|---|---|---|
| gate-pool fallback | PASS | All 8 empty/short role×territory combos clicked through the real UI — every one drew a full gateSize pending (role cards first, off-role top-up after); no silent bounce; no remaining soft-lock (zero territories have an empty full pool). |
| one-action-per-turn | PASS | Forced screen-state, stale detached rr-begin, forced consolidate — all blocked with byte-identical state snapshots; regulator audits/checks confirmed exempt. |
| pending/state corruption | PASS | 7 corrupt blobs → fresh start or clamped board, zero exceptions, scheduler byte-identical. Non-defect note: corrupt blob persists (re-discarded each load) until a new campaign overwrites it. |
| debrief/print fallback | PASS | Ghost answer ids render via id-fallback in debrief and print; single-sign negative capital in both. |
| UI regression | PASS | 375px zero hscroll; 33 measured targets ≥44px; 17 pin labels zero overlap at 1800px; consolidate-at-limit disabled + "Consolidated ✓"; 2-turn autoplay clean. |

Gate status: **GREEN** — Task 14 complete.
