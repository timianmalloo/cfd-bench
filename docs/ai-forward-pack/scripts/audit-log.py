#!/usr/bin/env python3
"""audit-log.py — the AI-Forward Pack audit & change log bundle (audit-and-change-log.md).

Durable, committed, history-as-knowledge for a repo: an append-only record of every
meaningful prompt / skill / script / decision, so any future Copilot or Claude Code
session reads the project's own history instead of starting blind. The canonical logs
are append-only JSONL (clean git diffs, like docs/health-history.jsonl); the viewer
reads a derived window.AUDIT_DATA JS (loadable over file://, like docs/docs-index.js).
Python 3.8+, stdlib only — no dependencies.

Two logs, one bundle:
  docs/audit/audit-log.jsonl    every action (shortname, datetime, session, prompt, summary, …)
  docs/audit/change-log.jsonl   the meaningful design changes / decisions (+ git before/after)
  docs/audit/audit-data.js      derived window.AUDIT_DATA = {audit:[…], changes:[…]} (the viewer's data)
  docs/audit/index.html         the interactive viewer (self-bootstrapped from the template)

Subcommands
  append      Add an audit entry.            (Audit Mandate — every skill's last action)
  change      Add a change-log entry.        (Change Mandate — collectknowledge/define-architecture/design-slice/migrate)
  list        Show the last N entries (audit|change). For the CLI skill.
  search      Filter by --session / --since / --until / --keyword. For the CLI skill.
  get         Print one entry by --id (use --field prompt to extract the prompt to re-run).
  render      Regenerate audit-data.js from the JSONL and ensure the viewer exists (repair).
  git-context Print the current git {sha, short, branch, pushed} as JSON (a helper).
  verify      Fail when any log line is unreadable — the system of record must never lose
              an entry silently (FR-052). CI-able.
  suggest     Discern unlogged meaningful changes (recent commits + new ADRs/notes not in the change log).
  import      Ingest a session-export JSON array of turns into the audit log (build on session history).

Conventions
  --root defaults to docs/. The audit dir is <root>/audit. The viewer template is resolved
  relative to this script (pack/templates or docs/ai-forward-pack/templates). git is optional —
  every git call degrades gracefully when git or a repo is absent. This tool never invents a
  prompt or a summary; required fields must be supplied (flags, --*-file, or --from-json -).
"""
import argparse, datetime, html, json, os, re, subprocess, sys

# Windows consoles default to cp1252, which cannot encode the box/arrow glyphs this
# tool prints - `prompt-log.py --help` crashed outright with UnicodeEncodeError (FR-047).
# The other scripts survived only because their glyphs happen to exist in cp1252, which is
# luck rather than an invariant, so the guard is applied uniformly.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


ISO = "%Y-%m-%dT%H:%M:%SZ"
AUDIT_KINDS = ["skill", "command", "script", "prompt", "commit", "manual", "session-import"]
CHANGE_KINDS = ["architecture", "design", "knowledge", "migration", "decision", "spec", "other"]


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime(ISO)


def parse_iso(s):
    """Parse an ISO-8601 UTC stamp. Returns None on anything unparseable -- an unusable
    --started value must degrade to 'no duration recorded', never to a wrong duration."""
    if not s:
        return None
    t = str(s).strip().replace("Z", "+00:00")
    try:
        d = datetime.datetime.fromisoformat(t)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def duration_fields(started, ended_iso):
    """Instrumentation over inference: when a start stamp is supplied, RECORD the elapsed
    seconds rather than leaving a future reader to model it. Returns {} when the start is
    absent or unparseable, and refuses a negative duration (clock skew) rather than
    emitting a number that is precise and wrong."""
    s = parse_iso(started)
    e = parse_iso(ended_iso) or datetime.datetime.now(datetime.timezone.utc)
    if s is None:
        return {}
    secs = (e - s).total_seconds()
    if secs < 0:
        return {"started_at": s.strftime(ISO), "duration_seconds": None,
                "duration_note": "start is after end (clock skew); duration not recorded"}
    return {"started_at": s.strftime(ISO), "duration_seconds": round(secs, 1)}


# --- per-run spans: make PARALLELISM measurable (P8, IO2) ----------------------------
# Summed agent time cannot distinguish serial from parallel. A profiled session reported
# 67 runs totalling 152.6 minutes and called that proof of fan-out, but 152.6 minutes sits
# comfortably inside its ~240 minutes of wall clock -- fully serial execution fits the same
# numbers. The claim was unfalsifiable because only DURATIONS were recorded.
#
# A start and an end per run fixes that: the union of the intervals is the wall clock the
# work actually occupied, and speedup = summed / union. Idle gaps between waves are excluded
# from the union, so a long quiet period cannot understate the parallelism that did happen.

def parse_agent_run(spec):
    """'<agent>|<start-iso>|<end-iso>' -> a span dict, or None when unusable.

    Degrades to None on anything unparseable or time-reversed, never to a plausible wrong
    span (IO8) -- a fabricated interval would corrupt the very measurement it exists for.
    """
    parts = [p.strip() for p in str(spec).split("|")]
    if len(parts) != 3 or not parts[0]:
        return None
    agent, start, end = parts
    s, e = parse_iso(start), parse_iso(end)
    if s is None or e is None:
        return None
    secs = (e - s).total_seconds()
    if secs < 0:
        return None
    return {"agent": agent, "started_at": s.strftime(ISO), "ended_at": e.strftime(ISO),
            "duration_seconds": round(secs, 1), "_s": s, "_e": e}


