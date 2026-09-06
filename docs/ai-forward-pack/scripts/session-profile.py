#!/usr/bin/env python3
"""session-profile.py — measure how agent sessions actually ran, across harnesses and models.

Instrumentation over inference (IO1) pointed at the agent's own work: instead of reasoning
about why a session felt slow, expensive or drifty, READ the telemetry every harness already
writes to disk and turn it into a findings table (what happened, with evidence) and a fixes
table (which pack surface owns the control). This is the "asleep half" of continuous
improvement (`/dream`) specialised to performance, efficiency, task adherence, fan-out and
cross-harness coordination — the /session-profiler skill drives it.

Sources (all local, all read-only):

  GitHub Copilot CLI   ~/.copilot/session-store.db        sessions, turns, assistant_usage_events
                       ~/.copilot/session-state/<id>/events.jsonl   the full event stream
                       ~/.copilot/settings.json           model / contextTier / effortLevel
  Claude Code          ~/.claude/projects/<slug>/<session>.jsonl    the transcript

A repo is selected by path (`--repo <path>`, repeatable). Copilot sessions match on cwd or the
`owner/name` remote; Claude Code sessions match on the project slug of the repo path and of each
of its git worktrees. Every number is either read from the store or labelled as an estimate;
a measurement path that does not exist reports "not recorded", never a plausible number (IO8).

Subcommands
  discover   list the sessions found for the repo(s) in the window
  profile    per-turn metrics + findings + fixes for the selected sessions; writes
             docs/profiles/<sp-id>/{profile.json,profile.md} in the FIRST --repo (or --out-root)
  compare    aggregate the same metrics by model family x harness (the tuning view)
  fixes      print the fix catalog (finding id -> pack surface -> control)

Python 3.8+, stdlib only. Windows-safe (utf-8 stdout, read-only SQLite URI).
"""
import argparse
import collections
import datetime as _dt
import glob
import json
import os
import re
import sqlite3
import statistics
import subprocess
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

NOT_RECORDED = "not recorded"
HERE = os.path.dirname(os.path.abspath(__file__))

# Calibration used ONLY for character->token estimates of static text (system prompts, files).
# Two measured points disagree (4.83 chars/token over knowledge docs on claude-opus-5;
# 3.54 over a full Copilot system prompt on claude-opus-4.8), so the figure is a parameter,
# printed with every estimate, never presented as a measurement (NG6).
CHARS_PER_TOKEN = 3.54

# --------------------------------------------------------------------------- catalogs
# The fix catalog: every finding maps to a pack surface that owns its control. Keep the ids
# stable - profiles reference them and /dream mines them.
FIXES = collections.OrderedDict([
    ("F-01", {"title": "CLAUDE.md is an `@AGENTS.md` import, not a copy",
              "where": "adapters/managed-blocks/CLAUDE.block.md; INSTALL.md 1.1; pack-doctor `claude-md import`",
              "control": "pack-doctor FAILs a repo whose CLAUDE.md carries the managed block beside an AGENTS.md that carries it too"}),
    ("F-02", {"title": "Measure the real static prefix, not the knowledge docs alone",
              "where": "scripts/context-budget.py prefix; context-budget.json",
              "control": "`context-budget.py prefix --gate` ratchets the whole prefix (blocks + always-on + tool/host allowance)"}),
    ("F-03", {"title": "Declare tier and fan-out cap in the goal state; record them in the audit entry",
              "where": "knowledge/communication-and-task-discipline.md CT19; scripts/audit-log.py --tier/--fan-out; /dream PACK-O miner",
              "control": "audit selfcheck + /dream flag a substantive turn with no tier, or a fan-out above the tier cap with no named hard gate"}),
    ("F-04", {"title": "Every delegation carries a tool-call budget and a convergence condition",
              "where": "knowledge/execution-graph-optimization.md GO7; agent cards; audit `agent_runs`",
              "control": "a sub-agent past its budget stops and reports; the audit entry records calls vs budget"}),
    ("F-05", {"title": "Persona cards are self-sufficient; no orientation reads",
              "where": "adapters/*/agents/*.md (inline operating standard + do-not-read list)",
              "control": "eval: a persona transcript contains no view of AGENTS.md / persona-* / agent-body-of-knowledge"}),
    ("F-06", {"title": "Progressive-disclosure skills; never re-invoke an active skill",
              "where": "commands/*/SKILL.md + reference/; context-budget.py skills (ratchet)",
              "control": "`context-budget.py skills --gate` fails unacknowledged SKILL.md growth; /dream flags a skill invoked twice in one turn"}),
    ("F-07", {"title": "Re-read guard hook",
              "where": "adapters/hooks/reread-guard.py (+ .github/hooks/ai-forward.json, .claude/settings.json)",
              "control": "the hook warns on the third identical view in a turn and on a paged tool output viewed whole"}),
    ("F-08", {"title": "UI craft docs load on demand with a rule index; screenshots stay out of the main context",
              "where": "knowledge/ui-*.md (load: skill + rule index); commands/ui-design",
              "control": "Tier B/C totals in context-budget; /ui-design Stage 3 reads the craft JSON"}),
    ("F-09", {"title": "Session hygiene: a new task starts a new session; tier and effort are per phase",
              "where": "knowledge/session-worktree-discipline.md WT1a; INSTALL.md (Copilot); pack-doctor `copilot settings`",
              "control": "pack-doctor WARNs on long_context + high effort as global defaults; this profiler flags context accretion"}),
    ("F-10", {"title": "Tune guidance per model family from measured drift, not priors",
              "where": "docs/profiles/ (this tool's compare view); knowledge/execution-graph-optimization.md GO19",
              "control": "`session-profile.py compare` - a family with 2x the drift indicators of another is a tuning finding"}),
    ("F-11", {"title": "Register the class, not the instance",
              "where": "docs/lessons/defect-classes.md (CTX-*); knowledge/continuous-improvement.md 6",
              "control": "each class row links to the control above; /dream re-surfaces an uncontrolled recurrence"}),
    ("F-12", {"title": "Ask each host for its richest reasoning summary, and treat summary-derived judgements as Inferred",
              "where": "INSTALL.md 1.6; adapters/hooks/claude-code.settings.hooks.json (showThinkingSummaries); pack-doctor `claude settings`",
              "control": "SP-17 reports visible-reasoning share per family; a family under 10% marks every text-derived drift finding Inferred"}),
    ("F-13", {"title": "Externalize reasoning by construction: a one-line intent on every shell call",
              "where": "knowledge/communication-and-task-discipline.md CT26; the managed block; agent cards",
              "control": "SP-18 intent-trace coverage per family; below 90% is a finding; the hook and the profiler read the same field"}),
])

# Finding catalog: id -> (title, default severity, fix ids). Severity uses the pack scale.
FINDINGS = collections.OrderedDict([
    ("SP-01", ("Context accretion: the main conversation grew past the point where every step re-reads a book", "Major", ["F-09", "F-01"])),
    ("SP-02", ("Instruction double-load: two near-identical custom-instruction blocks in the static prefix", "Major", ["F-01"])),
    ("SP-03", ("Static prefix larger than the budget models", "Major", ["F-02"])),
    ("SP-04", ("Re-reads: the same file viewed three or more times in one turn, or a paged tool output viewed whole", "Minor", ["F-07"])),
    ("SP-05", ("Skill re-injection: the same skill invoked more than once in a session", "Minor", ["F-06"])),
    ("SP-06", ("Council above tier: a fan-out on a turn that declared no tier", "Major", ["F-03"])),
    ("SP-07", ("Sub-agent runaway: a delegation past a sane tool-call/token budget, or one the parent had to tell to converge", "Major", ["F-04"])),
    ("SP-08", ("Persona orientation reads: a sub-agent reading the roster docs or AGENTS.md to find out what it is", "Minor", ["F-05"])),
    ("SP-09", ("No goal state: a substantive turn whose first reply carries no Goal / Done when", "Major", ["F-03"])),
    ("SP-10", ("Tail latency: main-agent time-to-first-token p90 above 20 s", "Minor", ["F-09", "F-02"])),
    ("SP-11", ("Cap firings: harness completion nudges or user aborts inside a turn", "Minor", ["F-03"])),
    ("SP-12", ("Images and failed requests in the main context", "Minor", ["F-08"])),
    ("SP-13", ("Hook overhead above 5% of wall clock", "Nit", [])),
    ("SP-14", ("Model-family gap: one family carries 2x the cost or drift indicators of another on comparable turns", "Major", ["F-10"])),
    ("SP-15", ("Concurrent sessions in one checkout: overlapping sessions with the same cwd", "Major", ["F-09"])),
    ("SP-16", ("Knowledge at hand re-fetched: the main agent viewed an instruction file that is already in its prefix", "Minor", ["F-08", "F-02"])),
    ("SP-17", ("Reasoning visibility: the share of billed reasoning that came back as readable text", "Nit", ["F-12"])),
    ("SP-18", ("Intent-trace coverage: shell calls that carry a one-line description (the reasoning trace a profiler can read)", "Minor", ["F-13"])),
])

