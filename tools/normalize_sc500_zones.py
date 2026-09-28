#!/usr/bin/env python3
"""
Give every SC-500 board zone a player-facing label.

The deck authors split on convention: some boards named their zones the way a
practitioner says them ("Azure Firewall", "Conditional Access"), others left
internal slugs ("sas-scope", "syslog-cef", "secure score rec"). The zone name is
rendered on the board as a drop target, so a slug is a defect the build cannot
see — every gate passes while the player reads machine punctuation.

The rename is field-level: zones[].key, zones[].name and the items[].answer that
must match it exactly. Prose is rewritten only for slugs distinctive enough that
a whole-file replace cannot collide with ordinary English — never for a key like
"deny" or "agents", which would corrupt the surrounding sentence.

Usage:
    python3 tools/normalize_sc500_zones.py [--check]
"""
import argparse
import glob
import json
import os
import re

DECKS = "data/decks/sc500"

# deck id -> {old zone key: player-facing label}
RENAMES = {
    "governance-controls": {
        "deny": "Policy deny",
        "audit": "Policy audit",
        "auto-remediate": "DeployIfNotExists",
        "resource-lock": "Resource lock",
        "defender-standard": "Compliance standard",
        "scope-binding": "Assignment scope",
    },
    "posture-triage": {
        "secure score rec": "Secure score recommendation",
        "attack path": "Attack path",
        "security alert": "Security alert",
        "compliance control": "Compliance control",
        "governance rule": "Governance rule",
        "plan coverage": "Plan coverage",
    },
    "sentinel-collection": {
        "connectors": "Data connector",
        "content-hub": "Content hub solution",
        "syslog-cef": "Syslog and CEF",
        "windows-dcr": "Windows collection rule",
        "custom-ingestion": "Custom ingestion",
        "tables-retention": "Table plan and retention",
    },
    "storage-exposure": {
        "sas-scope": "SAS scope",
        "anonymous-access": "Anonymous access",
        "network-boundary": "Network boundary",
        "encryption-keys": "Encryption keys",
        "entra-authorization": "Entra authorization",
        "defender-detection": "Defender detection",
    },
    "server-hardening": {
        "jit access": "Just-in-time access",
        "bastion": "Azure Bastion",
        "plan coverage": "Plan coverage",
        "agentless scanning": "Agentless scanning",
        "change monitoring": "Change monitoring",
        "disk and boot": "Disk and boot integrity",
    },
    "app-platform-defense": {
        "registry-supply-chain": "Registry and supply chain",
        "admission-policy": "Admission policy",
        "workload-identity": "Workload identity",
        "app-inbound-rules": "Inbound access rules",
        "runtime-detection": "Runtime detection",
        "network-isolation": "Network isolation",
    },
    "security-copilot": {
        "plugins": "Plugin",
        "promptbooks": "Promptbook",
        "agents": "Agent",
        "experience": "Experience surface",
        "capacity": "Compute capacity",
        "roles": "Role and access",
    },
}

# A slug is safe to replace in prose only if it cannot occur as ordinary English.
def prose_safe(key: str) -> bool:
    return "-" in key or (" " in key and key.islower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report, do not write")
    args = ap.parse_args()

    changed = 0
    for path in sorted(glob.glob(os.path.join(DECKS, "*.json"))):
        deck_id = os.path.basename(path)[:-5]
        mapping = RENAMES.get(deck_id)
        if not mapping:
            continue
        raw = open(path, encoding="utf-8").read()
        deck = json.loads(raw)

        keys = {z["key"] for z in deck.get("zones", [])}
        missing = set(mapping) - keys
        if missing:
            raise SystemExit(f"{deck_id}: rename targets not present as zones: {sorted(missing)}")

        # Prose first, on the raw text, before the structural fields move.
        for old, new in mapping.items():
            if prose_safe(old):
                raw = re.sub(rf"(?<![\w-]){re.escape(old)}(?![\w-])", new, raw)
        deck = json.loads(raw)

        for z in deck["zones"]:
            if z["key"] in mapping:
                z["name"] = mapping[z["key"]]
                z["key"] = mapping[z["key"]]
            else:
                z["key"] = z["name"] = mapping.get(z["key"], z["key"])
        for it in deck["items"]:
            it["answer"] = mapping.get(it["answer"], it["answer"])

        zone_keys = {z["key"] for z in deck["zones"]}
        bad = [it["id"] for it in deck["items"] if it["answer"] not in zone_keys]
        if bad:
            raise SystemExit(f"{deck_id}: answers no longer match a zone: {bad}")

        print(f"{deck_id}: {len(mapping)} zones renamed")
        if not args.check:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(deck, fh, ensure_ascii=False, indent=1)
        changed += 1

    print(f"{'would rename' if args.check else 'renamed'} {changed} decks")


if __name__ == "__main__":
    main()