def parallelism_fields(runs):
    """Union-of-intervals wall clock vs summed run time, from a list of parse_agent_run spans.

    Returns {} when no usable span is present -- "not recorded" rather than a speedup of 1.0
    that a reader would mistake for a measurement of serial execution.
    """
    spans = [r for r in (runs or []) if r]
    if not spans:
        return {}
    total = round(sum(r["duration_seconds"] for r in spans), 1)

    # Union of the intervals: sort by start, merge overlaps, sum the merged lengths.
    ordered = sorted(spans, key=lambda r: r["_s"])
    union, cur_s, cur_e = 0.0, ordered[0]["_s"], ordered[0]["_e"]
    for r in ordered[1:]:
        if r["_s"] > cur_e:
            union += (cur_e - cur_s).total_seconds()
            cur_s, cur_e = r["_s"], r["_e"]
        elif r["_e"] > cur_e:
            cur_e = r["_e"]
    union += (cur_e - cur_s).total_seconds()
    union = round(union, 1)

    # Peak concurrency: sweep the endpoints. Ends are processed before starts at the same
    # instant, so a run that ends exactly as another begins is handover, not overlap.
    events = []
    for r in spans:
        events.append((r["_s"], 1))
        events.append((r["_e"], 0))
    events.sort(key=lambda ev: (ev[0], ev[1]))
    live = peak = 0
    for _, delta in events:
        live += 1 if delta else -1
        peak = max(peak, live)

    return {"agent_seconds": total, "span_seconds": union,
            "speedup": round(total / union, 2) if union else None,
            "peak_concurrency": peak}


# --- persona yield: measure what a convocation was WORTH (P6) -------------------------
# Convening cost has always been visible; convening value was not. In the profiled session
# the two advisory personas took 57% of all agent time and changed nothing that shipped,
# while the four hard-veto personas took 24% and drove material change -- knowable only in
# hindsight, and only by hand, because findings-accepted was never recorded against the
# persona that raised them. Recording it makes the roster tunable on evidence.

def parse_persona_yield(spec):
    """'<persona>|<raised>|<accepted>' -> a yield record, or None when unusable.

    Refuses accepted > raised and negative counts: a row that cannot be true would corrupt
    every ratio derived from it, and a corrupt ratio is worse than a missing one (IO8).
    """
    parts = [p.strip() for p in str(spec).split("|")]
    if len(parts) != 3 or not parts[0]:
        return None
    persona, raised, accepted = parts
    try:
        raised, accepted = int(raised), int(accepted)
    except ValueError:
        return None
    if raised < 0 or accepted < 0 or accepted > raised:
        return None
    return {"persona": persona, "raised": raised, "accepted": accepted}


def aggregate_persona_yield(entries):
    """Roll persona_yield records up across audit entries.

    `acceptance` is None when nothing was raised: 0/0 is an absence of evidence, not a
    measured 0% -- reporting 0.0 would read as a verdict on a persona never actually asked.
    """
    out = {}
    for entry in entries or []:
        for row in (entry or {}).get("persona_yield") or []:
            name = row.get("persona")
            if not name:
                continue
            acc = out.setdefault(name, {"raised": 0, "accepted": 0, "sessions": 0})
            acc["raised"] += int(row.get("raised") or 0)
            acc["accepted"] += int(row.get("accepted") or 0)
            acc["sessions"] += 1
    for acc in out.values():
        acc["acceptance"] = (round(acc["accepted"] / acc["raised"], 2)
                             if acc["raised"] else None)
    return out


def should_reconvene(stats, advisory=True):
    """Should this persona be convened AGAIN on the same work? (P6)

    Advisory lenses re-convene on evidence: a repeat run has to be earned by a finding that
    was actually accepted. Hard-veto lenses are never yield-gated -- a veto exists to be
    able to say no, and gating it on past productivity would silence precisely the review
    that has been quiet because the work was clean.

    A persona with no history always gets its first run; the rule gates repeats, not entry.
    """
    if not advisory:
        return True
    if not stats or not stats.get("raised"):
        return True
    return bool(stats.get("accepted"))


# --- run-start markers: make duration DEFAULT-ON (IO1) -------------------------------
# A flag someone has to remember is not "measurable by default". The grounding step calls
# `start --session <id>`, which persists the stamp; `append` then picks it up automatically,
# so no caller threads a variable through and no skill can silently forget the measurement.
# The store is ephemeral per-run state, not project history -- it is git-ignored, and its
# absence degrades to "no duration recorded", never to a wrong one (IO8).
STARTS_FILE = ".run-starts.json"
STARTS_MAX_AGE_DAYS = 7


def _starts_path(root):
    return os.path.join(audit_dir(root), STARTS_FILE)


def _read_starts(root):
    try:
        with open(_starts_path(root), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}  # unreadable/corrupt -> no duration, never a wrong duration (IO8)


def _write_starts(root, data):
    p = _starts_path(root)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, p)
    except OSError as exc:
        # FR-052. Never let bookkeeping fail the audit write itself — but never lose the
        # measurement silently either (IO8: degrade to "not recorded", AND say so).
        print(f"warning: could not persist the run-start marker at {p} ({exc}). "
              f"This run will have no measured duration.", file=sys.stderr)


def _prune_starts(data):
    """Drop markers older than the max age so an abandoned run cannot later attach an absurd
    duration to an unrelated entry."""
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=STARTS_MAX_AGE_DAYS)
    out = {}
    for k, v in data.items():
        t = parse_iso(v)
        if t is not None and t >= cutoff:
            out[k] = v
    return out


def record_start(root, session, stamp=None):
    stamp = stamp or now_iso()
    data = _prune_starts(_read_starts(root))
    if session:
        data[str(session)] = stamp
    _write_starts(root, data)
    return stamp


def consume_start(root, session):
    """Return the recorded start for this session and clear it, so one marker measures one
    run. Returns None when there is none -- which degrades to no duration (IO8)."""
    if not session:
        return None
    data = _prune_starts(_read_starts(root))
    stamp = data.pop(str(session), None)
    if stamp is not None:
        _write_starts(root, data)
    return stamp