INTENT_TOOLS = {"copilot": {"powershell", "bash", "shell"}, "claude": {"Bash", "PowerShell"}}

ORIENTATION_DOCS = ("agents.md", "claude.md", "agent-persona-catalog", "persona-cards", "persona-audit",
                    "agent-body-of-knowledge")
CONVERGE_RX = re.compile(r"\b(converge now|stop (further )?investigat|stop investigating|wrap up now)\b", re.I)
GOAL_RX = re.compile(r"\bGoal\s*[:\uff1a]", re.I)
DONE_RX = re.compile(r"\bDone[\s-]*when\b", re.I)
TIER_RX = re.compile(r"\bTier\s*[:\uff1a]?\s*\**\s*T[0-3]\b", re.I)
NUDGE_RX = re.compile(r"not yet marked the task as complete|you have not finished|haven't finished|Keep working autonomously", re.I)
PAGED_OUTPUT_RX = re.compile(r"copilot-tool-output-[0-9a-f-]+\.txt$", re.I)
IMAGE_RX = re.compile(r"\.(png|jpe?g|gif|webp|bmp)$", re.I)
INSTRUCTION_RX = re.compile(r"[\\/](\.github[\\/]instructions[\\/][^\\/]+\.instructions\.md|AGENTS\.md|CLAUDE\.md)$", re.I)
SEVERITY_RANK = {"Blocker": 0, "Major": 1, "Minor": 2, "Nit": 3}


# --------------------------------------------------------------------------- helpers
def parse_ts(s):
    if not s:
        return None
    try:
        s = s.replace("Z", "+00:00")
        d = _dt.datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=_dt.timezone.utc)
        return d
    except (ValueError, AttributeError):
        return None


def iso(d):
    return d.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def pct(values, q):
    if not values:
        return None
    vals = sorted(values)
    idx = min(len(vals) - 1, max(0, int(round(q * (len(vals) - 1)))))
    return vals[idx]


def est_tokens(chars):
    return int(round(chars / CHARS_PER_TOKEN))


def model_family(model):
    m = (model or "").lower()
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"
    if m.startswith("gemini"):
        return "google"
    return "other" if m else "unknown"


def norm_path(p):
    return os.path.normcase(os.path.normpath(os.path.abspath(p))) if p else ""


def git(args, cwd):
    try:
        out = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=20)
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def repo_identity(path):
    """Everything a session could have recorded to say 'I ran in this repo'."""
    path = os.path.abspath(path)
    roots = {norm_path(path)}
    top = git(["rev-parse", "--show-toplevel"], path).strip()
    if top:
        roots.add(norm_path(top))
    for line in git(["worktree", "list", "--porcelain"], path).splitlines():
        if line.startswith("worktree "):
            roots.add(norm_path(line[len("worktree "):].strip()))
    remote = git(["remote", "get-url", "origin"], path).strip()
    slug = ""
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$", remote)
    if m:
        slug = "{0}/{1}".format(m.group(1), m.group(2)).lower()
    return {"path": path, "roots": roots, "slug": slug}


def repo_label(path):
    """A canonical, worktree-independent name for a repo (class PACK-P: a generated artifact
    must never stamp the worktree folder name): the origin owner/name when there is one, else
    the basename of the PRIMARY checkout from `git worktree list`, else the basename."""
    ident = repo_identity(path)
    if ident["slug"]:
        return ident["slug"].split("/")[-1]
    first = git(["worktree", "list", "--porcelain"], path).splitlines()
    if first and first[0].startswith("worktree "):
        return os.path.basename(first[0][len("worktree "):].strip())
    return os.path.basename(os.path.abspath(path))


def claude_slug(path):
    """Claude Code names a project directory by replacing every non-alphanumeric character in
    the absolute path with '-'. Observed: C:\\projects\\ai-forward -> C--projects-ai-forward."""
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(path))


def in_repo(identity, cwd, repository=None):
    if repository and identity["slug"] and repository.lower() == identity["slug"]:
        return True
    if not cwd:
        return False
    c = norm_path(cwd)
    for r in identity["roots"]:
        if c == r or c.startswith(r + os.sep):
            return True
    return False


# --------------------------------------------------------------------------- Copilot CLI
def copilot_home():
    return os.environ.get("COPILOT_HOME") or os.path.join(os.path.expanduser("~"), ".copilot")


