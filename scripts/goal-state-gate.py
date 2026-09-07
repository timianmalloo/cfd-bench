#!/usr/bin/env python3
"""Goal-state gate (AI-Forward proposal 3.b) - a required, static merge check.

Fails when an audit entry INTRODUCED in this PR (present in HEAD's committed audit log but not on
origin/main) is a substantive turn that recorded no goal-state (`done_when`), declared no `tier`, or
convened more sub-agents than its declared `fan_out` cap. Historical entries are grandfathered - a
forward-only ratchet, not a retroactive audit.

It reuses the vendored, unmodified `audit-log.py selfcheck --json` (the single source of truth for
what counts as substantive and what counts as a gap / tier-gap / over-cap) and intersects the ids it
reports with the ids new in this PR. No pack file is modified. The reusable `--gate`/`--since` form
lives in AI-Forward (rev 63); this repo can drop this script and call that once it updatepacks.

Honest limit: a gate enforces the QUALITY of the audit entries that exist (with the audit mandate
that skills append as their last action); it cannot force a turn to be recorded.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = "docs/audit/audit-log.jsonl"
SELFCHECK = "docs/ai-forward-pack/scripts/audit-log.py"
BASE = "origin/main"


def _run(args):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")


def main() -> int:
    base = _run(["git", "show", f"{BASE}:{LOG}"])
    if base.returncode != 0:
        print("goal-state gate: base audit log unreadable (origin/main); skipping (fail-open).")
        return 0
    known = set()
    for line in base.stdout.splitlines():
        line = line.strip()
        if line:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict) and entry.get("id"):
                known.add(entry["id"])
    report = _run(["python", SELFCHECK, "selfcheck", "--json"])
    if report.returncode != 0:
        print("goal-state gate: selfcheck failed:\n" + report.stderr, file=sys.stderr)
        return 2
    data = json.loads(report.stdout)
    new = lambda k: [e for e in data.get(k, []) if e.get("id") and e["id"] not in known]
    gaps, tier_gaps, over = new("gaps"), new("tier_gaps"), new("over_cap")
    if not (gaps or tier_gaps or over):
        print("goal-state gate: PASS - every audit entry new in this PR has a goal-state, tier, and fan-out within cap.")
        return 0
    print("goal-state gate: FAIL - audit entries new in this PR break the goal-state rule (CT19/PACK-O).")
    for e in gaps:
        print(f"  [no goal-state] {e.get('shortname','?')} ({e.get('id')})")
    for e in tier_gaps:
        print(f"  [no tier]       {e.get('shortname','?')} ({e.get('id')})")
    for e in over:
        print(f"  [over fan-out]  {e.get('shortname','?')} ({e.get('id')}): {e.get('agent_runs')} vs cap {e.get('fan_out')}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