def audit_dir(root):
    return os.path.join(root, "audit")


def log_path(root, which):
    return os.path.join(audit_dir(root), "audit-log.jsonl" if which == "audit" else "change-log.jsonl")


# ---------- JSONL read / append ----------
# FR-052. A malformed line must not be fatal (the log has to keep working) but it must not
# be INVISIBLE either: this file is the system of record and the corpus /dream mines, so a
# silently-dropped entry means a consolidation pass reasons over an incomplete corpus while
# reporting success — a success-shaped failure in the system built to prevent them. So the
# read still succeeds, and every skip is counted, warned about, and assertable by `verify`.
LOG_READ_SKIPS = []


def read_log(root, which, warn=True):
    p = log_path(root, which)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as handle:
        for lineno, ln in enumerate(handle, 1):
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError as exc:
                LOG_READ_SKIPS.append({"file": p, "line": lineno, "error": str(exc)})
                if warn:
                    print(f"warning: {p}:{lineno} is not valid JSON and was SKIPPED ({exc}). "
                          f"This log is the system of record — repair the line; "
                          f"`audit-log.py verify` fails while it is unreadable.",
                          file=sys.stderr)
    return out


def append_log(root, which, entry):
    os.makedirs(audit_dir(root), exist_ok=True)
    with open(log_path(root, which), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


_MISSING = object()     # distinguishes "not supplied" from an explicit allocator=None


def _load_allocator():
    """The collision-proof allocator, if this install has it. None if it does not.

    A GRACEFUL fallback, not an optional feature: audit-log.py is pack-managed and ships to
    repositories whose installed pack may predate coord_ids.py. Returning None there keeps
    the legacy sequence working rather than crashing somebody's audit log.
    """
    if os.environ.get("COORD_LEGACY_IDS"):
        return None                       # the rollback half of expand-migrate-contract
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        from coord_ids import new_id
    except ImportError:
        return None
    return new_id


def next_id(entries, prefix, allocator=_MISSING):
    """Mint the next identifier. EXPAND step of expand-migrate-contract (ADR-0008).

    This function was literally the KG-B shape: max(existing) + 1 over the LOCAL file only.
    Two branches minting before either has pushed cannot see each other, so the collision is
    structural -- nine recorded occurrences, twice reaching main, once destroying an entry
    when the conflict was resolved by deduping on the id.

    The sequential path is RETAINED, not deleted: every existing al-NNNN keeps its value,
    there is no backfill (so nothing is guessed), and COORD_LEGACY_IDS=1 restores the old
    scheme entirely. Removing it is the CONTRACT step and is a later decision.
    """
    if allocator is _MISSING:
        allocator = _load_allocator()
    if allocator is not None:
        return allocator(prefix)
    n = 0
    for e in entries:
        m = re.match(prefix + r"-(\d+)$", str(e.get("id", "")))
        if m:
            n = max(n, int(m.group(1)))
    return f"{prefix}-{n + 1:04d}"


# ---------- git helpers (always graceful) ----------
def git(args, root):
    try:
        cwd = os.path.dirname(os.path.abspath(root)) or "."
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def git_context(root):
    sha = git(["rev-parse", "HEAD"], root)
    if not sha:
        return {"sha": None, "short": None, "branch": None, "pushed": None}
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    # pushed == no commits ahead of the upstream (None when there is no upstream)
    ahead = git(["rev-list", "--count", "@{upstream}..HEAD"], root)
    pushed = (ahead == "0") if ahead is not None else None
    return {"sha": sha, "short": sha[:9], "branch": branch, "pushed": pushed}


def commits_between(before, after, root):
    if not before or not after:
        return []
    out = git(["log", "--pretty=%h %s", f"{before}..{after}"], root)
    return [ln for ln in (out or "").split("\n") if ln.strip()]


# FR-071 (class SELF-REPORT). `suggest` must not re-surface its own bookkeeping. Two filters,
# per audit-and-change-log.md CL3: keep only commits whose subject signals a decision, and drop
# commits that ARE the logging action (they wrote an audit .jsonl -> already logged by definition).
DECISION_SIGNAL = re.compile(r"\b(feat|BREAKING|migrate|arch|decision|adr)\b", re.I)


def _suggests_decision(subject):
    """CL3: a commit is a suggest candidate only if its subject signals a decision."""
    return bool(DECISION_SIGNAL.search(subject or ""))


def _is_logging_commit(sha, root):
    """A commit that wrote the CHANGE log is already a change-log closeout, not an unlogged
    change (FR-071 self-report). Scoped to change-log.jsonl - `suggest` is about the change log,
    so an audit-only commit (every skill writes one, AL5) can still be a genuine unlogged decision."""
    files = git(["show", "--name-only", "--pretty=format:", sha], root) or ""
    return any(f.strip().endswith("audit/change-log.jsonl")
               for f in files.splitlines() if f.strip())


# ---------- graph hub node (AL7: the bundle must BE a graph node) ----------
HUB = """---
id: audit-log
title: "Audit & Change Log"
type: doc
status: accepted
owner: "@maintainers"
tags: [audit, history, change-log, project-memory]
links: []
review-by: %s
review-suggested: []
summary: >-
  The durable, committed history of what was prompted, done, and decided in this
  repository, so work compounds across sessions. The two JSONL files are the source
  of truth; audit-data.js and index.html are derived projections.
---

# Audit & Change Log

`audit-log.jsonl` records every meaningful prompt, skill run and script; `change-log.jsonl`
records the design decisions. Browse them at [`index.html`](index.html) or via `/auditlog`.
All writes go through `audit-log.py` - never hand-append the JSONL.
"""


def ensure_hub(adir):
    """AL7 requires the bundle be registered in the knowledge graph through a hub artifact.
    Nothing created it: a fresh install produced audit-data.js, audit-log.jsonl and
    index.html but no .md, so the bundle was invisible to the graph. Bootstrapped here
    alongside the viewer (AL11) because the same trigger applies - if it is missing, make it.

    Links are deliberately EMPTY: a fresh install has no other artifact to point at, and a
    dangling link fails `docs-graph.py validate` outright. An INBOUND link (from the UI guide
    hub, or the first skill-authored artifact) clears the orphan check - verified by execution.
    """
    path = os.path.join(adir, "audit-log.md")
    if os.path.exists(path):
        return False
    stamp = now_iso()
    review = "%d%s" % (int(stamp[:4]) + 1, stamp[4:10])
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(HUB % review)
    return True


# ---------- viewer (self-bootstrap from the template) ----------
def find_template():
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "..", "templates", "audit-explorer.template.html"),
                 os.path.join(here, "..", "..", "templates", "audit-explorer.template.html")):
        if os.path.exists(cand):
            return os.path.abspath(cand)
    return None


