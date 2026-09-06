#!/usr/bin/env python3
"""coord-core.py - agent coordination, Phase 1 walking skeleton.

Holds the record of intent and answers "may this session touch this artifact?" from it.
Append-only JSONL, one file per session; every piece of state is a fold over it. No daemon,
no database, no dependency beyond the standard library (ADR-0007).

Four controls here were observed failing on the un-fixed shape before they were trusted:
  LOG-A     an append onto a file not ending in a newline fuses two records and loses BOTH
  R4        a check that scanned nothing must not report "free"
  CTRL-PORT os.open without O_BINARY translates newlines on Windows -- which also MASKED
            the LOG-A control, because a stray CR still terminates a line
  F8        a claim over the coordination record itself would lock the substrate

Design: docs/design/coord-core-phase1.md
"""
import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TTL_DEFAULT = 300
SESSION_STALE_SECONDS = 8 * 3600
COORD_DIRNAME = ".agents"
SESSION_CONTRACT = "docs/collaboration/session-contracts.md"
REQUESTS_FILE = "requests.jsonl"


class CoordError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# --- paths & identity -------------------------------------------------------

def repo_root(cwd):
    """The PRIMARY checkout of this repository, from any worktree.

    The record is per REPOSITORY, not per checkout. `--git-common-dir` is the primitive
    that says so: from a linked worktree it returns the primary .git (absolute), and from
    the primary checkout it returns a relative ".git". Its parent is the primary checkout
    in both cases.

    Found by running the Phase-1 demo: with the root defaulting to cwd/.agents, every
    worktree got its own private record and two sessions could never see each other -
    which is the exact criterion this phase exists to satisfy.

    Read from the filesystem, NOT by shelling out to `git rev-parse --git-common-dir`.
    The first implementation did shell out and cost ~35 ms of the check's budget - measured
    at 82 ms p95, which met NFR-P1 but blew straight through ADR-0007's own 60 ms
    compaction trigger. On the hot path of every edit, a subprocess is not free.

    The layout this reads is git's own:
      primary checkout -> .git is a DIRECTORY; the repo root is its parent
      linked worktree  -> .git is a FILE holding "gitdir: <primary>/.git/worktrees/<name>"
    """
    here = Path(cwd).resolve()
    for candidate in [here, *here.parents]:
        dot_git = candidate / ".git"
        if dot_git.is_dir():
            return candidate
        if dot_git.is_file():
            try:
                text = dot_git.read_text(encoding="utf-8").strip()
            except OSError:
                break
            if text.startswith("gitdir:"):
                gitdir = Path(text.split(":", 1)[1].strip())
                if not gitdir.is_absolute():
                    gitdir = candidate / gitdir
                parts = gitdir.resolve().parts
                if "worktrees" in parts:
                    common = Path(*parts[: parts.index("worktrees")])
                    return common.parent
            break
    return here     # not a git repo: degrade to the directory, and say nothing false


def resolve_root(cwd, raw):
    """Resolve COORD_ROOT, refusing anything outside the repository.

    COORD_ROOT is attacker-controllable input that selects which file becomes trusted
    state (STRIDE B1, elevation of privilege). Found at the design gate, not in the draft.
    """
    base = repo_root(cwd)
    root = Path(raw).resolve() if raw else (base / COORD_DIRNAME).resolve()
    try:
        root.relative_to(base)
    except ValueError:
        return None, {"code": "COORD-NOT-CHECKED-ROOT",
                      "reason": "COORD_ROOT resolves outside the repository: {}".format(root)}
    return root, None


def _norm(p):
    return str(p).replace("\\", "/").replace("**", "*")


def _literal_segments(pattern):
    """The leading path segments of a pattern that contain no wildcard."""
    segs = []
    for seg in _norm(pattern).split("/"):
        if any(ch in seg for ch in "*?["):
            break
        segs.append(seg)
    return segs


def overlaps(a, b):
    """Do two path patterns intersect? Prefer a false positive: a false refusal costs a
    message, a false grant costs a merge.

    Compared by SEGMENT, not by string prefix, so src/Foo/** and src/FooBar/** are
    correctly disjoint.

    simplify: fnmatch both ways plus a segment-prefix test.
      ceiling: a wildcard in the middle of a pattern, and character classes.
      upgrade trigger: the first refusal a human calls wrong, or Phase 3's artifact-class
      registry introducing nested patterns.
    """
    na, nb = _norm(a), _norm(b)
    if na == nb:
        return True
    if fnmatch.fnmatch(nb, na) or fnmatch.fnmatch(na, nb):
        return True
    sa, sb = _literal_segments(na), _literal_segments(nb)
    n = min(len(sa), len(sb))
    return sa[:n] == sb[:n]


# --- the record -------------------------------------------------------------

def make_event(kind, session, agent, wi, path, at, ttl=TTL_DEFAULT, seq=None):
    first = next((seg for seg in _norm(path).split("/") if seg not in (".", "")), "")
    if first == COORD_DIRNAME:
        raise CoordError("COORD-CLAIM-SELF",
                         "a claim over the coordination record itself is refused")
    event = {"kind": kind, "session": session, "agent": agent, "wi": wi,
             "path": _norm(path), "at": float(at)}
    if kind == "claim":
        event["ttl"] = float(ttl)
    if seq is not None:
        event["seq"] = int(seq)
    return event


def _next_seq(logfile):
    if not logfile.exists():
        return 1
    n = 0
    with open(logfile, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return n + 1


def append_event(root, event):
    """Append one event as exactly one write() - atomic under O_APPEND (spike S3)."""
    logdir = Path(root) / "log"
    logdir.mkdir(parents=True, exist_ok=True)
    logfile = logdir / "{}.jsonl".format(event["session"])
    if "seq" not in event:
        event["seq"] = _next_seq(logfile)
    payload = json.dumps(event, sort_keys=True) + "\n"

    # LOG-A: emit a LEADING newline when the file does not already end in one, so a fused
    # record is impossible to express rather than merely detectable (control ladder rung 1).
    # The file may have been left unterminated by a merge resolution or a hand edit -- the
    # writer owns this seam because no single actor otherwise does.
    if logfile.exists() and logfile.stat().st_size:
        with open(logfile, "rb") as fh:
            fh.seek(-1, os.SEEK_END)
            last = fh.read(1)
        if last not in (b"\n", b"\r"):
            payload = "\n" + payload

    # CTRL-PORT: O_BINARY (Windows only; 0 elsewhere) stops newline translation, so the
    # committed bytes are LF on every platform as .gitattributes requires. It also stops a
    # stray CR from masking the LOG-A control above -- which is how that masking was found.
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0)
    fd = os.open(str(logfile), flags, 0o644)
    try:
        os.write(fd, payload.encode("utf-8"))   # exactly one write() -- atomic (spike S3)
    finally:
        os.close(fd)
    return event


def read_events(root):
    """Return (events, errors, files_scanned).

    Errors are collected, never raised - but a single error makes the whole check
    not_checked. Fail safe, never open (NFR-R2).
    """
    logdir = Path(root) / "log"
    events, errors, files = [], [], 0
    if not logdir.is_dir():
        return events, errors, files
    for logfile in sorted(logdir.glob("*.jsonl")):
        files += 1
        with open(logfile, "r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    errors.append("{}:{}: {}".format(logfile.name, lineno, exc.msg))
    events.sort(key=lambda e: (e.get("at", 0.0), e.get("session", ""), e.get("seq", 0)))
    return events, errors, files


def fold(events, now):
    """Pure fold: events -> live leases. Replaying is idempotent (NFR-R1).

    derive-don't-store (DM7): `expires` is computed here (at + ttl) and never persisted.
    Two stored definitions of one quantity is the defect signature.
    """
    leases, seen = {}, set()
    for event in events:
        ident = (event.get("session"), event.get("seq"))
        if ident in seen:            # F9: a retried tool call must not take a second lease
            continue
        seen.add(ident)
        key = (event.get("path"), event.get("session"))
        if event.get("kind") == "claim":
            leases[key] = {"path": event["path"], "session": event["session"],
                           "agent": event.get("agent", event["session"]),
                           "wi": event.get("wi", ""),
                           "expires": event["at"] + event.get("ttl", TTL_DEFAULT)}
        elif event.get("kind") == "release":
            leases.pop(key, None)
    return {k: v for k, v in leases.items() if v["expires"] > now}


# --- the decision -----------------------------------------------------------

def check(root, path, me, now):
    if not me:
        return {"decision": "not_checked", "path": path, "files_scanned": 0,
                "events_scanned": 0, "code": "COORD-NOT-CHECKED-IDENTITY",
                "reason": "AGENT_SESSION is unset, so this session has no identity to check"}

    events, errors, files = read_events(root)

    if errors:
        return {"decision": "not_checked", "path": path, "files_scanned": files,
                "events_scanned": len(events), "code": "COORD-NOT-CHECKED-RECORD",
                "reason": "the record could not be read: " + "; ".join(errors[:3])}

    # R4: a control that scanned nothing has not reported clean. An empty corpus and a
    # clean corpus must never render the same. Written because this architecture's own
    # allocator spike printed "COLLISION-FREE" over zero identifiers.
    if files == 0:
        return {"decision": "not_checked", "path": path, "files_scanned": 0,
                "events_scanned": 0, "code": "COORD-NOT-CHECKED-RECORD",
                "reason": "0 files scanned - there is no record here, so nothing was checked"}

    for lease in fold(events, now).values():
        if lease["session"] != me and overlaps(lease["path"], path):
            return {"decision": "deny", "path": path, "files_scanned": files,
                    "events_scanned": len(events), "code": "COORD-REFUSED",
                    "holder": lease["agent"], "session": lease["session"],
                    "wi": lease["wi"], "expires_in": int(lease["expires"] - now),
                    "reason": "an unexpired lease overlaps your pattern"}

    return {"decision": "allow", "path": path, "files_scanned": files,
            "events_scanned": len(events), "code": None, "reason": ""}


def _safe(value, limit=200):
    """Strip control characters and cap length before interpolating into the refusal.

    STRIDE B4, elevation: the refusal is rendered into ANOTHER MODEL'S context. The
    template is fixed and nothing is interpolated into prose, but an interpolated VALUE
    carrying a newline could still add a line that reads as an instruction. This is the
    Phase-4 trust boundary arriving three phases early, so it is closed here.
    """
    text = "".join(ch for ch in str(value) if ch.isprintable())
    return text[:limit]


def render(decision):
    """Four labelled lines, fixed order: what happened - who - why - what to do.

    No colour is load-bearing: every state is distinguishable from the text and the exit
    code alone. Accessibility and machine-readability are the same requirement here.
    "refused" is never softened to "denied" or "unavailable" - the reader is a model that
    must not read the outcome as a transient failure worth retrying.
    """
    decision = {k: (_safe(v) if isinstance(v, str) else v) for k, v in decision.items()}
    verdict = decision["decision"]
    if verdict == "allow":
        return ""
    if verdict == "deny":
        return ("REFUSED  {path}\n"
                "  held by   {holder} - {wi} - expires in {expires_in}s\n"
                "  because   {reason}\n"
                "  remedy    wait, claim a disjoint subset, or record a block on {wi}"
                ).format(**decision)
    return ("NOT CHECKED  {path}\n"
            "  held by   unknown - this check did not run\n"
            "  because   {reason}\n"
            "  remedy    fix the condition above, then re-run; this is not a pass"
            ).format(**decision)


EXIT = {"allow": 0, "deny": 3, "not_checked": 4}


# --- the decisions store (Phase 2) ------------------------------------------
#
# TWO STORES, TWO GRAINS, ONE READER EACH.
#   log/       one row is one INTENT event  (claim/release/session)  -> FOLDED
#   decisions/ one row is one ENFORCEMENT decision (allow/deny/ask)  -> NEVER folded
#
# Phase 1 appended refusals into the folded log. That is now wrong, and the reason is
# Phase 1's own measurement: the check was 63 ms p95 at 10,000 events, already at
# ADR-0007's 60 ms compaction trigger. Phase 2 records a decision PER EDIT - orders of
# magnitude more traffic than one per claim - so folding those would blow the hot path
# within a day. Keeping them out means the fold stays proportional to CLAIMS, not EDITS,
# and the metric that decides whether this phase worked costs nothing to collect.

def append_decision(root, session, agent, path, decision):
    """Record one enforcement decision. Never folded; read by `tail` and `metrics`.

    G14: the verdict is computed BEFORE this is attempted and cannot be changed by it.
    A refusal that cannot be recorded is still a refusal.
    """
    logdir = Path(root) / "decisions"
    # The stored kind is the UBIQUITOUS LANGUAGE word, not the internal one: "refused",
    # never "denied". The store is read by humans in `tail`, and the vocabulary is the
    # same one the refusal itself uses.
    kind = {"allow": "allowed", "deny": "refused",
            "not_checked": "not_checked"}.get(decision.get("decision"), "unknown")
    record = {"kind": kind,
              "session": session or "anon", "agent": agent or "anon",
              "wi": decision.get("wi", ""), "path": _norm(path),
              "at": time.time(), "code": decision.get("code")}
    try:
        logdir.mkdir(parents=True, exist_ok=True)
        logfile = logdir / "{}.jsonl".format(record["session"])
        payload = json.dumps(record, sort_keys=True) + "\n"
        if logfile.exists() and logfile.stat().st_size:
            with open(logfile, "rb") as fh:
                fh.seek(-1, os.SEEK_END)
                if fh.read(1) not in (b"\n", b"\r"):    # LOG-A, same seam
                    payload = "\n" + payload
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0)
        fd = os.open(str(logfile), flags, 0o644)
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception:
        pass    # never let a bookkeeping failure change a verdict


