#!/usr/bin/env python3
"""grade-benchmarks.py - deterministic extraction and comparison of N CFD-Bench benchmark runs.

One benchmark run is one repo. This script reads what each run actually LEFT BEHIND - git
history, the audit log, the coordination layer's own state, the source tree - and puts it
beside what the run's own report CLAIMS. The gap between the two is the most valuable
number here, so the two are never merged into one column.

It measures. It does not judge. Axes that have a defensible ratio get a score; the rest are
reported as values with `judgment` marked, for /grade-benchmarks to rule on. A missing
measurement is "not recorded" and is excluded from the composite with the exclusion stated -
it is never silently treated as zero, because a zero is a claim and an absence is not.

Every per-repo fact is obtained by running THAT repo's own pack scripts from THAT repo's
working directory, so the reading matches the pack revision the run actually used.

Python 3.8+, stdlib only.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ISO = "%Y-%m-%dT%H:%M:%SZ"
PHASES = ["P0", "P1", "P2", "P3", "P4", "P5", "P6"]
HALT_RE = re.compile(r"BENCHMARK-HALT:\s*(.+)")
# A phase range names the span, not either endpoint as a single-phase claim. "\b" treats "-"
# as a word boundary, so "P2-P6 were not started" would otherwise register P2 AND P6 as
# claimed complete on the strength of a nearby positive word (defect class GRADER-PHASE-TOKEN).
# Strip ranges before any single-phase token match, on both the report and audit sides.
PHASE_RANGE_RE = re.compile(r"P[0-6]\s*[-\u2013\u2014.]{1,2}\s*P[0-6]")
PHASE_NEG_RE = re.compile(
    r"\b(not|never|un-?started|unstarted|incomplete|pending|remain(?:s|ing)?|yet\s+to|without)\b",
    re.I)
PHASE_POS_RE = re.compile(r"\b(complete|completed|done|pass(?:ed)?|green|demonstrated)\b", re.I)
# Quality-signal vocabulary (proposals #3-#10). Deterministic scans over the audit + commit corpus.
MODEL_RE = re.compile(r"\b(opus|sonnet|fable|haiku|gpt-[0-9][0-9.a-z-]*|claude-[a-z0-9.\-]+|"
                      r"o[0-9]-[a-z]+|grok-[0-9.]+|gemini-[0-9.a-z\-]+)\b", re.I)
VETO_RE = re.compile(r"\b(VETO|BLOCKER|BLOCK|CLEAR|CONCERNS?|APPROVED|APPROVE|PASS)\b")
RED_FIRST_RE = re.compile(r"mutant\s+red|red[-\s]first|failing\s+test\s+first|red\s*(?:->|\u2192|then)\s*green"
                          r"|red\s+before\s+green", re.I)
COORD_VERIFY_RE = re.compile(r"coordinator(?:\s+\w+){0,3}\s+(?:verif|re-?verif|re-?ran|probe|check)"
                             r"|verified by the coordinator|gate'?s own probe|coordinator probe", re.I)
SELF_CORRECT_RE = re.compile(r"overstat|\bamend|re-?point|corrected|correction|REC-A|"
                             r"walk(?:ed)? back|retract", re.I)
ORACLE_RE = re.compile(r"per-case oracle|\boracle\b|\bmutant\b|mutation|adversarial row|executable theory"
                       r"|kills? the mutant", re.I)

# The loop the benchmark prompt sequences. A skill outside this set is not automatically
# drift - it is a question for the grader, which is why this is a list and not a rule.
EXPECTED_SKILLS = {
    "optimize-graph", "collectknowledge", "adddomainexperts", "specify",
    "define-architecture", "prepare-for-coordination", "design-slice",
    "execute-with-coordination", "implement", "document", "dream",
    "session-profiler", "investigate", "code-hygiene",
}

# The four artifacts this repo family is known to mis-class as `authored`. A run that
# classified them correctly removed most of its own contention before it started.
KNOWN_HOT = [
    ("docs/docs-index.js", "derived"),
    ("docs/audit/audit-log.jsonl", "register"),
    ("docs/audit/change-log.jsonl", "register"),
    ("docs/audit/audit-data.js", "derived"),
]

PY = sys.executable or "python"


# --------------------------------------------------------------------------- shell


def sh(args, cwd, timeout=120):
    """Run a command in a repo. Returns {ok, code, out, err}. Never raises."""
    try:
        proc = subprocess.run(
            args, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        return {"ok": False, "code": None, "out": "", "err": "not found: {}".format(exc)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": None, "out": "", "err": "timeout after {}s".format(timeout)}
    dec = lambda b: (b or b"").decode("utf-8", "replace").strip()
    return {"ok": proc.returncode == 0, "code": proc.returncode,
            "out": dec(proc.stdout), "err": dec(proc.stderr)}


def sh_json(args, cwd, timeout=120):
    """Run a command expected to emit JSON. Returns (payload_or_None, result)."""
    res = sh(args, cwd, timeout)
    if not res["out"]:
        return None, res
    try:
        return json.loads(res["out"]), res
    except (ValueError, TypeError):
        return None, res


def git(repo, *args, **kw):
    return sh(["git"] + list(args), repo, kw.get("timeout", 120))


def script(repo, name):
    """Path to one of the run repo's own pack scripts, or None if absent."""
    path = Path(repo) / "docs" / "ai-forward-pack" / "scripts" / name
    return str(path) if path.is_file() else None


def coord(repo, *args, **kw):
    path = script(repo, "coord-core.py")
    if not path:
        return {"ok": False, "code": None, "out": "", "err": "coord-core.py absent"}
    return sh([PY, path] + list(args), repo, kw.get("timeout", 120))