def project_name(root):
    return os.path.basename(os.path.abspath(os.path.join(root, "..")))


def render(root, project=None):
    """Regenerate audit-data.js and the managed viewer from canonical sources."""
    ensure_hub(audit_dir(root))
    os.makedirs(audit_dir(root), exist_ok=True)
    data = {"project": project or project_name(root), "generated": now_iso(),
            "audit": read_log(root, "audit"), "changes": read_log(root, "change")}
    # </ is escaped so a prompt containing </script> can never break the <script> host.
    payload = json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")
    body = ("// Derived from docs/audit/*.jsonl by scripts/audit-log.py — DO NOT hand-edit"
            " (the JSONL logs are the source of truth; see audit-and-change-log.md).\n"
            "window.AUDIT_DATA = " + payload + ";\n")
    with open(os.path.join(audit_dir(root), "audit-data.js"), "w", encoding="utf-8") as out:
        out.write(body)
    idx = os.path.join(audit_dir(root), "index.html")
    tpl = find_template()
    if tpl:
        with open(tpl, encoding="utf-8") as src:
            viewer = src.read().replace(
                "__PROJECT__", html.escape(data["project"], quote=True)
            )
        with open(idx, "w", encoding="utf-8") as out:
            out.write(viewer)
    return data


# ---------- field collection (flags / files / stdin JSON) ----------
def _read_field(value, value_file):
    if value_file:
        if value_file == "-":
            return sys.stdin.read().rstrip("\n")
        with open(value_file, encoding="utf-8") as handle:
            return handle.read().rstrip("\n")
    return value

def _from_json(arg):
    if not arg:
        return {}
    if arg == "-":
        text = sys.stdin.read()
    else:
        with open(arg, encoding="utf-8") as handle:
            text = handle.read()
    obj = json.loads(text)
    return obj if isinstance(obj, dict) else {}


# ---------- subcommands ----------
def cmd_start(args):
    """Instrumentation over inference (IO1): called as a skill's FIRST action (grounding). It
    persists the run's start stamp keyed by session, so the closing `append` records
    duration_seconds automatically -- no flag to remember, no variable to thread through.
    That is what makes the measurement default-on rather than opt-in."""
    stamp = record_start(args.root, args.session)
    print(stamp)
    return 0


def cmd_append(args):
    base = _from_json(getattr(args, "from_json", None))
    prompt = _read_field(args.prompt, args.prompt_file) or base.get("prompt")
    summary = _read_field(args.summary, args.summary_file) or base.get("summary")
    shortname = args.shortname or base.get("shortname")
    session = args.session or base.get("session")
    missing = [k for k, v in [("shortname", shortname), ("session", session),
                              ("prompt", prompt), ("summary", summary)] if not v]
    if missing:
        sys.stderr.write(f"audit-log append: missing required field(s): {', '.join(missing)}\n")
        return 2
    entries = read_log(args.root, "audit")
    entry = {
        "id": next_id(entries, "al"),
        "shortname": shortname,
        "datetime": args.datetime or base.get("datetime") or now_iso(),
        "session": session,
        "prompt": prompt,
        "summary": summary,
        "kind": args.kind or base.get("kind") or "manual",
        "skill": args.skill or base.get("skill"),
        "tool": args.tool or base.get("tool"),
        "actor": args.actor or base.get("actor"),
        "artifacts": (args.artifact or []) or base.get("artifacts") or [],
        "tags": (args.tag or []) or base.get("tags") or [],
        "outcome": args.outcome or base.get("outcome") or "success",
    }
    # Front-matter goal-state (CT19): done_when is the terminal condition, and is the PACK-O
    # PRESENCE signal /dream mines (a substantive turn without it skipped the front matter, AL5b).
    for _opt in ("goal", "done_when", "tier"):
        _v = getattr(args, _opt, None) or base.get(_opt)
        if _v:
            entry[_opt] = _v
    # CT19 tier + fan-out cap: the ceremony budget the turn declared. fan_out is the CAP it
    # declared; agent_runs (below) is what it actually convened, so /dream can compare the two.
    _fo = getattr(args, "fan_out", None)
    if _fo is None:
        _fo = base.get("fan_out")
    if _fo is not None:
        entry["fan_out"] = int(_fo)
    # Watcher telemetry convention (AL2a): an OPTIONAL `signals` object carrying the deterministic
    # signals a turn actually OBSERVED at close, read by the watcher's DeterministicSignalsDeriver to
    # lift an imported episode above its conservative default. Honest by construction - only supplied
    # fields are emitted, so anything absent stays a conservative default rather than a fabricated
    # value (spec L127 / NG1). The flags cover the safe, close-observable booleans; a richer caller
    # may supply the full object (incl. the judgement-laden guidance_*/coordination_* counts, which
    # get no flag precisely so a harness cannot fabricate them) via --from-json.
    _signals = dict(base.get("signals") or {})
    for _flag, _key in (("signal_verification_path", "verification_path"),
                        ("signal_verification_executed", "verification_executed"),
                        ("signal_acceptance_met", "acceptance_met"),
                        ("signal_regression", "regression")):
        _sv = getattr(args, _flag, None)
        if _sv is not None:
            _signals[_key] = (_sv == "true")
    if _signals:
        entry["signals"] = _signals
    # Instrumentation over inference (IO1): duration is DEFAULT-ON. An explicit --started wins;
    # otherwise the stamp recorded by `start --session` at grounding is picked up automatically,
    # so no caller has to remember a flag. Absent/unparseable/skewed -> no duration, never a
    # wrong one (IO8). This closes the gap that forced the optimize-graph back-test to model
    # elapsed time instead of measuring it.
    _started = (args.started or base.get("started_at")
                or consume_start(args.root, session))
    entry.update(duration_fields(_started, entry["datetime"]))
    # P8: per-run spans make fan-out measurable. Summed agent time cannot tell serial from
    # parallel; the union of the intervals can. Unusable spans are dropped and COUNTED, so a
    # partial record never masquerades as a complete one.
    _specs = (getattr(args, "agent_run", None) or []) or base.get("agent_run") or []
    if _specs:
        _spans = [parse_agent_run(s) for s in _specs]
        _usable = [s for s in _spans if s]
        if _usable:
            entry["agent_runs"] = [{k: v for k, v in s.items() if not k.startswith("_")}
                                   for s in _usable]
            entry["parallelism"] = parallelism_fields(_usable)
        _dropped = len(_spans) - len(_usable)
        if _dropped:
            entry.setdefault("parallelism", {})["unparseable_runs"] = _dropped
    # P6: what the convocation was worth, not just what it cost.
    _yields = (getattr(args, "persona_yield", None) or []) or base.get("persona_yield") or []
    if _yields:
        _rows = [r for r in (parse_persona_yield(y) for y in _yields) if r]
        if _rows:
            entry["persona_yield"] = _rows
    if args.change or base.get("change"):
        entry["change"] = args.change or base.get("change")
    if args.git:
        entry["git"] = git_context(args.root)
    append_log(args.root, "audit", entry)
    render(args.root, args.project)
    print(entry["id"])
    return 0