def read_decisions(root):
    logdir = Path(root) / "decisions"
    out = []
    if not logdir.is_dir():
        return out
    for logfile in sorted(logdir.glob("*.jsonl")):
        with open(logfile, "r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue    # a damaged decision is lost telemetry, not lost state
    out.sort(key=lambda d: d.get("at", 0.0))
    return out


def append_record(path, record):
    """Append one JSONL row to a small operator ledger."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, sort_keys=True) + "\n"
    if Path(path).exists() and Path(path).stat().st_size:
        with open(path, "rb") as fh:
            fh.seek(-1, os.SEEK_END)
            if fh.read(1) not in (b"\n", b"\r"):
                payload = "\n" + payload
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0)
    fd = os.open(str(path), flags, 0o644)
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)


def request_log_path(root):
    return Path(root) / REQUESTS_FILE


def read_request_events(root):
    path = request_log_path(root)
    if not path.is_file():
        return [], []
    events, errors = [], []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                errors.append("{}:{}: {}".format(path.name, lineno, exc.msg))
    events.sort(key=lambda e: e.get("at", 0.0))
    return events, errors


def fold_requests(events):
    requests = {}
    for event in events:
        rid = event.get("id")
        if not rid:
            continue
        if event.get("kind") == "request-add":
            row = dict(event)
            row["status"] = "open"
            requests[rid] = row
        elif event.get("kind") == "request-resolve" and rid in requests:
            requests[rid] = dict(requests[rid])
            requests[rid]["status"] = "resolved"
            requests[rid]["resolution"] = event.get("resolution", "")
            requests[rid]["resolved_at"] = event.get("at")
            requests[rid]["resolved_by"] = event.get("session", "")
    return sorted(requests.values(), key=lambda r: r.get("at", 0.0))


# --- git plumbing -----------------------------------------------------------

def _git(repo, *args):
    """Run git and READ THE RESULT BACK. An exit code is not a result (CTRL-E)."""
    try:
        proc = subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                              text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "{}: {}".format(exc.__class__.__name__, exc)
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "git {} failed".format(args[0])).strip()
    return proc.stdout, None


def unique_commits(repo):
    """Commits reachable from HEAD and from NO other ref. Returns (count, reason_code).

    `--all` is FORBIDDEN in this expression. Spike S9 reproduced the recorded bug:
    `git rev-list HEAD --not --all` returns 0 for a branch holding exactly one commit
    that exists nowhere else, because --all implicitly includes HEAD -- so the expression
    reduces to `HEAD --not HEAD` and reports SAFE for the one case the guard exists to
    catch. `--exclude=<branch> --all` fails identically, because it does not exclude HEAD.
    """
    out, err = _git(repo, "rev-parse", "--is-inside-work-tree")
    if err:
        return None, "COORD-NOT-CHECKED-GIT"

    out, err = _git(repo, "symbolic-ref", "-q", "--short", "HEAD")
    if err or not (out or "").strip():
        # Detached: every PR gate runs here, and "does my work exist anywhere else?" has
        # no meaning. Decline. A control that cannot see is not licensed to accuse.
        return None, "COORD-DETACHED"
    current = out.strip()

    out, err = _git(repo, "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes")
    if err:
        return None, "COORD-NOT-CHECKED-GIT"
    peers = [r for r in out.split() if r != "refs/heads/" + current]
    if not peers:
        # Nothing to compare against: a fresh repo genuinely has one copy of everything.
        # Reported distinctly so it does not train people to switch the guard off.
        return None, "COORD-NO-PEER-REFS"

    out, err = _git(repo, "rev-list", "HEAD", "--not", *peers)
    if err:
        return None, "COORD-NOT-CHECKED-GIT"
    return len([line for line in out.split() if line]), None


def staged_paths(repo):
    """Staged paths, NUL-separated. Returns (paths, error).

    S8: `--cached` works before the first commit; appending HEAD is FATAL there, so HEAD
    is never passed. The -z form is required - a path containing a space is otherwise
    split, and one containing a quote is otherwise escaped.
    """
    out, err = _git(repo, "diff", "--cached", "--name-only", "-z")
    if err:
        return None, err
    return [p for p in out.split("\0") if p], None


# --- CLI --------------------------------------------------------------------

def _identity():
    session = os.environ.get("AGENT_SESSION")
    return session, os.environ.get("AGENT_NAME") or session


def _build_parser():
    parser = argparse.ArgumentParser(prog="coord", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    claim = sub.add_parser("claim", help="declare intent over an artifact set")
    claim.add_argument("--wi", required=True)
    claim.add_argument("--path", required=True)
    claim.add_argument("--ttl", type=float, default=TTL_DEFAULT)

    chk = sub.add_parser("check", help="may this session touch this path?")
    chk.add_argument("path")
    chk.add_argument("--json", action="store_true")

    rel = sub.add_parser("release", help="drop a lease")
    rel.add_argument("--path", required=True)
    rel.add_argument("--wi", default="WI-0")

    tail = sub.add_parser("tail", help="the merged chronological stream")
    tail.add_argument("-n", type=int, default=20)

    # --- Phase 2: enforcement ---
    sub.add_parser("hook", help="PreToolUse adapter: stdin JSON in, decision JSON out")
    sub.add_parser("precommit", help="the universal floor: refuse unclaimed staged paths")
    guard = sub.add_parser("guard", help="refuse to move HEAD over work held in one place")
    guard.add_argument("--fix", action="store_true", help="push, the cheapest second copy")
    ses = sub.add_parser("session", help="one session per working tree")
    ses.add_argument("action", choices=["start", "end", "list"])
    ses.add_argument("--json", action="store_true")
    collab = sub.add_parser("collaborate", help="cross-session collaboration checks")
    collab.add_argument("action", choices=["check", "summary"])
    collab.add_argument("--json", action="store_true")
    req = sub.add_parser("request", help="record or resolve a seam request")
    req_sub = req.add_subparsers(dest="request_action", required=True)
    req_add = req_sub.add_parser("add", help="append an open seam request")
    req_add.add_argument("--to", required=True)
    req_add.add_argument("--contract", required=True)
    req_add.add_argument("--reason", required=True)
    req_add.add_argument("--from-role", default="")
    req_add.add_argument("--path", default="")
    req_list = req_sub.add_parser("list", help="list seam requests")
    req_list.add_argument("--json", action="store_true")
    req_list.add_argument("--status", choices=["open", "resolved", "all"], default="open")
    req_resolve = req_sub.add_parser("resolve", help="resolve a seam request")
    req_resolve.add_argument("id")
    req_resolve.add_argument("--resolution", required=True)
    # WT1-WT12: a new session starts in a new worktree, and nothing is left behind.
    wt = sub.add_parser("worktree", help="session worktree lifecycle: new | list | cleanup")
    wt.add_argument("action", choices=["new", "list", "cleanup"])
    wt.add_argument("--branch", help="branch to create; name it for the WORK, not the session")
    wt.add_argument("--base", help="commit/branch to branch from (default: current HEAD)")
    # `worktree new` is the FIRST command of a session, before AGENT_SESSION is necessarily
    # exported, so the id may be passed directly. Everywhere else the env var remains the
    # convention and this flag simply overrides it.
    wt.add_argument("--session", dest="wt_session",
                    help="session id to register (default: $AGENT_SESSION)")
    wt.add_argument("--remove", action="store_true",
                    help="cleanup: actually delete. Off by default - deletion is irreversible")
    met = sub.add_parser("metrics", help="the four measures this layer exists to move")
    met.add_argument("--json", action="store_true")
    sub.add_parser("install", help="write the pre-commit hook; print the settings entry")

    # --- Phase 3 ---
    cls = sub.add_parser("class", help="what class is this artifact?")
    cls.add_argument("path"); cls.add_argument("--json", action="store_true")
    md = sub.add_parser("merge-derived", help="the .gitattributes merge driver (always 0)")
    md.add_argument("result"); md.add_argument("base")
    md.add_argument("theirs"); md.add_argument("realpath")
    rg = sub.add_parser("regen", help="run the regenerations the driver deferred")
    rg.add_argument("--timeout", type=float, default=120)
    sub.add_parser("doctor", help="is the driver effective? is the registry sane?")
    alloc = sub.add_parser("allocate", help="one collision-proof identifier")
    alloc.add_argument("--scheme", required=True)
    res = sub.add_parser("resolve", help="resolve an id prefix; never picks a first match")
    res.add_argument("prefix"); res.add_argument("--register", required=True)
    mr = sub.add_parser("merge-register", help="union two append-only registers (always 0)")
    mr.add_argument("result"); mr.add_argument("base")
    mr.add_argument("theirs"); mr.add_argument("realpath")
    pl = sub.add_parser("plugin", help="emit the bundle both harnesses read; never installs")
    pl.add_argument("--emit", required=True, metavar="DIR")
    return parser


MERGE_DRIVER_NAME = "coord-regen"
REGISTER_DRIVER_NAME = "coord-register"


MAX_PATH = 4096
HOOK_MARKER = "# coord-core pre-commit floor"
HOOK_BODY = """#!/bin/sh
{marker}
# The universal floor: every harness has a commit boundary, and no settings key removes it.
exec "{python}" "{script}" precommit
"""


# --- Phase 3: the collision-proof allocator ---------------------------------
#
# KG-B has NINE recorded occurrences of client-minted sequential ids colliding across
# branches, twice reaching main, once silently DESTROYING an entry. The prevention built for
# it scans every remote branch, works, takes about a second over 22 branches -- and collided
# again within the hour, because two sessions that mint before either has pushed are
# invisible to each other by construction. So the only rung that holds is rung 1: make the
# collision impossible to express.
#
# NOT uuid.uuid7: absent on the installed 3.12, present on the "3.x"-pinned CI runner. A
# stdlib call that exists on the runner and not on the developer's machine is PACK-J by
# construction (spike S1).

# ONE implementation, in coord_ids.py, imported by this script AND by audit-log.py. Six
# duplicated lines across two scripts is ONE-A -- the copies are identical at birth and only
# diverge later, when one is edited. The sys.path line is what makes the sibling import work
# both when this file is RUN and when a test loads it via importlib.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from coord_ids import new_id, resolve_prefix          # noqa: E402  (path set above)


# --- register merges: the half that unique ids do NOT solve ------------------

def entry_fingerprint(row):
    """A stable identity for a register entry, EXCLUDING its id.

    The id is deliberately excluded. In the recorded KG-B instance the two entries had the
    SAME id and different content, and the register's own write-up names them by
    `shortname` rather than by id because rebases had renumbered them three times. A
    fingerprint keyed on the id would both miss the real loss and cry wolf on every
    legitimate renumber.

    `renumbered_from` is excluded for the same reason, and the conservation check found
    that itself: it is provenance ABOUT a merge, not part of the entry's identity, and
    including it made a renumbered entry look destroyed.
    """
    body = {k: v for k, v in row.items() if k not in ("id", "renumbered_from")}
    return json.dumps(body, sort_keys=True, ensure_ascii=False)


def conservation_lost(ours, theirs, merged):
    """Entries present on either side and absent from the merge. Empty means conserved.

    Unique ids stop the COLLISION; only this stops the RESOLUTION from destroying an entry,
    which is what actually happened. The recorded resolution reported "203 ours + 203 theirs
    -> 203 unique" and was caught only because that arithmetic is impossible.
    """
    after = {entry_fingerprint(r) for r in merged}
    lost = []
    for row in list(ours) + list(theirs):
        fp = entry_fingerprint(row)
        if fp not in after and fp not in {entry_fingerprint(x) for x in lost}:
            lost.append(row)
    return lost


def merge_register(ours, theirs, base=None):
    """Union two append-only registers by fingerprint. Returns (merged, lost).

    Append-only means the correct resolution is a union, never a pick. Order is preserved:
    ours first, then whatever theirs adds.

    When `base` is supplied, KG-B's own prescribed resolution also applies: *the id is a
    sequence, not an identity.* The side that already published an id keeps it, and an
    entry this merge INTRODUCES on a colliding id is renumbered from the allocator rather
    than deduped away. NFR-C2 still holds -- nothing already in the base is ever rewritten,
    and with no base the driver cannot tell who published first, so it conserves and does
    not guess.
    """
    merged, seen, taken = [], set(), set()
    published = {str(r.get("id")) for r in (base or [])}
    for source_is_ours, row in ([(True, r) for r in ours] + [(False, r) for r in theirs]):
        fp = entry_fingerprint(row)
        if fp in seen:
            continue
        seen.add(fp)
        eid = str(row.get("id", ""))
        if base is not None and eid in taken and eid not in published:
            row = dict(row)
            scheme = eid.split("-", 1)[0] if "-" in eid else "id"
            row["id"] = new_id(scheme)
            row["renumbered_from"] = eid    # provenance: a renumber must leave a trace
            eid = row["id"]
        taken.add(eid)
        merged.append(row)
    return merged, conservation_lost(ours, theirs, merged)


def _read_jsonl(path):
    rows = []
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        rows.append(json.loads(line))       # a parse error propagates: never guess a register
    return rows


def cmd_merge_register(result_path, base_path, theirs_path, real_path):
    """The merge driver for `register`-class artifacts. ALWAYS exits 0 (the S12b rule)."""
    try:
        ours = _read_jsonl(result_path)
        theirs = _read_jsonl(theirs_path)
        try:
            base = _read_jsonl(base_path)   # %O: which ids were already published
        except (OSError, json.JSONDecodeError):
            base = None                     # no base -> conserve, but never guess a renumber
    except (OSError, json.JSONDecodeError) as exc:
        # A register we cannot read must not be "merged" -- guessing here is exactly how an
        # entry disappears. Make the failure visible in the file instead.
        _write_conflict(result_path, result_path, theirs_path,
                        "{} is unreadable as JSONL ({}); not merging".format(
                            real_path, exc.__class__.__name__))
        return 0
    merged, lost = merge_register(ours, theirs, base=base)
    if lost:
        _write_conflict(result_path, result_path, theirs_path,
                        "{} entry/entries would be lost by this merge".format(len(lost)))
        return 0
    Path(result_path).write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in merged),
        encoding="utf-8", newline="\n")
    return 0


# --- Phase 3: the artifact-class registry -----------------------------------
#
# The class decides the MECHANISM entirely (ADR-0009). Measured: the six busiest files in
# the reference repo are all generated, so a uniform lease aims at 13/60 and misses 58/60.

CLASSES = ("authored", "derived", "register", "hotspot")
REGISTRY_NAME = "artifacts.yml"
REGEN_OWED = "regen-owed.txt"


def load_registry(root):
    """Parse `.agents/artifacts.yml` into [(pattern, class, command)].

    simplify: a line-oriented parser for `pattern: class [command...]` plus `#` comments,
      NOT general YAML.
      ceiling: anchors, nesting, multi-line values.
      upgrade trigger: the first registry a human writes that this rejects.
    Thirty lines against a dependency the pack does not have (NFR-P2) -- the
    Gratuitous-Dependency gate holds at rung 5.

    Raises CoordError; never returns a partly-parsed registry, because a half-read registry
    would silently reclassify whatever it failed to read.
    """
    path = Path(root) / REGISTRY_NAME
    if not path.is_file():
        return None                      # unregistered != empty. The caller says "advisory".
    entries, seen = [], {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise CoordError("COORD-CLASS-CONFLICT",
                             "{}:{}: expected `pattern: class [command]`".format(
                                 REGISTRY_NAME, lineno))
        pattern, rest = line.split(":", 1)
        pattern = _norm(pattern.strip())
        parts = rest.strip().split(None, 1)
        klass = parts[0] if parts else ""
        command = parts[1].strip() if len(parts) > 1 else ""
        if klass not in CLASSES:
            raise CoordError("COORD-CLASS-CONFLICT",
                             "{}:{}: unknown class {!r}; expected one of {}".format(
                                 REGISTRY_NAME, lineno, klass, ", ".join(CLASSES)))
        # STRIDE B7: a pattern escaping the repository would let the registry point the
        # driver at something outside it.
        bad = _reject_path(pattern)
        if bad:
            raise CoordError("COORD-CLASS-CONFLICT",
                             "{}:{}: {}".format(REGISTRY_NAME, lineno, bad))
        # A derived class with no regenerate command cannot do its job: it would resolve
        # every merge and leave the artifact permanently stale while claiming to be handled.
        if klass == "derived" and not command:
            raise CoordError("COORD-CLASS-CONFLICT",
                             "{}:{}: a `derived` pattern needs a regenerate command".format(
                                 REGISTRY_NAME, lineno))
        if pattern in seen and seen[pattern] != klass:
            # H7: overlapping patterns of DIFFERENT class are a registry error, never a
            # precedence rule -- first-match-wins would make a path's class depend on
            # file ordering.
            raise CoordError("COORD-CLASS-CONFLICT",
                             "{}:{}: {!r} is classified both {!r} and {!r}".format(
                                 REGISTRY_NAME, lineno, pattern, seen[pattern], klass))
        seen[pattern] = klass
        entries.append((pattern, klass, command))
    return entries


def classify(root, path):
    """(class, reason_code). Longest matching pattern wins; the default is `authored`.

    Pattern: Null Object -- an unclassified path yields the SAFE class, so no call site
    needs a branch for "unknown".
    """
    try:
        entries = load_registry(root)
    except CoordError as exc:
        return "authored", exc.code
    if entries is None:
        return "authored", "COORD-CLASS-UNREGISTERED"
    target = _norm(path)
    best = None
    for pattern, klass, _cmd in entries:
        if fnmatch.fnmatch(target, pattern) and (best is None or len(pattern) > len(best[0])):
            best = (pattern, klass)
    return (best[1] if best else "authored"), None


def regen_command(root, path):
    try:
        entries = load_registry(root) or []
    except CoordError:
        return None
    target = _norm(path)
    best = None
    for pattern, klass, cmd in entries:
        if klass == "derived" and fnmatch.fnmatch(target, pattern):
            if best is None or len(pattern) > len(best[0]):
                best = (pattern, cmd)
    return best[1] if best else None


# --- the deferred-regeneration debt -----------------------------------------
#
# The driver RESOLVES during the merge and regenerates AFTERWARDS. It cannot regenerate in
# place: git runs merge drivers per file in arbitrary order, so a derived artifact's own
# sources may still be unmerged when its driver runs, and regenerating then produces output
# from a half-merged tree. This is the shape the prior art already uses (sync-generated.ps1
# rebases, then regenerates) and the reason the design was amended during implementation.

def record_regen_owed(root, path):
    owed = set(regen_owed(root))
    owed.add(_norm(path))
    target = Path(root) / REGEN_OWED
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(p + "\n" for p in sorted(owed)), encoding="utf-8", newline="\n")


def regen_owed(root):
    target = Path(root) / REGEN_OWED
    if not target.is_file():
        return []
    return [l.strip() for l in target.read_text(encoding="utf-8").splitlines() if l.strip()]


def clear_regen_owed(root, paths):
    remaining = [p for p in regen_owed(root) if p not in set(paths)]
    target = Path(root) / REGEN_OWED
    if remaining:
        target.write_text("".join(p + "\n" for p in remaining), encoding="utf-8", newline="\n")
    elif target.exists():
        target.unlink()


def _reject_path(path):
    """Reasons a path may not be checked at all. Returns a reason, or None if it is fine.

    STRIDE B4/B5, tampering: the path is never opened, never globbed against the
    filesystem, and never passed to a shell - but a path that escapes the repository has
    no meaning in a repo-scoped lease, and answering "free" for it would be a false grant.
    """
    if len(path) > MAX_PATH:
        return "the path exceeds the length bound"
    normalised = _norm(path)
    if "\0" in path or not path.strip():
        return "the path contains a NUL or is empty"
    segments = [s for s in normalised.split("/") if s not in ("", ".")]
    depth = 0
    for segment in segments:
        depth += -1 if segment == ".." else 1
        if depth < 0:
            return "the path escapes the repository"
    return None


# --- Phase 3: harness adapters ----------------------------------------------
#
# THE TWO ENVELOPES ARE NOT SIMILAR. Established by execution, not by documentation:
#
#   Claude   {"tool_name": "Edit", "tool_input": {"file_path": "src/a.cs"}}
#   Copilot  {"hookType": "preToolUse",
#             "input": {"cwd": "C:\\repo",
#                       "toolCalls": [{"name": "edit", "args": "{\"path\": \"C:\\repo\\src\\a.cs\"}"}]}}
#
# Copilot batches N tool calls into ONE invocation, `args` is a JSON STRING rather than an
# object, the path field is `path` not `file_path`, and the path is ABSOLUTE. A hook that
# reads tool_input.file_path finds nothing in a Copilot payload and returns "allow" for
# every edit -- a silent no-op wearing the shape of enforcement. The conformance suite
# caught exactly that before any of it shipped.
#
# Shape recorded from ~/.copilot/session-state/*/events.jsonl: 55,541 preToolUse
# invocations, of which `powershell` is the commonest single tool (26,210) -- the
# shell-bypass path named as G4 in the Phase-2 design, here measured rather than supposed.

# Tools that WRITE. Everything else carries no path we care about, and one that carries no
# path must never have one invented for it.
_WRITE_TOOLS = {"edit", "create", "write", "apply_patch", "str_replace", "multiedit",
                "notebookedit"}
_PATH_KEYS = ("file_path", "path", "filePath", "notebook_path")

HARNESS_STATUS = {
    "claude": {
        "edit_boundary": "enforcing",
        "why": "PreToolUse contract established by execution and the deny response is "
               "honoured (spike S5, five cases incl. both fail-safe paths).",
    },
    "copilot": {
        # The architecture's condition 2, CLOSED by a live session on 2026-08-24 rather
        # than assumed either way.
        "edit_boundary": "enforcing",
        "why": "A live Copilot CLI 1.0.80 session honoured a deny: a read of an unleased "
               "file succeeded, a write to a leased one was refused with our reason "
               "rendered verbatim into the transcript, and the file was unmodified. "
               "RESIDUAL, unchanged: Copilot fails OPEN on a 30s hook timeout, so a hung "
               "hook allows. Our measured check is 63ms p95, and the commit floor backs it.",
    },
}


def _relativise(path, repo, cwd=None):
    """An absolute harness path made repo-relative, or left alone if already relative."""
    if not path:
        return None
    text = _norm(path)
    for base in (cwd, repo):
        if not base:
            continue
        prefix = _norm(base).rstrip("/") + "/"
        if text.lower().startswith(prefix.lower()):
            return text[len(prefix):]
    return text


def parse_hook_request(event, repo):
    """Normalise any harness's PreToolUse envelope to [(tool_name, repo_relative_path)].

    A path of None means "this tool call carries no path" -- a shell command, a search, a
    read. That is not the same as "no path found", and the difference decides whether the
    layer has an opinion at all.
    """
    if not isinstance(event, dict):
        return []

    # Copilot: a batch, under input.toolCalls, with args as a JSON string.
    payload = event.get("input")
    if isinstance(payload, dict) and isinstance(payload.get("toolCalls"), list):
        cwd = payload.get("cwd")
        calls = []
        for call in payload["toolCalls"]:
            if not isinstance(call, dict):
                continue
            name = str(call.get("name", ""))
            args = call.get("args")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (ValueError, TypeError):
                    args = None
            path = None
            if isinstance(args, dict):
                for key in _PATH_KEYS:
                    if args.get(key):
                        path = _relativise(args[key], repo, cwd)
                        break
            calls.append((name, path))
        return calls

    # Claude: one call, flat.
    if "tool_name" in event or "tool_input" in event:
        name = str(event.get("tool_name", ""))
        tool_input = event.get("tool_input")
        path = None
        if isinstance(tool_input, dict):
            for key in _PATH_KEYS:
                if tool_input.get(key):
                    path = _relativise(tool_input[key], repo)
                    break
        return [(name, path)]

    return []


def detect_harness(event):
    if isinstance(event, dict) and isinstance(event.get("input"), dict) \
            and "toolCalls" in event["input"]:
        return "copilot"
    return "claude"


def hook_decision_of(response):
    """Read a decision back out of any harness's response envelope.

    Used by the conformance suite so the assertion does not have to know which shape it is
    looking at -- adding a harness means adding a fixture and a branch here, not rewriting
    the tests.
    """
    if not isinstance(response, dict):
        return None
    block = response.get("hookSpecificOutput")
    if isinstance(block, dict) and block.get("permissionDecision"):
        return block["permissionDecision"]
    return response.get("permissionDecision") or response.get("decision")


def hook_response_is_valid(response, harness):
    """Does this response match the envelope that harness actually reads?

    Copilot consumes the Claude plugin format, and the recorded corpus does not show the
    response shape -- so both adapters emit the Claude envelope and this returns True for
    both. That is a DELIBERATE, RECORDED assumption, not a verified fact: it is exactly
    what a live Copilot deny would confirm or refute (H13).
    """
    if not isinstance(response, dict):
        return False
    block = response.get("hookSpecificOutput")
    if not isinstance(block, dict):
        return False
    return (block.get("hookEventName") == "PreToolUse"
            and block.get("permissionDecision") in ("allow", "deny", "ask")
            and isinstance(block.get("permissionDecisionReason"), str))


def hook_response(decision, reason):
    """The PreToolUse envelope. ALWAYS printed, and the caller ALWAYS exits 0 - the
    harness reads the decision in the JSON, not the exit code. Conflating them would make
    a crashed hook indistinguishable from a refusal.
    """
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason}})


def _not_checked(reason):
    return hook_response("ask", "NOT CHECKED  -\n  held by   unknown - this check did"
                         " not run\n  because   {}\n"
                         "  remedy    fix the condition above; this is not a pass"
                         .format(reason))


def cmd_hook(root, session, agent, now, stdin_text, repo=None):
    """G1: this must never raise. A hook that crashes on a bad payload blocks every edit.

    Envelope-agnostic: `parse_hook_request` normalises whichever harness is calling. Copilot
    BATCHES tool calls, so one invocation can carry several paths -- and if any of them is
    refused the whole batch is refused. A false refusal costs a message; a false grant costs
    a merge.
    """
    try:
        event = json.loads(stdin_text or "")
        if not isinstance(event, dict):
            raise ValueError("payload is not an object")
        calls = parse_hook_request(event, repo or root)
    except Exception as exc:
        return _not_checked("unreadable hook payload ({})".format(exc.__class__.__name__))

    if not calls:
        return _not_checked("the payload matched no known harness envelope")

    # The PARSER normalises the envelope; the POLICY lives here. Reads are parallel and
    # writes serialize, so a `view` of a leased artifact is allowed -- refusing reads would
    # be both wrong and the fastest way to get the hook switched off.
    paths = [p for name, p in calls if p and str(name).lower() in _WRITE_TOOLS]
    if not paths:
        # G2: powershell, view, grep -- 26,210 of the recorded Copilot invocations are
        # `powershell` alone. A call that carries no path, or only reads one, is allowed.
        return hook_response("allow", "coordination: no write to a coordinated path")

    worst = None
    for path in paths:
        bad = _reject_path(str(path))                   # B4 tampering
        if bad:
            return _not_checked(bad)
        # B4 spoofing: identity is the ENVIRONMENT's, never the payload's sessionId.
        decision = check(root, str(path), session, now)
        append_decision(root, session, agent, path, decision)
        if decision["decision"] == "deny":
            worst = decision
            break                                       # the batch is already refused
        if decision["decision"] == "not_checked" and worst is None:
            worst = decision

    if worst is None:
        return hook_response("allow", "coordination: {} path(s) free or mine"
                             .format(len(paths)))
    mapped = {"deny": "deny", "not_checked": "ask"}[worst["decision"]]
    return hook_response(mapped, render(worst))


def cmd_precommit(root, repo, session, agent, now):
    paths, err = staged_paths(repo)
    if err is not None:
        print("COORD-NOT-CHECKED-GIT: {}".format(_safe(err, 300)))
        return 4
    if not paths:
        print("0 staged paths - nothing to check")
        return 0

    # US-8: a repository that has not adopted the layer runs in ADVISORY mode and SAYS SO,
    # rather than implying enforcement it cannot deliver. Blocking every commit in every
    # unconfigured repo is how a floor gets deleted instead of adopted.
    _, _, files = read_events(root)
    if files == 0:
        print("advisory: no coordination record in this repository, so nothing was checked."
              "\n  {} staged path(s) allowed. Run `coord claim` to make this enforcing."
              .format(len(paths)))
        return 0

    refused = []
    for path in paths:
        decision = check(root, path, session, now)
        append_decision(root, session, agent, path, decision)
        if decision["decision"] == "deny":
            refused.append(decision)
        elif decision["decision"] == "not_checked":
            print(render(decision))
            return 4
    if refused:
        for decision in refused:
            print(render(decision))
        print("\n{} of {} staged path(s) are held by another session".format(
            len(refused), len(paths)))
        return 3
    print("{} staged path(s) checked - all free or mine".format(len(paths)))
    return 0


def cmd_guard(repo, fix):
    count, reason = unique_commits(repo)
    if reason == "COORD-DETACHED":
        print("COORD-DETACHED  HEAD is detached, so 'does this exist anywhere else' has no"
              " meaning here. NOT CHECKED - this is not a pass.")
        return 4
    if reason == "COORD-NOT-CHECKED-GIT":
        print("COORD-NOT-CHECKED-GIT  git could not answer; nothing was checked.")
        return 4
    if reason == "COORD-NO-PEER-REFS":
        print("COORD-NO-PEER-REFS  there are no other refs in this repository, so nothing"
              " here exists in a second place.\n  remedy    push, or accept that this is a"
              " fresh repository")
        return 3
    if count:
        out, _ = _git(repo, "rev-list", "--oneline", "-n", "20", "HEAD", "--not",
                      *[r for r in (_git(repo, "for-each-ref", "--format=%(refname)",
                                         "refs/heads", "refs/remotes")[0] or "").split()
                        if r != "refs/heads/" + (_git(repo, "symbolic-ref", "-q",
                                                      "--short", "HEAD")[0] or "").strip()])
        print("COORD-UNIQUE-WORK  {} commit(s) exist here and nowhere else:".format(count))
        for line in (out or "").splitlines():
            print("  {}".format(_safe(line, 120)))
        print("  remedy    push - it is the cheapest way to make the work exist twice")
        if fix:
            _, err = _git(repo, "push")
            if err:
                print("  push failed: {}".format(_safe(err, 200)))
                return 3
            recount, _ = unique_commits(repo)
            if recount:
                print("  push reported success but {} commit(s) are still unique"
                      .format(recount))
                return 3
            print("  pushed - now safe")
            return 0
        return 3
    print("safe to move HEAD - nothing here exists in only one place")
    return 0


def _worktree_key(cwd):
    return str(Path(cwd).resolve()).replace("\\", "/")


def active_sessions(root, now, stale_seconds=SESSION_STALE_SECONDS):
    """Fold the append-only record into active collaboration sessions.

    The session ledger is evidence that someone announced themselves, not proof that nobody
    else exists (DC-024). This fold therefore reports only positive liveness; callers that
    need absence-of-use proof must also inspect the filesystem/worktree state.
    """
    events, errors, files = read_events(root)
    leases = fold(events, now)
    claims_by_session = {}
    for lease in leases.values():
        claims_by_session.setdefault(lease["session"], []).append({
            "path": lease["path"],
            "wi": lease.get("wi", ""),
            "agent": lease.get("agent", lease["session"]),
            "expires": lease.get("expires"),
        })

    live = {}
    for event in events:
        session = event.get("session")
        if not session:
            continue
        if event.get("kind") == "session-start":
            live[session] = {
                "session": session,
                "agent": event.get("agent", session),
                "worktree": event.get("worktree", ""),
                "started_at": event.get("at", 0.0),
                "last_at": event.get("at", 0.0),
                "claims": [],
            }
            continue
        if event.get("kind") == "session-end":
            live.pop(session, None)
            continue
        if session in live:
            live[session]["last_at"] = max(live[session]["last_at"], event.get("at", 0.0))

    sessions = []
    for session, state in live.items():
        if now - state.get("last_at", 0.0) >= stale_seconds:
            continue
        state = dict(state)
        state["claims"] = sorted(claims_by_session.get(session, []), key=lambda c: c["path"])
        sessions.append(state)
    sessions.sort(key=lambda s: (s.get("worktree", ""), s.get("session", "")))
    return sessions, errors, files


def session_contract_path(repo):
    return Path(repo) / SESSION_CONTRACT


def _role_token(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _strip_cell(value):
    value = value.strip()
    if value.startswith("`") and value.endswith("`") and len(value) >= 2:
        value = value[1:-1]
    return value.strip()


def contract_ownership(repo):
    """Parse the simple ownership tables from the session contract template.

    This is intentionally Markdown-shaped rather than a general Markdown parser: the pack
    owns the template and the rows are `| Path | Why |` under `### <Role> owns`.
    Unknown shapes simply yield no ownership facts; the contract remains human-readable.
    """
    path = session_contract_path(repo)
    if not path.is_file():
        return {}
    ownership, current = {}, None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        heading = re.match(r"^###\s+(.+?)\s+owns\s*$", raw.strip(), flags=re.IGNORECASE)
        if heading:
            current = heading.group(1).strip()
            ownership.setdefault(current, [])
            continue
        if raw.startswith("### "):
            current = None
            continue
        if not current or not raw.strip().startswith("|"):
            continue
        cells = [_strip_cell(c) for c in raw.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower() in ("path", "---") or set(cells[0]) <= {"-"}:
            continue
        ownership.setdefault(current, []).append({"path": _norm(cells[0]), "why": cells[1]})
    return {role: rows for role, rows in ownership.items() if rows}


def infer_session_roles(session, agent, ownership):
    """Infer contract role membership from session/agent labels.

    This stays advisory. A false warning costs a message; a false grant is what creates
    cross-owned edits. A later slice can replace this with explicit `COORD_ROLE`.
    """
    tokens = {t for t in re.split(r"[^a-z0-9]+", "{} {}".format(session, agent).lower()) if t}
    roles = []
    for role in ownership:
        role_tokens = [t for t in re.split(r"[^a-z0-9]+", role.lower()) if t]
        if role_tokens and all(token in tokens for token in role_tokens):
            roles.append(role)
    return roles


def owner_rows_for_path(ownership, path):
    owners = []
    for role, rows in ownership.items():
        for row in rows:
            if overlaps(row["path"], path):
                owners.append({"role": role, "path": row["path"], "why": row.get("why", "")})
    return owners


def collaboration_findings(root, repo, now, snapshot=None):
    """Return collaboration health findings.

    This is a small operator gate over the live session fold. It is deliberately advisory:
    it catches the AI-DE class where two sessions had to publish a contract and claim files
    to avoid merge/rebase damage, but it does not pretend a claim is a distributed lock.
    """
    sessions, errors, files = snapshot or active_sessions(root, now)
    findings = []
    if errors:
        findings.append({
            "code": "COORD-COLLAB-NOT-CHECKED-RECORD",
            "severity": "blocker",
            "reason": "coordination record is unreadable: {}".format(_safe("; ".join(errors[:2]), 200)),
        })
        return findings
    if files == 0:
        findings.append({
            "code": "COORD-COLLAB-NOT-CHECKED-EMPTY",
            "severity": "blocker",
            "reason": "0 coordination files scanned; no collaboration state established",
        })
        return findings
    if len(sessions) > 1 and not session_contract_path(repo).is_file():
        findings.append({
            "code": "COORD-COLLAB-NO-CONTRACT",
            "severity": "blocker",
            "reason": "{} active sessions but {} is missing".format(
                len(sessions), SESSION_CONTRACT),
        })
    ownership = contract_ownership(repo)
    if ownership:
        for item in sessions:
            roles = infer_session_roles(item.get("session", ""), item.get("agent", ""), ownership)
            for claim in item.get("claims", []):
                owners = owner_rows_for_path(ownership, claim.get("path", ""))
                if owners and not any(o["role"] in roles for o in owners):
                    findings.append({
                        "code": "COORD-COLLAB-CROSS-OWNED-CLAIM",
                        "severity": "warning",
                        "reason": "session {} claims {} owned by {}".format(
                            item["session"], claim.get("path", ""),
                            ", ".join(sorted({o["role"] for o in owners}))),
                    })
    if len(sessions) > 1:
        no_claims = [s["session"] for s in sessions if not s.get("claims")]
        if no_claims:
            findings.append({
                "code": "COORD-COLLAB-NO-CLAIMS",
                "severity": "warning",
                "reason": "active session(s) with no claims: {}".format(", ".join(sorted(no_claims))),
            })
    return findings


def cmd_session_list(root, now, as_json=False):
    sessions, errors, files = active_sessions(root, now)
    payload = {"files_scanned": files, "sessions": sessions, "errors": errors}
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if not errors else 4
    if errors:
        print("COORD-NOT-CHECKED-RECORD: {}".format(_safe("; ".join(errors[:2]), 200)))
        return 4
    print("{} active session(s); {} file(s) scanned".format(len(sessions), files))
    for item in sessions:
        print("  {:<24} {:<18} {}  {} claim(s)".format(
            _safe(item["session"], 24),
            _safe(item.get("agent", ""), 18),
            _safe(item.get("worktree", ""), 90),
            len(item.get("claims", []))))
        for claim in item.get("claims", []):
            print("    - {:<30} {}".format(_safe(claim.get("wi", ""), 30),
                                           _safe(claim.get("path", ""), 120)))
    return 0


def cmd_collaborate(root, repo, action, now, as_json=False):
    if action not in ("check", "summary"):
        return 2
    sessions, errors, files = active_sessions(root, now)
    findings = collaboration_findings(root, repo, now, snapshot=(sessions, errors, files))
    request_events, request_errors = read_request_events(root)
    requests = fold_requests(request_events)
    open_requests = [r for r in requests if r.get("status") == "open"]
    payload = {"files_scanned": files, "active_sessions": sessions, "findings": findings,
               "contract": SESSION_CONTRACT, "contract_exists": session_contract_path(repo).is_file()}
    if action == "summary":
        payload["requests"] = open_requests
        payload["request_errors"] = request_errors
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        if action == "summary":
            return 0
        return 3 if any(f.get("severity") == "blocker" for f in findings) else 0
    print("collaboration: {} active session(s); contract {}".format(
        len(sessions), "present" if payload["contract_exists"] else "missing"))
    for item in sessions:
        print("  session {:<24} agent {:<18} claims {}".format(
            _safe(item["session"], 24), _safe(item.get("agent", ""), 18),
            len(item.get("claims", []))))
    if action == "summary":
        print("requests: {} open".format(len(open_requests)))
        for request in open_requests:
            print("  {:<22} -> {:<12} {}".format(
                _safe(request.get("id", ""), 22),
                _safe(request.get("to", ""), 12),
                _safe(request.get("contract", ""), 90)))
    if not findings:
        print("collaboration check: OK")
        return 0
    for finding in findings:
        print("{}  {}  {}".format(finding["severity"].upper(), finding["code"],
                                  finding["reason"]))
    if action == "summary":
        return 0
    return 3 if any(f.get("severity") == "blocker" for f in findings) else 0


def cmd_request(root, action, now, session, agent, args):
    events, errors = read_request_events(root)
    if errors:
        print("COORD-REQUEST-NOT-CHECKED  {}".format(_safe("; ".join(errors[:2]), 200)),
              file=sys.stderr)
        return 4
    if action == "add":
        rid = new_id("req")
        record = {"kind": "request-add", "id": rid, "at": now,
                  "session": session or "anon", "agent": agent or "anon",
                  "from": args.from_role or agent or session or "unknown",
                  "to": args.to, "contract": args.contract,
                  "reason": args.reason, "path": _norm(args.path or "")}
        append_record(request_log_path(root), record)
        print(json.dumps({"id": rid, "status": "open"}))
        return 0
    if action == "resolve":
        folded = {r["id"]: r for r in fold_requests(events)}
        if args.id not in folded:
            print("COORD-REQUEST-NOT-FOUND  {}".format(_safe(args.id, 80)))
            return 4
        append_record(request_log_path(root), {"kind": "request-resolve", "id": args.id,
                                               "at": now, "session": session or "anon",
                                               "agent": agent or "anon",
                                               "resolution": args.resolution})
        print(json.dumps({"id": args.id, "status": "resolved",
                          "resolution": args.resolution}))
        return 0
    # list
    folded = fold_requests(events)
    if args.status != "all":
        folded = [r for r in folded if r.get("status") == args.status]
    payload = {"requests": folded, "events_scanned": len(events), "errors": []}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("{} request(s)".format(len(folded)))
        for request in folded:
            print("  {:<22} {:<8} -> {:<12} {}".format(
                _safe(request.get("id", ""), 22),
                _safe(request.get("status", ""), 8),
                _safe(request.get("to", ""), 12),
                _safe(request.get("contract", ""), 100)))
    return 0


# --- worktree lifecycle (session-worktree-discipline.md WT1-WT12) ------------
# This file already resolves the primary checkout from any tree and keys occupancy by
# worktree, so the lifecycle belongs here rather than in a parallel tool. WT1 makes a fresh
# worktree the DEFAULT unit of session isolation; WT6-WT12 close the half that actually rots:
# an isolation mechanism nobody cleans up becomes a disk of half-finished trees, one of which
# is eventually the only copy of some real work.

def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:48] or "session"


def worktree_inventory(repo):
    """Parse `git worktree list --porcelain`. Returns (records, error).

    Porcelain is used rather than the human format because a path containing a space is
    otherwise unparseable - the same reasoning as staged_paths()'s -z form.
    """
    out, err = _git(repo, "worktree", "list", "--porcelain")
    if err:
        return None, err
    records, current = [], {}
    for line in (out or "").splitlines():
        if not line.strip():
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current["path"] = value
        elif key == "branch":
            current["branch"] = value.replace("refs/heads/", "")
        elif key == "HEAD":
            current["head"] = value
        elif key in ("bare", "detached", "locked", "prunable"):
            current[key] = value or True
    if current:
        records.append(current)
    return records, None


def worktree_is_clean(path):
    """True when there is nothing modified, staged OR UNTRACKED.

    Untracked is the condition that matters most: a new file nobody has committed exists
    nowhere else, so deleting its tree destroys the only copy. `git status --porcelain`
    includes untracked by default and the -z form survives paths with spaces or quotes.
    """
    out, err = _git(path, "status", "--porcelain", "-z")
    if err:
        return None, err
    return not [p for p in (out or "").split("\0") if p.strip()], None


def worktree_safety(record, primary, cwd, live_keys, index):
    """WT7, in order, fail-safe. Returns (safe, reason).

    Every condition is a HARD STOP that reports rather than removes. A cleanup that deletes
    on a heuristic will eventually delete the tree that mattered, and that single event ends
    the adoption of the whole practice.
    """
    path = record.get("path", "")
    resolved = _worktree_key(path)
    if resolved == _worktree_key(primary):
        return False, "primary checkout - the reference tree is never cleanup"
    if resolved == _worktree_key(cwd):
        return False, "current working directory - deleting the floor you stand on"
    if record.get("locked"):
        return False, "locked by git"
    if resolved in live_keys:
        return False, "a live session holds it (coord session start, not ended)"
    if not os.path.isdir(path):
        return True, "directory is gone; only the git metadata remains (prunable)"
    clean, err = worktree_is_clean(path)
    if err:
        return False, "could not read status: {}".format(_safe(err, 120))
    if not clean:
        return False, "uncommitted or untracked changes - the only copy of that work"
    count, code = unique_commits(path)
    if count is None:
        return False, "could not compute unique commits ({})".format(code)
    if count > 0:
        return False, "{} commit(s) exist nowhere else - unmerged work".format(count)
    branch = record.get("branch")
    if branch and index.get(branch, 0) > 1:
        return False, "branch {} is checked out in another tree".format(_safe(branch, 60))
    return True, "clean, merged, unheld"


def cmd_worktree(root, repo, action, cwd, now, session=None, agent=None,
                 branch=None, base=None, remove=False):
    records, err = worktree_inventory(repo)
    if err:
        print("COORD-NOT-CHECKED-GIT: {}".format(_safe(err, 200)))
        return 4
    primary = records[0]["path"] if records else str(repo)

    if action == "new":
        name = branch or (session and "session/" + _slug(session))
        if not name:
            print("worktree new needs --branch <name> (or --session to derive one).\n"
                  "  Name it for the WORK, not the session (WT5): a tree called\n"
                  "  session-2026-08-22-a is one nobody can ever safely clean up.")
            return 2
        # Sibling of the primary, never inside it: a tree inside the repo would be walked by
        # docs-graph, check-consistency and every test that scans the tree.
        parent = os.path.dirname(os.path.abspath(primary))
        target = os.path.join(parent, "{}-{}".format(os.path.basename(os.path.abspath(primary)),
                                                     _slug(name)))
        if os.path.exists(target):
            print("COORD-WORKTREE-EXISTS  {}\n  remedy    cd there, or pick another --branch"
                  .format(_safe(target, 300)))
            return 3
        args = ["worktree", "add", "-b", name, target]
        if base:
            args.append(base)
        out, err = _git(repo, *args)
        if err:
            print("COORD-WORKTREE-ADD-FAILED: {}".format(_safe(err, 300)))
            return 4
        if session:
            append_event(root, {"kind": "session-start", "session": session,
                                "agent": agent or session, "wi": "WI-0", "path": "-",
                                "at": now, "worktree": _worktree_key(target)})
        print("worktree ready\n  branch    {}\n  path      {}\n  next      cd {}"
              .format(name, target, target))
        if session:
            print("  session   {} registered there".format(session))
        return 0

    # Shared state for list/cleanup.
    STALE_SECONDS = 8 * 3600
    events, errors, _ = read_events(root)
    if errors:
        print("COORD-NOT-CHECKED-RECORD: {}".format(_safe("; ".join(errors[:2]), 200)))
        return 4
    live = {}
    for event in events:
        key = event.get("worktree")
        if event.get("kind") == "session-start":
            live[key] = max(live.get(key, 0.0), event.get("at", 0.0))
        elif event.get("kind") == "session-end":
            live.pop(key, None)
    live_keys = {k for k, t in live.items() if k and now - t < STALE_SECONDS}
    index = {}
    for record in records:
        if record.get("branch"):
            index[record["branch"]] = index.get(record["branch"], 0) + 1

    verdicts = []
    for record in records:
        safe, reason = worktree_safety(record, primary, cwd, live_keys, index)
        verdicts.append((record, safe, reason))

    if action == "list":
        print("{} worktree(s); primary {}".format(len(records), _safe(primary, 200)))
        for record, safe, reason in verdicts:
            print("  {:<10} {:<44} {:<22} {}".format(
                "SAFE" if safe else "HELD",
                _safe(record.get("path", "?"), 140),
                _safe(record.get("branch") or "(detached)", 40),
                reason))
        return 0

    # cleanup: reports by default; --remove is the explicit gate on an irreversible act (WT8).
    removable = [(r, why) for r, safe, why in verdicts if safe]
    held = [(r, why) for r, safe, why in verdicts if not safe]
    # WT12: refusals are printed, because a silent skip is indistinguishable from finding
    # nothing - and the difference is exactly what the human needs.
    for record, why in held:
        print("KEEP    {:<44} {}".format(_safe(record.get("path", "?"), 140), why))
    if not removable:
        print("nothing to remove ({} tree(s) kept)".format(len(held)))
        out, err = _git(repo, "worktree", "prune")   # WT9: metadata still gets tidied
        return 0 if not err else 4
    for record, why in removable:
        print("{} {:<44} {}".format("REMOVE " if remove else "WOULD   ",
                                    _safe(record.get("path", "?"), 140), why))
    if not remove:
        print("\n{} tree(s) are safe to remove. Nothing was deleted - deleting a directory is\n"
              "irreversible and git cannot undo it, so it is opt-in (WT8):\n"
              "  coord worktree cleanup --remove".format(len(removable)))
        return 0
    failed = 0
    for record, _why in removable:
        out, err = _git(repo, "worktree", "remove", "--force", record.get("path", ""))
        if err:
            failed += 1
            print("  FAILED  {}: {}".format(_safe(record.get("path", "?"), 140), _safe(err, 160)))
    # WT9: a hand-deleted directory leaves .git/worktrees/<name> behind and git keeps the
    # name reserved, so the next `worktree add` fails describing a state the filesystem does
    # not show. Prune so the administrative record matches reality, then read it back (E14).
    _git(repo, "worktree", "prune")
    after, err = worktree_inventory(repo)
    remaining = len(after) if after else "?"
    print("removed {} of {} tree(s); {} remain".format(
        len(removable) - failed, len(removable), remaining))
    return 4 if failed else 0


def cmd_session(root, action, session, agent, cwd, now):
    # simplify: occupancy is the newest session-start with no matching session-end,
    #   inside a staleness window.
    #   ceiling: a session killed without `session end` holds the tree until it elapses.
    #   upgrade trigger: the first time a human is blocked by a dead session.
    STALE_SECONDS = 8 * 3600
    key = _worktree_key(cwd)
    events, errors, _ = read_events(root)
    if errors:
        print("COORD-NOT-CHECKED-RECORD: {}".format(_safe("; ".join(errors[:2]), 200)))
        return 4
    live = {}
    for event in events:
        if event.get("worktree") != key:
            continue
        if event.get("kind") == "session-start":
            live[event.get("session")] = event.get("at", 0.0)
        elif event.get("kind") == "session-end":
            live.pop(event.get("session"), None)
    live = {s: t for s, t in live.items() if now - t < STALE_SECONDS and s != session}

    if action == "start":
        if live:
            holder = sorted(live, key=live.get)[-1]
            print("COORD-WORKTREE-OCCUPIED  {}\n  held by   {}\n  because   one session per"
                  " working tree - two sessions in one tree is how work gets lost\n"
                  "  remedy    use a separate worktree, or run `coord session end` there"
                  .format(_safe(key, 300), _safe(holder)))
            return 3
        append_event(root, {"kind": "session-start", "session": session, "agent": agent,
                            "wi": "WI-0", "path": "-", "at": now, "worktree": key})
        print("session {} registered in {}".format(session, key))
        return 0

    append_event(root, {"kind": "session-end", "session": session, "agent": agent,
                        "wi": "WI-0", "path": "-", "at": now, "worktree": key})
    print("session {} released {}".format(session, key))
    return 0


def cmd_metrics(root, repo, as_json):
    decisions = read_decisions(root)
    allowed = sum(1 for d in decisions if d.get("kind") == "allowed")
    refused = sum(1 for d in decisions if d.get("kind") == "refused")
    unchecked = sum(1 for d in decisions if d.get("kind") == "not_checked")
    total = allowed + refused
    # G15 / R4: a rate over an empty corpus is not a measurement. Report the absence.
    pct = round(100.0 * allowed / total, 1) if total else None
    unique, unique_reason = unique_commits(repo)
    payload = {"decisions": len(decisions), "allowed": allowed, "refused": refused,
               "not_checked": unchecked, "edits_under_lease_pct": pct,
               "unique_commits": unique, "unique_commits_reason": unique_reason,
               "reason": "" if total else "no decisions recorded - nothing to rate"}
    if as_json:
        print(json.dumps(payload))
        return 0
    print("decisions        {}".format(payload["decisions"]))
    print("  allowed        {}".format(allowed))
    print("  refused        {}".format(refused))
    print("  not checked    {}".format(unchecked))
    print("edits under a held lease   {}".format(
        "{}%".format(pct) if pct is not None else "no decisions recorded - nothing to rate"))
    print("commits existing in one place   {}".format(
        unique if unique is not None else unique_reason))
    return 0


def cmd_install(repo, root):
    hooks, err = _git(repo, "rev-parse", "--git-path", "hooks")
    if err:
        print("COORD-NOT-CHECKED-GIT  {}".format(_safe(err, 200)))
        return 4
    hooks_dir = Path(hooks.strip())
    if not hooks_dir.is_absolute():
        hooks_dir = Path(repo) / hooks_dir
    hooks_dir.mkdir(parents=True, exist_ok=True)
    target = hooks_dir / "pre-commit"
    body = HOOK_BODY.format(marker=HOOK_MARKER, python=sys.executable,
                            script=str(Path(__file__).resolve()).replace("\\", "/"))
    if target.exists():
        existing = target.read_text(encoding="utf-8", errors="replace")
        if HOOK_MARKER not in existing:
            # G11 / B6: never overwrite somebody else's hook.
            print("COORD-HOOK-EXISTS  {} already exists and is not ours - not overwritten."
                  "\n  remedy    merge the two by hand, or move the existing hook aside"
                  .format(target))
            return 2
        if existing == body:
            print("pre-commit hook already installed (unchanged)")
            _print_settings_entry(repo)
            return 0
    target.write_text(body, encoding="utf-8", newline="\n")
    try:
        os.chmod(target, 0o755)
    except OSError:
        pass
    gitignore = Path(root) / ".gitignore"
    try:
        Path(root).mkdir(parents=True, exist_ok=True)
        current = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        if "decisions/" not in current:
            gitignore.write_text(current + "decisions/\n", encoding="utf-8", newline="\n")
    except OSError:
        pass
    print("Wrote {}  (shared by every worktree of this repo)".format(target))
    _install_merge_driver(repo, root)
    _print_settings_entry(repo)
    return 0


def _install_merge_driver(repo, root):
    """Register the driver in .git/config and declare it in .gitattributes.

    .git/config is per-clone and NEVER committed, which is why `coord doctor` exists and
    why the value is READ BACK here rather than assumed -- the recorded CTRL-E instance was
    a `git config` that failed while the script reported success.
    """
    try:
        entries = load_registry(root)
    except CoordError as exc:
        print("merge driver not installed: {}".format(exc.code))
        return
    if not entries:
        return
    me = str(Path(__file__).resolve()).replace("\\", "/")
    # Pattern: Strategy, keyed by artifact class. The class decides the MECHANISM entirely
    # (ADR-0009) -- derived artifacts are resolved and regenerated afterwards; registers are
    # unioned under a conservation assertion. One driver each, selected by .gitattributes.
    drivers = {
        MERGE_DRIVER_NAME: ("derived",
                            "coord: resolve derived artifacts, regenerate after the merge",
                            '"{}" "{}" merge-derived %A %O %B %P'.format(sys.executable, me)),
        REGISTER_DRIVER_NAME: ("register",
                               "coord: union append-only registers, conserving every entry",
                               '"{}" "{}" merge-register %A %O %B %P'.format(sys.executable, me)),
    }
    declared = {}
    for name, (klass, label, command) in drivers.items():
        patterns = [p for p, k, _c in entries if k == klass]
        if not patterns:
            continue
        _git(repo, "config", "merge.{}.name".format(name), label)
        _git(repo, "config", "merge.{}.driver".format(name), command)
        # CTRL-E: read the value back. The recorded instance was a `git config` that failed
        # while the script reported success, leaving the driver unregistered for weeks.
        got, _err = _git(repo, "config", "--get", "merge.{}.driver".format(name))
        if not (got or "").strip():
            print("merge driver {!r} registration FAILED - `git config` reported nothing back"
                  .format(name))
            continue
        declared[name] = patterns

    if not declared:
        return
    ga = Path(repo) / ".gitattributes"
    current = ga.read_text(encoding="utf-8") if ga.exists() else ""
    added = 0
    for name, patterns in sorted(declared.items()):
        for pattern in patterns:
            line = "{} merge={}".format(pattern, name)
            if line in current:
                continue
            if current and not current.endswith("\n"):
                current += "\n"                     # LOG-A's sibling seam
            current += line + "\n"
            added += 1
    if added:
        ga.write_text(current, encoding="utf-8", newline="\n")
    print("Registered {}; .gitattributes declares {} pattern(s)".format(
        ", ".join(repr(n) for n in sorted(declared)),
        sum(len(p) for p in declared.values())))


def _write_conflict(result_path, ours_path, theirs_path, reason):
    """Write conventional conflict markers into the driver's result file, then exit 0.

    S12b, the hazard this exists for: a driver that exits NON-ZERO leaves the file unmerged
    with OURS content and NO markers. It looks clean, and `git add .` commits ours and
    silently discards theirs. Writing the markers makes the failure visible in the file --
    where a human, `git diff --check`, and the pre-commit floor all see it.
    """
    def read(p):
        try:
            return Path(p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    body = ("{s} ours\n{ours}{m}\n{theirs}{e} theirs\n"
            .format(s="<" * 7, m="=" * 7, e=">" * 7,
                    ours=read(ours_path), theirs=read(theirs_path)))
    Path(result_path).write_text("# coord: {}\n".format(_safe(reason, 160)) + body,
                                 encoding="utf-8", newline="\n")


def cmd_merge_derived(root, repo, result_path, base_path, theirs_path, real_path):
    """The .gitattributes merge driver. ALWAYS returns 0 -- see _write_conflict.

    Resolves a `derived` artifact to OURS and records that a regeneration is owed; anything
    it cannot classify as derived gets conventional conflict markers instead.
    """
    try:
        klass, reason = classify(root, real_path)
        if klass != "derived":
            # H6/B7: the highest-severity path in the phase. If the registry does not say
            # this exact path is derived, the driver must NOT resolve it -- resolving an
            # authored file is how a merge silently overwrites someone's work.
            _write_conflict(result_path, result_path, theirs_path,
                            "{} is classified {}{}; not resolving".format(
                                real_path, klass, " (" + reason + ")" if reason else ""))
            return 0
        # Resolve to ours, byte for byte. `result_path` (%A) already holds ours; touching
        # nothing else is the whole of STRIDE B8's mitigation -- %P is identity, never a
        # write target.
        record_regen_owed(root, real_path)
        return 0
    except Exception as exc:                      # never exit non-zero; never raise
        try:
            _write_conflict(result_path, result_path, theirs_path,
                            "driver error: {}".format(exc.__class__.__name__))
        except Exception:
            pass
        return 0


def cmd_regen(root, repo, timeout=120):
    """Run the regenerations the driver deferred. Returns (exit_code, results).

    A failed regeneration STAYS OWED and reports non-zero: a stale derived artifact looks
    finished, which is worse than a conflict.
    """
    results, done = [], []
    for path in regen_owed(root):
        command = regen_command(root, path)
        if not command:
            results.append({"path": path, "status": "no-command"})
            continue
        try:
            # DEVIATION (Rules of the Road §4, FR-075): shell=True is deliberate. `command` is a
            # regeneration command resolved from the repo-local coordination registry
            # (regen_command -> load_registry) - a trusted config source editable only by someone
            # with repo write access, never untrusted or network input, so this is not an injection
            # surface. It is retained rather than tokenized because registry regen commands may use
            # shell operators (&&, |, >) and must run identically on POSIX and Windows; a shlex
            # arg-list split mishandles Windows path separators and would break the regen path.
            proc = subprocess.run(command, cwd=str(repo), shell=True, capture_output=True,
                                  text=True, timeout=timeout)
            ok = proc.returncode == 0
            results.append({"path": path, "status": "ok" if ok else "failed",
                            "detail": _safe((proc.stderr or proc.stdout).strip(), 200)})
            if ok:
                done.append(path)
        except subprocess.TimeoutExpired:
            results.append({"path": path, "status": "failed",
                            "detail": "regeneration exceeded {}s".format(timeout)})
        except OSError as exc:
            results.append({"path": path, "status": "failed",
                            "detail": "{}: {}".format(exc.__class__.__name__, exc)})
    clear_regen_owed(root, done)
    failed = [r for r in results if r["status"] != "ok"]
    return (1 if failed else 0), results


def driver_status(repo):
    """Is the merge driver EFFECTIVE? Requires reading BOTH sources (spike S13).

    `git check-attr` reports the DECLARATION whether or not a driver exists, and
    `git config` reports the registration without knowing what it covers. Only comparing
    the two finds the gap -- and .git/config is per-clone and never committed, so a fresh
    clone or a new worktree is exactly where the gap appears.
    """
    declared, err = _git(repo, "check-attr", "--all", "--", ".")
    names = set()
    out, _ = _git(repo, "config", "--get-regexp", r"^merge\..*\.driver")
    for line in (out or "").splitlines():
        parts = line.split(".", 2)
        if len(parts) >= 3:
            names.add(parts[1])
    attrs, _ = _git(repo, "ls-files")
    declared_names, covered = set(), 0
    for f in (attrs or "").splitlines():
        got, _e = _git(repo, "check-attr", "merge", "--", f)
        if got and ": merge: " in got:
            value = got.rsplit(": merge: ", 1)[1].strip()
            if value not in ("unspecified", "unset", "set"):
                declared_names.add(value)
                covered += 1
    missing = sorted(declared_names - names)
    return {"declared": sorted(declared_names), "registered": sorted(names),
            "missing": missing, "covered_paths": covered,
            # R4: a scan of zero tracked files has not established "none declared".
            "files_scanned": len((attrs or "").splitlines())}


def cmd_doctor(root, repo):
    problems = 0
    try:
        entries = load_registry(root)
        if entries is None:
            print("registry         NOT PRESENT (advisory)")
            print("  effect      every path is treated as `authored`; nothing is regenerated")
            print("  remedy      create .agents/{} to make classification real".format(
                REGISTRY_NAME))
        else:
            print("registry         ok - {} pattern(s)".format(len(entries)))
    except CoordError as exc:
        print("registry         {}".format(exc.code))
        print("  because     {}".format(_safe(str(exc), 200)))
        problems += 1

    status = driver_status(repo)
    if status["missing"]:
        print("merge driver     NOT EFFECTIVE  [COORD-DRIVER-NOT-EFFECTIVE]")
        print("  declared    .gitattributes covers {} path(s) via {}".format(
            status["covered_paths"], ", ".join(status["missing"])))
        print("  registered  no - `git config merge.<name>.driver` is unset in this clone")
        print("  effect      those files will conflict normally instead of regenerating")
        print("  remedy      run `coord install` in this clone; .git/config is per-clone"
              " and never committed")
        problems += 1
    elif status["declared"]:
        print("merge driver     effective - {} declared, {} registered".format(
            ", ".join(status["declared"]), ", ".join(status["registered"])))
    elif status["files_scanned"] == 0:
        # R4 again, in code written the same afternoon the rule was cited. A scan of zero
        # tracked files has not established that no driver is declared.
        print("merge driver     NOT CHECKED - 0 tracked files scanned, so nothing was"
              " established")
        problems += 1
    else:
        print("merge driver     none declared ({} tracked file(s) scanned)".format(
            status["files_scanned"]))

    owed = regen_owed(root)
    if owed:
        print("regeneration     {} artifact(s) OWED - run `coord regen`".format(len(owed)))
        problems += 1

    # NFR-S2: state the limit of our own control rather than implying enforcement we have
    # not established. Copilot's deny contract is unverified, so it is reported advisory.
    for name, status in sorted(HARNESS_STATUS.items()):
        print("harness {:<8} edit boundary: {}".format(name, status["edit_boundary"]))
        if status["edit_boundary"] != "enforcing":
            print("  because     {}".format(_safe(status["why"], 400)))
            print("  effect      the commit floor is the real enforcement for this harness")

    return 1 if problems else 0


PLUGIN_NAME = "coord-agent-coordination"


def cmd_plugin_emit(out_dir):
    """Write the plugin bundle BOTH harnesses read. It never installs anything.

    S14 established that Copilot CLI consumes the Claude plugin format verbatim --
    `.claude-plugin/plugin.json` plus `hooks/hooks.json` with the same matcher/hooks shape
    and the same ${CLAUDE_PLUGIN_ROOT} placeholder. One bundle therefore serves both, which
    is what made NFR-C1 cheap.

    STRIDE B9: this writes only where it is told and PRINTS what it wrote. It never edits
    ~/.copilot/settings.json or .claude/settings.json, because a layer that grants itself
    tool permissions is the elevation it exists to prevent -- the same rule `install`
    follows by printing the settings entry rather than writing it.
    """
    out = Path(out_dir)
    manifest_path = out / ".claude-plugin" / "plugin.json"
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}
        if existing.get("name") != PLUGIN_NAME:
            print("COORD-PLUGIN-FOREIGN  {} already holds a different plugin ({!r}) -"
                  " not overwritten.\n  remedy    emit to another directory"
                  .format(manifest_path, _safe(existing.get("name", "unknown"), 60)))
            return 2

    me = str(Path(__file__).resolve()).replace("\\", "/")
    manifest = {
        "name": PLUGIN_NAME,
        "description": "Refuse an edit to an artifact another session holds a lease on.",
        "version": "0.1.0",
        "author": {"name": "AI-Forward Pack"},
        "license": "MIT",
        "keywords": ["agent-coordination", "leases", "pretooluse"],
    }

    # THE COMMAND SHAPE IS LOAD-BEARING, and it was got wrong first time.
    # A live Copilot run denied EVERY tool call with "(hook errored)" and the hook script
    # never executed at all -- no output, no side effect, nothing. The bundle then emitted
    # `"C:\...\python.exe" "C:/...coord-core.py" hook`: a QUOTED EXECUTABLE.
    # The one plugin known to work on this machine (wt-agent-hooks, 55,541 invocations)
    # quotes its SCRIPT but never its interpreter:
    #     powershell -NoProfile ... -File "${CLAUDE_PLUGIN_ROOT}/hooks/send-event.ps1" ...
    # So: a bare interpreter resolved from PATH, a quoted script path, and the script
    # shipped INSIDE the bundle and addressed via ${CLAUDE_PLUGIN_ROOT} -- which also
    # means the bundle is relocatable rather than pinned to an absolute path.
    launcher = ("#!/usr/bin/env python3\n"
                '"""Launcher for the coord PreToolUse hook. Emitted by `coord plugin`.\n\n'
                "Kept minimal on purpose: the harness runs THIS, and it delegates. It exists\n"
                "because a hook command must name a bare interpreter and a quoted script\n"
                "inside the bundle -- a quoted absolute interpreter path does not execute.\n"
                '"""\n'
                "import runpy, sys\n"
                'COORD = r"{}"\n'
                'sys.argv = [COORD, "hook"]\n'
                'runpy.run_path(COORD, run_name="__main__")\n').format(me)

    hooks = {"hooks": {"PreToolUse": [{
        "matcher": ".*",
        "hooks": [{"type": "command",
                   "command": 'python "${CLAUDE_PLUGIN_ROOT}/hooks/hook.py"',
                   "timeout": 10}]}]}}

    (out / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (out / "hooks").mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
    (out / "hooks" / "hook.py").write_text(launcher, encoding="utf-8", newline="\n")
    (out / "hooks" / "hooks.json").write_text(json.dumps(hooks, indent=2) + "\n",
                                              encoding="utf-8", newline="\n")

    print("Wrote the plugin bundle to {}".format(out))
    print("  {}".format(manifest_path))
    print("  {}".format(out / "hooks" / "hooks.json"))
    print("")
    print("This tool does NOT install it. Load it yourself, per harness:")
    print("  Copilot CLI   copilot --plugin-dir \"{}\"".format(out))
    print("  Claude Code   add the entry `coord install` prints, or install as a plugin")
    print("")
    for name, status in sorted(HARNESS_STATUS.items()):
        print("  {:<8} edit boundary: {}".format(name, status["edit_boundary"]))
    print("  Copilot is advisory at the edit boundary until a live session proves a deny is")
    print("  honoured. The commit floor enforces there regardless.")
    return 0


def _print_settings_entry(repo):
    """Print the hook entry for a human to paste.

    Built with json.dumps, NOT by hand. The hand-formatted version shipped literal `{{`
    braces (from .format escaping on lines that never called .format) and an unescaped
    Windows path - output that reads correctly and is invalid the moment it is pasted.
    A serializer cannot make either mistake.
    """
    entry = {"hooks": {"PreToolUse": [{
        "matcher": "Write|Edit",
        "hooks": [{"type": "command",
                   "command": sys.executable,
                   "args": [str(Path(__file__).resolve()), "hook"],
                   "timeout": 5}]}]}}
    print("")
    print("Add this to .claude/settings.json yourself - this tool does not edit it:")
    for line in json.dumps(entry, indent=2).splitlines():
        print("  " + line)
    print("")
    print("Enforcement can be switched off by disableAllHooks, allowManagedHooksOnly, or")
    print("strictPluginOnlyCustomization. The pre-commit floor cannot.")


def main(argv=None):
    args = _build_parser().parse_args(argv)

    root, err = resolve_root(os.getcwd(), os.environ.get("COORD_ROOT"))
    if err:
        payload = {"decision": "not_checked", "path": "-"}
        payload.update(err)
        print(render(payload), file=sys.stderr)
        return 4

    session, agent = _identity()
    now = time.time()

    repo = repo_root(os.getcwd())

    if args.cmd == "hook":
        # ALWAYS exit 0: the harness reads the decision in the JSON, not the exit code.
        print(cmd_hook(root, session, agent, now, sys.stdin.read(), repo=repo))
        return 0

    if args.cmd == "guard":
        return cmd_guard(repo, args.fix)

    if args.cmd == "install":
        return cmd_install(repo, root)

    if args.cmd == "class":
        klass, reason = classify(root, args.path)
        payload = {"path": args.path, "class": klass, "code": reason,
                   "reason": ("no registry at .agents/{} - advisory, everything is"
                              " `authored`".format(REGISTRY_NAME)
                              if reason == "COORD-CLASS-UNREGISTERED"
                              else ("the registry could not be read"
                                    if reason else ""))}
        print(json.dumps(payload) if args.json else
              "{}  {}{}".format(klass, args.path,
                                "  [" + reason + "]" if reason else ""))
        return 0

    if args.cmd == "merge-derived":
        return cmd_merge_derived(root, repo, args.result, args.base,
                                 args.theirs, args.realpath)

    if args.cmd == "regen":
        code, results = cmd_regen(root, repo, args.timeout)
        for r in results:
            print("{:<10} {}  {}".format(r["status"], r["path"], r.get("detail", "")))
        if not results:
            print("nothing owed")
        return code

    if args.cmd == "doctor":
        return cmd_doctor(root, repo)

    if args.cmd == "allocate":
        print(new_id(args.scheme))
        return 0

    if args.cmd == "plugin":
        return cmd_plugin_emit(args.emit)

    if args.cmd == "merge-register":
        return cmd_merge_register(args.result, args.base, args.theirs, args.realpath)

    if args.cmd == "resolve":
        try:
            rows = _read_jsonl(args.register)
        except (OSError, json.JSONDecodeError) as exc:
            print("COORD-NOT-CHECKED-RECORD  {} is unreadable: {}".format(
                _safe(args.register, 200), exc.__class__.__name__))
            return 4
        status, result, corpus = resolve_prefix(rows, args.prefix)
        if status == "unique":
            print(result["id"])
            return 0
        if status == "ambiguous":
            print("COORD-PREFIX-AMBIGUOUS  {!r} matches {} entries in a corpus of {}:"
                  .format(args.prefix, len(result), corpus))
            for row in result:
                print("  {}  {}".format(row.get("id"), _safe(row.get("shortname", ""), 80)))
            print("  remedy    lengthen the prefix; this never picks a first match")
            return 3
        # R4: "not found" carries the corpus size, so an empty register cannot render as a
        # searched one.
        print("COORD-PREFIX-NOMATCH  {!r} matches nothing in a corpus of {} entries"
              .format(args.prefix, corpus))
        return 4

    if args.cmd == "metrics":
        return cmd_metrics(root, repo, args.json)

    # Dispatched BEFORE the identity gate: `worktree list` and `cleanup` are read/maintenance
    # commands, and refusing to tell someone what trees exist because AGENT_SESSION is unset
    # would make the orphan check unreachable exactly when it is most needed (WT10).
    if args.cmd == "worktree":
        chosen = getattr(args, "wt_session", None) or session
        return cmd_worktree(root, repo, args.action, os.getcwd(), now,
                            session=chosen, agent=agent or chosen, branch=args.branch,
                            base=args.base, remove=args.remove)

    if args.cmd == "session" and args.action == "list":
        return cmd_session_list(root, now, args.json)

    if args.cmd == "collaborate":
        return cmd_collaborate(root, repo, args.action, now, args.json)

    if args.cmd == "request":
        return cmd_request(root, args.request_action, now, session, agent, args)

    if args.cmd == "check":
        decision = check(root, args.path, session, now)
        append_decision(root, session, agent, args.path, decision)
        print(json.dumps(decision) if args.json else render(decision))
        return EXIT[decision["decision"]]

    if args.cmd == "precommit":
        if not session:
            # ADVISORY, not blocking. `check` returns 4 here and should -- you asked a
            # question and there is no identity to answer it with. But this hook runs on
            # EVERY commit in the repository, including a human's by hand and any tool's,
            # and a floor that refuses all of them is a floor that gets deleted rather
            # than adopted. Same trade as the missing-registry case (US-8), and NFR-S2
            # already concedes this is an integrity control, not a security one.
            print("advisory: AGENT_SESSION is unset, so nothing was checked."
                  "\n  set AGENT_SESSION to make this commit boundary enforcing.")
            return 0
        return cmd_precommit(root, repo, session, agent, now)

    if not session:
        print(render({"decision": "not_checked", "path": "-",
                      "code": "COORD-NOT-CHECKED-IDENTITY",
                      "reason": "AGENT_SESSION is unset"}), file=sys.stderr)
        return 4

    if args.cmd == "claim":
        decision = check(root, args.path, session, now)
        if decision["decision"] == "deny":
            append_decision(root, session, agent, args.path, decision)
            print(render(decision))
            return 3
        try:
            append_event(root, make_event("claim", session, agent, args.wi,
                                          args.path, now, args.ttl))
        except CoordError as exc:
            print("{}: {}".format(exc.code, exc), file=sys.stderr)
            return 2
        print("granted  {}  {}".format(args.path, args.wi))
        return 0

    if args.cmd == "release":
        try:
            append_event(root, make_event("release", session, agent, args.wi,
                                          args.path, now))
        except CoordError as exc:
            print("{}: {}".format(exc.code, exc), file=sys.stderr)
            return 2
        print("released {}".format(args.path))
        return 0

    if args.cmd == "session":
        return cmd_session(root, args.action, session, agent, os.getcwd(), now)

    if args.cmd == "tail":
        # tail is the HUMAN stream, so it reads BOTH stores. `check` is the machine
        # verdict, so it reads only log/. Two grains, two stores, one reader each.
        events, errors, files = read_events(root)
        events = sorted(events + read_decisions(root), key=lambda e: e.get("at", 0.0))
        if files == 0 and not events:
            print("0 files scanned - there is no record here", file=sys.stderr)
            return 4
        for event in events[-args.n:]:
            stamp = time.strftime("%H:%M:%S", time.localtime(event.get("at", 0)))
            print("{}  {:<10} {:<9} {}  {}".format(
                stamp, event.get("agent", "?"), event.get("kind", "?"),
                event.get("path", ""), event.get("wi", "")))
        for line in errors:
            print("  ! unreadable: {}".format(line), file=sys.stderr)
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