def copilot_settings(home):
    try:
        with open(os.path.join(home, "settings.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _ro(db):
    return sqlite3.connect("file:{0}?mode=ro".format(db.replace("\\", "/")), uri=True)


def copilot_sessions(identity, since, home):
    db = os.path.join(home, "session-store.db")
    if not os.path.isfile(db):
        return []
    try:
        con = _ro(db)
        rows = con.execute("select id, cwd, repository, summary, created_at, updated_at from sessions").fetchall()
    except sqlite3.Error as exc:
        print("session-profile: cannot read {0}: {1}".format(db, exc), file=sys.stderr)
        return []
    out = []
    for sid, cwd, repository, summary, created, updated in rows:
        if not in_repo(identity, cwd, repository):
            continue
        c = parse_ts(created)
        u = parse_ts(updated)
        if since and (u or c) and (u or c) < since:
            continue
        out.append({"harness": "copilot", "id": sid, "cwd": cwd, "repository": repository,
                    "title": summary or "", "started": iso(c), "updated": iso(u),
                    "events": os.path.join(home, "session-state", sid, "events.jsonl"), "db": db})
    con.close()
    return out


def _load_events(path):
    events = []
    if not os.path.isfile(path):
        return events
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    return events


def _args_of(x):
    a = x.get("arguments")
    if isinstance(a, str):
        try:
            a = json.loads(a)
        except ValueError:
            a = {"_raw": a}
    return a or {}


def _new_turn():
    return {"prompt": "", "started": None, "delivery": "", "tools": collections.Counter(), "view_bytes": 0,
            "views": collections.Counter(), "paged_full_views": 0, "image_views": 0, "instruction_views": [],
            "skills": collections.Counter(), "asst_msgs": 0, "asst_text_chars": 0, "goal_state": False, "tier": False,
            "first_asst_seen": False, "nudges": 0, "aborts": 0, "errors": 0, "hook_s": 0.0, "sub": {},
            "converge_nudges": 0, "sub_orientation_reads": [], "sub_tools": 0,
            "reasoning_chars": 0, "intent_eligible": 0, "intent_with": 0}


def profile_copilot(sess, settings):
    """One Copilot session -> normalized turns + session-level facts."""
    con = _ro(sess["db"])
    usage = con.execute(
        "select turn_index, agent_id, model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
        "reasoning_tokens, total_nano_aiu, duration_ms, time_to_first_token_ms, initiator, finish_reason, created_at, "
        "reasoning_effort from assistant_usage_events where session_id=? order by id", (sess["id"],)).fetchall()
    con.close()
    events = _load_events(sess["events"])
    byid = {e.get("id"): e for e in events}

    # Turn boundaries = main-conversation user messages. The log is linear, so the rule is
    # positional (verified on the captured stream): the first user.message after a
    # subagent.started is that sub-agent's prompt; a 'queued' message is a parent->sub-agent
    # follow-up (write_agent); a message with no delivery value is never a human turn.
    # Attribution (verified on the captured stream): every event that belongs to a sub-agent
    # carries a top-level `agentId` (its user.message, system.message, assistant.*, tool.*),
    # main-conversation events carry none. A human turn is a main user.message delivered
    # 'idle' or 'steering'; anything else on the main line ('queued', no delivery) is a
    # parent->sub-agent message.
    sub_names = {}
    for e in events:
        if e.get("type") == "subagent.started":
            d = e.get("data") or {}
            sub_names[e.get("agentId")] = d.get("agentDisplayName") or d.get("agentName") or "sub-agent"
    mains = [e for e in events if e.get("type") == "user.message" and not e.get("agentId")
             and (e.get("data") or {}).get("delivery") in ("idle", "steering")]
    main_iids = {(e.get("data") or {}).get("interactionId") for e in mains}
    bounds = [parse_ts(e.get("timestamp")) for e in mains]

    def window(t):
        idx = None
        for i, b in enumerate(bounds):
            if b and t and t >= b:
                idx = i
        return idx

    # system prompt facts (the first big system.message is the main agent's prefix)
    prefix = {"chars": None, "first_chars": None, "blocks": [], "note": NOT_RECORDED}
    for e in events:
        if e.get("type") != "system.message" or e.get("agentId"):
            continue
        c = (e.get("data") or {}).get("content") or ""
        if len(c) < 100000:
            continue
        if prefix["first_chars"] is None:
            prefix["first_chars"] = len(c)
        prefix["chars"] = len(c)  # the most recent main-conversation prefix wins: it is what the next request pays
        sizes = []
        for m in re.finditer(r"<custom_instruction>", c):
            end = c.find("</custom_instruction>", m.start())
            sizes.append((end - m.start()) if end > 0 else 0)
        prefix["blocks"] = sizes
        prefix["note"] = "measured chars of the latest main prefix; tokens are an estimate at {0} chars/token".format(CHARS_PER_TOKEN)

    T = collections.defaultdict(_new_turn)
    for i, e in enumerate(mains):
        d = e.get("data") or {}
        c = d.get("content") or ""
        t = T[i]
        t["prompt"] = c[:160].replace("\n", " ")
        t["started"] = iso(parse_ts(e.get("timestamp")))
        t["delivery"] = d.get("delivery") or ""
        tc = d.get("transformedContent")
        tc = tc if isinstance(tc, str) else ""
        if c == "" and NUDGE_RX.search(tc):
            t["nudges"] += 1
            t["prompt"] = "(harness completion nudge)"
    starts, hooks, sub_names = {}, {}, {}
    for e in events:
        et = e.get("type")
        d = e.get("data") or {}
        ts = parse_ts(e.get("timestamp"))
        if et == "subagent.started":
            sub_names[e.get("agentId")] = d.get("agentDisplayName") or d.get("agentName") or "sub-agent"
        w = window(ts)
        if w is None:
            continue
        t = T[w]
        if et == "tool.execution_start":
            starts[d.get("toolCallId")] = (ts, d, e)
        elif et == "tool.execution_complete":
            s = starts.get(d.get("toolCallId"))
            if not s:
                continue
            sd, se = s[1], s[2]
            a = _args_of(sd)
            tn = sd.get("toolName") or "?"
            res = d.get("result")
            rs = len(json.dumps(res)) if res is not None else 0
            path = str(a.get("path") or a.get("file_path") or "")
            if not e.get("agentId") and d.get("interactionId") in main_iids:
                t["tools"][tn] += 1
                if tn == "view":
                    t["view_bytes"] += rs
                    if path:
                        t["views"][path] += 1
                        if PAGED_OUTPUT_RX.search(path) and not a.get("view_range"):
                            t["paged_full_views"] += 1
                        if IMAGE_RX.search(path):
                            t["image_views"] += 1
                        if INSTRUCTION_RX.search(path):
                            t["instruction_views"].append(path)
                if tn == "skill":
                    t["skills"][str(a.get("skill") or a.get("name") or "?")] += 1
                if tn == "write_agent":
                    msg = str(a.get("message") or a.get("prompt") or a.get("content") or "")
                    if CONVERGE_RX.search(msg):
                        t["converge_nudges"] += 1
                if tn in INTENT_TOOLS["copilot"]:
                    t["intent_eligible"] += 1
                    if str(a.get("description") or "").strip():
                        t["intent_with"] += 1
            else:
                t["sub_tools"] += 1
                name = sub_names.get(e.get("agentId") or se.get("agentId"), "sub-agent")
                if tn == "view" and path and any(k in path.lower() for k in ORIENTATION_DOCS):
                    t["sub_orientation_reads"].append("{0}: {1}".format(name or "sub-agent", os.path.basename(path)))
        elif et == "assistant.message" and not e.get("agentId") and d.get("interactionId") in main_iids:
            t["asst_msgs"] += 1
            c = d.get("content") or ""
            t["asst_text_chars"] += len(c)
            t["reasoning_chars"] += len(d.get("reasoningText") or "")
            if not t["first_asst_seen"] and c.strip():
                t["first_asst_seen"] = True
                t["goal_state"] = bool(GOAL_RX.search(c) and DONE_RX.search(c))
                t["tier"] = bool(TIER_RX.search(c))
        elif et == "subagent.completed":
            t["sub"][e.get("agentId")] = {
                "name": d.get("agentDisplayName") or d.get("agentName"), "model": d.get("model"),
                "tokens": d.get("totalTokens"), "tool_calls": d.get("totalToolCalls"),
                "duration_s": round((d.get("durationMs") or 0) / 1000.0)}
        elif et == "abort":
            t["aborts"] += 1
        elif et == "session.error":
            t["errors"] += 1
        elif et == "hook.start":
            hooks[d.get("hookInvocationId")] = ts
        elif et == "hook.end":
            s = hooks.get(d.get("hookInvocationId"))
            if s and ts:
                t["hook_s"] += (ts - s).total_seconds()

    # token metrics per turn from the store: align usage rows to event windows by time
    U = collections.defaultdict(list)
    for row in usage:
        (turn_index, agent_id, model, inp, out, cr, cw, rsn, aiu, dur, ttft, initiator, finish, created, effort) = row
        w = window(parse_ts(created))
        if w is None:
            continue
        U[w].append({"main": agent_id is None, "model": model, "in": inp or 0, "out": out or 0,
                     "cr": cr or 0, "cw": cw or 0, "rsn": rsn or 0, "aiu": (aiu or 0) / 1e9,
                     "dur": (dur or 0) / 1000.0, "ttft": (ttft / 1000.0) if ttft else None,
                     "created": parse_ts(created), "finish": finish, "effort": effort})
    turns = []
    for i in sorted(T):
        t = T[i]
        rows = U.get(i, [])
        main = [r for r in rows if r["main"]]
        subs = [r for r in rows if not r["main"]]
        ttfts = [r["ttft"] for r in main if r["ttft"]]
        models = sorted({r["model"] for r in rows if r["model"]})
        wall = None
        cs = [r["created"] for r in rows if r["created"]]
        if cs:
            wall = round((max(cs) - min(cs)).total_seconds() + rows[-1]["dur"])
        rereads = {p: n for p, n in t["views"].items() if n >= 3}
        turns.append({
            "turn": i, "prompt": t["prompt"], "started": t["started"], "delivery": t["delivery"],
            "models": models, "families": sorted({model_family(m) for m in models}),
            "wall_s": wall, "main_requests": len(main), "sub_requests": len(subs),
            "ctx_start": main[0]["in"] if main else None, "ctx_end": main[-1]["in"] if main else None,
            "ctx_max": max([r["in"] for r in main]) if main else None,
            "cache_read": sum(r["cr"] for r in rows), "uncached_in": sum(max(r["in"] - r["cr"] - r["cw"], 0) for r in rows),
            "cache_write": sum(r["cw"] for r in rows), "output": sum(r["out"] for r in rows),
            "reasoning": sum(r["rsn"] for r in rows), "cost_aiu": round(sum(r["aiu"] for r in rows), 1),
            "main_api_s": round(sum(r["dur"] for r in main)), "all_api_s": round(sum(r["dur"] for r in rows)),
            "ttft_p50": round(pct(ttfts, 0.5), 1) if ttfts else None,
            "ttft_p90": round(pct(ttfts, 0.9), 1) if ttfts else None,
            "ttft_max": round(max(ttfts), 1) if ttfts else None,
            "tools": dict(t["tools"]), "view_bytes": t["view_bytes"], "rereads": rereads,
            "paged_full_views": t["paged_full_views"], "image_views": t["image_views"],
            "instruction_views": t["instruction_views"], "skills": {k: v for k, v in t["skills"].items() if v},
            "asst_msgs": t["asst_msgs"], "asst_text_chars": t["asst_text_chars"],
            "goal_state": t["goal_state"], "tier": t["tier"], "nudges": t["nudges"], "aborts": t["aborts"],
            "errors": t["errors"], "hook_s": round(t["hook_s"]),
            "sub_agents": list(t["sub"].values()), "sub_tool_calls": t["sub_tools"],
            "converge_nudges": t["converge_nudges"], "sub_orientation_reads": t["sub_orientation_reads"],
            "reasoning_main": sum(r["rsn"] for r in main), "reasoning_chars": t["reasoning_chars"],
            "intent_eligible": t["intent_eligible"], "intent_with": t["intent_with"],
            "effort": collections.Counter(r["effort"] for r in main if r["effort"]).most_common(1)[0][0] if any(r["effort"] for r in main) else None,
        })
    facts = {"harness": "copilot", "id": sess["id"], "title": sess["title"], "cwd": sess["cwd"],
             "started": sess["started"], "updated": sess["updated"],
             "settings": {k: settings.get(k) for k in ("model", "contextTier", "effortLevel")},
             "prefix_chars": prefix["chars"], "prefix_tokens_est": est_tokens(prefix["chars"]) if prefix["chars"] else None,
             "prefix_first_chars": prefix["first_chars"], "prefix_blocks": prefix["blocks"], "prefix_note": prefix["note"],
             "compactions": sum(1 for e in events if str(e.get("type", "")).startswith("session.compact")),
             "events": len(events), "usage_rows": len(usage)}
    return facts, turns


# --------------------------------------------------------------------------- Claude Code
def claude_home():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def claude_sessions(identity, since, home):
    projects = os.path.join(home, "projects")
    if not os.path.isdir(projects):
        return []
    wanted = {claude_slug(r).lower() for r in identity["roots"]} | {claude_slug(identity["path"]).lower()}
    out = []
    for name in sorted(os.listdir(projects)):
        if name.lower() not in wanted:
            continue
        for path in sorted(glob.glob(os.path.join(projects, name, "*.jsonl"))):
            sid = os.path.splitext(os.path.basename(path))[0]
            mtime = _dt.datetime.fromtimestamp(os.path.getmtime(path), _dt.timezone.utc)
            if since and mtime < since:
                continue
            title, cwd = "", None
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for k, line in enumerate(fh):
                        if k > 400:
                            break
                        if '"ai-title"' in line or ('"cwd"' in line and not cwd):
                            try:
                                r = json.loads(line)
                            except ValueError:
                                continue
                            title = r.get("aiTitle") or title
                            cwd = cwd or r.get("cwd")
            except OSError:
                pass
            out.append({"harness": "claude", "id": sid, "path": path, "project": name,
                        "updated": iso(mtime), "started": None, "title": title, "cwd": cwd})
    return out


def _text_of(content):
    if isinstance(content, str):
        return content
    parts = []
    for b in content or []:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text") or "")
    return "\n".join(parts)


def profile_claude(sess):
    recs = _load_events(sess["path"])
    title, cwd, cost_state = "", None, None
    for r in recs:
        if r.get("type") == "ai-title":
            title = r.get("aiTitle") or title
        if r.get("type") == "cost-state":
            cost_state = r
        if not cwd and r.get("cwd"):
            cwd = r.get("cwd")
    turn_idx, T = -1, []
    seen_msg = set()
    for r in recs:
        rt = r.get("type")
        if rt not in ("user", "assistant"):
            continue
        msg = r.get("message") or {}
        side = bool(r.get("isSidechain"))
        ts = parse_ts(r.get("timestamp"))
        if rt == "user" and not side:
            content = msg.get("content")
            is_human = (r.get("origin") or {}).get("kind") == "human" or isinstance(content, str)
            has_tool_result = isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
            text = _text_of(content)
            if is_human and not has_tool_result:
                turn_idx += 1
                T.append({"prompt": text[:160].replace("\n", " "), "started": iso(ts), "requests": [],
                          "sub_requests": [], "tools": collections.Counter(), "views": collections.Counter(),
                          "image_views": 0, "instruction_views": [], "skills": collections.Counter(),
                          "asst_text_chars": 0, "asst_msgs": 0, "goal_state": False, "tier": False,
                          "first_asst_seen": False, "nudges": 0, "sub_agents": collections.OrderedDict(),
                          "sub_tools": 0, "sub_orientation_reads": [], "converge_nudges": 0, "models": set(),
                          "ended": None, "reasoning_chars": 0, "intent_eligible": 0, "intent_with": 0})
                m = re.search(r"<command-name>/([\w-]+)</command-name>", text)
                if m:
                    T[-1]["skills"][m.group(1)] += 1
            elif turn_idx >= 0 and NUDGE_RX.search(text):
                T[turn_idx]["nudges"] += 1
            continue
        if turn_idx < 0:
            continue
        t = T[turn_idx]
        if rt == "assistant":
            mid = msg.get("id")
            usage = msg.get("usage") or {}
            model = msg.get("model")
            if model:
                t["models"].add(model)
            if mid and mid not in seen_msg and usage:
                seen_msg.add(mid)
                row = {"main": not side, "model": model,
                       "in": (usage.get("input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0)
                             + (usage.get("cache_creation_input_tokens") or 0),
                       "cr": usage.get("cache_read_input_tokens") or 0,
                       "cw": usage.get("cache_creation_input_tokens") or 0,
                       "out": usage.get("output_tokens") or 0,
                       "rsn": ((usage.get("output_tokens_details") or {}).get("thinking_tokens") or 0),
                       "created": ts}
                (t["requests"] if not side else t["sub_requests"]).append(row)
                t["ended"] = ts
                if side:
                    aid = r.get("agentId") or r.get("sessionId")
                    t["sub_agents"].setdefault(aid, {"name": "sub-agent", "tool_calls": 0, "tokens": 0})
                    t["sub_agents"][aid]["tokens"] += row["in"] + row["out"]
            for b in msg.get("content") or []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "thinking" and not side:
                    t["reasoning_chars"] += len(b.get("thinking") or "")
                if b.get("type") == "text" and not side:
                    c = b.get("text") or ""
                    t["asst_text_chars"] += len(c)
                    t["asst_msgs"] += 1
                    if not t["first_asst_seen"] and c.strip():
                        t["first_asst_seen"] = True
                        t["goal_state"] = bool(GOAL_RX.search(c) and DONE_RX.search(c))
                        t["tier"] = bool(TIER_RX.search(c))
                elif b.get("type") == "tool_use":
                    name = b.get("name") or "?"
                    inp = b.get("input") or {}
                    path = str(inp.get("file_path") or inp.get("path") or "")
                    if side:
                        t["sub_tools"] += 1
                        aid = r.get("agentId") or r.get("sessionId")
                        t["sub_agents"].setdefault(aid, {"name": "sub-agent", "tool_calls": 0, "tokens": 0})
                        t["sub_agents"][aid]["tool_calls"] += 1
                        if name == "Read" and path and any(k in path.lower() for k in ORIENTATION_DOCS):
                            t["sub_orientation_reads"].append(os.path.basename(path))
                        continue
                    t["tools"][name] += 1
                    if name in INTENT_TOOLS["claude"]:
                        t["intent_eligible"] += 1
                        if str(inp.get("description") or "").strip():
                            t["intent_with"] += 1
                    if name in ("Agent", "Task"):
                        desc = str(inp.get("description") or inp.get("subagent_type") or "agent")
                        t["sub_agents"].setdefault("task-" + str(len(t["sub_agents"])), {"name": desc, "tool_calls": 0, "tokens": 0})
                    if name == "Read" and path:
                        t["views"][path] += 1
                        if IMAGE_RX.search(path):
                            t["image_views"] += 1
                        if INSTRUCTION_RX.search(path):
                            t["instruction_views"].append(path)
                    if name == "Skill":
                        t["skills"][str(inp.get("skill") or "?")] += 1
                    if name == "SendMessage" and CONVERGE_RX.search(str(inp.get("message") or "")):
                        t["converge_nudges"] += 1
    turns = []
    for i, t in enumerate(T):
        main = t["requests"]
        rows = main + t["sub_requests"]
        started = parse_ts(t["started"])
        wall = round((t["ended"] - started).total_seconds()) if (t["ended"] and started) else None
        rereads = {p: n for p, n in t["views"].items() if n >= 3}
        turns.append({
            "turn": i, "prompt": t["prompt"], "started": t["started"], "delivery": "idle",
            "models": sorted(t["models"]), "families": sorted({model_family(m) for m in t["models"]}),
            "wall_s": wall, "main_requests": len(main), "sub_requests": len(t["sub_requests"]),
            "ctx_start": main[0]["in"] if main else None, "ctx_end": main[-1]["in"] if main else None,
            "ctx_max": max([r["in"] for r in main]) if main else None,
            "cache_read": sum(r["cr"] for r in rows), "uncached_in": sum(max(r["in"] - r["cr"] - r["cw"], 0) for r in rows),
            "cache_write": sum(r["cw"] for r in rows), "output": sum(r["out"] for r in rows),
            "reasoning": sum(r["rsn"] for r in rows), "cost_aiu": None,
            "main_api_s": None, "all_api_s": None, "ttft_p50": None, "ttft_p90": None, "ttft_max": None,
            "tools": dict(t["tools"]), "view_bytes": None, "rereads": rereads, "paged_full_views": 0,
            "image_views": t["image_views"], "instruction_views": t["instruction_views"],
            "skills": dict(t["skills"]), "asst_msgs": t["asst_msgs"], "asst_text_chars": t["asst_text_chars"],
            "goal_state": t["goal_state"], "tier": t["tier"], "nudges": t["nudges"], "aborts": 0, "errors": 0,
            "hook_s": None, "sub_agents": list(t["sub_agents"].values()), "sub_tool_calls": t["sub_tools"],
            "converge_nudges": t["converge_nudges"], "sub_orientation_reads": t["sub_orientation_reads"],
            "reasoning_main": sum(r["rsn"] for r in main), "reasoning_chars": t["reasoning_chars"],
            "intent_eligible": t["intent_eligible"], "intent_with": t["intent_with"], "effort": None,
        })
    facts = {"harness": "claude", "id": sess["id"], "title": title, "cwd": cwd,
             "started": T[0]["started"] if T else None, "updated": sess["updated"],
             "settings": {}, "prefix_chars": None, "prefix_tokens_est": None, "prefix_blocks": [],
             "prefix_note": NOT_RECORDED + " (Claude Code transcripts do not store the system prompt; use `context-budget.py prefix`)",
             "compactions": sum(1 for r in recs if r.get("type") == "system" and "compact" in str(r.get("subtype", ""))),
             "events": len(recs), "usage_rows": len(seen_msg),
             "cost_usd": round(cost_state.get("totalCostUSD"), 2) if cost_state and cost_state.get("totalCostUSD") is not None else None}
    return facts, turns


# --------------------------------------------------------------------------- findings
def _ev(turn, note):
    return {"turn": turn, "note": note}


def detect(session):
    """Rule-based detectors over one profiled session. Returns finding dicts with evidence.
    Every rule is deterministic; the 'confidence' is Verified for measured facts and Inferred
    where a heuristic (regex over text) stands in for a field the harness does not record."""
    facts, turns = session["facts"], session["turns"]
    out = []

    def add(fid, evidence, metric=None, confidence="Verified", severity=None):
        title, sev, fixes = FINDINGS[fid]
        out.append({"id": fid, "title": title, "severity": severity or sev, "confidence": confidence,
                    "session": facts["id"], "harness": facts["harness"], "evidence": evidence,
                    "metric": metric, "fixes": fixes})

    ev = [_ev(t["turn"], "context {0:,} -> {1:,} tokens over {2} main requests".format(t["ctx_start"], t["ctx_end"], t["main_requests"]))
          for t in turns if t["ctx_end"] and (t["ctx_end"] > 300000 or (t["ctx_start"] and t["ctx_end"] - t["ctx_start"] > 150000))]
    if ev:
        add("SP-01", ev[:8], {"max_ctx": max(t["ctx_max"] or 0 for t in turns), "compactions": facts["compactions"]})
    blocks = facts.get("prefix_blocks") or []
    big = sorted([b for b in blocks if b > 20000], reverse=True)
    if len(big) >= 2 and abs(big[0] - big[1]) < 0.15 * big[0]:
        add("SP-02", [_ev(None, "custom-instruction blocks of {0:,} and {1:,} chars in the static prefix".format(big[0], big[1]))],
            {"blocks": big[:2], "duplicate_tokens_est": est_tokens(big[1])})
    if facts.get("prefix_tokens_est") and facts["prefix_tokens_est"] > 60000:
        add("SP-03", [_ev(None, "static prefix ~{0:,} est. tokens ({1:,} chars; {2})".format(
            facts["prefix_tokens_est"], facts["prefix_chars"], facts["prefix_note"]))],
            {"prefix_tokens_est": facts["prefix_tokens_est"]}, confidence="Inferred")
    ev = []
    for t in turns:
        for p, n in sorted(t["rereads"].items(), key=lambda kv: -kv[1])[:4]:
            ev.append(_ev(t["turn"], "{0} viewed {1}x".format(os.path.basename(p), n)))
        if t["paged_full_views"]:
            ev.append(_ev(t["turn"], "{0} paged tool output(s) viewed whole".format(t["paged_full_views"])))
    if ev:
        add("SP-04", ev[:10], {"turns_with_rereads": sum(1 for t in turns if t["rereads"] or t["paged_full_views"])})
    tot = collections.Counter()
    for t in turns:
        tot.update(t["skills"])
    rep = {k: v for k, v in tot.items() if v >= 2}
    if rep:
        add("SP-05", [_ev(None, "{0} invoked {1}x".format(k, v)) for k, v in sorted(rep.items(), key=lambda kv: -kv[1])],
            {"repeat_invocations": sum(v - 1 for v in rep.values())})
    ev = [_ev(t["turn"], "{0} sub-agent(s), no tier declared: {1}".format(len(t["sub_agents"]), ", ".join(str(s.get("name")) for s in t["sub_agents"][:6])))
          for t in turns if len(t["sub_agents"]) >= 3 and not t["tier"]]
    if ev:
        add("SP-06", ev[:6], {"turns": len(ev)}, confidence="Inferred")
    ev = []
    for t in turns:
        for s in t["sub_agents"]:
            if (s.get("tool_calls") or 0) > 40 or (s.get("tokens") or 0) > 1000000:
                ev.append(_ev(t["turn"], "{0}: {1} tool calls, {2:,} tokens, {3}s".format(
                    s.get("name"), s.get("tool_calls"), s.get("tokens") or 0, s.get("duration_s", "?"))))
        if t["converge_nudges"]:
            ev.append(_ev(t["turn"], "parent sent {0} converge/stop message(s)".format(t["converge_nudges"])))
    if ev:
        add("SP-07", ev[:8], {"count": len(ev)})
    ev = [_ev(t["turn"], r) for t in turns for r in t["sub_orientation_reads"]]
    if ev:
        add("SP-08", ev[:10], {"reads": len(ev)})
    subst = [t for t in turns if t["main_requests"] >= 3 and t["delivery"] != "steering" and t["nudges"] == 0]
    ev = [_ev(t["turn"], "'{0}' - first reply has no Goal / Done when".format(t["prompt"][:60])) for t in subst if not t["goal_state"]]
    if ev:
        add("SP-09", ev[:8], {"missing": len(ev), "substantive": len(subst)}, confidence="Inferred")
    ev = [_ev(t["turn"], "ttft p50 {0}s / p90 {1}s / max {2}s over {3} main requests".format(t["ttft_p50"], t["ttft_p90"], t["ttft_max"], t["main_requests"]))
          for t in turns if t["ttft_p90"] and t["ttft_p90"] > 20]
    if ev:
        add("SP-10", ev[:6], {"worst_p90": max(t["ttft_p90"] for t in turns if t["ttft_p90"])})
    n = sum(t["nudges"] + t["aborts"] for t in turns)
    if n:
        add("SP-11", [_ev(t["turn"], "{0} nudge(s), {1} abort(s)".format(t["nudges"], t["aborts"])) for t in turns if t["nudges"] or t["aborts"]][:8], {"count": n})
    n_img = sum(t["image_views"] for t in turns)
    n_err = sum(t["errors"] for t in turns)
    if n_img or n_err:
        add("SP-12", [_ev(t["turn"], "{0} image view(s), {1} failed request(s)".format(t["image_views"], t["errors"])) for t in turns if t["image_views"] or t["errors"]][:8],
            {"image_views": n_img, "errors": n_err})
    hw = [(t["hook_s"], t["wall_s"]) for t in turns if t["hook_s"] and t["wall_s"]]
    if hw:
        share = sum(h for h, _ in hw) / max(1, sum(w for _, w in hw))
        if share > 0.05:
            add("SP-13", [_ev(None, "hooks {0:.0f}s of {1:.0f}s wall ({2:.0f}%)".format(sum(h for h, _ in hw), sum(w for _, w in hw), 100 * share))], {"share": round(share, 3)})
    ev = [_ev(t["turn"], os.path.basename(p)) for t in turns for p in t["instruction_views"]]
    if ev:
        add("SP-16", ev[:8], {"reads": len(ev)})
    # SP-17: how much of the billed reasoning came back as text. Informational: it decides how much
    # weight any text-derived judgement can carry (below 10% visible, drift read from text is Inferred).
    rsn = sum(t["reasoning_main"] for t in turns)
    chars = sum(t["reasoning_chars"] for t in turns)
    if rsn:
        share = min(1.0, est_tokens(chars) / float(rsn))
        add("SP-17", [_ev(None, "{0:,} reasoning tokens billed on the main line; {1:,} chars of reasoning text on disk (~{2:.0f}% visible at {3} chars/token)".format(
            rsn, chars, 100 * share, CHARS_PER_TOKEN))], {"visible_share": round(share, 3), "reasoning_tokens": rsn, "reasoning_chars": chars},
            confidence="Verified", severity="Nit")
    # SP-18: intent-trace coverage - the one reasoning trace every host records (the description on a shell call).
    elig = sum(t["intent_eligible"] for t in turns)
    with_ = sum(t["intent_with"] for t in turns)
    if elig:
        cov = with_ / float(elig)
        if cov < 0.9:
            add("SP-18", [_ev(t["turn"], "{0}/{1} shell calls carried an intent".format(t["intent_with"], t["intent_eligible"]))
                          for t in turns if t["intent_eligible"] and t["intent_with"] < t["intent_eligible"]][:8],
                {"coverage": round(cov, 3), "eligible": elig})
    out.sort(key=lambda f: SEVERITY_RANK.get(f["severity"], 9))
    return out


def cross_session_findings(sessions):
    """SP-15 concurrent sessions in one checkout (same cwd, overlapping windows)."""
    spans = []
    for s in sessions:
        f = s["facts"]
        a, b = parse_ts(f.get("started")), parse_ts(f.get("updated"))
        if a and b and f.get("cwd"):
            spans.append((norm_path(f["cwd"]), a, b, f["harness"], f["id"]))
    ev = []
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            p1, a1, b1, h1, i1 = spans[i]
            p2, a2, b2, h2, i2 = spans[j]
            if p1 == p2 and a1 <= b2 and a2 <= b1:
                ev.append(_ev(None, "{0}:{1} and {2}:{3} overlapped in {4}".format(h1, i1[:8], h2, i2[:8], p1)))
    if not ev:
        return []
    title, sev, fixes = FINDINGS["SP-15"]
    return [{"id": "SP-15", "title": title, "severity": sev, "confidence": "Verified", "session": "*",
             "harness": "*", "evidence": ev[:8], "metric": {"pairs": len(ev)}, "fixes": fixes}]


def family_comparison(sessions):
    """Aggregate per (family, harness): the tuning view. Drift indicators are counts per turn."""
    agg = collections.defaultdict(lambda: {"turns": 0, "main_requests": 0, "cache_read": 0, "output": 0, "reasoning": 0,
                                           "cost_aiu": 0.0, "ttft_p90": [], "ctx_end": [], "sub_agents": 0,
                                           "rereads": 0, "skill_repeats": 0, "no_goal": 0, "no_tier_with_fanout": 0,
                                           "converge_nudges": 0, "nudges": 0, "wall_s": 0,
                                           "reasoning_main": 0, "reasoning_chars": 0, "intent_eligible": 0, "intent_with": 0,
                                           "effort": collections.Counter()})
    for s in sessions:
        for t in s["turns"]:
            if not t["models"]:
                continue
            key = ("+".join(t["families"]), s["facts"]["harness"])
            a = agg[key]
            a["turns"] += 1
            a["main_requests"] += t["main_requests"]
            a["cache_read"] += t["cache_read"]
            a["output"] += t["output"]
            a["reasoning"] += t["reasoning"]
            a["cost_aiu"] += t["cost_aiu"] or 0
            if t["ttft_p90"]:
                a["ttft_p90"].append(t["ttft_p90"])
            if t["ctx_end"]:
                a["ctx_end"].append(t["ctx_end"])
            a["sub_agents"] += len(t["sub_agents"])
            a["rereads"] += sum(t["rereads"].values())
            a["skill_repeats"] += sum(max(v - 1, 0) for v in t["skills"].values())
            a["no_goal"] += 0 if (t["goal_state"] or t["main_requests"] < 3) else 1
            a["no_tier_with_fanout"] += 1 if (len(t["sub_agents"]) >= 3 and not t["tier"]) else 0
            a["converge_nudges"] += t["converge_nudges"]
            a["nudges"] += t["nudges"] + t["aborts"]
            a["wall_s"] += t["wall_s"] or 0
            a["reasoning_main"] += t.get("reasoning_main") or 0
            a["reasoning_chars"] += t.get("reasoning_chars") or 0
            a["intent_eligible"] += t.get("intent_eligible") or 0
            a["intent_with"] += t.get("intent_with") or 0
            if t.get("effort"):
                a["effort"][t["effort"]] += 1
    rows = []
    for (fam, harness), a in sorted(agg.items()):
        n = max(a["turns"], 1)
        drift = a["sub_agents"] + a["rereads"] + a["skill_repeats"] + a["no_goal"] + a["no_tier_with_fanout"] + a["converge_nudges"] + a["nudges"]
        rows.append({"family": fam, "harness": harness, "turns": a["turns"],
                     "requests_per_turn": round(a["main_requests"] / n, 1),
                     "cache_read_per_turn": int(a["cache_read"] / n), "output_per_turn": int(a["output"] / n),
                     "reasoning_per_turn": int(a["reasoning"] / n),
                     "cost_aiu_per_turn": round(a["cost_aiu"] / n, 1) if a["cost_aiu"] else None,
                     "ttft_p90_median": round(statistics.median(a["ttft_p90"]), 1) if a["ttft_p90"] else None,
                     "ctx_end_median": int(statistics.median(a["ctx_end"])) if a["ctx_end"] else None,
                     "wall_s_per_turn": int(a["wall_s"] / n),
                     "reasoning_share_of_output": round(a["reasoning_main"] / float(a["output"]), 2) if a["output"] else None,
                     "visible_reasoning_pct": (round(100.0 * min(1.0, est_tokens(a["reasoning_chars"]) / float(a["reasoning_main"])), 1) if a["reasoning_main"] else None),
                     "intent_trace_pct": (round(100.0 * a["intent_with"] / a["intent_eligible"], 1) if a["intent_eligible"] else None),
                     "effort": (a["effort"].most_common(1)[0][0] if a["effort"] else NOT_RECORDED),
                     "drift_per_turn": round(drift / n, 2),
                     "drift_breakdown": {k: a[k] for k in ("sub_agents", "rereads", "skill_repeats", "no_goal", "no_tier_with_fanout", "converge_nudges", "nudges")}})
    findings = []
    comparable = [r for r in rows if r["turns"] >= 3]
    if len(comparable) >= 2:
        by_drift = sorted(comparable, key=lambda r: -r["drift_per_turn"])
        hi, lo = by_drift[0], by_drift[-1]
        if lo["drift_per_turn"] > 0 and hi["drift_per_turn"] >= 2 * lo["drift_per_turn"]:
            title, sev, fixes = FINDINGS["SP-14"]
            findings.append({"id": "SP-14", "title": title, "severity": sev, "confidence": "Verified", "session": "*",
                             "harness": "*", "evidence": [_ev(None, "{0}/{1}: {2} drift indicators per turn vs {3}/{4}: {5}".format(
                                 hi["family"], hi["harness"], hi["drift_per_turn"], lo["family"], lo["harness"], lo["drift_per_turn"])),
                                                         _ev(None, "caveat: the turn mix differs ({0} vs {1} turns); confirm on like-for-like tasks before tuning".format(hi["turns"], lo["turns"]))],
                             "metric": {"hi": hi["drift_per_turn"], "lo": lo["drift_per_turn"]}, "fixes": fixes})
    return rows, findings


# --------------------------------------------------------------------------- rendering
def _md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join(str(c) if c is not None else "\u2014" for c in r) + " |")
    return "\n".join(out)


def _fmt(n):
    if n is None:
        return NOT_RECORDED
    if isinstance(n, float):
        return "{0:,.1f}".format(n)
    if isinstance(n, int):
        return "{0:,}".format(n)
    return str(n)


def _frontmatter(profile):
    repos = ", ".join(profile.get("repo_labels") or [repo_label(r) for r in profile["repos"]])
    top = ", ".join(f["id"] for f in profile["findings"][:3]) or "none"
    return "\n".join([
        "---",
        "id: profile-{0}".format(profile["id"]),
        'title: "Session profile {0} - {1}"'.format(profile["id"], repos),
        "type: doc",
        "status: accepted",
        'owner: "@timianmalloo"',
        "tags: [profile, session-profiler, efficiency, adherence]",
        "links:",
        "  - { to: design-session-profiler, rel: relates-to }",
        'review-by: "{0}"'.format((_dt.date.today() + _dt.timedelta(days=90)).isoformat()),
        "summary: >-",
        "  Measured pass over {0} session(s) in {1} ({2}); {3} finding(s), top: {4}.".format(
            len(profile["sessions"]), repos, profile["window"], len(profile["findings"]), top),
        "---",
        "",
    ])


def render_markdown(profile):
    lines = [_frontmatter(profile) + "# Session profile {0}".format(profile["id"]), "",
             "*Generated {0} by `session-profile.py`. Every number is read from the harness's own store unless marked est. (chars/token = {1}). "
             "A missing measurement reads `{2}`, never a guess (IO8).*".format(profile["generated"], CHARS_PER_TOKEN, NOT_RECORDED), "",
             "**Repos:** " + ", ".join(profile.get("repo_labels") or [repo_label(r) for r in profile["repos"]]) + "  ", "**Window:** " + profile["window"] + "  ",
             "**Sessions:** {0} ({1})".format(len(profile["sessions"]), ", ".join(sorted({s["facts"]["harness"] for s in profile["sessions"]}))), ""]
    lines += ["## Findings", ""]
    if profile["findings"]:
        rows = []
        for f in profile["findings"]:
            ev = "; ".join(("t{0}: ".format(e["turn"]) if e.get("turn") is not None else "") + e["note"] for e in f["evidence"][:3])
            rows.append([f["id"], f["severity"], f["confidence"], f["title"], "{0}:{1}".format(f["harness"], str(f["session"])[:8]), ev.replace("|", "/"), ", ".join(f["fixes"])])
        lines.append(_md_table(["id", "severity", "confidence", "finding", "session", "evidence", "fix"], rows))
    else:
        lines.append("*No findings - either the sessions are clean or the window is empty. Check the session table below.*")
    lines += ["", "## Fixes (the pack surfaces that own the controls)", ""]
    used = collections.OrderedDict()
    for f in profile["findings"]:
        for fx in f["fixes"]:
            used.setdefault(fx, []).append(f["id"])
    rows = [[fx, FIXES[fx]["title"], FIXES[fx]["where"], FIXES[fx]["control"], ", ".join(sorted(set(ids)))] for fx, ids in used.items()]
    lines.append(_md_table(["fix", "what", "where in the pack", "control that fails on recurrence", "findings"], rows) if rows else "*none*")
    lines += ["", "## Model family x harness (the tuning view)", ""]
    lines.append(_md_table(["family", "harness", "turns", "req/turn", "cache-read/turn", "out/turn", "reasoning/turn", "reasoning visible", "effort", "intent trace", "cost/turn (AIU)", "ttft p90 (median)", "ctx end (median)", "wall s/turn", "drift/turn"],
                           [[r["family"], r["harness"], r["turns"], r["requests_per_turn"], _fmt(r["cache_read_per_turn"]), _fmt(r["output_per_turn"]), _fmt(r["reasoning_per_turn"]),
                             (str(r["visible_reasoning_pct"]) + "%") if r["visible_reasoning_pct"] is not None else NOT_RECORDED, r["effort"],
                             (str(r["intent_trace_pct"]) + "%") if r["intent_trace_pct"] is not None else NOT_RECORDED,
                             _fmt(r["cost_aiu_per_turn"]), _fmt(r["ttft_p90_median"]), _fmt(r["ctx_end_median"]), r["wall_s_per_turn"], r["drift_per_turn"]] for r in profile["comparison"]]))
    lines += ["", "*drift/turn = sub-agents + re-reads + skill repeats + missing goal state + fan-out without tier + converge nudges + cap firings, per turn. "
              "reasoning visible = reasoning text on disk as a share of billed reasoning tokens (est.); below 10% every text-derived drift judgement is Inferred. "
              "effort = the host's recorded reasoning effort (Copilot) or not recorded (Claude Code). intent trace = shell calls carrying a one-line description.*", ""]
    for s in profile["sessions"]:
        f = s["facts"]
        lines += ["## {0} session `{1}` \u2014 {2}".format(f["harness"], f["id"][:8], f.get("title") or ""), "",
                  "started {0} \u00b7 updated {1} \u00b7 cwd `{2}` \u00b7 prefix {3} \u00b7 compactions {4}{5}".format(
                      f.get("started"), f.get("updated"), f.get("cwd"),
                      ("~{0:,} est. tokens / {1:,} chars".format(f["prefix_tokens_est"], f["prefix_chars"]) if f.get("prefix_chars") else NOT_RECORDED),
                      f.get("compactions"), (" \u00b7 settings {0}".format(f["settings"]) if f.get("settings") else "")), ""]
        rows = []
        for t in s["turns"]:
            rows.append([t["turn"], t["prompt"][:48].replace("|", "/"), "+".join(t["families"]) or "\u2014", t["main_requests"], _fmt(t["ctx_start"]), _fmt(t["ctx_end"]),
                         _fmt(t["cache_read"]), _fmt(t["output"]), _fmt(t["cost_aiu"]), _fmt(t["ttft_p90"]), t["wall_s"], len(t["sub_agents"]),
                         sum(t["rereads"].values()), "yes" if t["goal_state"] else "no", "yes" if t["tier"] else "no"])
        lines.append(_md_table(["turn", "prompt", "family", "main req", "ctx start", "ctx end", "cache read", "output", "cost AIU", "ttft p90", "wall s", "subs", "re-reads", "goal", "tier"], rows))
        lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- commands
def _select(args):
    since = None
    if args.days:
        since = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=args.days)
    found = []
    for repo in args.repo:
        if not os.path.isdir(repo):
            print("session-profile: not a directory: {0}".format(repo), file=sys.stderr)
            continue
        ident = repo_identity(repo)
        if args.harness in ("all", "copilot"):
            found += copilot_sessions(ident, since, args.copilot_home or copilot_home())
        if args.harness in ("all", "claude"):
            found += claude_sessions(ident, since, args.claude_home or claude_home())
    if getattr(args, "session", None):
        want = set(args.session)
        found = [s for s in found if s["id"] in want or any(s["id"].startswith(w) for w in want)]
    found.sort(key=lambda s: s.get("updated") or "", reverse=True)
    if getattr(args, "limit", None):
        found = found[:args.limit]
    return found, since


def cmd_discover(args):
    found, _ = _select(args)
    if not found:
        print("no sessions found for {0} (harness={1}, days={2})".format(", ".join(args.repo), args.harness, args.days))
        return 1
    print("{0:8} {1:9} {2:20} {3:20} {4}".format("harness", "id", "started", "updated", "title / cwd"))
    for s in found:
        print("{0:8} {1:9} {2:20} {3:20} {4}".format(s["harness"], s["id"][:8], (s.get("started") or "-")[:19], (s.get("updated") or "-")[:19],
                                                     (s.get("title") or "") + ("  " + s["cwd"] if s.get("cwd") else "")))
    print("\n{0} session(s)".format(len(found)))
    return 0


def _profile_all(found, args):
    settings = copilot_settings(args.copilot_home or copilot_home())
    sessions = []
    for s in found:
        try:
            facts, turns = profile_copilot(s, settings) if s["harness"] == "copilot" else profile_claude(s)
        except Exception as exc:  # noqa: BLE001 - a broken store must not abort the profile; it is REPORTED
            print("session-profile: skipping {0}:{1} - {2}: {3}".format(s["harness"], s["id"][:8], type(exc).__name__, exc), file=sys.stderr)
            continue
        sessions.append({"facts": facts, "turns": turns})
    findings = []
    for s in sessions:
        findings += detect(s)
    comparison, fam_findings = family_comparison(sessions)
    findings += fam_findings + cross_session_findings(sessions)
    findings.sort(key=lambda f: SEVERITY_RANK.get(f["severity"], 9))
    return sessions, findings, comparison


def profile_id(root):
    d = os.path.join(root, "docs", "profiles")
    n = 0
    if os.path.isdir(d):
        for name in os.listdir(d):
            m = re.match(r"sp-(\d+)$", name)
            if m:
                n = max(n, int(m.group(1)))
    return "sp-{0:04d}".format(n + 1)


def cmd_profile(args):
    found, since = _select(args)
    if not found:
        print("no sessions found for {0} (harness={1}, days={2})".format(", ".join(args.repo), args.harness, args.days))
        return 1
    sessions, findings, comparison = _profile_all(found, args)
    root = os.path.abspath(args.out_root or args.repo[0])
    pid = profile_id(root)
    profile = {"id": pid, "generated": iso(_dt.datetime.now(_dt.timezone.utc)), "repos": [os.path.abspath(r) for r in args.repo],
               "repo_labels": [repo_label(r) for r in args.repo],
             "window": "last {0} days".format(args.days) if args.days else "all sessions",
               "chars_per_token": CHARS_PER_TOKEN, "sessions": sessions, "findings": findings, "comparison": comparison,
               "fixes": FIXES}
    out_dir = os.path.join(root, "docs", "profiles", pid)
    if args.json_only:
        print(json.dumps(profile, ensure_ascii=False, indent=2, default=str))
        return 0
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "profile.json"), "w", encoding="utf-8") as fh:
        json.dump(profile, fh, ensure_ascii=False, indent=2, default=str)
    md = render_markdown(profile)
    with open(os.path.join(out_dir, "profile.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    _index(root, profile)
    _audit(root, pid, len(sessions), len(findings), args.session_id)
    print("profile {0}: {1} session(s), {2} finding(s)".format(pid, len(sessions), len(findings)))
    print("  report: {0}".format(os.path.join(out_dir, "profile.md")))
    if args.print_markdown:
        print()
        print(md)
    return 0


def _index(root, profile):
    d = os.path.join(root, "docs", "profiles")
    path = os.path.join(d, "PROFILES.md")
    header = ("---\nid: session-profiles\ntitle: \"Session profiles\"\ntype: doc\nstatus: accepted\nowner: \"@timianmalloo\"\n"
              "tags: [profile, session-profiler, index]\nlinks:\n  - { to: design-session-profiler, rel: relates-to }\n"
              "review-by: \"2027-03-05\"\nsummary: >-\n  Index of /session-profiler runs - each row is one measured pass over the harness telemetry, "
              "mined by /dream as findings.\n---\n\n"
              "# Session profiles\n\n*Each row is one measured pass over the harness telemetry (`session-profile.py`). "
              "Mined by `/dream` as findings.*\n\n| id | generated | repos | sessions | findings | top |\n|---|---|---|---|---|---|\n")
    if not os.path.isfile(path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(header)
    top = ", ".join(f["id"] for f in profile["findings"][:3]) or "\u2014"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("| [{0}]({0}/profile.md) | {1} | {2} | {3} | {4} | {5} |\n".format(
            profile["id"], profile["generated"], ", ".join(profile.get("repo_labels") or [repo_label(r) for r in profile["repos"]]),
            len(profile["sessions"]), len(profile["findings"]), top))


def _audit(root, pid, n_sessions, n_findings, session):
    script = os.path.join(root, "docs", "ai-forward-pack", "scripts", "audit-log.py")
    if not os.path.isfile(script):
        script = os.path.join(root, "pack", "scripts", "audit-log.py")
    if not os.path.isfile(script):
        return
    try:
        subprocess.run([sys.executable, script, "append", "--shortname", "session-profile-" + pid, "--kind", "script",
                        "--skill", "session-profiler", "--session", session or "session-profile-job",
                        "--prompt", "session-profile.py profile", "--summary",
                        "Profile {0}: {1} session(s), {2} finding(s)".format(pid, n_sessions, n_findings),
                        "--artifact", "docs/profiles/{0}/profile.md".format(pid)],
                       cwd=root, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass


def cmd_compare(args):
    found, _ = _select(args)
    if not found:
        print("no sessions found")
        return 1
    sessions, findings, comparison = _profile_all(found, args)
    if args.json_only:
        print(json.dumps({"comparison": comparison, "findings": [f for f in findings if f["id"] == "SP-14"]}, indent=2, default=str))
        return 0
    print(_md_table(["family", "harness", "turns", "req/turn", "cache-read/turn", "out/turn", "reasoning/turn", "reasoning visible", "effort", "intent trace", "cost/turn", "ttft p90 med", "ctx end med", "wall s/turn", "drift/turn"],
                    [[r["family"], r["harness"], r["turns"], r["requests_per_turn"], _fmt(r["cache_read_per_turn"]), _fmt(r["output_per_turn"]), _fmt(r["reasoning_per_turn"]),
                      (str(r["visible_reasoning_pct"]) + "%") if r["visible_reasoning_pct"] is not None else NOT_RECORDED, r["effort"],
                      (str(r["intent_trace_pct"]) + "%") if r["intent_trace_pct"] is not None else NOT_RECORDED,
                      _fmt(r["cost_aiu_per_turn"]), _fmt(r["ttft_p90_median"]), _fmt(r["ctx_end_median"]), r["wall_s_per_turn"], r["drift_per_turn"]] for r in comparison]))
    for r in comparison:
        print("  {0}/{1} drift breakdown: {2}".format(r["family"], r["harness"], r["drift_breakdown"]))
    for f in findings:
        if f["id"] == "SP-14":
            print("\n{0} [{1}] {2}: {3}".format(f["id"], f["severity"], f["title"], f["evidence"][0]["note"]))
    return 0


def cmd_fixes(args):
    print(_md_table(["fix", "what", "where in the pack", "control"], [[k, v["title"], v["where"], v["control"]] for k, v in FIXES.items()]))
    print()
    print(_md_table(["finding", "severity", "title", "fixes"], [[k, v[1], v[0], ", ".join(v[2])] for k, v in FINDINGS.items()]))
    return 0


def main(argv=None):
    global CHARS_PER_TOKEN
    ap = argparse.ArgumentParser(prog="session-profile.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", action="append", default=[], help="repo path (repeatable); the first one receives docs/profiles/")
    ap.add_argument("--days", type=int, default=30, help="window in days (0 = all)")
    ap.add_argument("--harness", choices=["all", "copilot", "claude"], default="all")
    ap.add_argument("--session", action="append", help="restrict to session id(s) or prefixes")
    ap.add_argument("--limit", type=int, default=None, help="newest N sessions")
    ap.add_argument("--copilot-home", help="override ~/.copilot")
    ap.add_argument("--claude-home", help="override ~/.claude")
    ap.add_argument("--chars-per-token", type=float, default=None, help="override the estimate ratio ({0})".format(CHARS_PER_TOKEN))
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("discover", help="list matching sessions")
    p.set_defaults(func=cmd_discover)
    p = sub.add_parser("profile", help="profile sessions and write docs/profiles/<sp-id>/")
    p.add_argument("--out-root", help="repo root that receives docs/profiles/ (default: first --repo)")
    p.add_argument("--json-only", action="store_true", help="print JSON, write nothing")
    p.add_argument("--print-markdown", action="store_true")
    p.add_argument("--session-id", help="audit session id to record")
    p.set_defaults(func=cmd_profile)
    p = sub.add_parser("compare", help="aggregate by model family x harness")
    p.add_argument("--json-only", action="store_true")
    p.set_defaults(func=cmd_compare)
    p = sub.add_parser("fixes", help="print the fix and finding catalogs")
    p.set_defaults(func=cmd_fixes)
    args = ap.parse_args(argv)
    if args.chars_per_token:
        CHARS_PER_TOKEN = args.chars_per_token
    if not getattr(args, "func", None):
        ap.print_help()
        return 0
    if args.cmd != "fixes" and not args.repo:
        print("session-profile: --repo <path> is required", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