def cmd_change(args):
    base = _from_json(getattr(args, "from_json", None))
    title = args.title or base.get("title")
    summary = _read_field(args.summary, args.summary_file) or base.get("summary")
    missing = [k for k, v in [("title", title), ("summary", summary)] if not v]
    if missing:
        sys.stderr.write(f"audit-log change: missing required field(s): {', '.join(missing)}\n")
        return 2
    after = git_context(args.root)
    before = args.git_before or base.get("git_before")
    entries = read_log(args.root, "change")
    entry = {
        "id": next_id(entries, "cl"),
        "datetime": args.datetime or now_iso(),
        "session": args.session or base.get("session"),
        "kind": args.kind or base.get("kind") or "decision",
        "skill": args.skill or base.get("skill"),
        "title": title,
        "prompt": _read_field(args.prompt, args.prompt_file) or base.get("prompt"),
        "summary": summary,
        "rationale": args.rationale or base.get("rationale"),
        "artifacts": (args.artifact or []) or base.get("artifacts") or [],
        "tags": (args.tag or []) or base.get("tags") or [],
        "git": {"before": before, "after": after.get("sha"), "branch": after.get("branch"),
                "pushed": after.get("pushed"), "commits": commits_between(before, after.get("sha"), args.root)},
    }
    if args.supersedes or base.get("supersedes"):
        entry["supersedes"] = args.supersedes or base.get("supersedes")
    if args.audit_ref or base.get("audit_ref"):
        entry["audit_ref"] = args.audit_ref or base.get("audit_ref")
    append_log(args.root, "change", entry)
    render(args.root, args.project)
    print(entry["id"])
    return 0


def _fmt_row(e, which):
    when = (e.get("datetime") or "")[:16].replace("T", " ")
    if which == "audit":
        label = e.get("shortname") or e.get("skill") or e.get("kind") or "—"
    else:
        label = e.get("title") or e.get("kind") or "—"
    summ = (e.get("summary") or "").replace("\n", " ")
    if len(summ) > 80:
        summ = summ[:77] + "…"
    sess = (e.get("session") or "")[:8]
    return f"{e.get('id','?'):<8} {when:<16} {sess:<8} {label[:24]:<24} {summ}"


def cmd_list(args):
    entries = read_log(args.root, args.kind)
    if args.json:
        print(json.dumps(entries[-args.n:], ensure_ascii=False, indent=2))
        return 0
    sel = entries[-args.n:]
    if not sel:
        print(f"(no {args.kind} entries yet)")
        return 0
    print(f"{'id':<8} {'datetime':<16} {'session':<8} {'label':<24} summary")
    for e in sel:
        print(_fmt_row(e, args.kind))
    return 0


def _matches(e, kw):
    if not kw:
        return True
    hay = " ".join(str(e.get(k, "")) for k in
                   ("id", "shortname", "title", "prompt", "summary", "skill", "kind", "actor"))
    hay += " " + " ".join(e.get("tags") or []) + " " + " ".join(e.get("artifacts") or [])
    return kw.lower() in hay.lower()


def cmd_search(args):
    entries = read_log(args.root, args.kind)
    res = []
    for e in entries:
        if args.session and args.session not in str(e.get("session", "")):
            continue
        dt = str(e.get("datetime", ""))
        if args.since and dt < args.since:
            continue
        if args.until and dt > args.until:
            continue
        if not _matches(e, args.keyword):
            continue
        res.append(e)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if not res:
        print("(no matches)")
        return 0
    print(f"{'id':<8} {'datetime':<16} {'session':<8} {'label':<24} summary")
    for e in res:
        print(_fmt_row(e, args.kind))
    print(f"\n{len(res)} match(es)")
    return 0


