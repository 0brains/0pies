#!/usr/bin/env python3
"""Regulatory Risk balance simulator (plan Task 4 / ADD §9.4-5).

Monte-Carlo campaigns against the REAL campaign config in
data/aigp/knowledge/domain-ii.json (read-only — this script never writes it).

    python3 tools/rr_sim.py [--p 0.9] [--runs 2000] [--grades "26,22,17,12,8"] [--proto]

With no --p it runs the full gate battery p ∈ {.9, .5, .3}. Until the Task-8
event deck lands, --proto approximates the regulator with 17 generic audits
keyed to each binding territory's opsHooks plus generic role-shift / check /
info events in the ADD §4.4 proportions; with a non-empty campaign.events the
real deck is used. Weighting follows ADD §4.3 exactly; the player policy is the
plan's greedy walk (expand cheapest until 2 holds then highest-market; defend
notices first, L2+ before L1; consolidate at capital ≤ 3 while a pool remains)
plus a tabu step — two consecutive fails deprioritise a territory until the
rest have been tried. A notice does not age in the regulator phase that served
it (its first defend window opens next turn). For p ≥ 0.75 one forced gate
fail is injected per campaign (plan Task 4 Step 4: the strong player must
absorb a stumble).

SIM SUMMARY (2000 runs each, --proto, seed 7, comprehensive market 4,
grades "26,21,14,5,3" — controller ruling after the Task-4 flags):

  p    bust%   median-bust-turn   pre-t3-busts   grade distribution
  0.9    0.5%  t14                0              A+ 29.1%  A 22.8%  B 36.4%  C 11.1%  D 0.2%  F 0.5%
  0.5   90.0%  t10                0              A+ 0.0%   A 0.0%   B 0.1%   C 6.1%  D 2.4%  F 91.5%
  0.3   99.9%  t7                 0              A+ 0.0%   A 0.0%   B 0.0%   C 0.1%  D 0.0%  F 100.0%

  Gates: 0 busts before turn 3 at every p PASS · p=.3 median bust turn 7 ∈ [5,10] PASS
  Avoider ceiling PROOF: all twelve 1-point territories held + max capital 8 =
    12 + 8 = 20 < A cut 21 and ≥ B cut 14 → grade B. Ceiling restored PASS.
  p=.9 A-or-A+ 51.9% vs relaxed gate ≥ 55% — NARROW MISS, not tunable: the A
    cut is hard-floored at 21 by the avoider ceiling, and B/C/D cuts cannot
    move the A-or-A+ rate. p=.9 cumulative (all 2000 runs): ≥26 29.1% · ≥22
    46.8% · ≥21 51.9% · ≥20 57.6% · ≥19 61.5%; median survivor score 21.
    Closing the last 3.1pp needs either A cut 20 (breaks the ceiling) or a
    further comprehensive market bump — controller's call, left as-is.
  p=.5 bust rate 90.0%: ACCEPTED by controller ruling (2026-08-02) — the
    plan's [25,60]% window was mis-calibrated; ADD §8.1's economy (mid player
    busts ~t8–10; conditional median here t10) is authoritative. Floor with
    ALL opsHooks stripped is 85.8%, so no permitted knob reaches the window.
    p=.5 surviving median grade C via the C cut at 5 (survivor median score
    5–6); D 3–4 keeps a meaningful band below it.

REAL-DECK RE-RUN (Task 8, 2026-08-02: 33-event deck, 173 cards, 2000 runs,
seed 7, grades unchanged "26,21,14,5,3"):

  p    bust%   median-bust-turn   pre-t3-busts   grade distribution
  0.9    1.1%  t10                0              A+ 29.2%  A 20.7%  B 35.6%  C 13.0%  D 0.4%  F 1.1%
  0.5   94.7%  t8                 0              A+ 0.0%   A 0.0%   B 0.1%   C 4.2%   D 0.7%  F 95.0%
  0.3  100.0%  t6                 0              A+ 0.0%   A 0.0%   B 0.0%   C 0.1%   D 0.0%  F 100.0%

  Gates: 0 pre-turn-3 busts at every p PASS · p=.3 median bust t6 ∈ [5,10]
    PASS · p=.5 bust 94.7% within the accepted ~90% ruling band (surviving
    median grade C) PASS · avoider B-ceiling structural proof unchanged
    (12 + 8 = 20 < A cut 21) PASS.
  Standing ruling check: p=.9 A-or-A+ 49.9% ≥ 45% → comprehensive-tier
    market stays 4 (no market-5 bump fired). Grades confirmed unchanged:
    A+ 26 · A 21 · B 14 · C 5 · D 3.

OPEN-MAP + ENTRY-COST RE-RUN (2026-08-03: launch anywhere from turn 1, tier
entry cost charged on the gate attempt — comprehensive ₿2, sectoral ₿1, rest 0,
non-refundable; policy skips targets it cannot afford and keeps a survival
buffer of entryCost + gateFailCost + 1 before entering a costed regime; 33-event
real deck, 2000 runs, seed 7, grades RETUNED to "22,21,12,5,3"):

  p    bust%   median-bust-turn   pre-t3-busts   grade distribution
  0.9    5.7%  t9                 0              A+ 0.1%  A 0.5%  B 51.8%  C 41.4%  D 0.7%  F 5.7%
  0.5   94.3%  t7                 0              A+ 0.0%  A 0.0%  B 0.1%   C 4.7%   D 1.0%  F 94.3%
  0.3  100.0%  t6                 0              A+ 0.0%  A 0.0%  B 0.0%   C 0.1%   D 0.0%  F 100.0%

  Gates: 0 pre-turn-3 busts at every p PASS · p=.3 median bust t6 ∈ [5,10]
    PASS · p=.5 bust 94.3% within the accepted ~90% ruling band (surviving
    median grade C, precedent 94.7% accepted 2026-08-02) PASS · avoider
    B-ceiling structural proof: the twelve entry-free 1-point territories
    (7 voluntary + 3 proposed + 1 treaty + 1 none) + capital cap 8 = 20 <
    A cut 21 → best all-voluntary strategy still grades B PASS.
  p=.9 A-or-A+ 0.6% vs ≥ 45% — STRUCTURAL MISS, not grade-tunable: entry
    costs compress every strategy to ≈ +0.7–1.0 net score per action turn
    (comprehensive: 4 market − ~2.7 expected entry+fail spend per hold;
    free 2-Q gate: ~0.66/turn; consolidate: ~0.9/turn), so the p=.9
    survivor distribution is median 12, p90 17, max 23/2000 — while the
    avoider ceiling hard-floors the A cut at 21. Reaching 45% A-or-A+
    would need A ≈ 12, deep below the 20 ceiling, or a markets/costs
    change (forbidden knob). GRADES retuned instead: A+ 26→22 (top score
    observed 23 — keeps A+ attainable), A 21 unchanged (ceiling floor),
    B 14→12 (strong-player median → surviving median grade B at p=.9),
    C 5 / D 3 unchanged (p=.5 survivor median 6 keeps C meaningful).

STAKE-REFUND RESOLUTION (2026-08-03, controller ruling — supersedes the grade
retune above): the entry cost became a STAKE — charged when the first gate
question is shown, RETURNED on a gate pass (capped at capitalCap), lost on a
fail or withdrawal, gateFailCost still stacking on a fail. This preserves the
"harder + costs more capital" intent (affordability-gates entry; failure in a
comprehensive regime costs up to ₿3) without taxing successful play. The
standing market-5 ruling's trigger (p=.9 A-or-A+ < 45%) was met, so the
comprehensive market went 4 → 5; grades restored to A+ 26 · A 21 · B 14 ·
C 5 · D 3. Final table (2000 runs, seed 7):

  p    bust%   median-bust-turn   pre-t3-busts   grade distribution
  0.9    5.9%  t9                 0              A+ 15.6%  A 12.0%  B 33.4%  C 32.5%  D 0.6%  F 5.9%
  0.5   94.1%  t7                 0              C 4.8%  D 1.1%  F 94.1%
  0.3  100.0%  t6                 0              C 0.1%  F 100.0%

  Gates: 0 pre-t3 busts PASS · p=.5 94.1% in band PASS · p=.3 median t6 PASS ·
    avoider ceiling 20 < A-cut 21 PASS (comprehensive market is outside the
    avoider path) · p=.9 A-or-A+ 27.6% vs the legacy 45% gate: ACCEPTED SHORT —
    the open-map economy is deliberately harder per Dave's 2026-08-03
    direction; median surviving grade B at p=.9, A/A+ reachable but earned.
    Flagged to Dave for a final ruling; every remaining lever (sectoral
    market, capital cap, A-cut below 21) breaks a standing constraint.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "aigp" / "knowledge" / "domain-ii.json"

# Proto consolidate-pool sizes per territory (planned wave counts; the real
# limit is min(2, pool) per ADD §1.1). Only used until cards land.
PROTO_CONSOLIDATE = {
    "map-eu": 3, "map-kr": 2, "map-cn": 2, "map-jp": 2, "map-us": 2,
    "map-us-co": 3, "map-us-il": 1, "map-us-tx": 1, "map-us-nyc": 2,
    "map-us-ca": 2, "map-ca": 2, "map-br": 2, "map-in": 2, "map-uk": 2,
    "map-au": 2, "map-coe": 2, "map-sg": 2, "map-tw": 2, "map-pe": 2,
    "map-ch": 2, "map-ae": 1, "map-ke": 2,
}

PLAYER_OPS = {"hiring", "genai"}   # §8.1: the sim's declared ops include hiring


def load():
    d = json.loads(DATA.read_text())
    camp = d["campaign"]
    cov = {j["id"]: j["coverage"] for j in d["map"]["jurisdictions"]}
    tiers = camp["config"]["tiers"]
    terrs = {}
    for t in camp["territories"]:
        tier = tiers[cov[t["mapId"]]]
        terrs[t["mapId"]] = {
            "id": t["mapId"], "unlock": t["unlock"],
            "opsHooks": set(t["opsHooks"]),
            "gateSize": tier["gateSize"], "market": tier["market"],
            "noticeOnFail": tier["noticeOnFail"],
            "entryCost": tier.get("entryCost", 0),
            "coverage": cov[t["mapId"]],
        }
    return camp, terrs


def proto_deck(terrs):
    """17 generic audits keyed to opsHooks + generic shifts/checks/info (§4.4)."""
    audit_alloc = {  # 17 audits over the 10 binding territories
        "map-eu": 3, "map-us": 3, "map-kr": 2, "map-cn": 2, "map-us-ca": 2,
        "map-us-il": 1, "map-us-tx": 1, "map-us-nyc": 1, "map-ae": 1, "map-pe": 1,
    }
    deck = []
    for terr, n in audit_alloc.items():
        for i in range(n):
            deck.append({
                "id": f"proto-audit-{terr}-{i}",
                "weight": {"holdings": [terr], "operations": sorted(terrs[terr]["opsHooks"]),
                           "coverage": [], "hats": [], "minTurn": 0},
                "effect": {"type": "audit", "territory": terr},
            })
    for role in ("provider", "importer"):
        deck.append({"id": f"proto-shift-{role}",
                     "weight": {"holdings": [], "operations": [], "coverage": [], "hats": [], "minTurn": 5},
                     "effect": {"type": "roleShift", "toRole": role}})
    for i in range(4):  # penalty checks (2 traps + 2 sweeps)
        deck.append({"id": f"proto-check-pen-{i}",
                     "weight": {"holdings": [], "operations": [], "coverage": [], "hats": [], "minTurn": 0},
                     "effect": {"type": "check", "penalty": 1, "reward": 0}})
    for i in range(3):  # reward checks (rubber-band lifeline)
        deck.append({"id": f"proto-check-rew-{i}",
                     "weight": {"holdings": [], "operations": [], "coverage": [], "hats": [], "minTurn": 0},
                     "effect": {"type": "check", "penalty": 0, "reward": 1}})
    for i in range(3):
        deck.append({"id": f"proto-info-{i}",
                     "weight": {"holdings": [], "operations": [], "coverage": [], "hats": [], "minTurn": 0},
                     "effect": {"type": "info"}})
    return deck


class Sim:
    def __init__(self, camp, terrs, deck, p, rng, grades):
        self.cfg = camp["config"]
        self.terrs = terrs
        self.deck = deck
        self.p = p
        self.rng = rng
        self.grades = grades
        self.capital = self.cfg["startCapital"]
        self.held: set[str] = set()
        self.suspended: set[str] = set()
        self.notices: dict[str, dict] = {}   # terr -> {level, age}
        self.sanctions = 0
        self.role = "deployer"
        self.shifts = 0
        self.consolidated: dict[str, int] = {}
        self.tabu: dict[str, int] = {}   # consecutive-fail counts per territory
        self.drawn: set[str] = set()
        self.bust_turn = None
        # forced stumble for the strong player: first expand at/after this turn
        # auto-fails its first question (exactly once per campaign)
        self.stumble_turn = rng.randint(2, 8) if p >= 0.75 else None
        self.stumbled = False

    def ask(self) -> bool:
        return self.rng.random() < self.p

    def unlocked(self, t) -> bool:
        # Open map (2026-08-03): every territory is launchable from turn 1;
        # the data's unlock fields are ignored by the engine and the sim alike.
        return True

    def expand_target(self):
        # greedy walk with a tabu step: two consecutive fails on a territory
        # deprioritise it until everything else has been tried (a real player
        # does not bang on the same 3-question gate all campaign).
        # Affordability: entry cost is charged on the gate attempt and entering
        # must not itself bust you, so targets with capital ≤ entryCost are
        # skipped (mirrors the engine's disabled launch/expand buttons).
        # A costed regime is only entered with a survival buffer: entry + a
        # possible gate fail must leave ≥ 2 capital (a real player does not
        # pay ₿2 to sit at 1 capital with audits pending). Free regimes keep
        # the bare must-not-bust rule.
        def afford(t):
            c = t["entryCost"]
            return self.capital > c + (self.cfg["gateFailCost"] + 1 if c else 0)
        cands = [t for t in self.terrs.values()
                 if t["id"] not in self.held and t["id"] not in self.suspended
                 and self.unlocked(t) and afford(t)]
        if not cands:
            return None
        fresh = [t for t in cands if self.tabu.get(t["id"], 0) < 2]
        pool = fresh or cands
        if len(self.held) < 2:
            pool.sort(key=lambda t: (t["gateSize"], t["market"]))
        else:
            pool.sort(key=lambda t: (-t["market"], t["gateSize"]))
        return pool[0]

    def spawn_notice(self, terr_id):
        # "fresh" defers aging: a notice served this turn opens its defend
        # window next turn, so it does not age in the phase that served it
        if terr_id not in self.notices:
            self.notices[terr_id] = {"level": 1, "age": 0, "fresh": True}

    def gate(self, t, turn):
        # Tier entry cost — charged up front on the gate attempt, non-refundable
        # (pass does not return it; a fail costs gateFailCost on top).
        self.capital -= t["entryCost"]
        forced = (self.stumble_turn is not None and not self.stumbled
                  and turn >= self.stumble_turn)
        for q in range(t["gateSize"]):
            fail = (forced and q == 0) or not self.ask()
            if forced and q == 0:
                self.stumbled = True
            if fail:
                self.capital -= self.cfg["gateFailCost"]
                self.tabu[t["id"]] = self.tabu.get(t["id"], 0) + 1
                if t["noticeOnFail"] and (PLAYER_OPS & t["opsHooks"]):
                    self.spawn_notice(t["id"])
                return
        self.held.add(t["id"])
        # Entry stake returns on a pass (engine rrResolvePass mirrors this).
        self.capital = min(self.cfg["capitalCap"], self.capital + t["entryCost"])
        self.tabu.pop(t["id"], None)

    def defend(self, terr_id):
        n = self.notices[terr_id]
        need = 1 if n["level"] == 1 else 2
        if all(self.ask() for _ in range(need)):
            del self.notices[terr_id]
            self.suspended.discard(terr_id)
        else:
            self.capital -= 1

    def consolidate_target(self):
        for terr_id in sorted(self.held):
            limit = min(2, PROTO_CONSOLIDATE.get(terr_id, 1))
            if self.consolidated.get(terr_id, 0) < limit:
                return terr_id
        return None

    def consolidate(self, terr_id):
        self.consolidated[terr_id] = self.consolidated.get(terr_id, 0) + 1
        if self.ask():
            self.capital = min(self.cfg["capitalCap"], self.capital + 1)

    def player_phase(self, turn):
        # defend first, L2+ before L1 (an open notice is a ticking -2)
        if self.notices:
            tgt = max(self.notices,
                      key=lambda k: (self.notices[k]["level"], self.notices[k]["age"]))
            self.defend(tgt)
            return
        if self.capital <= 3 and self.consolidate_target():
            self.consolidate(self.consolidate_target())
            return
        t = self.expand_target()
        if t:
            self.gate(t, turn)
        elif self.consolidate_target():
            self.consolidate(self.consolidate_target())

    # --- regulator ---
    def event_weight(self, ev, turn):
        w = ev["weight"]
        eff = ev["effect"]
        if turn < w.get("minTurn", 0):
            return 0
        if w.get("hats"):
            return 0   # sim player's hat gates nothing in proto mode
        if eff["type"] == "audit":
            terr = eff["territory"]
            if terr != "match" and terr not in self.held and terr not in self.notices:
                return 0
        if eff["type"] == "roleShift":
            if turn < self.cfg["roleShiftMinTurn"] or self.shifts >= self.cfg["roleShiftMax"] \
               or eff.get("toRole") == self.role:
                return 0
        base = 1
        holds = w.get("holdings", [])
        if any(h in self.held for h in holds):
            base += 2
        noticed = [h for h in holds if h in self.notices]
        if noticed:
            base += 2 if any(self.notices[h]["level"] >= 2 for h in noticed) else 1
        if set(w.get("operations", [])) & PLAYER_OPS:
            base += 2
        covs = set(w.get("coverage", []))
        if covs and sum(1 for h in self.held if self.terrs[h]["coverage"] in covs) >= 2:
            base += 1
        if eff.get("reward", 0) > 0 and self.capital <= 2:
            base += 2
        return base

    def regulator_phase(self, turn):
        # a. aging + escalation (a notice served this turn does not age yet —
        # its first defend window opens next turn)
        for terr_id, n in list(self.notices.items()):
            if n.pop("fresh", False):
                continue
            n["age"] += 1
            if n["level"] == 1 and n["age"] >= self.cfg["escalateEveryTurns"]:
                n["level"] = 2
            elif n["level"] == 2 and n["age"] >= 2 * self.cfg["escalateEveryTurns"]:
                n["level"] = 3
                self.capital -= self.cfg["l3Cost"]
                self.sanctions += 1
                if terr_id in self.held:
                    self.suspended.add(terr_id)
        # b. one weighted event draw without replacement
        pool = [e for e in self.deck if e["id"] not in self.drawn]
        if not pool:
            self.drawn = {e["id"] for e in self.deck
                          if e["effect"]["type"] == "roleShift" and e["id"] in self.drawn}
            pool = [e for e in self.deck if e["id"] not in self.drawn]
        weighted = [(e, self.event_weight(e, turn)) for e in pool]
        weighted = [(e, wt) for e, wt in weighted if wt > 0]
        if not weighted:
            return
        total = sum(wt for _, wt in weighted)
        pick = self.rng.uniform(0, total)
        for e, wt in weighted:
            pick -= wt
            if pick <= 0:
                break
        self.drawn.add(e["id"])
        self.resolve(e)

    def resolve(self, ev):
        eff = ev["effect"]
        kind = eff["type"]
        if kind == "audit":
            terr = eff["territory"]
            if terr == "match":
                cands = [h for h in ev["weight"].get("holdings", [])
                         if h in self.held or h in self.notices] or sorted(self.held)
                if not cands:
                    return
                terr = self.rng.choice(cands)
            if not self.ask():
                self.capital -= 1
                if self.terrs[terr]["noticeOnFail"]:
                    self.spawn_notice(terr)
        elif kind == "check":
            if self.ask():
                if eff.get("reward"):
                    self.capital = min(self.cfg["capitalCap"], self.capital + eff["reward"])
            elif eff.get("penalty"):
                self.capital -= eff["penalty"]
        elif kind == "roleShift":
            self.role = eff.get("toRole", self.role)
            self.shifts += 1
            comp = sorted(h for h in self.held if self.terrs[h]["coverage"] == "comprehensive")
            if comp:
                self.spawn_notice(self.rng.choice(comp))

    def run(self):
        for turn in range(1, self.cfg["turns"] + 1):
            self.player_phase(turn)
            if self.capital <= 0:
                self.bust_turn = turn
                return "F", turn
            self.regulator_phase(turn)
            if self.capital <= 0:
                self.bust_turn = turn
                return "F", turn
        market = sum(self.terrs[h]["market"] for h in self.held if h not in self.suspended)
        score = market + self.capital - len(self.notices) - 2 * self.sanctions
        for g, cut in self.grades:
            if score >= cut:
                return g, None
        return "F", None


def battery(p, runs, grades, camp, terrs, deck, seed):
    rng = random.Random(seed)
    dist: dict[str, int] = {}
    busts: list[int] = []
    for _ in range(runs):
        g, bust = Sim(camp, terrs, deck, p, random.Random(rng.random()), grades).run()
        dist[g] = dist.get(g, 0) + 1
        if bust:
            busts.append(bust)
    return dist, busts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--p", type=float, default=None)
    ap.add_argument("--runs", type=int, default=2000)
    ap.add_argument("--grades", type=str, default=None,
                    help="comma cuts for A+,A,B,C,D e.g. '26,22,17,12,8'")
    ap.add_argument("--proto", action="store_true",
                    help="use the generic pre-Task-8 event deck")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    camp, terrs = load()
    if args.grades:
        cuts = [float(x) for x in args.grades.split(",")]
        grades = list(zip(["A+", "A", "B", "C", "D"], cuts)) + [("F", -999)]
    else:
        grades = [(g, c) for g, c in camp["config"]["grades"]]
    deck = proto_deck(terrs) if (args.proto or not camp.get("events")) else camp["events"]
    if not camp.get("events") and not args.proto:
        print("note: campaign.events is empty — falling back to --proto deck")

    order = ["A+", "A", "B", "C", "D", "F"]
    print(f"runs={args.runs} deck={'proto' if deck and str(deck[0]['id']).startswith('proto') else 'real'} "
          f"grades={[(g, c) for g, c in grades][:5]}")
    print(f"{'p':>4} {'bust%':>6} {'med-bust':>8} {'pre-t3':>6}  grades")
    for p in ([args.p] if args.p is not None else [0.9, 0.5, 0.3]):
        dist, busts = battery(p, args.runs, grades, camp, terrs, deck, args.seed)
        bust_pct = 100 * len(busts) / args.runs
        med = f"t{int(statistics.median(busts))}" if busts else "—"
        pre3 = sum(1 for b in busts if b < 3)
        gtxt = "  ".join(f"{g} {100 * dist.get(g, 0) / args.runs:.1f}%" for g in order)
        print(f"{p:>4} {bust_pct:>5.1f}% {med:>8} {pre3:>6}  {gtxt}")
        # surviving median grade
        survivors = [g for g in order[:-1] for _ in range(dist.get(g, 0))]
        if survivors:
            print(f"{'':>26}  surviving median grade: {survivors[len(survivors) // 2]}")


if __name__ == "__main__":
    main()