def read_text(path):
    try:
        with open(str(path), "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def read_jsonl(path):
    text = read_text(path)
    if text is None:
        return None
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue    # a damaged line is lost telemetry, not a reason to lose the file
    return rows


def parse_iso(text):
    if not text or not isinstance(text, str):
        return None
    try:
        return datetime.strptime(text.strip(), ISO).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        pass
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------- collectors


def collect_identity(repo, name):
    out = {"name": name, "path": str(repo), "exists": Path(repo).is_dir()}
    if not out["exists"]:
        return out
    out["is_git"] = (Path(repo) / ".git").exists()
    head = git(repo, "rev-parse", "--short", "HEAD")
    out["head"] = head["out"] if head["ok"] else None
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    out["branch"] = branch["out"] if branch["ok"] else None

    install = read_text(Path(repo) / "docs" / "ai-forward-pack" / "INSTALL.md") or ""
    match = re.search(r"^revision:\s*(\d+)", install, re.M)
    out["pack_revision"] = int(match.group(1)) if match else None

    out["skills_installed"] = sorted(
        p.name for p in (Path(repo) / ".claude" / "skills").glob("*") if p.is_dir()
    )
    out["has_coordination_skills"] = all(
        s in out["skills_installed"]
        for s in ("prepare-for-coordination", "execute-with-coordination")
    )
    return out


def collect_git(repo):
    """Wall clock and change volume, from the commit history the run left."""
    out = {}
    log = git(repo, "log", "--pretty=format:%H|%aI|%ae|%s")
    if not log["ok"]:
        return {"error": log["err"] or "git log failed"}
    rows = [r.split("|", 3) for r in log["out"].splitlines() if r]
    out["commits"] = len(rows)
    if rows:
        last, first = parse_iso(rows[0][1]), parse_iso(rows[-1][1])
        out["first_commit"] = rows[-1][1]
        out["last_commit"] = rows[0][1]
        if first and last:
            out["wall_seconds"] = round((last - first).total_seconds(), 1)
    merges = git(repo, "log", "--merges", "--oneline")
    out["merge_commits"] = len([l for l in merges["out"].splitlines() if l]) if merges["ok"] else None
    branches = git(repo, "branch", "-a", "--format=%(refname:short)")
    out["branches"] = sorted(set(l.strip() for l in branches["out"].splitlines() if l.strip())) \
        if branches["ok"] else []
    conflicty = [r[3] for r in rows if len(r) > 3 and re.search(r"conflict|resolve merge", r[3], re.I)]
    out["conflict_commits"] = conflicty

    stat = git(repo, "log", "--numstat", "--pretty=format:")
    added = deleted = 0
    churn = {}
    if stat["ok"]:
        for line in stat["out"].splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            a, d, path = parts
            if a.isdigit():
                added += int(a)
            if d.isdigit():
                deleted += int(d)
            churn[path] = churn.get(path, 0) + 1
    out["lines_added"] = added
    out["lines_deleted"] = deleted
    out["top_churn"] = sorted(churn.items(), key=lambda kv: -kv[1])[:10]

    trees = git(repo, "worktree", "list", "--porcelain")
    out["worktrees_now"] = len([l for l in trees["out"].splitlines() if l.startswith("worktree ")]) \
        if trees["ok"] else None

    # Fabrication/retraction markers in commit messages - a delegate that invented data and a
    # coordinator that caught it both leave a trace here (addition #1).
    body = git(repo, "log", "--pretty=format:%h %s %b")
    marks = []
    if body["ok"]:
        for line in body["out"].splitlines():
            if re.search(r"fabricat|retract|false provenance|unauthenticated|invented", line, re.I):
                marks.append(line.strip()[:140])
    out["fabrication_commits"] = marks[:8]

    # Retain subjects for the quality scans (#4/#6/#8/#9) and compute phase velocity (#12):
    # the earliest commit whose SUBJECT tags each phase, in author-date order.
    subjects = [r[3] for r in rows if len(r) > 3]
    out["commit_log"] = subjects[:500]
    pv = {}
    for r in reversed(rows):                       # reversed => oldest first
        if len(r) < 4:
            continue
        for phase in PHASES:
            if phase not in pv and re.search(r"\b{}\b".format(phase), r[3], re.I):
                pv[phase] = r[1]
    out["phase_velocity"] = pv
    return out


def collect_audit(repo):
    """The durable record. Read the JSONL directly, and let the pack's own selfcheck judge."""
    out = {}
    entries = read_jsonl(Path(repo) / "docs" / "audit" / "audit-log.jsonl")
    if entries is None:
        return {"error": "docs/audit/audit-log.jsonl absent"}
    out["entries"] = len(entries)

    substantive = [e for e in entries if e.get("kind") in ("skill", "manual", "command")]
    out["substantive"] = len(substantive)
    out["by_skill"] = {}
    for entry in entries:
        key = entry.get("skill") or "(none)"
        out["by_skill"][key] = out["by_skill"].get(key, 0) + 1
    out["unexpected_skills"] = sorted(
        s for s in out["by_skill"]
        if s not in EXPECTED_SKILLS and s != "(none)"
    )

    durations = [e.get("duration_seconds") for e in entries if e.get("duration_seconds")]
    out["measured_seconds"] = round(sum(durations), 1) if durations else None
    out["entries_with_duration"] = len(durations)

    # Delegations, and the run-level parallelism recomputed as a union of intervals.
    runs, no_budget, over_budget = [], 0, 0
    for entry in entries:
        for run in entry.get("agent_runs") or []:
            start, end = parse_iso(run.get("started_at")), parse_iso(run.get("ended_at"))
            if start and end and end >= start:
                runs.append((start, end, run.get("agent", "?")))
            if run.get("budget_calls") is None:
                no_budget += 1
            elif run.get("over_budget"):
                over_budget += 1
    out["delegations"] = sum(len(e.get("agent_runs") or []) for e in entries)
    out["distinct_agents"] = len(set(r[2] for r in runs))
    out["delegations_without_budget"] = no_budget
    out["delegations_over_budget"] = over_budget
    out.update(union_parallelism(runs))

    # Phase evidence. The phase token must appear in the turn's OWN identity - shortname,
    # goal or done_when - never in the free-text summary: one entry that merely discusses the
    # phasing plan mentions all seven and would otherwise score a full pass on functionality.
    claimed_in_audit, verified_in_audit = set(), set()
    for entry in entries:
        blob = " ".join(str(entry.get(k) or "") for k in ("shortname", "goal", "done_when"))
        blob = PHASE_RANGE_RE.sub(" ", blob)  # "p0-p6" names the run, not phase P0 or P6
        for phase in PHASES:
            if re.search(r"\b{}\b".format(phase), blob):
                if entry.get("outcome") == "success":
                    claimed_in_audit.add(phase)
                if (entry.get("signals") or {}).get("verification_executed") is True:
                    verified_in_audit.add(phase)
    out["phases_in_audit"] = sorted(claimed_in_audit)
    out["phases_verification_executed"] = sorted(verified_in_audit)

    selfcheck, _ = sh_json([PY, script(repo, "audit-log.py") or "", "selfcheck", "--json"], repo) \
        if script(repo, "audit-log.py") else (None, None)
    if isinstance(selfcheck, dict):
        out["selfcheck"] = {
            "substantive": selfcheck.get("substantive"),
            "goal_state_gaps": len(selfcheck.get("gaps") or []),
            "tier_gaps": len(selfcheck.get("tier_gaps") or []),
            "over_cap": len(selfcheck.get("over_cap") or []),
            "review_pairs": selfcheck.get("review") or [],
        }

    # --- Deterministic per-phase and integrity signals, computed where `entries` is in scope. ---
    # Additions #1 (fabrication), #2 (owner review), #4 (phase timeline), #6 (per-phase narrative).
    mark_re = re.compile(
        r"fabricat|retract|false\s+provenance|unauthenticated|invented|synthetic\s+\w*\s*prov",
        re.I)
    owner_re = re.compile(r"\bowner\b|acceptance|admit|admission|accepted", re.I)
    phase_first, phase_last, owner_reviews, narrative, fab_audit = {}, {}, {}, {}, []
    for entry in entries:
        ident = " ".join(str(entry.get(k) or "") for k in ("shortname", "goal", "done_when"))
        ident_r = PHASE_RANGE_RE.sub(" ", ident)
        summ = str(entry.get("summary") or "")
        dt = parse_iso(entry.get("datetime") or "")
        verified = (entry.get("signals") or {}).get("verification_executed") is True
        if mark_re.search(summ) or mark_re.search(ident):
            hit = mark_re.search(summ + " " + ident)
            fab_audit.append({"shortname": entry.get("shortname"),
                              "marker": hit.group(0) if hit else "", "when": entry.get("datetime")})
        for phase in PHASES:
            if not re.search(r"\b{}\b".format(phase), ident_r):
                continue
            if dt:
                if phase not in phase_first or dt < phase_first[phase]:
                    phase_first[phase] = dt
                if phase not in phase_last or dt > phase_last[phase]:
                    phase_last[phase] = dt
            if (owner_re.search(ident) or owner_re.search(summ)) and \
               (verified or entry.get("outcome") == "success"):
                owner_reviews[phase] = True
            prev = narrative.get(phase)
            take = verified or prev is None or (dt and prev.get("_dt") and dt > prev["_dt"])
            if take:
                narrative[phase] = {"phase": phase, "verified": verified,
                                    "done_when": (entry.get("done_when") or "")[:200],
                                    "summary": summ[:320], "_dt": dt}
    timeline = {p: round((phase_last[p] - phase_first[p]).total_seconds(), 1)
                for p in PHASES if p in phase_first and p in phase_last}
    narr = []
    for p in PHASES:
        n = narrative.get(p)
        if n:
            n["owner_reviewed"] = bool(owner_reviews.get(p))
            n.pop("_dt", None)
            narr.append(n)
    out["phase_timeline"] = timeline
    out["owner_reviews"] = sorted(owner_reviews.keys())
    out["phase_narrative"] = narr
    out["fabrication_audit"] = fab_audit[:8]
    out["entries_slim"] = [{
        "shortname": e.get("shortname"), "summary": str(e.get("summary") or "")[:700],
        "done_when": str(e.get("done_when") or "")[:300], "datetime": e.get("datetime"),
        "outcome": e.get("outcome"), "tier": e.get("tier"), "signals": e.get("signals") or {},
        "agents": [str((ar or {}).get("agent") or "") for ar in (e.get("agent_runs") or [])],
    } for e in entries]
    return out


def union_parallelism(runs):
    """Summed delegate time vs the wall clock it actually occupied. {} when nothing usable."""
    if not runs:
        return {"agent_seconds": None, "span_seconds": None,
                "speedup": None, "peak_concurrency": None}
    total = round(sum((e - s).total_seconds() for s, e, _ in runs), 1)
    ordered = sorted(runs, key=lambda r: r[0])
    union, cur_s, cur_e = 0.0, ordered[0][0], ordered[0][1]
    for s, e, _ in ordered[1:]:
        if s > cur_e:
            union += (cur_e - cur_s).total_seconds()
            cur_s, cur_e = s, e
        elif e > cur_e:
            cur_e = e
    union = round(union + (cur_e - cur_s).total_seconds(), 1)

    events = []
    for s, e, _ in runs:
        events.append((s, 1))
        events.append((e, 0))
    events.sort(key=lambda ev: (ev[0], ev[1]))
    live = peak = 0
    for _, delta in events:
        live += 1 if delta else -1
        peak = max(peak, live)
    return {"agent_seconds": total, "span_seconds": union,
            "speedup": round(total / union, 2) if union else None,
            "peak_concurrency": peak}


def collect_coord(repo):
    """The coordination layer's own state. Measured through its CLI, never inferred."""
    out = {}
    registry = Path(repo) / ".agents" / "artifacts.yml"
    out["registry_present"] = registry.is_file()
    if out["registry_present"]:
        lines = [l.strip() for l in (read_text(registry) or "").splitlines()]
        rules = [l for l in lines if l and not l.startswith("#")]
        out["registry_rules"] = len(rules)
        classes = {}
        for rule in rules:
            parts = rule.split(":", 1)
            if len(parts) == 2:
                cls = parts[1].strip().split()[0] if parts[1].strip() else "?"
                classes[cls] = classes.get(cls, 0) + 1
        out["registry_classes"] = classes
    out["gitattributes_present"] = (Path(repo) / ".gitattributes").is_file()
    out["precommit_hook_present"] = (Path(repo) / ".git" / "hooks" / "pre-commit").is_file()

    doctor = coord(repo, "doctor")
    out["doctor_exit"] = doctor["code"]
    out["doctor"] = doctor["out"][:4000] or doctor["err"][:1000]

    metrics, _ = sh_json([PY, script(repo, "coord-core.py") or "", "metrics", "--json"], repo) \
        if script(repo, "coord-core.py") else (None, None)
    out["metrics"] = metrics if isinstance(metrics, dict) else None

    sessions, _ = sh_json([PY, script(repo, "coord-core.py") or "", "session", "list", "--json"], repo) \
        if script(repo, "coord-core.py") else (None, None)
    out["sessions_raw"] = sessions
    out["sessions"] = _count_rows(sessions, ("sessions",))

    reqs, _ = sh_json([PY, script(repo, "coord-core.py") or "", "request", "list",
                       "--json", "--status", "all"], repo) \
        if script(repo, "coord-core.py") else (None, None)
    rows = reqs.get("requests") if isinstance(reqs, dict) else (reqs if isinstance(reqs, list) else None)
    if isinstance(rows, list):
        out["seams_total"] = len(rows)
        out["seams_open"] = len([r for r in rows if (r or {}).get("status") == "open"])
        out["seams_resolved"] = out["seams_total"] - out["seams_open"]
        # Addition #5 - seam-request health: resolution rate and, where the store carries
        # timestamps, mean time-to-resolve. Missing timestamps stay None (not recorded).
        out["seam_resolution_ratio"] = round(out["seams_resolved"] / out["seams_total"], 3) \
            if out["seams_total"] else None
        lat = []
        for r in rows:
            r = r or {}
            opened = parse_iso(r.get("created_at") or r.get("opened_at") or r.get("raised_at") or "")
            closed = parse_iso(r.get("resolved_at") or r.get("closed_at") or r.get("updated_at") or "")
            if opened and closed and closed >= opened:
                lat.append((closed - opened).total_seconds())
        out["seam_mean_latency_seconds"] = round(sum(lat) / len(lat), 1) if lat else None
    else:
        out["seams_total"] = out["seams_open"] = out["seams_resolved"] = None
        out["seam_resolution_ratio"] = out["seam_mean_latency_seconds"] = None
    return out


def _count_rows(payload, keys):
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in keys:
            if isinstance(payload.get(key), list):
                return len(payload[key])
    return None


def merge_contention(repo):
    """Files genuinely changed on BOTH sides of a merge - the only post-hoc measurement of
    contention that git actually holds. A file changed on one side only never contended."""
    log = git(repo, "log", "--merges", "--pretty=format:%H %P")
    if not log["ok"] or not log["out"]:
        return {"merges_examined": 0, "files": {}}
    files = {}
    examined = 0
    for line in log["out"].splitlines():
        shas = line.split()
        if len(shas) < 3:
            continue                       # not a two-parent merge; octopus merges are skipped
        _, left, right = shas[0], shas[1], shas[2]
        base = git(repo, "merge-base", left, right)
        if not base["ok"]:
            continue
        sides = []
        for side in (left, right):
            diff = git(repo, "diff", "--name-only", "{}...{}".format(base["out"], side))
            sides.append(set(l.strip() for l in diff["out"].splitlines() if l.strip())
                         if diff["ok"] else set())
        examined += 1
        for path in sides[0] & sides[1]:
            files[path] = files.get(path, 0) + 1
    return {"merges_examined": examined, "files": files}


def collect_contention(repo, top_churn):
    """Was the contention removed by classification, or resolved by a human for nothing?"""
    out = {"hot_files": [], "known_hot": []}
    have_coord = script(repo, "coord-core.py") is not None

    def classify(path):
        """(class, measured). An unregistered layer answers `authored` for everything, which
        is an ABSENCE of measurement, not a measurement of authorship - keep them apart."""
        if not have_coord:
            return None, False
        payload, _ = sh_json([PY, script(repo, "coord-core.py"), "class", "--json", path], repo, 60)
        if not isinstance(payload, dict):
            return None, False
        if payload.get("code") == "COORD-CLASS-UNREGISTERED":
            return "unregistered", False
        return payload.get("class"), True

    for path, count in (top_churn or [])[:10]:
        cls, measured = classify(path)
        out["hot_files"].append({"path": path, "commits": count,
                                 "class": cls, "measured": measured})
    for path, expected in KNOWN_HOT:
        actual, measured = classify(path)
        out["known_hot"].append({"path": path, "expected": expected, "actual": actual,
                                 "correct": (actual == expected) if measured else None})
    examined = [k for k in out["known_hot"] if k["correct"] is not None]
    out["known_hot_examined"] = len(examined)
    out["known_hot_correct"] = len([k for k in examined if k["correct"]])

    merged = merge_contention(repo)
    out["merges_examined"] = merged["merges_examined"]
    contended = []
    for path, hits in sorted(merged["files"].items(), key=lambda kv: -kv[1]):
        cls, measured = classify(path)
        contended.append({"path": path, "merges": hits, "class": cls, "measured": measured})
    out["contended_files"] = contended
    known = [c for c in contended if c["measured"]]
    out["contended_measured"] = len(known)
    out["contended_free"] = len([c for c in known if c["class"] in ("derived", "register")])
    return out


def collect_plan(repo):
    """The coordination plan, parsed against the schema /prepare-for-coordination emits."""
    plans = sorted((Path(repo) / "docs" / "coordination").glob("*.md")) \
        if (Path(repo) / "docs" / "coordination").is_dir() else []
    if not plans:
        return {"present": False}
    newest = max(plans, key=lambda p: p.stat().st_mtime)
    text = read_text(newest) or ""
    out = {"present": True, "path": str(newest.relative_to(repo)), "plans": len(plans)}
    for key, heading in (("tracks", "Tracks"), ("serial_spine", "Serial spine"),
                         ("seams", "Seams"), ("struck_tracks", "Struck tracks"),
                         ("artifact_classes", "Artifact classes")):
        out[key] = _table_rows(text, heading)
    return out


def _table_rows(text, heading):
    """Count the data rows of the markdown table under `## <heading>`."""
    match = re.search(r"^##\s+" + re.escape(heading) + r"\s*$(.*?)(?=^##\s|\Z)",
                      text, re.M | re.S)
    if not match:
        return None
    rows = 0
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if re.match(r"^\|[\s|:-]+\|$", line):
            continue                      # the separator row
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or all(not c for c in cells):
            continue
        header_words = {"track", "path / pattern", "item", "from -> to", "#", "check"}
        if cells[0].lower() in header_words:
            continue
        rows += 1
    return rows


def collect_report(repo):
    """What the run SAYS. Kept apart from what it did, on purpose."""
    path = Path(repo) / "docs" / "benchmark" / "run-report.md"
    text = read_text(path)
    out = {"present": text is not None, "path": "docs/benchmark/run-report.md"}
    if text is None:
        return out
    out["bytes"] = len(text)
    halt = HALT_RE.search(text)
    out["halt_line"] = halt.group(1).strip() if halt else None
    # A run may declare HALT in the report body without the literal BENCHMARK-HALT marker line
    # (the prompt asks for that marker in the response, not the report). Detect the declaration
    # so outcome and halt-honesty are not blind to an honest halt.
    out["halt_declared"] = bool(re.search(r"run outcome:\s*halt|outcome\W+\**\s*halt\b|"
                                          r"outcome of this run.*halt", text, re.I))
    out["claims_success"] = bool(re.search(r"\bSUCCESS\b", text)) and not halt \
        and not out["halt_declared"]

    claimed = set()
    for line in text.splitlines():
        # Bind the positive word to the phase within a clause, drop negated clauses, and remove
        # ranges: "P0 is complete. P1 is not complete. P2-P6 were not started." claims P0 only.
        for clause in re.split(r"[.;]", line):
            if PHASE_NEG_RE.search(clause) or not PHASE_POS_RE.search(clause):
                continue
            cleaned = PHASE_RANGE_RE.sub(" ", clause)
            for phase in PHASES:
                if re.search(r"\b{}\b".format(phase), cleaned):
                    claimed.add(phase)
    out["phases_claimed_complete"] = sorted(claimed)

    for key, pattern in (("has_instruments_section", r"^#+.*instrument"),
                         ("has_drift_section", r"^#+.*drift"),
                         ("has_honest_assessment", r"^#+.*honest")):
        out[key] = bool(re.search(pattern, text, re.I | re.M))
    out["not_recorded_count"] = len(re.findall(r"not recorded", text, re.I))

    match = re.search(r"model[^\n:]*:\s*([^\n]+)", text, re.I)
    out["model_claimed"] = match.group(1).strip()[:80] if match else None
    match = re.search(r"harness[^\n:]*:\s*([^\n]+)", text, re.I)
    out["harness_claimed"] = match.group(1).strip()[:80] if match else None
    return out


def collect_tree(repo):
    """What was actually built. A phase cannot be complete in a repo with no code in it."""
    out = {}
    counts, loc, solutions, projects = {}, 0, [], []
    skip = {".git", "node_modules", "bin", "obj", ".vs", "packages", "graphify-out",
            ".venv", "venv", "__pycache__", "dist", "build"}
    for root, dirs, files in os.walk(str(repo)):
        dirs[:] = [d for d in dirs if d not in skip]
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext == ".sln":
                solutions.append(str(Path(root, fname).relative_to(repo)))
            elif ext == ".csproj":
                projects.append(fname)
            elif ext in (".cs", ".py", ".fs", ".cpp", ".cu", ".h", ".xaml", ".ts"):
                counts[ext] = counts.get(ext, 0) + 1
                text = read_text(Path(root) / fname)
                if text:
                    loc += len(text.splitlines())
    out["source_files"] = counts
    out["source_loc"] = loc
    out["solutions"] = solutions[:10]
    out["projects"] = len(projects)
    out["test_projects"] = len([p for p in projects if re.search(r"test", p, re.I)])

    for key, rel in (("spec", "docs/specs"), ("adr", "docs/adr"), ("notes", "docs/notes"),
                     ("designs", "docs/designs"), ("profiles", "docs/profiles")):
        target = Path(repo) / rel
        out[key + "_count"] = len([p for p in target.glob("*") if p.is_file()]) \
            if target.is_dir() else 0
    out["defect_classes_present"] = (Path(repo) / "docs" / "lessons" / "defect-classes.md").is_file()
    return out


def verify_build(repo, solutions, timeout):
    """Opt-in. The only way to observe final functionality instead of reading a claim."""
    if not shutil.which("dotnet"):
        return {"attempted": False, "reason": "dotnet not on PATH"}
    if not solutions:
        return {"attempted": False, "reason": "no .sln found"}
    sln = solutions[0]
    build = sh(["dotnet", "build", sln, "--nologo", "-v", "q"], repo, timeout)
    test = sh(["dotnet", "test", sln, "--nologo", "-v", "q"], repo, timeout) \
        if build["ok"] else {"ok": False, "code": None, "out": "", "err": "skipped: build failed"}
    tail = lambda r: ((r["out"] or "") + "\n" + (r["err"] or "")).strip()[-1500:]
    return {"attempted": True, "solution": sln,
            "build_ok": build["ok"], "build_tail": tail(build),
            "test_ok": test["ok"], "test_tail": tail(test)}


# --------------------------------------------------------------------------- integrity


def integrity(run):
    """Where the report and the record disagree. This is the highest-value output here."""
    findings = []

    def add(sev, claim, observed):
        findings.append({"severity": sev, "claim": claim, "observed": observed})

    report, audit = run["report"], run["audit"]
    coord_facts, tree, git_facts = run["coord"], run["tree"], run["git"]

    if not report.get("present"):
        add("high", "run report required by the prompt", "docs/benchmark/run-report.md absent")
    if report.get("claims_success") and report.get("halt_line"):
        add("high", "report claims SUCCESS", "a BENCHMARK-HALT line is present in the same file")

    claimed = set(report.get("phases_claimed_complete") or [])
    in_audit = set(audit.get("phases_in_audit") or [])
    verified = set(audit.get("phases_verification_executed") or [])
    if claimed - in_audit:
        add("high", "phases reported complete: {}".format(", ".join(sorted(claimed - in_audit))),
            "no successful audit entry names them")
    if claimed - verified:
        add("medium", "phases reported complete: {}".format(", ".join(sorted(claimed - verified))),
            "no audit entry for them records verification_executed=true")
    if claimed and tree.get("source_loc", 0) == 0:
        add("high", "phases reported complete", "zero lines of source in the tree")
    if claimed and tree.get("test_projects", 0) == 0:
        add("high", "phases reported complete under TDD", "no test project found")

    if (coord_facts.get("sessions") or 0) > 1 and (git_facts.get("worktrees_now") or 0) <= 1 \
            and not git_facts.get("branches"):
        add("medium", "{} coordination sessions registered".format(coord_facts["sessions"]),
            "one worktree and no branches remain - trees removed without a record")
    if not coord_facts.get("registry_present"):
        add("high", "coordination required by the prompt",
            ".agents/artifacts.yml absent - the layer never got turned on")
    elif not coord_facts.get("gitattributes_present"):
        add("medium", "artifact registry written",
            ".gitattributes absent - merge drivers were declared nowhere")
    if (audit.get("delegations") or 0) > 0 and (audit.get("delegations_without_budget") or 0) > 0:
        add("medium", "{} delegations recorded".format(audit["delegations"]),
            "{} carry no budget - an unbounded fan-out reads exactly like a well-behaved one"
            .format(audit["delegations_without_budget"]))
    if not tree.get("defect_classes_present"):
        add("low", "continuous improvement is a primary directive",
            "docs/lessons/defect-classes.md was never created")

    fab = (audit.get("fabrication_audit") or []) + (git_facts.get("fabrication_commits") or [])
    if fab:
        add("high", "benchmark integrity (prompt section 7 makes fabrication disqualifying)",
            "{} fabrication/retraction marker(s) in the audit and/or commit record - a delegate "
            "invented data; catching and retracting it does not make the run clean".format(len(fab)))

    build = run.get("build") or {}
    if build.get("attempted") and not build.get("build_ok"):
        add("high", "report describes a working tool", "dotnet build failed in this repo")
    elif build.get("attempted") and build.get("build_ok") and not build.get("test_ok"):
        add("high", "report describes passing tests", "dotnet test failed in this repo")
    return findings


# --------------------------------------------------------------------------- axes


def score_axes(run):
    """Seven axes. A score only where a ratio is defensible; everything else is `judgment`."""
    audit, coord_facts, git_facts = run["audit"], run["coord"], run["git"]
    cont, tree, report = run["contention"], run["tree"], run["report"]
    axes = {}

    def axis(key, values, score=None, judgment=False, note=""):
        axes[key] = {"values": values, "score": score, "judgment": judgment, "note": note}

    # 1. Performance - no absolute scale exists. Reported raw; normalised across the set later.
    axis("performance", {
        "wall_seconds": git_facts.get("wall_seconds"),
        "measured_seconds": audit.get("measured_seconds"),
        "commits": git_facts.get("commits"),
        "lines_added": git_facts.get("lines_added"),
        "audit_entries": audit.get("entries"),
    }, judgment=True, note="relative to this comparison set only; no absolute scale exists")

    # 2. Parallelism - more is not better (GO6: ~15x multiplier). Reported, judged by the skill.
    axis("parallelism", {
        "delegations": audit.get("delegations"),
        "distinct_agents": audit.get("distinct_agents"),
        "peak_concurrency": audit.get("peak_concurrency"),
        "agent_seconds": audit.get("agent_seconds"),
        "span_seconds": audit.get("span_seconds"),
        "speedup": audit.get("speedup"),
        "worktrees_now": git_facts.get("worktrees_now"),
        "branches": len(git_facts.get("branches") or []),
        "tracks_planned": (run["plan"] or {}).get("tracks"),
    }, judgment=True, note="parallelism is a cost multiplier; the question is whether it paid")

    # 3. Coordination - a hygiene ratio over things that are either on or off.
    checks = [
        coord_facts.get("registry_present"),
        coord_facts.get("gitattributes_present"),
        coord_facts.get("precommit_hook_present"),
        bool((run["plan"] or {}).get("present")),
        bool((run["plan"] or {}).get("serial_spine")),
    ]
    known = [c for c in checks if c is not None]
    pct = (coord_facts.get("metrics") or {}).get("edits_under_lease_pct")
    parts = [len([c for c in known if c]) / len(known)] if known else []
    if pct is not None:
        parts.append(float(pct) / 100.0)
    if coord_facts.get("seams_total"):
        parts.append(coord_facts["seams_resolved"] / coord_facts["seams_total"])
    axis("coordination", {
        "registry_present": coord_facts.get("registry_present"),
        "registry_rules": coord_facts.get("registry_rules"),
        "gitattributes": coord_facts.get("gitattributes_present"),
        "pre_commit_hook": coord_facts.get("precommit_hook_present"),
        "sessions_registered": coord_facts.get("sessions"),
        "decisions": (coord_facts.get("metrics") or {}).get("decisions"),
        "refused": (coord_facts.get("metrics") or {}).get("refused"),
        "edits_under_lease_pct": pct,
        "seams_raised": coord_facts.get("seams_total"),
        "seams_resolved": coord_facts.get("seams_resolved"),
        "plan_present": (run["plan"] or {}).get("present"),
        "plan_tracks": (run["plan"] or {}).get("tracks"),
        "plan_struck_tracks": (run["plan"] or {}).get("struck_tracks"),
        "seam_resolution_ratio": coord_facts.get("seam_resolution_ratio"),
        "seam_mean_latency_seconds": coord_facts.get("seam_mean_latency_seconds"),
    }, score=round(sum(parts) / len(parts), 3) if parts else None)

    # 4. Contention - did classification remove it, or did someone resolve it by hand? Scored
    # ONLY where the registry actually answered: an unclassified repo has no contention
    # measurement, and the missing registry is already charged once against coordination. A
    # run with no merges at all is likewise "not recorded" and must not collect a free 1.0.
    examined = cont.get("known_hot_examined") or 0
    measured_hot = [h for h in cont.get("hot_files") or [] if h.get("measured")]
    free_hot = len([h for h in measured_hot if h["class"] in ("derived", "register")])
    contended, free = cont.get("contended_measured") or 0, cont.get("contended_free") or 0
    parts = []
    if examined:
        parts.append(cont["known_hot_correct"] / examined)
    if measured_hot:
        parts.append(free_hot / len(measured_hot))
    if contended:
        parts.append(free / contended)
    axis("contention", {
        "merges_examined": cont.get("merges_examined"),
        "files_contended_in_a_merge": len(cont.get("contended_files") or []),
        "contended_needing_no_human": "{}/{}".format(free, contended) if contended else None,
        "known_hot_classified_right": "{}/{}".format(cont.get("known_hot_correct"), examined)
                                      if examined else None,
        "busiest_files_needing_no_coordination":
            "{}/{}".format(free_hot, len(measured_hot)) if measured_hot else None,
        "conflict_labelled_commits": len(git_facts.get("conflict_commits") or []),
    }, score=round(sum(parts) / len(parts), 3) if parts else None,
        note="scored only where the artifact registry answered; a run with no merges and a "
             "run that never classified both read as not recorded, for different reasons")

    # 5. Task focus - the goal-state presence signal, straight from the pack's own selfcheck.
    self_check = audit.get("selfcheck") or {}
    subst = self_check.get("substantive") or audit.get("substantive") or 0
    parts = []
    if subst:
        parts.append(max(0.0, 1.0 - (self_check.get("goal_state_gaps") or 0) / subst))
        parts.append(max(0.0, 1.0 - (self_check.get("tier_gaps") or 0) / subst))
        parts.append(max(0.0, 1.0 - (self_check.get("over_cap") or 0) / subst))
    if audit.get("delegations"):
        parts.append(1.0 - min((audit.get("delegations_without_budget") or 0) /
                               audit["delegations"], 1.0))
    axis("task_focus", {
        "substantive_turns": subst,
        "goal_state_gaps": self_check.get("goal_state_gaps"),
        "tier_gaps": self_check.get("tier_gaps"),
        "fan_out_over_cap": self_check.get("over_cap"),
        "delegations_without_budget": audit.get("delegations_without_budget"),
        "delegations_over_budget": audit.get("delegations_over_budget"),
    }, score=round(sum(parts) / len(parts), 3) if parts else None)

    # 6. Drift - extraction only. Whether a summary drifted from its done_when is a reading.
    axis("drift", {
        "review_pairs": len(self_check.get("review_pairs") or []),
        "unexpected_skills": audit.get("unexpected_skills"),
        "delegations_over_budget": audit.get("delegations_over_budget"),
        "conflict_commits": len(git_facts.get("conflict_commits") or []),
    }, judgment=True, note="done_when -> summary pairs are in the JSON; judge each one")

    # 7. Final functionality - phases with EXECUTED verification, out of seven.
    verified = len(audit.get("phases_verification_executed") or [])
    build = run.get("build") or {}
    parts = [verified / len(PHASES)]
    if build.get("attempted"):
        parts.append(1.0 if build.get("test_ok") else (0.5 if build.get("build_ok") else 0.0))
    axis("functionality", {
        "phases_claimed_complete": report.get("phases_claimed_complete"),
        "phases_in_audit": audit.get("phases_in_audit"),
        "phases_verification_executed": audit.get("phases_verification_executed"),
        "source_loc": tree.get("source_loc"),
        "projects": tree.get("projects"),
        "test_projects": tree.get("test_projects"),
        "specs": tree.get("spec_count"),
        "adrs": tree.get("adr_count"),
        "build_ok": build.get("build_ok") if build.get("attempted") else None,
        "test_ok": build.get("test_ok") if build.get("attempted") else None,
    }, score=round(sum(parts) / len(parts), 3))
    return axes


def collect_derived(run):
    """Deterministic ratios built from facts already collected. These sharpen the two questions
    the raw axes leave open - 'how much of this volume was real output?' and 'what did a phase
    actually cost?' - and they feed the comparison radar. A ratio with a zero denominator is
    'not recorded' (None), never a fabricated zero (IO8)."""
    audit = run.get("audit") or {}
    report = run.get("report") or {}
    git = run.get("git") or {}
    integ = run.get("integrity") or []
    axes = run.get("axes") or {}
    quality = run.get("quality") or {}

    demonstrated = len(audit.get("phases_verification_executed") or [])
    claimed = len(report.get("phases_claimed_complete") or [])
    measured = audit.get("measured_seconds") or 0

    high = sum(1 for i in integ if i.get("severity") == "high")
    med = sum(1 for i in integ if i.get("severity") == "medium")
    integrity_score = max(0.0, round(1.0 - 0.34 * high - 0.10 * med, 3))

    # Addition #1 - fabrication events, and #3 - halt honesty (does the stated outcome match the
    # record?). Honesty is not verification: an honest halt that says "P0 done, P1 not, P2-P6 not
    # started" scores full marks even if a phase lacks a structured signal. What it punishes is
    # claiming SUCCESS while incomplete, or claiming far more complete than the record demonstrates.
    fab_events = len(audit.get("fabrication_audit") or []) + len(git.get("fabrication_commits") or [])
    demonstrated_set = set(audit.get("phases_verification_executed") or [])
    claimed_set = set(report.get("phases_claimed_complete") or [])
    terminal = bool(report.get("halt_line") or report.get("halt_declared")
                    or report.get("claims_success"))
    excess = max(0, len(claimed_set - demonstrated_set) - 1)   # allow the one halted-at phase
    hh = 1.0
    if not terminal:
        hh -= 0.5
    if report.get("claims_success") and demonstrated < len(PHASES):
        hh -= 0.6
    hh -= 0.2 * excess
    halt_honesty = round(max(0.0, min(1.0, hh)), 3)

    # Derived/register artifacts are bookkeeping, not product. Their churn inflates the
    # line count without moving the build forward, so the authored share is the honest signal.
    bookkeeping = ("docs-index.js", "audit-data.js", "audit-log.jsonl", "change-log.jsonl")
    churn = git.get("top_churn") or []
    total_touch = sum(n for _, n in churn)
    book_touch = sum(n for f, n in churn if any(f.endswith(b) for b in bookkeeping))
    authored_churn_ratio = round((total_touch - book_touch) / total_touch, 3) if total_touch else None

    dele = audit.get("delegations") or 0
    budget_issues = (audit.get("delegations_without_budget") or 0) + \
                    (audit.get("delegations_over_budget") or 0)
    delegation_discipline = round(max(0.0, 1.0 - budget_issues / dele), 3) if dele else None

    added = git.get("lines_added") or 0
    deleted = git.get("lines_deleted") or 0

    def sc(key):
        return (axes.get(key) or {}).get("score")

    return {
        "demonstrated_phases": demonstrated,
        "claimed_phases": claimed,
        "demonstration_ratio": round(demonstrated / len(PHASES), 3),
        "verification_density": round(demonstrated / claimed, 3) if claimed else None,
        "integrity_score": integrity_score,
        "high_findings": high,
        "medium_findings": med,
        "cost_per_demonstrated_phase_seconds": round(measured / demonstrated, 1) if demonstrated else None,
        "commits_per_demonstrated_phase": round((git.get("commits") or 0) / demonstrated, 1) if demonstrated else None,
        "authored_churn_ratio": authored_churn_ratio,
        "rework_ratio": round(deleted / added, 3) if added else None,
        "delegation_discipline": delegation_discipline,
        "parallel_speedup": audit.get("speedup"),
        "worktrees_now": git.get("worktrees_now"),
        "fabrication_events": fab_events,
        "halt_honesty": halt_honesty,
        "owner_reviews_present": len(audit.get("owner_reviews") or []),
        "seam_resolution_ratio": (run.get("coord") or {}).get("seam_resolution_ratio"),
        "review_rigor": quality.get("review_rigor_score"),
        "distinct_delegate_models": (quality.get("model_allocation") or {}).get("distinct_models"),
        "vetoes_raised": (quality.get("veto_ledger") or {}).get("vetoes"),
        "red_first_hits": quality.get("red_first_hits"),
        "coordinator_verifications": quality.get("coordinator_verification_hits"),
        "self_corrections": quality.get("self_correction_hits"),
        "oracle_mutation_hits": quality.get("oracle_mutation_hits"),
        "defect_class_conversion": quality.get("defect_class_conversion"),
        "phase_order_inversions": quality.get("phase_order_inversions"),
        # The rethought radar: seven deterministic 0..1 spokes, each higher-is-better and as
        # orthogonal as the data allows. The old radar plotted Functionality and Phase-demo, which
        # were the SAME number (both demonstrated/7) - a wasted spoke. It is replaced by
        # Completeness (what was demonstrated), Verification (did the claims have evidence),
        # Efficiency (real output vs bookkeeping churn) and Honesty (did the outcome match the
        # record). Judgment axes are still excluded - no defensible ratio exists for them.
        "radar": {
            "Completeness": round(demonstrated / len(PHASES), 3),
            "Verification": round(demonstrated / claimed, 3) if claimed else 0.0,
            "Integrity": integrity_score,
            "Coordination": sc("coordination"),
            "Task focus": sc("task_focus"),
            "Efficiency": authored_churn_ratio,
            "Honesty": halt_honesty,
            "Review rigor": quality.get("review_rigor_score"),
        },
    }


def collect_quality(repo, run):
    """Deterministic quality signals scanned from the audit + commit corpus and the tree
    (proposals #3-#10). Corpus scans are heuristic but reproducible; every count degrades to
    zero, never to a fabricated value. The model behind a delegate is read from the agent name
    (e.g. 'plan-review-sonnet'), which is the only place the audit records it."""
    audit = run.get("audit") or {}
    git_facts = run.get("git") or {}
    entries = audit.get("entries_slim") or []
    corpus = [" ".join(str(e.get(k) or "") for k in ("shortname", "summary", "done_when"))
              for e in entries] + (git_facts.get("commit_log") or [])

    # #3 delegate model allocation.
    model_counts, named = {}, 0
    for e in entries:
        for name in e.get("agents") or []:
            named += 1
            m = MODEL_RE.search(name)
            key = m.group(0).lower() if m else "unspecified"
            model_counts[key] = model_counts.get(key, 0) + 1
    distinct_models = len([k for k in model_counts if k != "unspecified"])

    # #4 adversarial-review / veto ledger.
    veto_events = []
    for text in corpus:
        for vm in VETO_RE.finditer(text):
            win = text[max(0, vm.start() - 48): vm.end() + 48]
            mm, pm = MODEL_RE.search(win), re.search(r"\b[Pp][0-6]\b|\bS[0-9]\b", win)
            veto_events.append({"verdict": vm.group(0).upper(),
                                "model": mm.group(0).lower() if mm else None,
                                "where": pm.group(0).upper() if pm else None})
    vetoes = [v for v in veto_events if v["verdict"] in ("VETO", "BLOCK", "BLOCKER")]
    clears = [v for v in veto_events if v["verdict"] in ("CLEAR", "PASS", "APPROVE", "APPROVED")]
    reviewer_models = sorted(set(v["model"] for v in veto_events if v["model"]))

    # #5 oracle/mutation, #6 red-first, #8 coordinator verification, #9 self-correction.
    oracle_hits = sum(1 for t in corpus if ORACLE_RE.search(t))
    red_first_hits = sum(1 for t in corpus if RED_FIRST_RE.search(t))
    coord_verify_hits = sum(1 for t in corpus if COORD_VERIFY_RE.search(t))
    self_correct_hits = sum(1 for t in corpus if SELF_CORRECT_RE.search(t))

    # #7 defect-class control conversion.
    dc = read_text(Path(repo) / "docs" / "lessons" / "defect-classes.md") or ""
    dc_classes = len(re.findall(r"(?m)^###\s+\S", dc))
    dc_uncontrolled = len(re.findall(r"NONE YET|uncontrolled", dc, re.I))
    dc_conversion = round(max(0, dc_classes - dc_uncontrolled) / dc_classes, 3) if dc_classes else None

    # #10 phase ordering: earliest-seen order vs canonical, and inversions.
    pv = git_facts.get("phase_velocity") or {}
    by_time = sorted([p for p in PHASES if p in pv], key=lambda p: pv[p])
    inversions = sum(1 for i in range(len(by_time)) for j in range(i + 1, len(by_time))
                     if PHASES.index(by_time[i]) > PHASES.index(by_time[j]))

    review_rigor = round(min(1.0, (len(veto_events) / 8.0)
                             * (1.0 if len(reviewer_models) >= 2 else 0.7)), 3) if veto_events else 0.0
    return {
        "model_allocation": {"counts": model_counts, "distinct_models": distinct_models,
                             "delegations_named": named},
        "veto_ledger": {"events": veto_events[:40], "vetoes": len(vetoes), "clears": len(clears),
                        "reviewer_models": reviewer_models},
        "review_rigor_score": review_rigor,
        "oracle_mutation_hits": oracle_hits,
        "red_first_hits": red_first_hits,
        "coordinator_verification_hits": coord_verify_hits,
        "self_correction_hits": self_correct_hits,
        "defect_classes": dc_classes,
        "defect_class_conversion": dc_conversion,
        "phase_order_seen": by_time,
        "phase_order_inversions": inversions,
    }


def grade_run(repo, name, do_build, build_timeout):
    run = {"identity": collect_identity(repo, name)}
    if not run["identity"]["exists"]:
        run["error"] = "path does not exist"
        return run
    run["git"] = collect_git(repo)
    run["audit"] = collect_audit(repo)
    run["coord"] = collect_coord(repo)
    run["contention"] = collect_contention(repo, run["git"].get("top_churn"))
    run["plan"] = collect_plan(repo)
    run["report"] = collect_report(repo)
    run["tree"] = collect_tree(repo)
    run["build"] = verify_build(repo, run["tree"].get("solutions"), build_timeout) \
        if do_build else {"attempted": False, "reason": "not requested"}
    run["outcome"] = ("HALT" if (run["report"].get("halt_line") or run["report"].get("halt_declared"))
                      else "SUCCESS" if run["report"].get("claims_success")
                      else "not recorded")
    run["axes"] = score_axes(run)
    run["integrity"] = integrity(run)
    run["quality"] = collect_quality(repo, run)

    # #2 snapshot pin + live-run detector, #11 cross-harness cost proxies.
    last = parse_iso((run["git"] or {}).get("last_commit"))
    age_h = round((datetime.now(timezone.utc) - last).total_seconds() / 3600, 1) if last else None
    status = git(repo, "status", "--porcelain")
    dirty = bool(status["ok"] and status["out"].strip())
    run["snapshot"] = {
        "graded_sha": (run["identity"] or {}).get("head"),
        "last_commit": (run["git"] or {}).get("last_commit"),
        "last_commit_age_hours": age_h,
        "working_tree_dirty": dirty,
        "run_active": bool(dirty or (age_h is not None and age_h < 12)),
    }
    run["cost"] = {
        "native_unit": "not recorded (harness token/AIU store not read by the grader)",
        "wall_seconds": (run["git"] or {}).get("wall_seconds"),
        "measured_seconds": (run["audit"] or {}).get("measured_seconds"),
        "commits": (run["git"] or {}).get("commits"),
        "lines_added": (run["git"] or {}).get("lines_added"),
        "reasoning_visibility": "not recorded",
    }

    run["derived"] = collect_derived(run)
    (run.get("audit") or {}).pop("entries_slim", None)   # scratch data, kept out of the payload
    (run.get("git") or {}).pop("commit_log", None)
    scored = [a["score"] for a in run["axes"].values() if a["score"] is not None]
    run["deterministic_floor"] = round(sum(scored) / len(scored), 3) if scored else None
    run["axes_not_scored"] = sorted(k for k, a in run["axes"].items() if a["score"] is None)
    return run


# --------------------------------------------------------------------------- rendering


def humanize(seconds):
    """Seconds as something a reader can compare at a glance, with the raw value kept."""
    seconds = float(seconds)
    if seconds < 90:
        return "{:.0f}s".format(seconds)
    if seconds < 5400:
        return "{:.0f}m".format(seconds / 60)
    if seconds < 172800:
        return "{:.1f}h".format(seconds / 3600)
    return "{:.1f}d".format(seconds / 86400)


def fmt(value, key=None):
    if value is None:
        return "not recorded"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if key and key.endswith(("_seconds", " seconds")) and isinstance(value, (int, float)):
        return "{} ({:,.0f}s)".format(humanize(value), value)
    if isinstance(value, float):
        return "{:g}".format(round(value, 3))
    if isinstance(value, int):
        return "{:,}".format(value)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "none"
    return str(value)


def render_text(runs):
    names = [r["identity"]["name"] for r in runs]
    width = max([12] + [len(n) for n in names])
    lines = ["", "BENCHMARK COMPARISON - {} run(s)".format(len(runs)), ""]

    def row(label, values):
        lines.append("  {:<28}".format(label[:28]) +
                     "".join("{:<{w}}".format(str(v)[:width + 2], w=width + 4) for v in values))

    row("", names)
    lines.append("  " + "-" * (28 + (width + 4) * len(names)))
    row("outcome", [r.get("outcome", "?") for r in runs])
    row("pack revision", [fmt(r["identity"].get("pack_revision")) for r in runs])
    row("deterministic floor", [fmt(r.get("deterministic_floor")) for r in runs])
    lines.append("")
    for key in ("performance", "parallelism", "coordination", "contention",
                "task_focus", "drift", "functionality"):
        marks = []
        for r in runs:
            axis = (r.get("axes") or {}).get(key) or {}
            marks.append("judgment" if axis.get("judgment") else fmt(axis.get("score")))
        row(key, marks)
    lines.append("")
    for run in runs:
        lines.append("  {} - integrity findings: {}".format(
            run["identity"]["name"], len(run.get("integrity") or []) or "none"))
        for finding in (run.get("integrity") or [])[:12]:
            lines.append("      [{}] {} -> {}".format(
                finding["severity"], finding["claim"], finding["observed"]))
    halted = [r for r in runs if r.get("outcome") == "HALT"]
    if halted:
        lines.append("")
        for run in halted:
            lines.append("  HALT {}: {}".format(run["identity"]["name"],
                                                run["report"].get("halt_line")))
    lines.append("")
    lines.append("  The floor is a floor, not a grade: it averages only the axes with a")
    lines.append("  defensible ratio. Axes marked `judgment` are for /grade-benchmarks to rule on.")
    lines.append("")
    return "\n".join(lines)


AXIS_TITLES = [
    ("performance", "Performance"), ("parallelism", "Parallelism"),
    ("coordination", "Coordination"), ("contention", "Contention"),
    ("task_focus", "Task focus"), ("drift", "Drift"), ("functionality", "Final functionality"),
]


def render_verdict_markdown(verdict):
    """The grader's ruling, in the canonical view. Same content as the interactive one."""
    if not verdict:
        return []
    out = ["## Ranking", ""]
    ranking = verdict.get("ranking") or []
    for i, row in enumerate(ranking, 1):
        out.append("{}. **{}** - {}".format(i, row.get("run", "?"), row.get("why", "")))
    if not ranking:
        out.append("*No ranking recorded.*")
    out.append("")
    if verdict.get("downgrades"):
        out += ["### Downgrades - reported complete, evidence absent", "",
                "| run | phase | missing evidence |", "|---|---|---|"]
        for d in verdict["downgrades"]:
            out.append("| {} | {} | {} |".format(d.get("run", ""), d.get("phase", ""),
                                                 d.get("missing", "")))
        out.append("")
    if verdict.get("learned"):
        out += ["### What the pack should learn", ""]
        out += ["- " + str(x) for x in verdict["learned"]]
        out.append("")
    return out


def render_markdown(runs, generated, verdict=None):
    names = [r["identity"]["name"] for r in runs]
    head = "| metric | " + " | ".join(names) + " |"
    rule = "|---" * (len(names) + 1) + "|"
    out = ["# Benchmark comparison", "",
           "Generated {}. Extraction is deterministic; the axes marked **judgment** carry no".format(generated),
           "score because no defensible ratio exists for them - they are for the grader to rule on.",
           ""] + render_verdict_markdown(verdict) + ["## Summary", "", head, rule]

    def row(label, values):
        out.append("| {} | ".format(label) + " | ".join(fmt(v, label) for v in values) + " |")

    row("outcome", [r.get("outcome") for r in runs])
    row("pack revision", [r["identity"].get("pack_revision") for r in runs])
    row("coordination skills installed", [r["identity"].get("has_coordination_skills") for r in runs])
    row("integrity findings", [len(r.get("integrity") or []) for r in runs])
    row("deterministic floor", [r.get("deterministic_floor") for r in runs])
    out.append("")

    out += ["## Derived metrics", "",
            "*Deterministic ratios. 'Demonstration' and 'integrity' are the radar's two non-axis "
            "spokes; a zero-denominator ratio reads 'not recorded', never a fabricated zero.*", "",
            head, rule]
    derived_rows = [
        ("demonstrated / claimed phases",
         lambda d: "{} / {}".format(d.get("demonstrated_phases"), d.get("claimed_phases"))),
        ("demonstration ratio (of 7)", lambda d: d.get("demonstration_ratio")),
        ("verification density (demo/claimed)", lambda d: d.get("verification_density")),
        ("integrity score", lambda d: d.get("integrity_score")),
        ("high / medium findings",
         lambda d: "{} / {}".format(d.get("high_findings"), d.get("medium_findings"))),
        ("cost per demonstrated phase", lambda d: d.get("cost_per_demonstrated_phase_seconds")),
        ("commits per demonstrated phase", lambda d: d.get("commits_per_demonstrated_phase")),
        ("authored churn ratio (vs bookkeeping)", lambda d: d.get("authored_churn_ratio")),
        ("rework ratio (deleted/added)", lambda d: d.get("rework_ratio")),
        ("delegation budget discipline", lambda d: d.get("delegation_discipline")),
        ("parallel speedup", lambda d: d.get("parallel_speedup")),
        ("worktrees open at grade time", lambda d: d.get("worktrees_now")),
        ("halt honesty", lambda d: d.get("halt_honesty")),
        ("fabrication/retraction events", lambda d: d.get("fabrication_events")),
        ("phases with owner review", lambda d: d.get("owner_reviews_present")),
        ("seam resolution ratio", lambda d: d.get("seam_resolution_ratio")),
        ("review rigor", lambda d: d.get("review_rigor")),
        ("distinct delegate models", lambda d: d.get("distinct_delegate_models")),
        ("vetoes raised", lambda d: d.get("vetoes_raised")),
        ("red-first signals", lambda d: d.get("red_first_hits")),
        ("coordinator verifications", lambda d: d.get("coordinator_verifications")),
        ("in-flight self-corrections", lambda d: d.get("self_corrections")),
        ("oracle/mutation signals", lambda d: d.get("oracle_mutation_hits")),
        ("defect-class control conversion", lambda d: d.get("defect_class_conversion")),
        ("phase-order inversions", lambda d: d.get("phase_order_inversions")),
    ]
    for label, get in derived_rows:
        unit = "_seconds" if "cost per demonstrated phase" in label else label
        out.append("| {} | ".format(label) + " | ".join(
            fmt(get(r.get("derived") or {}), unit) for r in runs) + " |")
    out.append("")

    # Addition #6 - the auto-drafted per-phase evidence, with #2 (owner review) and #4 (span).
    out += ["## Per-phase evidence", "",
            "*Auto-drafted from the audit: for each phase, whether it carries an executed "
            "verification signal, whether an owner-review entry accepted it, its audit time-span, "
            "and the done_when -> summary the grader should quote. Edit, do not trust blindly.*", ""]
    for run in runs:
        out += ["### {}".format(run["identity"]["name"]), ""]
        narr = (run.get("audit") or {}).get("phase_narrative") or []
        tl = (run.get("audit") or {}).get("phase_timeline") or {}
        if not narr:
            out += ["No per-phase audit entries found.", ""]
            continue
        out += ["| phase | verified | owner review | audit span | evidence summary |",
                "|---|---|---|---|---|"]
        for n in narr:
            span = tl.get(n["phase"])
            out.append("| {} | {} | {} | {} | {} |".format(
                n["phase"], "yes" if n.get("verified") else "no",
                "yes" if n.get("owner_reviewed") else "no",
                fmt(span, "_seconds") if span is not None else "not recorded",
                (n.get("summary") or "").replace("|", "\\|")[:200]))
        out.append("")

    # Addition #1 - fabrication/retraction markers surfaced explicitly.
    out += ["## Fabrication & retraction markers", ""]
    any_fab = False
    for run in runs:
        fa = (run.get("audit") or {}).get("fabrication_audit") or []
        fc = (run.get("git") or {}).get("fabrication_commits") or []
        if not fa and not fc:
            continue
        any_fab = True
        out += ["### {}".format(run["identity"]["name"]),
                "*{} marker(s). Section 7 makes fabrication disqualifying; a clean retraction does "
                "not make the run clean.*".format(len(fa) + len(fc)), ""]
        for f in fa:
            out.append("- audit `{}`: '{}' ({})".format(
                f.get("shortname"), f.get("marker"), f.get("when")))
        for c in fc:
            out.append("- commit: {}".format(str(c).replace("|", "\\|")))
        out.append("")
    if not any_fab:
        out += ["No fabrication or retraction markers found in the audit or commit record.", ""]

    # #2 snapshot / activity and #1 delta.
    out += ["## Snapshot, activity & delta", "", head, rule]

    def qrow(label, fn):
        out.append("| {} | ".format(label) + " | ".join(fmt(fn(r)) for r in runs) + " |")

    qrow("graded SHA", lambda r: (r.get("snapshot") or {}).get("graded_sha"))
    qrow("run active (provisional)", lambda r: (r.get("snapshot") or {}).get("run_active"))
    qrow("last commit age (h)", lambda r: (r.get("snapshot") or {}).get("last_commit_age_hours"))
    qrow("working tree dirty", lambda r: (r.get("snapshot") or {}).get("working_tree_dirty"))

    def _d(r, key):
        return ((r.get("delta") or {}).get(key) or {}).get("delta") if r.get("delta") else None
    qrow("\u0394 demonstrated phases", lambda r: _d(r, "demonstrated_phases"))
    qrow("\u0394 deterministic floor", lambda r: _d(r, "deterministic_floor"))
    qrow("\u0394 commits (vs prior grade)", lambda r: _d(r, "commits"))
    out += ["", "*A grade is a snapshot at the graded SHA. 'run active' means the working tree is "
            "dirty or a commit landed within 12h - the grade is then provisional. \u0394 is versus the "
            "most recent prior grade of the same run in this folder (blank if none).*", ""]

    # #3 / #4 delegate models & veto ledger.
    out += ["## Delegate models & veto ledger", ""]
    for run in runs:
        q = run.get("quality") or {}
        ma, vl = (q.get("model_allocation") or {}), (q.get("veto_ledger") or {})
        out += ["### {}".format(run["identity"]["name"]), "",
                "- delegate model mix: {}".format(", ".join(
                    "{} x{}".format(k, v) for k, v in sorted((ma.get("counts") or {}).items()))
                    or "none recorded"),
                "- reviewer models in verdicts: {}".format(
                    ", ".join(vl.get("reviewer_models") or []) or "none"),
                "- vetoes raised: {} | clears: {}".format(vl.get("vetoes"), vl.get("clears")), ""]
        events = vl.get("events") or []
        if events:
            out += ["| verdict | reviewer model | where |", "|---|---|---|"]
            for ev in events[:20]:
                out.append("| {} | {} | {} |".format(
                    ev.get("verdict"), ev.get("model") or "-", ev.get("where") or "-"))
            out.append("")

    # #12 phase velocity, with #10 ordering.
    out += ["## Phase velocity", ""]
    for run in runs:
        pv = (run.get("git") or {}).get("phase_velocity") or {}
        q = run.get("quality") or {}
        if not pv:
            out += ["### {} - no phase-tagged commits".format(run["identity"]["name"]), ""]
            continue
        out += ["### {}".format(run["identity"]["name"]),
                "Seen order {} ({} inversions vs P0..P6).".format(
                    " -> ".join(q.get("phase_order_seen") or []) or "none",
                    q.get("phase_order_inversions")), "",
                "| phase | first commit |", "|---|---|"]
        for p in PHASES:
            if p in pv:
                out.append("| {} | {} |".format(p, pv[p]))
        out.append("")

    for key, title in AXIS_TITLES:
        out += ["## {}".format(title), ""]
        axis0 = (runs[0].get("axes") or {}).get(key) or {}
        if axis0.get("note"):
            out += ["*{}*".format(axis0["note"]), ""]
        out += [head, rule]
        row("score", ["judgment" if ((r["axes"].get(key) or {}).get("judgment"))
                      else (r["axes"].get(key) or {}).get("score") for r in runs])
        keys = []
        for run in runs:
            for k in ((run["axes"].get(key) or {}).get("values") or {}):
                if k not in keys:
                    keys.append(k)
        for k in keys:
            row(k, [((r["axes"].get(key) or {}).get("values") or {}).get(k) for r in runs])
        out.append("")
        judged = ((verdict or {}).get("judgment") or {}).get(key) or {}
        for run in runs:
            text = judged.get(run["identity"]["name"])
            if text:
                out += ["**{}** - {}".format(run["identity"]["name"], text), ""]

    out += ["## Integrity - claimed vs observed", ""]
    for run in runs:
        out += ["### {}".format(run["identity"]["name"]), ""]
        findings = run.get("integrity") or []
        if not findings:
            out += ["No divergence found between the run report and the record.", ""]
            continue
        out += ["| severity | claim | observed |", "|---|---|---|"]
        for f in findings:
            out.append("| {} | {} | {} |".format(f["severity"], f["claim"], f["observed"]))
        out.append("")

    halted = [r for r in runs if r.get("outcome") == "HALT"]
    if halted:
        out += ["## Halts", ""]
        for run in halted:
            out.append("- **{}**: {}".format(run["identity"]["name"],
                run["report"].get("halt_line")
                or "declared HALT in the report body (no BENCHMARK-HALT marker line)"))
        out.append("")
    return "\n".join(out)


PAGE = r"""<title>Benchmark comparison</title>
<style>
:root{
  --bg:#faf9f7; --panel:#ffffff; --panel-2:#f4f2ee; --ink:#191817; --muted:#6d6a65;
  --line:#e3dfd8; --line-2:#cfc9bf; --accent:#8a4b2a; --accent-ink:#fff;
  --hi:#a3301c; --med:#8a6410; --lo:#4f6377; --ok:#2c6a45; --bar:#c8a68c;
  --focus:#8a4b2a;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#121212; --panel:#1a1a19; --panel-2:#222220; --ink:#eceae7; --muted:#9b9791;
  --line:#2d2c2a; --line-2:#3d3b38; --accent:#d59468; --accent-ink:#1a1a19;
  --hi:#e4796a; --med:#d9ab44; --lo:#93a7b8; --ok:#6fc294; --bar:#6a5140;
  --focus:#d59468;
}}
:root[data-theme="dark"]{
  --bg:#121212; --panel:#1a1a19; --panel-2:#222220; --ink:#eceae7; --muted:#9b9791;
  --line:#2d2c2a; --line-2:#3d3b38; --accent:#d59468; --accent-ink:#1a1a19;
  --hi:#e4796a; --med:#d9ab44; --lo:#93a7b8; --ok:#6fc294; --bar:#6a5140;
  --focus:#d59468;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);margin:0;
  font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px;border-radius:4px}
main{max-width:1180px;margin:0 auto;padding:0 1.25rem 6rem}

header.top{position:sticky;top:0;z-index:30;background:var(--bg);
  border-bottom:1px solid var(--line);padding:1.5rem 0 .85rem;margin-bottom:0}
header.top .inner{max-width:1180px;margin:0 auto;padding:0 1.25rem}
h1{font-size:1.75rem;letter-spacing:-.021em;margin:0 0 .2rem;font-weight:640}
.meta{color:var(--muted);font-size:13px;margin:0 0 .85rem}
.controls{display:flex;flex-wrap:wrap;gap:.45rem;align-items:center}
button.ctl,label.ctl{background:var(--panel);color:var(--ink);border:1px solid var(--line-2);
  border-radius:999px;padding:.32rem .8rem;font:inherit;font-size:12.5px;cursor:pointer;
  display:inline-flex;align-items:center;gap:.4rem;line-height:1.4}
button.ctl:hover{border-color:var(--accent)}
button.ctl[aria-pressed="true"]{background:var(--accent);color:var(--accent-ink);
  border-color:var(--accent)}
button.ctl[hidden]{display:none}
input.search{background:var(--panel);color:var(--ink);border:1px solid var(--line-2);
  border-radius:999px;padding:.34rem .85rem;font:inherit;font-size:12.5px;min-width:15rem}
.spacer{flex:1 1 2rem}

nav.axes{position:sticky;top:0;z-index:20;background:var(--bg);padding:.6rem 0 .7rem;
  border-bottom:1px solid var(--line);margin-bottom:1.6rem;
  display:flex;flex-wrap:wrap;gap:.35rem}
nav.axes a{color:var(--muted);text-decoration:none;font-size:12.5px;border-radius:999px;
  padding:.26rem .7rem;border:1px solid transparent}
nav.axes a:hover{color:var(--ink);border-color:var(--line-2)}

section{scroll-margin-top:5rem}
h2{font-size:.82rem;letter-spacing:.09em;text-transform:uppercase;color:var(--accent);
  margin:2.6rem 0 .3rem;font-weight:660}
h3{font-size:1rem;margin:1.5rem 0 .5rem;font-weight:620}
p.note{color:var(--muted);font-size:13px;max-width:74ch;margin:.15rem 0 .85rem}
p.note.ok{color:var(--ok)}

.wrap{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:12px}
table{border-collapse:separate;border-spacing:0;width:100%;font-size:13.5px}
th,td{text-align:left;padding:.5rem .85rem;border-bottom:1px solid var(--line);
  white-space:nowrap;vertical-align:top}
thead th{position:sticky;top:0;background:var(--panel);z-index:2;font-weight:620;
  color:var(--muted);font-size:11.5px;letter-spacing:.05em;text-transform:uppercase}
thead th.run{cursor:pointer;color:var(--ink);text-transform:none;font-size:13px;
  letter-spacing:0}
thead th.run:hover{color:var(--accent)}
th.metric,td.metric{position:sticky;left:0;background:var(--panel);z-index:1;
  white-space:normal;min-width:16rem;color:var(--muted)}
thead th.metric{z-index:3}
tbody tr:hover td{background:var(--panel-2)}
tbody tr:hover td.metric{background:var(--panel-2)}
tr:last-child td{border-bottom:0}
td.pin,th.pin{background:var(--panel-2)}
.n{color:var(--muted)}
.j{color:var(--med);font-style:italic}
.num{font-variant-numeric:tabular-nums}

.score{display:flex;align-items:center;gap:.5rem}
.bar{flex:0 0 4.5rem;height:5px;border-radius:3px;background:var(--line);overflow:hidden}
.bar i{display:block;height:100%;background:var(--bar);border-radius:3px}

.sev{font-weight:660;text-transform:uppercase;font-size:10.5px;letter-spacing:.06em}
.sev.high{color:var(--hi)} .sev.medium{color:var(--med)} .sev.low{color:var(--lo)}
.badge{display:inline-flex;align-items:center;justify-content:center;min-width:1.35rem;
  padding:0 .35rem;height:1.35rem;border-radius:999px;background:var(--panel-2);
  color:var(--muted);font-size:11px;font-weight:640;margin-left:.35rem}
.badge.hi{background:var(--hi);color:#fff}

.halt{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--hi);
  border-radius:10px;padding:.75rem 1rem;margin:.5rem 0}
.halt strong{color:var(--hi)}

details.run{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  margin:.6rem 0;overflow:hidden}
details.run>summary{cursor:pointer;padding:.75rem 1rem;font-weight:600;list-style:none;
  display:flex;align-items:center;gap:.6rem}
details.run>summary::-webkit-details-marker{display:none}
details.run>summary::before{content:"\25B8";color:var(--muted);transition:transform .12s}
details.run[open]>summary::before{transform:rotate(90deg)}
details.run>summary:hover{background:var(--panel-2)}
.body{padding:.2rem 1rem 1rem;border-top:1px solid var(--line)}
.kv{display:grid;grid-template-columns:minmax(9rem,auto) 1fr;gap:.15rem .9rem;
  font-size:13px;margin:.5rem 0 1rem}
.kv dt{color:var(--muted)} .kv dd{margin:0}
pre{background:var(--panel-2);border:1px solid var(--line);border-radius:8px;
  padding:.7rem .85rem;overflow-x:auto;font-size:12px;line-height:1.5;margin:.4rem 0 1rem;
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.pair{border-left:2px solid var(--line-2);padding:.1rem 0 .1rem .8rem;margin:.7rem 0}
.pair .dw{color:var(--muted);font-size:12.5px}
.pair .sm{font-size:13px;margin-top:.2rem}
.empty{color:var(--muted);font-size:13px;font-style:italic;padding:.4rem 0}
ol.rank{padding-left:1.3rem;margin:.4rem 0 1.4rem}
ol.rank li{margin:.5rem 0;padding-left:.2rem}
ol.rank li::marker{color:var(--accent);font-weight:660}
ol.rank .sm{color:var(--muted);font-size:13px;margin-top:.15rem;max-width:76ch}
ul.learned{margin:.3rem 0 1.2rem;padding-left:1.2rem;max-width:76ch}
ul.learned li{margin:.35rem 0}

footer{margin-top:3.5rem;padding-top:1.2rem;border-top:1px solid var(--line);
  color:var(--muted);font-size:12.5px;max-width:76ch}
noscript{display:block;background:var(--panel);border:1px solid var(--hi);border-radius:10px;
  padding:1rem;margin:1.5rem 0}
@media (max-width:640px){
  th.metric,td.metric{position:static;min-width:11rem}
  h1{font-size:1.4rem}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>

<header class="top"><div class="inner">
  <h1>Benchmark comparison</h1>
  <p class="meta" id="meta"></p>
  <div class="controls" id="controls"></div>
</div></header>

<main>
<noscript><strong>This report is interactive and needs JavaScript.</strong> The canonical
static view is the <code>.md</code> file written beside it, which carries the same content.</noscript>
<nav class="axes" id="nav"></nav>
<div id="app"></div>
<footer id="foot"></footer>
</main>

<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
(function(){
"use strict";
var D = JSON.parse(document.getElementById("payload").textContent);
var RUNS = D.runs || [];
var AXES = [["performance","Performance"],["parallelism","Parallelism"],
            ["coordination","Coordination"],["contention","Contention"],
            ["task_focus","Task focus"],["drift","Drift"],
            ["functionality","Final functionality"]];

var S = {diff:false, q:"", hidden:{}, pin:null, sev:{high:true,medium:true,low:true}};
var CTLS = [];   /* every toggle, with a reader for its own state (see syncControls) */
var V = D.verdict || null;   /* the grader's ruling, merged in by --verdict */

/* ---- formatting: mirrors fmt() in grade-benchmarks.py ---- */
function humanize(s){
  s = Number(s);
  if(s < 90) return s.toFixed(0)+"s";
  if(s < 5400) return (s/60).toFixed(0)+"m";
  if(s < 172800) return (s/3600).toFixed(1)+"h";
  return (s/86400).toFixed(1)+"d";
}
function group(n){ return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ","); }
function fmt(v, key){
  if(v === null || v === undefined) return "not recorded";
  if(typeof v === "boolean") return v ? "yes" : "no";
  if(key && /_seconds$|\sseconds$/.test(key) && typeof v === "number")
    return humanize(v)+" ("+group(Math.round(v))+"s)";
  if(typeof v === "number")
    return Number.isInteger(v) ? group(v) : String(Math.round(v*1000)/1000);
  if(Array.isArray(v)) return v.length ? v.join(", ") : "none";
  return String(v);
}
function el(tag, cls, text){
  var e = document.createElement(tag);
  if(cls) e.className = cls;
  if(text !== undefined && text !== null) e.textContent = text;
  return e;
}
var SVGNS = "http://www.w3.org/2000/svg";
function svg(tag, attrs){
  var e = document.createElementNS(SVGNS, tag);
  if(attrs) for(var k in attrs){ if(attrs.hasOwnProperty(k)) e.setAttribute(k, attrs[k]); }
  return e;
}
var PALETTE = ["#8a4b2a","#2c6a45","#4f6377","#8a6410","#7a3550","#3a5f8a","#6a5acd","#a3301c"];

/* ---- derived metrics as table rows (label x run) ---- */
function derivedRows(){
  var defs = [
    ["demonstrated / claimed phases", function(d){ return d.demonstrated_phases+" / "+d.claimed_phases; }],
    ["demonstration ratio (of 7)", function(d){ return d.demonstration_ratio; }],
    ["verification density (demo/claimed)", function(d){ return d.verification_density; }],
    ["integrity score", function(d){ return d.integrity_score; }],
    ["high / medium findings", function(d){ return d.high_findings+" / "+d.medium_findings; }],
    ["cost / demonstrated phase", function(d){ return d.cost_per_demonstrated_phase_seconds==null
        ? null : humanize(d.cost_per_demonstrated_phase_seconds); }],
    ["commits / demonstrated phase", function(d){ return d.commits_per_demonstrated_phase; }],
    ["authored churn ratio (vs bookkeeping)", function(d){ return d.authored_churn_ratio; }],
    ["rework ratio (deleted/added)", function(d){ return d.rework_ratio; }],
    ["delegation budget discipline", function(d){ return d.delegation_discipline; }],
    ["parallel speedup", function(d){ return d.parallel_speedup; }],
    ["worktrees open at grade time", function(d){ return d.worktrees_now; }],
    ["halt honesty", function(d){ return d.halt_honesty; }],
    ["fabrication/retraction events", function(d){ return d.fabrication_events; }],
    ["phases with owner review", function(d){ return d.owner_reviews_present; }],
    ["seam resolution ratio", function(d){ return d.seam_resolution_ratio; }],
    ["review rigor", function(d){ return d.review_rigor; }],
    ["distinct delegate models", function(d){ return d.distinct_delegate_models; }],
    ["vetoes raised", function(d){ return d.vetoes_raised; }],
    ["red-first signals", function(d){ return d.red_first_hits; }],
    ["coordinator verifications", function(d){ return d.coordinator_verifications; }],
    ["in-flight self-corrections", function(d){ return d.self_corrections; }],
    ["oracle/mutation signals", function(d){ return d.oracle_mutation_hits; }],
    ["defect-class control conversion", function(d){ return d.defect_class_conversion; }],
    ["phase-order inversions", function(d){ return d.phase_order_inversions; }]
  ];
  return defs.map(function(def){
    return [def[0], RUNS.map(function(r){ return def[1](r.derived||{}); })];
  });
}

/* ---- the comparison radar (Kiviat): six deterministic 0-1 spokes, runs overlaid ---- */
function radarSpokes(runs){
  for(var i=0;i<runs.length;i++){
    var rd = (runs[i].derived||{}).radar;
    if(rd) return Object.keys(rd);
  }
  return [];
}
function kiviat(runs){
  var sec = el("section"); sec.id = "kiviat";
  sec.appendChild(el("h2",null,"Comparison radar"));
  sec.appendChild(el("p","note","Six deterministic 0-1 spokes per run, overlaid so runs stack for "
    + "comparison. A missing score sits at the centre. The judgment axes (performance, parallelism, "
    + "drift) are not plotted - they carry no defensible ratio, by design."));
  var spokes = radarSpokes(runs);
  if(spokes.length < 3){
    sec.appendChild(el("p","empty","Not enough scored spokes to plot a radar."));
    return sec;
  }
  var W=560, H=440, cx=W/2, cy=H/2+4, R=150, N=spokes.length;
  var s = svg("svg",{viewBox:"0 0 "+W+" "+H, width:"100%", height:"auto",
                     role:"img", "aria-label":"Comparison radar of deterministic scores"});
  function pt(ai, frac){
    var ang = -Math.PI/2 + ai*2*Math.PI/N;
    return [cx+Math.cos(ang)*R*frac, cy+Math.sin(ang)*R*frac];
  }
  [0.25,0.5,0.75,1].forEach(function(fr){
    var pts=[]; for(var a=0;a<N;a++){ var p=pt(a,fr); pts.push(p[0].toFixed(1)+","+p[1].toFixed(1)); }
    s.appendChild(svg("polygon",{points:pts.join(" "), fill:"none",
                                 stroke:"#cfc9bf", "stroke-width":"1"}));
  });
  for(var a=0;a<N;a++){
    var o=pt(a,1);
    s.appendChild(svg("line",{x1:cx, y1:cy, x2:o[0].toFixed(1), y2:o[1].toFixed(1),
                              stroke:"#e3dfd8", "stroke-width":"1"}));
    var lp=pt(a,1.16);
    var tx=svg("text",{x:lp[0].toFixed(1), y:lp[1].toFixed(1), fill:"#6d6a65",
      "font-size":"11", "font-family":"ui-sans-serif,system-ui,Segoe UI,Roboto,sans-serif",
      "text-anchor": lp[0]<cx-6?"end":(lp[0]>cx+6?"start":"middle"),
      "dominant-baseline": lp[1]<cy-4?"auto":(lp[1]>cy+4?"hanging":"middle")});
    tx.textContent = spokes[a];
    s.appendChild(tx);
  }
  runs.forEach(function(r, ri){
    var rd=(r.derived||{}).radar||{}, pts=[], col=PALETTE[ri%PALETTE.length];
    for(var a=0;a<N;a++){
      var v=rd[spokes[a]]; if(v===null||v===undefined) v=0;
      var p=pt(a, Math.max(0,Math.min(1,v))); pts.push(p[0].toFixed(1)+","+p[1].toFixed(1));
    }
    s.appendChild(svg("polygon",{points:pts.join(" "), fill:col, "fill-opacity":"0.12",
                                 stroke:col, "stroke-width":"2"}));
    for(var b=0;b<N;b++){
      var vv=rd[spokes[b]]; if(vv===null||vv===undefined) vv=0;
      var q=pt(b, Math.max(0,Math.min(1,vv)));
      s.appendChild(svg("circle",{cx:q[0].toFixed(1), cy:q[1].toFixed(1), r:"2.6", fill:col}));
    }
  });
  sec.appendChild(s);
  var lg=el("div"); lg.style.cssText="margin-top:8px;display:flex;flex-wrap:wrap;gap:14px";
  runs.forEach(function(r,ri){
    var it=el("span"); it.style.cssText="display:inline-flex;align-items:center;gap:6px;font-size:13px";
    var sw=el("span"); sw.style.cssText="display:inline-block;width:11px;height:11px;border-radius:2px;"
      + "background:"+PALETTE[ri%PALETTE.length];
    it.appendChild(sw);
    it.appendChild(document.createTextNode(r.identity.name+" (floor "+fmt(r.deterministic_floor)+")"));
    lg.appendChild(it);
  });
  sec.appendChild(lg);
  return sec;
}

/* ---- addition #6: auto-drafted per-phase evidence (with #2 owner review, #4 span) ---- */
function perPhase(runs){
  var sec = el("section"); sec.id = "perphase";
  sec.appendChild(el("h2",null,"Per-phase evidence"));
  sec.appendChild(el("p","note","Auto-drafted from the audit: for each phase, an executed "
    + "verification signal, an owner-review acceptance, the audit time-span, and the evidence "
    + "summary to quote. Edit, do not trust blindly."));
  runs.forEach(function(r){
    sec.appendChild(el("h3",null,r.identity.name));
    var narr=(r.audit||{}).phase_narrative||[], tl=(r.audit||{}).phase_timeline||{};
    if(!narr.length){ sec.appendChild(el("p","empty","No per-phase audit entries found.")); return; }
    var wrap=el("div","wrap"), t=el("table"), th=el("thead"), hr=el("tr");
    ["phase","verified","owner review","audit span","evidence summary"].forEach(function(x,i){
      hr.appendChild(el("th", i===4?"metric":null, x)); });
    th.appendChild(hr); t.appendChild(th);
    var tb=el("tbody");
    narr.forEach(function(n){
      var tr=el("tr");
      tr.appendChild(el("td",null,n.phase));
      tr.appendChild(el("td",null,n.verified?"yes":"no"));
      tr.appendChild(el("td",null,n.owner_reviewed?"yes":"no"));
      var span=tl[n.phase];
      tr.appendChild(el("td",null, (span===null||span===undefined)?"not recorded":humanize(span)));
      tr.appendChild(el("td","metric", n.summary||""));
      tb.appendChild(tr);
    });
    t.appendChild(tb); wrap.appendChild(t); sec.appendChild(wrap);
  });
  return sec;
}

/* ---- addition #1: fabrication / retraction markers, surfaced explicitly ---- */
function fabrication(runs){
  var sec=el("section"); sec.id="fabrication";
  sec.appendChild(el("h2",null,"Fabrication & retraction markers"));
  var any=false;
  runs.forEach(function(r){
    var fa=(r.audit||{}).fabrication_audit||[], fc=(r.git||{}).fabrication_commits||[];
    if(!fa.length && !fc.length) return;
    any=true;
    sec.appendChild(el("h3",null,r.identity.name));
    sec.appendChild(el("p","note",(fa.length+fc.length)+" marker(s). Section 7 makes fabrication "
      + "disqualifying; a clean retraction does not make the run clean."));
    var ul=el("ul","learned");
    fa.forEach(function(f){ ul.appendChild(el("li",null,
      "audit "+(f.shortname||"")+": '"+(f.marker||"")+"' ("+(f.when||"")+")")); });
    fc.forEach(function(c){ ul.appendChild(el("li",null,"commit: "+c)); });
    sec.appendChild(ul);
  });
  if(!any) sec.appendChild(el("p","empty",
    "No fabrication or retraction markers found in the audit or commit record."));
  return sec;
}

/* ---- #1/#2 snapshot, activity & delta ---- */
function snapshotRows(){
  function snap(r,k){ return (r.snapshot||{})[k]; }
  function dl(r,k){ var d=(r.delta||{})[k]; return d? d.delta : null; }
  return [
    ["graded SHA", RUNS.map(function(r){ return snap(r,"graded_sha"); })],
    ["run active (provisional)", RUNS.map(function(r){ return snap(r,"run_active"); })],
    ["last commit age (h)", RUNS.map(function(r){ return snap(r,"last_commit_age_hours"); })],
    ["working tree dirty", RUNS.map(function(r){ return snap(r,"working_tree_dirty"); })],
    ["\u0394 demonstrated phases", RUNS.map(function(r){ return dl(r,"demonstrated_phases"); })],
    ["\u0394 deterministic floor", RUNS.map(function(r){ return dl(r,"deterministic_floor"); })],
    ["\u0394 commits (vs prior grade)", RUNS.map(function(r){ return dl(r,"commits"); })]
  ];
}
function snapshotSection(runs){
  var sec=el("section"); sec.id="snapshot";
  sec.appendChild(el("h2",null,"Snapshot, activity & delta"));
  if(runs.some(function(r){ return (r.snapshot||{}).run_active; })){
    var b=el("div","note"); b.style.cssText="border-left:3px solid var(--med);padding-left:10px";
    b.textContent="At least one run is still ACTIVE - its grade is a provisional snapshot at the "
      + "graded SHA and will move.";
    sec.appendChild(b);
  }
  sec.appendChild(el("p","note","A grade is a snapshot at the graded SHA. Delta is vs the most recent "
    + "prior grade of the same run in this folder."));
  sec.appendChild(table(snapshotRows(),"metric"));
  return sec;
}

/* ---- #3/#4 delegate models & veto ledger ---- */
function modelsVeto(runs){
  var sec=el("section"); sec.id="models";
  sec.appendChild(el("h2",null,"Delegate models & veto ledger"));
  runs.forEach(function(r){
    var q=r.quality||{}, ma=q.model_allocation||{}, vl=q.veto_ledger||{};
    sec.appendChild(el("h3",null,r.identity.name));
    var counts=ma.counts||{};
    var mix=Object.keys(counts).sort().map(function(k){return k+" x"+counts[k];}).join(", ")||"none recorded";
    sec.appendChild(el("p","note","delegate model mix: "+mix+" \u00b7 reviewer models: "
      + ((vl.reviewer_models||[]).join(", ")||"none")+" \u00b7 vetoes "+vl.vetoes+" / clears "+vl.clears));
    var events=vl.events||[];
    if(events.length){
      var wrap=el("div","wrap"), t=el("table"), th=el("thead"), hr=el("tr");
      ["verdict","reviewer model","where"].forEach(function(x){ hr.appendChild(el("th",null,x)); });
      th.appendChild(hr); t.appendChild(th); var tb=el("tbody");
      events.slice(0,20).forEach(function(ev){
        var tr=el("tr");
        tr.appendChild(el("td",null,ev.verdict));
        tr.appendChild(el("td",null,ev.model||"-"));
        tr.appendChild(el("td",null,ev.where||"-"));
        tb.appendChild(tr);
      });
      t.appendChild(tb); wrap.appendChild(t); sec.appendChild(wrap);
    }
  });
  return sec;
}

/* ---- #10/#12 phase velocity & ordering ---- */
function phaseVelocity(runs){
  var sec=el("section"); sec.id="velocity";
  sec.appendChild(el("h2",null,"Phase velocity"));
  runs.forEach(function(r){
    var pv=(r.git||{}).phase_velocity||{}, q=r.quality||{};
    sec.appendChild(el("h3",null,r.identity.name));
    if(!Object.keys(pv).length){ sec.appendChild(el("p","empty","No phase-tagged commits.")); return; }
    sec.appendChild(el("p","note","Seen order "+((q.phase_order_seen||[]).join(" \u2192 ")||"none")
      +" ("+q.phase_order_inversions+" inversions vs P0..P6)."));
    var wrap=el("div","wrap"), t=el("table"), th=el("thead"), hr=el("tr");
    ["phase","first commit"].forEach(function(x){ hr.appendChild(el("th",null,x)); });
    th.appendChild(hr); t.appendChild(th); var tb=el("tbody");
    ["P0","P1","P2","P3","P4","P5","P6"].forEach(function(p){
      if(pv[p]){ var tr=el("tr"); tr.appendChild(el("td",null,p)); tr.appendChild(el("td",null,pv[p])); tb.appendChild(tr); }
    });
    t.appendChild(tb); wrap.appendChild(t); sec.appendChild(wrap);
  });
  return sec;
}
function visible(){ return RUNS.filter(function(r){ return !S.hidden[r.identity.name]; }); }
function matches(label, values){
  if(!S.q) return true;
  var hay = (label+" "+values.map(function(v){return fmt(v);}).join(" ")).toLowerCase();
  return hay.indexOf(S.q.toLowerCase()) !== -1;
}
function same(values){
  var first = JSON.stringify(values[0]);
  return values.every(function(v){ return JSON.stringify(v) === first; });
}

/* ---- a metric-rows x run-columns table ---- */
function table(rows, header){
  var runs = visible();
  var wrap = el("div","wrap"), t = el("table");
  var thead = el("thead"), hr = el("tr");
  var th0 = el("th","metric", header); hr.appendChild(th0);
  runs.forEach(function(r){
    var th = el("th","run"+(S.pin===r.identity.name?" pin":""), r.identity.name);
    th.tabIndex = 0;
    th.title = "Click to pin this column";
    th.setAttribute("role","button");
    var toggle = function(){ S.pin = (S.pin===r.identity.name) ? null : r.identity.name; render(); };
    th.onclick = toggle;
    th.onkeydown = function(e){ if(e.key==="Enter"||e.key===" "){ e.preventDefault(); toggle(); } };
    hr.appendChild(th);
  });
  thead.appendChild(hr); t.appendChild(thead);

  var tb = el("tbody"), shown = 0;
  rows.forEach(function(row){
    var label = row[0], values = row[1].filter(function(_,i){
      return !S.hidden[RUNS[i].identity.name];
    });
    if(S.diff && runs.length > 1 && same(values)) return;
    if(!matches(label, values)) return;
    shown++;
    var tr = el("tr");
    tr.appendChild(el("td","metric", label));
    values.forEach(function(v,i){
      var td = el("td", (S.pin===runs[i].identity.name?"pin ":"") + (v===null?"n":""));
      if(v === "judgment"){ td.className += " j"; td.textContent = "judgment"; }
      else if(label === "score" && typeof v === "number"){
        var box = el("div","score"), bar = el("div","bar"), fill = el("i");
        fill.style.width = Math.max(0, Math.min(1, v))*100 + "%";
        bar.appendChild(fill); box.appendChild(bar);
        box.appendChild(el("span","num", fmt(v, label)));
        td.appendChild(box);
      } else { td.className += " num"; td.textContent = fmt(v, label); }
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
  if(!shown) tb.appendChild(el("tr")).appendChild(el("td","empty",
    S.diff ? "Every run agrees on every row here." : "No rows match the filter."))
    .colSpan = runs.length + 1;
  t.appendChild(tb); wrap.appendChild(t);
  return wrap;
}

function axisRows(key){
  var runs = visible();
  var rows = [["score", RUNS.map(function(r){
    var a = (r.axes||{})[key]||{}; return a.judgment ? "judgment" : (a.score===undefined?null:a.score);
  })]];
  var keys = [];
  RUNS.forEach(function(r){
    var vals = (((r.axes||{})[key]||{}).values)||{};
    Object.keys(vals).forEach(function(k){ if(keys.indexOf(k)===-1) keys.push(k); });
  });
  keys.forEach(function(k){
    rows.push([k.replace(/_/g," "), RUNS.map(function(r){
      var vals = (((r.axes||{})[key]||{}).values)||{};
      return (k in vals) ? vals[k] : null;
    })]);
  });
  return rows;
}

/* ---- per-run drill-down: the exhibits the grader has to quote ---- */
function detail(r){
  var d = el("details","run");
  var findings = (r.integrity||[]).length;
  var sum = el("summary");
  sum.appendChild(el("span",null, r.identity.name));
  sum.appendChild(el("span","n", " " + (r.outcome||"not recorded")));
  var b = el("span","badge"+(findings?" hi":""), String(findings));
  b.title = findings + " integrity finding(s)";
  sum.appendChild(b);
  d.appendChild(sum);

  var body = el("div","body");
  function kv(pairs){
    var dl = el("dl","kv");
    pairs.forEach(function(p){
      if(p[1] === undefined) return;
      dl.appendChild(el("dt",null,p[0]));
      dl.appendChild(el("dd",null,fmt(p[1],p[0])));
    });
    body.appendChild(dl);
  }
  function h(text){ body.appendChild(el("h3",null,text)); }
  function none(text){ body.appendChild(el("p","empty",text)); }

  var id = r.identity||{}, g = r.git||{}, a = r.audit||{}, c = r.coord||{},
      rep = r.report||{}, tree = r.tree||{}, plan = r.plan||{}, build = r.build||{};

  h("Identity");
  kv([["path",id.path],["head",id.head],["branch",id.branch],
      ["pack revision",id.pack_revision],["coordination skills",id.has_coordination_skills],
      ["harness claimed",rep.harness_claimed],["model claimed",rep.model_claimed],
      ["outcome",r.outcome],["halt",rep.halt_line]]);

  h("What it built");
  kv([["source loc",tree.source_loc],["projects",tree.projects],
      ["test projects",tree.test_projects],["specs",tree.spec_count],
      ["adrs",tree.adr_count],["defect classes file",tree.defect_classes_present],
      ["commits",g.commits],["wall_seconds",g.wall_seconds],
      ["lines added",g.lines_added],["lines deleted",g.lines_deleted],
      ["build ok",build.attempted?build.build_ok:null],
      ["tests ok",build.attempted?build.test_ok:null]]);
  if(build.attempted && build.test_tail){
    body.appendChild(el("pre",null,build.test_tail));
  }

  h("Phases");
  kv([["claimed complete (report)",rep.phases_claimed_complete],
      ["named in audit",a.phases_in_audit],
      ["verification executed",a.phases_verification_executed]]);

  h("Coordination plan");
  if(plan.present){
    kv([["plan",plan.path],["tracks",plan.tracks],["serial spine",plan.serial_spine],
        ["seams",plan.seams],["struck tracks",plan.struck_tracks],
        ["artifact classes",plan.artifact_classes]]);
  } else { none("No coordination plan was written."); }

  h("Delegations");
  kv([["delegations",a.delegations],["distinct agents",a.distinct_agents],
      ["peak concurrency",a.peak_concurrency],["agent_seconds",a.agent_seconds],
      ["span_seconds",a.span_seconds],["speedup",a.speedup],
      ["without a budget",a.delegations_without_budget],
      ["over budget",a.delegations_over_budget]]);

  h("Drift exhibits - done_when vs summary");
  var pairs = ((a.selfcheck||{}).review_pairs)||[];
  if(pairs.length){
    pairs.forEach(function(p){
      var box = el("div","pair");
      box.appendChild(el("div","dw","done_when: " + (p.done_when||"(none)")));
      box.appendChild(el("div","sm", p.summary||""));
      var tag = el("div","dw"); tag.textContent = p.shortname||""; box.appendChild(tag);
      body.appendChild(box);
    });
  } else { none("No done_when -> summary pairs recorded."); }

  h("Contention");
  var cont = r.contention||{};
  kv([["merges examined",cont.merges_examined],
      ["files contended in a merge",(cont.contended_files||[]).length],
      ["of those, measured",cont.contended_measured],
      ["needing no human",cont.contended_free]]);
  var hot = (cont.contended_files||[]).concat([]);
  if(!hot.length) hot = (cont.hot_files||[]).map(function(f){
    return {path:f.path, merges:f.commits, class:f["class"]};
  });
  if(hot.length){
    body.appendChild(el("pre",null, hot.slice(0,12).map(function(f){
      return (f["class"]||"?") + "\t" + (f.merges||0) + "\t" + f.path;
    }).join("\n")));
  } else { none("No contention measured."); }

  h("Coordination layer state");
  kv([["registry present",c.registry_present],["registry rules",c.registry_rules],
      [".gitattributes",c.gitattributes_present],["pre-commit hook",c.precommit_hook_present],
      ["sessions registered",c.sessions],["seams raised",c.seams_total],
      ["seams resolved",c.seams_resolved]]);
  if(c.doctor) body.appendChild(el("pre",null,c.doctor));

  h("Skills used");
  var by = a.by_skill||{};
  var names = Object.keys(by).sort(function(x,y){ return by[y]-by[x]; });
  if(names.length){
    body.appendChild(el("pre",null, names.map(function(n){
      return by[n] + "\t" + n; }).join("\n")));
  } else { none("No skill attribution in the audit log."); }
  if((a.unexpected_skills||[]).length)
    kv([["outside the expected loop",a.unexpected_skills]]);

  d.appendChild(body);
  return d;
}

/* ---- chrome ---- */
function buildControls(){
  var box = document.getElementById("controls");
  box.textContent = "";
  CTLS = [];
  function btn(label, isOn, fn, title){
    var b = el("button","ctl",label);
    b.type = "button";
    if(title) b.title = title;
    b.onclick = fn;
    box.appendChild(b);
    CTLS.push({el:b, on:isOn});
    return b;
  }
  btn("Differences only", function(){ return S.diff; },
      function(){ S.diff = !S.diff; render(); },
      "Hide every row on which all shown runs agree");

  var search = el("input","search");
  search.type = "search";
  search.placeholder = "Filter rows and findings";
  search.setAttribute("aria-label","Filter rows and findings");
  search.value = S.q;
  search.oninput = function(){ S.q = search.value; render(true); };
  box.appendChild(search);

  ["high","medium","low"].forEach(function(sev){
    btn(sev, function(){ return S.sev[sev]; }, function(){ S.sev[sev] = !S.sev[sev]; render(); },
        "Show " + sev + "-severity integrity findings");
  });

  box.appendChild(el("span","spacer"));

  RUNS.forEach(function(r){
    var n = r.identity.name;
    btn(n, function(){ return !S.hidden[n]; }, function(){ S.hidden[n] = !S.hidden[n]; render(); },
        "Show or hide this run");
  });

  var themes = ["system","light","dark"];
  var cur = localStorage.getItem("grade-theme") || "system";
  var tb = btn("theme: " + cur, function(){ return false; }, function(){
    cur = themes[(themes.indexOf(cur)+1) % themes.length];
    try{ localStorage.setItem("grade-theme", cur); }catch(e){}
    applyTheme(cur); tb.textContent = "theme: " + cur;
  }, "Cycle light, dark and system");
  applyTheme(cur);
}
function syncControls(){
  /* aria-pressed and the pill highlight are STATE, and state is read back after every
     render - a value stamped once at build time is stale from the first click. */
  CTLS.forEach(function(c){
    c.el.setAttribute("aria-pressed", c.on() ? "true" : "false");
  });
}
function applyTheme(mode){
  var root = document.documentElement;
  if(mode === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", mode);
}

function render(keepFocus){
  var active = keepFocus ? document.activeElement : null;
  var caret = active && active.selectionStart;
  var app = document.getElementById("app");
  app.textContent = "";
  var runs = visible();

  document.getElementById("meta").textContent =
    RUNS.length + " run(s), " + runs.length + " shown · generated " + D.generated;

  if(!runs.length){
    app.appendChild(el("p","empty","Every run is hidden. Turn one back on above."));
    syncControls();
    return;
  }

  var halted = runs.filter(function(r){ return r.outcome === "HALT"; });
  if(halted.length){
    var s = el("section"); s.id = "halts";
    s.appendChild(el("h2",null,"Halts"));
    halted.forEach(function(r){
      var d = el("div","halt");
      d.appendChild(el("strong",null,r.identity.name));
      d.appendChild(document.createTextNode(" — " + (r.report.halt_line
        || "declared HALT in the report body (no BENCHMARK-HALT marker line)")));
      s.appendChild(d);
    });
    app.appendChild(s);
  }

  if(V){
    var vs = el("section"); vs.id = "verdict";
    vs.appendChild(el("h2",null,"Ranking"));
    if(!(V.ranking||[]).length){
      vs.appendChild(el("p","empty","No ranking recorded."));
    } else {
      var ol = el("ol","rank");
      V.ranking.forEach(function(r){
        var li = el("li");
        li.appendChild(el("strong",null,r.run||""));
        if(r.why) li.appendChild(el("div","sm", r.why));
        ol.appendChild(li);
      });
      vs.appendChild(ol);
    }
    if((V.downgrades||[]).length){
      vs.appendChild(el("h3",null,"Downgrades \u2014 reported complete, evidence absent"));
      var w = el("div","wrap"), t = el("table"), th = el("thead"), hr = el("tr");
      ["run","phase","missing evidence"].forEach(function(x,i){
        hr.appendChild(el("th", i===2?"metric":null, x)); });
      th.appendChild(hr); t.appendChild(th);
      var tb = el("tbody");
      V.downgrades.forEach(function(d){
        var tr = el("tr");
        tr.appendChild(el("td",null,d.run||""));
        tr.appendChild(el("td",null,d.phase||""));
        tr.appendChild(el("td","metric",d.missing||""));
        tb.appendChild(tr);
      });
      t.appendChild(tb); w.appendChild(t); vs.appendChild(w);
    }
    if((V.learned||[]).length){
      vs.appendChild(el("h3",null,"What the pack should learn"));
      var ul = el("ul","learned");
      V.learned.forEach(function(x){ ul.appendChild(el("li",null,x)); });
      vs.appendChild(ul);
    }
    app.appendChild(vs);
  }

  var sum = el("section"); sum.id = "summary";
  sum.appendChild(el("h2",null,"Summary"));
  sum.appendChild(el("p","note","A blank is not recorded and is excluded from the floor "
    + "rather than counted as zero. The floor averages only the axes with a defensible "
    + "ratio - it is a floor, not a grade."));
  sum.appendChild(table([
    ["outcome", RUNS.map(function(r){ return r.outcome; })],
    ["pack revision", RUNS.map(function(r){ return r.identity.pack_revision; })],
    ["coordination skills installed", RUNS.map(function(r){ return r.identity.has_coordination_skills; })],
    ["phases with verification executed", RUNS.map(function(r){ return (r.audit.phases_verification_executed||[]).length; })],
    ["phases claimed complete", RUNS.map(function(r){ return (r.report.phases_claimed_complete||[]).length; })],
    ["integrity findings", RUNS.map(function(r){ return (r.integrity||[]).length; })],
    ["deterministic floor", RUNS.map(function(r){ return r.deterministic_floor; })]
  ], "metric"));
  app.appendChild(sum);

  var dv = el("section"); dv.id = "derived";
  dv.appendChild(el("h2",null,"Derived metrics"));
  dv.appendChild(el("p","note","Deterministic ratios that sharpen the raw axes: how much of the "
    + "line-count was real output vs bookkeeping, and what a demonstrated phase actually cost. "
    + "A zero-denominator ratio reads 'not recorded', never a fabricated zero."));
  dv.appendChild(table(derivedRows(), "metric"));
  app.appendChild(dv);

  app.appendChild(fabrication(runs));
  app.appendChild(perPhase(runs));
  app.appendChild(snapshotSection(runs));
  app.appendChild(modelsVeto(runs));
  app.appendChild(phaseVelocity(runs));

  AXES.forEach(function(pair){
    var key = pair[0], title = pair[1];
    var s = el("section"); s.id = key;
    s.appendChild(el("h2",null,title));
    var note = ((runs[0].axes||{})[key]||{}).note;
    if(note) s.appendChild(el("p","note",note));
    s.appendChild(table(axisRows(key), "measure"));
    var j = V && V.judgment && V.judgment[key];
    if(j){
      runs.forEach(function(r){
        var text = j[r.identity.name];
        if(!text) return;
        var box = el("div","pair");
        box.appendChild(el("div","dw", r.identity.name));
        box.appendChild(el("div","sm", text));
        s.appendChild(box);
      });
    }
    app.appendChild(s);
  });

  var ints = el("section"); ints.id = "integrity";
  ints.appendChild(el("h2",null,"Integrity — claimed vs observed"));
  ints.appendChild(el("p","note","What the run report says, beside what the record shows. "
    + "This is the gap that decides the ranking."));
  runs.forEach(function(r){
    var list = (r.integrity||[]).filter(function(f){
      if(!S.sev[f.severity]) return false;
      if(!S.q) return true;
      return (f.claim+" "+f.observed).toLowerCase().indexOf(S.q.toLowerCase()) !== -1;
    });
    ints.appendChild(el("h3",null,r.identity.name));
    if(!list.length){
      ints.appendChild(el("p","note ok", (r.integrity||[]).length
        ? "No finding matches the current filter."
        : "No divergence found between the run report and the record."));
      return;
    }
    var wrap = el("div","wrap"), t = el("table"),
        th = el("thead"), hr = el("tr");
    ["severity","claim","observed"].forEach(function(h,i){
      hr.appendChild(el("th", i?"metric":null, h));
    });
    th.appendChild(hr); t.appendChild(th);
    var tb = el("tbody");
    list.forEach(function(f){
      var tr = el("tr");
      var td = el("td");
      td.appendChild(el("span","sev "+f.severity, f.severity));
      tr.appendChild(td);
      tr.appendChild(el("td","metric", f.claim));
      tr.appendChild(el("td","metric", f.observed));
      tb.appendChild(tr);
    });
    t.appendChild(tb); wrap.appendChild(t); ints.appendChild(wrap);
  });
  app.appendChild(ints);

  var det = el("section"); det.id = "detail";
  det.appendChild(el("h2",null,"Per-run detail"));
  det.appendChild(el("p","note","The exhibits. Stage 2 of /grade-benchmarks has to quote from "
    + "here - a drift or parallelism verdict with no exhibit is an opinion."));
  runs.forEach(function(r){ det.appendChild(detail(r)); });
  app.appendChild(det);

  app.appendChild(kiviat(runs));

  syncControls();

  if(active && active.className === "search"){
    var s2 = document.querySelector("input.search");
    if(s2){ s2.focus(); if(caret !== null) s2.setSelectionRange(caret, caret); }
  }
}

function buildNav(){
  var nav = document.getElementById("nav");
  nav.textContent = "";
  var items = (V ? [["verdict","Ranking"]] : []).concat([["summary","Summary"],["derived","Derived metrics"],["fabrication","Fabrication"],["perphase","Per-phase evidence"],["snapshot","Snapshot & delta"],["models","Models & vetoes"],["velocity","Phase velocity"]])
      .concat(AXES).concat([["integrity","Integrity"],["detail","Per-run detail"],["kiviat","Comparison radar"]]);
  items.forEach(function(p){
    var a = el("a",null,p[1]); a.href = "#"+p[0]; nav.appendChild(a);
  });
}

document.getElementById("foot").textContent =
  "Extraction is deterministic and LLM-free: every number here was read from a run's own "
  + "git history, audit log, coordination store and source tree by tools/grade-benchmarks.py. "
  + "Performance, parallelism and drift carry no automatic score on purpose - there is no "
  + "absolute scale for speed, more parallelism is a cost multiplier rather than a result, "
  + "and whether a summary drifted from its stated done-when is a reading, not a count. "
  + "The canonical static view is the .md file beside this one.";

buildControls(); buildNav(); render();
})();
</script>"""


def render_html(runs, generated, verdict=None):
    """The interactive report. Everything renders client-side from the embedded payload, so
    drill-down works over file:// with no server and no dependency. The .md beside it stays
    the canonical static view, which is what the <noscript> points at."""
    payload = json.dumps({"generated": generated, "runs": runs, "verdict": verdict},
                         default=str)
    payload = payload.replace("</", "<\\/")      # never let a value close the script tag
    return PAGE.replace("__PAYLOAD__", payload)


# --------------------------------------------------------------------------- main


def _num_delta(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return {"from": a, "to": b, "delta": round(b - a, 3)}
    return {"from": a, "to": b, "delta": None}


def attach_deltas(outdir, runs):
    """#1 delta grading: compare each run to the most recent PRIOR grade of the same run that
    still exists in --out. A grade is a snapshot at a SHA; the delta is how far the run moved
    since the last one. No prior => delta is None (stated, never a fabricated zero)."""
    prior_runs = {}
    if outdir.is_dir():
        for p in sorted(outdir.glob("grade-*.json"), reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for r in data.get("runs") or []:
                name = (r.get("identity") or {}).get("name")
                if name and name not in prior_runs:
                    prior_runs[name] = (p.name, r)
    for run in runs:
        prev = prior_runs.get((run.get("identity") or {}).get("name"))
        if not prev:
            run["delta"] = None
            continue
        pname, pr = prev
        pd, cd = (pr.get("derived") or {}), (run.get("derived") or {})
        run["delta"] = {
            "against": pname,
            "prior_sha": (pr.get("snapshot") or {}).get("graded_sha") or (pr.get("identity") or {}).get("head"),
            "current_sha": (run.get("snapshot") or {}).get("graded_sha"),
            "demonstrated_phases": _num_delta(pd.get("demonstrated_phases"), cd.get("demonstrated_phases")),
            "deterministic_floor": _num_delta(pr.get("deterministic_floor"), run.get("deterministic_floor")),
            "commits": _num_delta((pr.get("git") or {}).get("commits"), (run.get("git") or {}).get("commits")),
        }


def resolve(token, base):
    """A bare name resolves as a sibling of the control repo, so `/grade-benchmarks r1, r2` works."""
    token = token.strip().strip(",").strip('"').strip("'")
    if not token:
        return None
    for candidate in (Path(token), base / token, base.parent / token):
        if candidate.is_dir():
            return candidate.resolve()
    return Path(token)      # report it as missing rather than silently dropping it


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Grade and compare N CFD-Bench benchmark runs, one repo per run.")
    ap.add_argument("repos", nargs="+",
                    help="run repos - paths or bare names; commas are allowed")
    ap.add_argument("--out", help="directory to write grade-<stamp>.{json,md,html} into")
    ap.add_argument("--json", action="store_true", help="print the full payload as JSON")
    ap.add_argument("--verify-build", action="store_true",
                    help="opt-in: run dotnet build and dotnet test in each repo")
    ap.add_argument("--build-timeout", type=int, default=900)
    ap.add_argument("--verdict", help="JSON file carrying the grader's ruling "
                    "{ranking, judgment, downgrades, learned}; merged into both outputs")
    ap.add_argument("--as-of", help="record a pin SHA for the grade; the working tree is what is "
                    "read, so a mismatch with HEAD is flagged, not checked out")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    base = Path.cwd()
    tokens = []
    for raw in args.repos:
        tokens += [t for t in re.split(r"[,\s]+", raw) if t]
    seen, repos = set(), []
    for token in tokens:
        path = resolve(token, base)
        if path and str(path) not in seen:
            seen.add(str(path))
            repos.append(path)

    verdict = None
    if args.verdict:
        # A verdict that cannot be read is a hard stop. Falling back to an unjudged report
        # would publish a grading pass with its conclusion silently missing.
        with open(args.verdict, "r", encoding="utf-8") as fh:
            verdict = json.load(fh)

    generated = datetime.now(timezone.utc).strftime(ISO)
    runs = [grade_run(p, p.name, args.verify_build, args.build_timeout) for p in repos]

    if args.as_of:
        for run in runs:
            snap = run.get("snapshot") or {}
            head = snap.get("graded_sha") or ""
            snap["requested_sha"] = args.as_of
            snap["pin_matches_head"] = bool(head and (head.startswith(args.as_of)
                                                      or args.as_of.startswith(head)))
            run["snapshot"] = snap
    if args.out:
        attach_deltas(Path(args.out), runs)

    payload = {"generated": generated, "control_repo": str(base), "runs": runs,
               "verdict": verdict, "axes_order": [k for k, _ in AXIS_TITLES]}

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(render_text(runs))

    if args.out:
        outdir = Path(args.out)
        outdir.mkdir(parents=True, exist_ok=True)
        stamp = generated.replace(":", "").replace("-", "")
        for suffix, body in (("json", json.dumps(payload, indent=2, default=str)),
                             ("md", render_markdown(runs, generated, verdict)),
                             ("html", render_html(runs, generated, verdict))):
            target = outdir / "grade-{}.{}".format(stamp, suffix)
            with open(str(target), "w", encoding="utf-8") as fh:
                fh.write(body)
            print("wrote {}".format(target))

    missing = [r for r in runs if r.get("error")]
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