def cmd_get(args):
    for which in ("audit", "change"):
        for e in read_log(args.root, which):
            if str(e.get("id")) == args.id:
                if args.field:
                    print(e.get(args.field, ""))
                else:
                    print(json.dumps(e, ensure_ascii=False, indent=2))
                return 0
    sys.stderr.write(f"audit-log get: id not found: {args.id}\n")
    return 1


def cmd_render(args):
    data = render(args.root, args.project)
    print(f"rendered {len(data['audit'])} audit + {len(data['changes'])} change entries "
          f"-> {os.path.join(audit_dir(args.root), 'audit-data.js')}")
    return 0


def cmd_git_context(args):
    print(json.dumps(git_context(args.root), indent=2))
    return 0


def cmd_yield(args):
    """Persona yield across the log: what each lens raised, and what actually landed (P6).

    This is the report the roster is tuned from. It never issues a verdict on a persona --
    it reports the ratio and marks the ones with no evidence either way, because "never
    raised anything" and "raised things nobody took" are different facts with different
    responses.
    """
    entries = read_log(args.root, "audit")
    stats = aggregate_persona_yield(entries)
    if not stats:
        print("no persona_yield records in the log yet - "
              "append with --persona-yield '<persona>|<raised>|<accepted>'")
        return 0
    rows = sorted(stats.items(), key=lambda kv: (kv[1]["acceptance"] is None,
                                                 kv[1]["acceptance"] or 0,
                                                 -kv[1]["raised"]))
    print(f"{'persona':<34}{'runs':>6}{'raised':>8}{'accepted':>10}{'acceptance':>12}")
    for name, acc in rows:
        ratio = "no evidence" if acc["acceptance"] is None else f"{acc['acceptance']:.0%}"
        print(f"{name:<34}{acc['sessions']:>6}{acc['raised']:>8}{acc['accepted']:>10}{ratio:>12}")
    print()
    print("An ADVISORY lens re-convenes on the same work only after a finding it raised was")
    print("accepted. A HARD-VETO lens is never yield-gated: a veto exists to be able to say")
    print("no, and a quiet one usually means the work was clean.")
    return 0


def cmd_verify(args):
    """FR-052. Assert the system of record is fully readable.

    `read_log` deliberately survives a malformed line so the tooling keeps working — but a
    line that is silently dropped is a line /dream will never see, and the consolidation
    would report success over an incomplete corpus. This makes the skip COUNTABLE and
    therefore gateable: exit 1 while any line is unreadable, naming file and line number.
    """
    del LOG_READ_SKIPS[:]
    counts = {}
    for which in ("audit", "change"):
        counts[which] = len(read_log(args.root, which, warn=False))
    if not LOG_READ_SKIPS:
        print(f"audit log verified: {counts['audit']} audit + {counts['change']} change "
              f"entries, 0 unreadable lines")
        return 0
    for skip in LOG_READ_SKIPS:
        print(f"UNREADABLE {skip['file']}:{skip['line']}: {skip['error']}", file=sys.stderr)
    print(f"audit log verify: {len(LOG_READ_SKIPS)} unreadable line(s) — these entries are "
          f"invisible to every reader, including /dream. Repair them.", file=sys.stderr)
    return 1


def cmd_suggest(args):
    """Advisory: surface meaningful changes that may not be in the change log yet."""
    changes = read_log(args.root, "change")
    last_after = None
    for e in changes:
        a = (e.get("git") or {}).get("after")
        if a:
            last_after = a
    head = git(["rev-parse", "HEAD"], args.root)
    findings = []

    def _candidate(ln):
        # CL3 + FR-071: surface a commit only if its subject signals a decision AND it is not
        # itself a logging closeout (a commit that wrote an audit .jsonl is already logged).
        ln = ln.strip()
        if not ln:
            return
        sha, _, subject = ln.partition(" ")
        if not _suggests_decision(subject):
            return
        if _is_logging_commit(sha, args.root):
            return
        findings.append(("commit", ln))

    if last_after and head:
        for ln in commits_between(last_after, head, args.root):
            _candidate(ln)
    elif head:
        for ln in (git(["log", "-n", str(args.n), "--pretty=%h %s"], args.root) or "").split("\n"):
            _candidate(ln)
    # New decision artifacts (ADRs / decision notes) not referenced by any change entry.
    referenced = " ".join(json.dumps(e) for e in changes)
    for sub in ("adr", "notes"):
        d = os.path.join(args.root, sub)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith(".md") and f[:-3] not in referenced and f not in referenced:
                    findings.append(("artifact", f"docs/{sub}/{f}"))
    if not findings:
        print("no unlogged meaningful changes detected")
        return 0
    print("Possible meaningful changes not yet in the change log "
          "(promote with `audit-log.py change`):")
    for kind, what in findings:
        print(f"  [{kind}] {what}")
    return 0


# PACK-O substantive turns: the kinds that carry a goal-state. Must match dream.py's PACKO_SUBSTANTIVE
# (the same presence check, run offline over the fleet corpus) - kept as one small stable definition
# per script because both are standalone stdlib scripts that cannot import each other cleanly.
PACKO_SUBSTANTIVE = {"skill", "manual", "prompt", "command"}


def cmd_selfcheck(args):
    """Bounded inline session self-assessment (FC-1, spec-agent-focus-controls). One deterministic
    pass over a session's substantive turns -> goal-state presence gaps + done_when->summary review
    pairs. Advisory and never a scope verdict (the agent/human judges drift); no network, no model,
    no second pass. This is the rung-2 mechanical aid to the CT25 closing self-assessment."""
    entries = read_log(args.root, "audit")
    if args.session:
        entries = [e for e in entries if e.get("session") == args.session]
    subst = [e for e in entries if e.get("kind") in PACKO_SUBSTANTIVE]
    gaps = [e for e in subst if not e.get("done_when")]
    have = [e for e in subst if e.get("done_when")]
    tier_gaps = [e for e in have if not e.get("tier")]
    over_cap = [e for e in subst if e.get("fan_out") is not None and len(e.get("agent_runs") or []) > int(e.get("fan_out") or 0)]
    review = [{"shortname": e.get("shortname", "?"),
               "done_when": e.get("done_when", ""),
               "summary": e.get("summary", "")} for e in have]
    if args.json:
        print(json.dumps({
            "session": args.session, "substantive": len(subst),
            "gaps": [{"shortname": e.get("shortname", "?"), "id": e.get("id")} for e in gaps],
            "tier_gaps": [{"shortname": e.get("shortname", "?"), "id": e.get("id")} for e in tier_gaps],
            "over_cap": [{"shortname": e.get("shortname", "?"), "id": e.get("id"), "fan_out": e.get("fan_out"),
                          "agent_runs": len(e.get("agent_runs") or [])} for e in over_cap],
            "review": review,
        }, ensure_ascii=False, indent=2))
        return 0
    scope = f"session {args.session}" if args.session else "all sessions"
    if not subst:
        print(f"no substantive turns for {scope}")
        return 0
    print(f"self-assessment ({scope}): {len(subst)} substantive turn(s), "
          f"{len(gaps)} without a goal-state")
    if gaps:
        print("  goal-state GAPS (substantive turns that recorded no done_when - the PACK-O signal):")
        for e in gaps:
            print(f"    [gap] {e.get('shortname', '?')}")
    else:
        print(f"  all {len(subst)} substantive turns recorded a goal-state.")
    if tier_gaps:
        print("  tier GAPS (goal-state without a tier - the ceremony budget was never declared, CT19 / CTX-C):")
        for e in tier_gaps:
            print(f"    [tier] {e.get('shortname', '?')}")
    if over_cap:
        print("  fan-out OVER CAP (more agent_runs than the declared fan_out - a council above tier unless a hard gate was named):")
        for e in over_cap:
            print(f"    [cap] {e.get('shortname', '?')}: {len(e.get('agent_runs') or [])} runs vs cap {e.get('fan_out')}")
    if review:
        print("  scope review (done_when -> summary; judge drift yourself, this is not a verdict):")
        for r in review:
            print(f"    {r['shortname']}: '{r['done_when'][:60]}' -> '{r['summary'][:80]}'")
    return 0


def cmd_import(args):
    """Ingest a session-export JSON array of turns into the audit log (build on session history)."""
    if args.file == "-":
        text = sys.stdin.read()
    else:
        with open(args.file, encoding="utf-8") as handle:
            text = handle.read()
    rows = json.loads(text)
    if isinstance(rows, dict):
        rows = rows.get("turns") or rows.get("entries") or [rows]
    entries = read_log(args.root, "audit")
    existing = {e.get("id") for e in entries}
    added = 0
    for r in rows:
        prompt = r.get("prompt") or r.get("user_message") or ""
        summary = r.get("summary") or r.get("assistant_response") or ""
        if not (prompt or summary):
            continue
        if len(summary) > 280:
            summary = summary[:277] + "…"
        eid = next_id(entries, "al")
        entry = {
            "id": eid,
            "shortname": r.get("shortname") or (r.get("session", "") or "session")[:8] + f"-t{r.get('turn_index', added)}",
            "datetime": r.get("datetime") or r.get("timestamp") or now_iso(),
            "session": r.get("session") or r.get("session_id") or args.session,
            "prompt": prompt,
            "summary": summary or "(imported turn)",
            "kind": "session-import",
            "skill": r.get("skill"),
            "tool": r.get("tool") or args.tool,
            "actor": r.get("actor"),
            "artifacts": r.get("artifacts") or [],
            "tags": r.get("tags") or ["imported"],
            "outcome": r.get("outcome") or "success",
        }
        if eid in existing:
            continue
        entries.append(entry)
        append_log(args.root, "audit", entry)
        existing.add(eid)
        added += 1
    render(args.root, args.project)
    print(f"imported {added} session turn(s) into the audit log")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="audit-log.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="docs", help="docs root (default: docs); audit dir is <root>/audit")
    ap.add_argument("--project", default=None, help="project name for the viewer (default: repo dir name)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_a = sub.add_parser("append", help="add an audit entry")
    ap_a.add_argument("--shortname"); ap_a.add_argument("--session"); ap_a.add_argument("--prompt")
    ap_a.add_argument("--prompt-file", dest="prompt_file"); ap_a.add_argument("--summary")
    ap_a.add_argument("--summary-file", dest="summary_file"); ap_a.add_argument("--datetime")
    ap_a.add_argument("--kind", choices=AUDIT_KINDS); ap_a.add_argument("--skill")
    ap_a.add_argument("--tool"); ap_a.add_argument("--actor")
    ap_a.add_argument("--artifact", action="append"); ap_a.add_argument("--tag", action="append")
    ap_a.add_argument("--outcome", choices=["success", "partial", "failed", "blocked"])
    ap_a.add_argument("--change", help="link to a change-log id (cl-NNNN)")
    ap_a.add_argument("--goal", help="the turn's goal (front matter CT19)")
    ap_a.add_argument("--done-when", dest="done_when", help="the terminal condition (front matter CT19); the PACK-O presence signal /dream mines (AL5b)")
    ap_a.add_argument("--tier", choices=["T0", "T1", "T2"], help="the turn's declared ceremony tier (front matter CT19)")
    ap_a.add_argument("--fan-out", dest="fan_out", type=int, help="the declared fan-out cap: most sub-agents the turn may convene (CT19; 0 at T0, 2 at T1)")
    # Watcher telemetry convention (AL2a): the safe, close-observable deterministic signals a turn
    # may record. Tri-state (absent -> omitted -> the watcher reader's conservative default; NG1).
    ap_a.add_argument("--signal-verification-path", dest="signal_verification_path",
                      choices=["true", "false"],
                      help="signal: a committed Proof Pack / verification path exists (watcher AL2a)")
    ap_a.add_argument("--signal-verification-executed", dest="signal_verification_executed",
                      choices=["true", "false"],
                      help="signal: the verification (red-observed) was actually executed")
    ap_a.add_argument("--signal-acceptance-met", dest="signal_acceptance_met",
                      choices=["true", "false"],
                      help="signal: the done_when acceptance criterion was met")
    ap_a.add_argument("--signal-regression", dest="signal_regression",
                      choices=["true", "false"],
                      help="signal: a known regression was introduced (a claim, so emit only when checked)")
    ap_a.add_argument("--git", action="store_true", help="capture current git context")
    ap_a.add_argument("--started", help="ISO-8601 UTC start stamp captured at grounding; records "
                                        "started_at + duration_seconds so elapsed time is MEASURED, "
                                        "not modeled (instrumentation over inference, IO1)")
    ap_a.add_argument("--agent-run", dest="agent_run", action="append", metavar="AGENT|START|END",
                      help="one sub-agent run as '<agent>|<start-iso>|<end-iso>'; repeatable. "
                           "Records agent_runs + a parallelism block (agent_seconds, span_seconds, "
                           "speedup, peak_concurrency) so fan-out is MEASURED, not asserted (P8). "
                           "Summed duration cannot tell serial from parallel; the union of the "
                           "intervals can.")
    ap_a.add_argument("--persona-yield", dest="persona_yield", action="append",
                      metavar="PERSONA|RAISED|ACCEPTED",
                      help="one persona's findings raised vs accepted; repeatable. Makes the "
                           "roster tunable on measured yield rather than belief (P6) — an "
                           "advisory lens re-convenes only on an accepted finding.")
    ap_a.add_argument("--from-json", dest="from_json", help="read fields from a JSON object (path or - for stdin)")

    ap_c = sub.add_parser("change", help="add a change-log entry")
    ap_c.add_argument("--title"); ap_c.add_argument("--summary"); ap_c.add_argument("--summary-file", dest="summary_file")
    ap_c.add_argument("--session"); ap_c.add_argument("--kind", choices=CHANGE_KINDS); ap_c.add_argument("--skill")
    ap_c.add_argument("--prompt"); ap_c.add_argument("--prompt-file", dest="prompt_file"); ap_c.add_argument("--rationale")
    ap_c.add_argument("--artifact", action="append"); ap_c.add_argument("--tag", action="append")
    ap_c.add_argument("--supersedes"); ap_c.add_argument("--audit-ref", dest="audit_ref")
    ap_c.add_argument("--git-before", dest="git_before", help="HEAD sha captured before the work began")
    ap_c.add_argument("--datetime")
    ap_c.add_argument("--from-json", dest="from_json", help="read fields from a JSON object (path or - for stdin)")

    ap_l = sub.add_parser("list", help="show the last N entries")
    ap_l.add_argument("--n", type=int, default=10); ap_l.add_argument("--kind", choices=["audit", "change"], default="audit")
    ap_l.add_argument("--json", action="store_true")

    ap_s = sub.add_parser("search", help="filter by session/datetime/keyword")
    ap_s.add_argument("--kind", choices=["audit", "change"], default="audit")
    ap_s.add_argument("--session"); ap_s.add_argument("--since"); ap_s.add_argument("--until")
    ap_s.add_argument("--keyword"); ap_s.add_argument("--json", action="store_true")

    ap_g = sub.add_parser("get", help="print one entry by id")
    ap_g.add_argument("--id", required=True); ap_g.add_argument("--field", help="print just this field (e.g. prompt)")

    sub.add_parser("render", help="regenerate audit-data.js and ensure the viewer exists")
    sub.add_parser("git-context", help="print current git context as JSON")
    ap_y = sub.add_parser("yield", help="persona yield: findings raised vs accepted (P6)")
    ap_y.set_defaults(func=cmd_yield)
    sub.add_parser("verify", help="fail if any log line is unreadable (FR-052; CI-able)")

    ap_sug = sub.add_parser("suggest", help="surface meaningful changes not yet in the change log")
    ap_sug.add_argument("--n", type=int, default=15)

    ap_sc = sub.add_parser("selfcheck", help="bounded inline session self-assessment (FC-1): "
                                             "goal-state presence gaps + scope review for a session")
    ap_sc.add_argument("--session", help="the session to self-assess (recommended)")
    ap_sc.add_argument("--json", action="store_true")

    ap_imp = sub.add_parser("import", help="ingest a session-export JSON array into the audit log")
    ap_imp.add_argument("--file", default="-", help="JSON file (or - for stdin)")
    ap_imp.add_argument("--session"); ap_imp.add_argument("--tool")

    ap_st = sub.add_parser("start", help="record this run's start stamp (call at grounding) so the "
                                         "closing `append` records duration automatically (IO1)")
    ap_st.add_argument("--session", help="session id the closing append will use")

    args = ap.parse_args()
    dispatch = {
        "append": cmd_append, "change": cmd_change, "list": cmd_list, "search": cmd_search,
        "get": cmd_get, "render": cmd_render, "git-context": cmd_git_context,
        "suggest": cmd_suggest, "import": cmd_import, "start": cmd_start,
        "verify": cmd_verify, "selfcheck": cmd_selfcheck, "yield": cmd_yield,
    }
    sys.exit(dispatch[args.cmd](args))


if __name__ == "__main__":
    main()
