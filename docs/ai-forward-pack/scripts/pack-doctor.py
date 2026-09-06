#!/usr/bin/env python3
"""pack-doctor.py — AI-Forward install-health check (deployable; runs in a TARGET repo).

Reports whether THIS repo has the pack installed and healthy: the installed revision, both
tool surfaces present, the managed blocks intact, and the knowledge graph valid + fresh.
One PASS/WARN/FAIL line per check with a suggested fix; exit 1 if any FAIL, or if any WARN
is present under --strict.

Distinct from tools/check-consistency.py (which validates the pack SOURCE — pack/ == docs).
A target repo has no pack/, so this checks INSTALL health, not source consistency.
Design: docs/design/pack-doctor.md. Stdlib only; composes docs-graph.py for the graph half.

Usage
  pack-doctor.py [--root <repo>] [--json] [--strict]
Exit: 0 all PASS/WARN (or all PASS under --strict) · 1 any FAIL/strict WARN.
"""
import argparse, json, os, re, sys

from bounded_process import run_bounded

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


PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def _result(name, status, detail, fix=""):
    return {"name": name, "status": status, "detail": detail, "fix": fix}


def check_installed(root):
    p = os.path.join(root, "docs", "ai-forward-pack", "INSTALL.md")
    if not os.path.exists(p):
        return _result("pack installed", FAIL,
                       "docs/ai-forward-pack/INSTALL.md not found",
                       "run /addpacktorepo (this repo has no pack installed)"), None
    with open(p, encoding="utf-8", errors="replace") as install_file:
        text = install_file.read()
    m = re.search(r"^revision:\s*(\d+)", text, re.M)
    if not m:
        return _result("pack installed", WARN, "INSTALL.md present but revision unreadable",
                       "re-run /updatepack to restamp the revision"), None
    rev = m.group(1)
    bv = re.search(r"^bundle_version:\s*'([^']+)'", text, re.M)
    detail = f"revision {rev}" + (f" ({bv.group(1)})" if bv else "")
    return _result("pack installed", PASS, detail), rev


def check_surface(root, label, subdirs):
    missing = [d for d in subdirs if not os.path.isdir(os.path.join(root, *d.split("/")))]
    surface = "Claude Code" if label == ".claude" else "Copilot"
    if not os.path.isdir(os.path.join(root, label)):
        return _result(f"{surface} surface", FAIL, f"{label}/ not present",
                       "run /updatepack (or pwsh tools/sync-pack.ps1 in the source repo)")
    if missing:
        return _result(f"{surface} surface", FAIL, f"missing: {', '.join(missing)}",
                       "run /updatepack to restore the full surface")
    return _result(f"{surface} surface", PASS, f"{label}/{{{','.join(s.split('/')[-1] for s in subdirs)}}} present")


IMPORT_RX = re.compile(r"^\s*@AGENTS\.md\s*$", re.M)
MARKER_RX = re.compile(r"AI-FORWARD-PACK:BEGIN")


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def check_claude_md_import(root):
    """CTX-B / F-01. Copilot CLI loads BOTH AGENTS.md and CLAUDE.md as custom instructions
    (measured: two ~58 KB <custom_instruction> blocks in one captured prefix), while Claude
    Code reads only CLAUDE.md and expands an `@AGENTS.md` import in place. The pack's
    byte-identical parity therefore pays the managed block twice on every Copilot request.
    The fix is structural, so the check is too: CLAUDE.md must be the import stub."""
    agents = _read(os.path.join(root, "AGENTS.md"))
    claude = _read(os.path.join(root, "CLAUDE.md"))
    if agents is None and claude is None:
        return _result("claude-md import", FAIL, "neither AGENTS.md nor CLAUDE.md present",
                       "paste the managed block into AGENTS.md and make CLAUDE.md `@AGENTS.md` (INSTALL 1.1)")
    if claude is None:
        return _result("claude-md import", WARN, "CLAUDE.md absent - Claude Code will not read AGENTS.md",
                       "create CLAUDE.md containing `@AGENTS.md` (Claude Code expands the import; INSTALL 1.1)")
    if agents is None:
        return _result("claude-md import", WARN, "AGENTS.md absent - Copilot has no instruction file",
                       "move the managed block to AGENTS.md and make CLAUDE.md `@AGENTS.md` (INSTALL 1.1)")
    if IMPORT_RX.search(claude):
        return _result("claude-md import", PASS, "CLAUDE.md imports AGENTS.md ({0:,} bytes); the block is loaded once per host".format(len(claude)))
    both_blocks = bool(MARKER_RX.search(agents)) and bool(MARKER_RX.search(claude))
    detail = "CLAUDE.md is a {0:,}-byte copy beside a {1:,}-byte AGENTS.md{2}".format(
        len(claude), len(agents), " - both carry the managed block" if both_blocks else "")
    return _result("claude-md import", WARN, detail + "; Copilot CLI loads both, so ~{0:,} est. tokens are paid twice per request (CTX-B)".format(int(len(claude) / 3.54)),
                   "replace CLAUDE.md's copy with a single `@AGENTS.md` line plus the short Claude Code addendum block (INSTALL 1.1)")


def check_copilot_settings():
    """F-09 / WT1a. `contextTier: long_context` and `effortLevel: high` as GLOBAL defaults let a
    session grow without a compaction and pay maximum reasoning on every T0 turn - the profiled
    23-hour session went 159k -> 564k tokens with zero compactions. Both are per-phase
    choices (GO19), so a global setting is reported, not assumed."""
    home = os.environ.get("COPILOT_HOME") or os.path.join(os.path.expanduser("~"), ".copilot")
    path = os.path.join(home, "settings.json")
    if not os.path.isfile(path):
        return _result("copilot settings", PASS, "no Copilot CLI settings.json on this machine (not installed, or defaults)")
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as exc:
        return _result("copilot settings", WARN, "cannot read {0}: {1}".format(path, exc), "fix the file; the check is fail-open")
    tier, effort = cfg.get("contextTier"), cfg.get("effortLevel")
    flags = []
    if tier == "long_context":
        flags.append("contextTier=long_context (never compacts; context accretes across tasks - CTX-A)")
    if effort == "high":
        flags.append("effortLevel=high as the global default (tail latency on every T0 step; per-phase per GO19)")
    if flags:
        return _result("copilot settings", WARN, "; ".join(flags),
                       "set these per session/phase (`/model`, `--effort`) rather than in ~/.copilot/settings.json; start a new session per task (WT1a)")
    return _result("copilot settings", PASS, "contextTier={0}, effortLevel={1}".format(tier or "default", effort or "default"))


def check_claude_settings(root):
    """F-12 / IO14. `showThinkingSummaries` is the richest thinking display Claude Code offers; a
    project that profiles its sessions wants it on. Project scope (.claude/settings.json) so it
    travels with the repo; the user file is reported but never edited."""
    text = _read(os.path.join(root, ".claude", "settings.json"))
    if text is None:
        return _result("claude settings", WARN, ".claude/settings.json absent",
                       "create it from adapters/hooks/claude-code.settings.hooks.json (hooks + showThinkingSummaries)")
    try:
        cfg = json.loads(text)
    except ValueError as exc:
        return _result("claude settings", WARN, "cannot parse .claude/settings.json: {0}".format(exc), "fix the JSON")
    if cfg.get("showThinkingSummaries") is True:
        return _result("claude settings", PASS, "showThinkingSummaries=true (the richest thinking display the host offers)")
    return _result("claude settings", WARN, "showThinkingSummaries not set - thinking is shown as a collapsed stub",
                   "set \"showThinkingSummaries\": true in .claude/settings.json (INSTALL 1.6); it changes the display, not the billed tokens")


def check_hooks(root):
    """F-07 / CTX-D. The re-read guard is a control only when a host runs it."""
    cop = os.path.join(root, ".github", "hooks", "ai-forward.json")
    cc = _read(os.path.join(root, ".claude", "settings.json")) or ""
    have = []
    if os.path.isfile(cop):
        have.append("Copilot (.github/hooks/ai-forward.json)")
    if "reread-guard" in cc:
        have.append("Claude Code (.claude/settings.json)")
    guard = os.path.isfile(os.path.join(root, "docs", "ai-forward-pack", "hooks", "reread-guard.py"))
    if have and guard:
        return _result("re-read guard hook", PASS, "installed for " + ", ".join(have))
    if have and not guard:
        return _result("re-read guard hook", FAIL, "hook config present but docs/ai-forward-pack/hooks/reread-guard.py is missing",
                       "copy adapters/hooks/reread-guard.py to docs/ai-forward-pack/hooks/ (INSTALL 1.5)")
    return _result("re-read guard hook", WARN, "not installed on either host",
                   "copy adapters/hooks/copilot.ai-forward-hooks.json to .github/hooks/ai-forward.json and merge adapters/hooks/claude-code.settings.hooks.json into .claude/settings.json (INSTALL 1.5)")


def check_block(root, fname):
    p = os.path.join(root, fname)
    if not os.path.exists(p):
        return _result(f"{fname} managed block", WARN, f"{fname} not present",
                       "run /updatepack to add the managed block")
    with open(p, encoding="utf-8", errors="replace") as instruction_file:
        text = instruction_file.read()
    begins = text.count("AI-FORWARD-PACK:BEGIN")
    ends = text.count("AI-FORWARD-PACK:END")
    if fname == "CLAUDE.md" and IMPORT_RX.search(text) and begins == 0:
        # The import form (INSTALL 1.1): the block lives once, in AGENTS.md; CLAUDE.md pulls it in.
        return _result(f"{fname} managed block", PASS, "import form (`@AGENTS.md`); the block is checked on AGENTS.md")
    if begins == 1 and ends == 1:
        return _result(f"{fname} managed block", PASS, "intact (1 block)")
    if begins == 0:
        return _result(f"{fname} managed block", FAIL, "no AI-FORWARD-PACK block",
                       "run /updatepack to paste the managed block")
    return _result(f"{fname} managed block", FAIL, f"{begins} begin / {ends} end markers (expected 1/1)",
                   "remove duplicate blocks; keep one BEGIN/END pair")


def check_graph(root):
    bundle = os.path.join(root, "docs", "ai-forward-pack", "scripts", "docs-graph.py")
    if not os.path.exists(bundle):
        return _result("knowledge graph", WARN, "docs-graph.py not found",
                       "run /updatepack to restore the script bundle")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        result = run_bounded(
            [sys.executable, bundle, "inventory"],
            cwd=root,
            env=env,
            timeout_seconds=30,
        )
    except Exception as e:
        return _result("knowledge graph", WARN, f"graph tool unavailable ({e})",
                       "check Python availability")
    if not getattr(result, "contained", True):
        detail = getattr(result, "containment_error", None) or "subprocess containment unavailable"
        return _result("knowledge graph", WARN, f"graph validation not run safely ({detail})",
                       "run docs-graph.py validate manually in a contained shell")
    if result.timed_out or result.limit_exceeded:
        detail = "timed out" if result.timed_out else f"exceeded {result.limit_exceeded} limit"
        return _result("knowledge graph", WARN, f"graph validation {detail}",
                       "inspect docs graph resource use")
    try:
        if result.returncode != 0:
            diagnostic = result.stderr.strip() or f"exit {result.returncode}"
            return _result(
                "knowledge graph",
                WARN,
                f"graph validation inconclusive ({diagnostic[:240]})",
                "run docs-graph.py validate manually",
            )
        info = json.loads(result.stdout)
        problems = info.get("problems", [])
        if problems:
            return _result("knowledge graph", FAIL, f"{len(problems)} graph problem(s)",
                           "run docs-graph.py validate for detail; fix frontmatter")
        n = info.get("artifacts", 0)
        if n == 0:
            return _result("knowledge graph", WARN, "no graph yet (0 artifacts)",
                           "the first skill run creates docs/docs-index.js")
        health_count = sum(len(info.get(key, [])) for key in ("stale", "flagged", "orphans"))
        if health_count:
            return _result("knowledge graph", WARN, "valid but has stale/flagged/orphan nodes",
                           "review review-by dates; run docs-graph.py freshness for detail")
        return _result("knowledge graph", PASS, "schema-valid, no dangling links, fresh")
    except Exception as exc:
        diagnostic = result.stderr.strip() or type(exc).__name__
        return _result("knowledge graph", WARN, f"graph validation inconclusive ({diagnostic[:240]})",
                       "run docs-graph.py validate manually")


def check_node_runner():
    """Report whether `npm run …` can actually resolve node on THIS machine.

    FR-055 / registered class PACK-C — *a documented command assumed portable*. The pack and
    its contributor docs say `npm run test:docs-explorer:core`. On a real Windows host that
    command printed `'node' is not recognized` while `node --version` succeeded and the
    identical test invocation run directly passed 31/31. A contributor sees a failure that
    is not a failure and may "fix" a healthy suite; CI is Linux-only so it never surfaces
    there — precisely the blind spot PACK-C describes.

    The probe is the diagnosis: node resolving *for you* proves nothing, because npm runs
    scripts through a **child shell** (cmd.exe on Windows, sh elsewhere) whose PATH can
    differ from your own. So this spawns that same shell and asks it for node — which is the
    only thing that predicts whether the documented command will work.

    Mirrors check_interpreter()'s stance for `python3`: name the working invocation for this
    machine once, here, instead of discovering it one command at a time (CI6).
    """
    def _works(argv):
        try:
            proc = run_bounded(argv, timeout_seconds=20)
        except (OSError, ValueError):
            return None
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return out.splitlines()[0] if proc.returncode == 0 and out.startswith("v") else None

    direct = _works(["node", "--version"])
    if direct is None:
        return _result("node runner", WARN,
                       "node is not on PATH; the Docs Explorer core tests cannot run here",
                       "install Node 22+ (https://nodejs.org) — the Python gates are unaffected")

    # The shell npm spawns for `npm run`, which is the actual failure point.
    if os.name == "nt":
        shell_argv = ["cmd", "/c", "node --version"]
        shell_name = "cmd.exe"
    else:
        shell_argv = ["sh", "-c", "node --version"]
        shell_name = "sh"
    via_shell = _works(shell_argv)
    if via_shell is not None:
        return _result("node runner", PASS,
                       "`npm run` resolves node here (%s); documented commands run as written"
                       % direct)

    return _result(
        "node runner", WARN,
        "node works directly (%s) but %s — the shell `npm run` spawns — cannot find it, so "
        "`npm run …` fails with \"'node' is not recognized\" even though your tests are fine."
        % (direct, shell_name),
        "run the script body directly instead, e.g. "
        "`node --test tests/docs_explorer/*.test.js`. To repair `npm run` itself, ensure the "
        "Node install directory is on the PATH the child shell inherits (on Windows, reopen "
        "the terminal after installing, or add it to the *machine* PATH and start a new "
        "session).")


def check_interpreter():
    """Report the invocation form that actually runs Python 3 on THIS machine.

    The pack documents `python3 …` because that is the POSIX-correct name and matches every
    script's shebang. It is not universally available: python.org's Windows installer ships
    `python.exe` and `py.exe` but **no `python3.exe`**, and Windows additionally provides a
    `python3` App-Execution-Alias that is not Python at all - it prints "Python was not
    found" and exits 9009. So a Windows reader copy-pasting a documented command sees what
    looks like a missing Python installation when Python is installed and working.

    This check exists so that failure is reported once, here, with the right answer, instead
    of being discovered one command at a time (continuous-improvement.md CI6 - convert the
    lesson into a control that fires at the moment of the mistake).
    """
    candidates = [("python3", ["python3", "--version"]),
                  ("python", ["python", "--version"]),
                  ("py -3", ["py", "-3", "--version"])]
    working = []
    for label, argv in candidates:
        try:
            proc = run_bounded(argv, timeout_seconds=15)
        except (OSError, ValueError):
            # Only "this command could not be launched" is an expected miss. A TypeError
            # here would be a bug in this call, and swallowing it would turn a programming
            # error into a plausible-looking FAIL - which is exactly how this check shipped
            # broken the first time.
            continue
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        if proc.returncode == 0 and out.startswith("Python 3"):
            working.append((label, out.splitlines()[0]))

    if not working:
        return _result("python interpreter", FAIL,
                       "no working Python 3 found as python3, python, or py -3",
                       "install Python 3 from python.org and re-run")

    forms = [w[0] for w in working]
    version = working[0][1]
    if "python3" in forms:
        return _result("python interpreter", PASS,
                       "`python3` works here (%s); documented commands run as written" % version)

    # Python 3 exists but not under the documented name - the Windows case.
    return _result(
        "python interpreter", WARN,
        "`python3` does not work here; use `%s` instead (%s). The pack documents `python3` "
        "because it is the POSIX name and matches the script shebangs." % (forms[0], version),
        "substitute `%s` for `python3` in documented commands. On Windows, python.org ships "
        "no python3.exe, and the `python3` you may see is a Microsoft Store alias that is not "
        "Python. Optionally disable it: Settings > Apps > Advanced app settings > App "
        "execution aliases." % forms[0])


def run(root):
    checks = [
        check_installed(root)[0],
        check_interpreter(),
        check_node_runner(),
        check_surface(root, ".claude", [".claude/knowledge", ".claude/skills", ".claude/agents"]),
        check_surface(root, ".github", [".github/instructions", ".github/prompts", ".github/agents"]),
        check_block(root, "CLAUDE.md"),
        check_block(root, "AGENTS.md"),
        check_claude_md_import(root),
        check_hooks(root),
        check_claude_settings(root),
        check_copilot_settings(),
        check_graph(root),
    ]
    return checks


def main():
    ap = argparse.ArgumentParser(description="AI-Forward install-health doctor")
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings and inconclusive checks as release-blocking failures",
    )
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    checks = run(root)
    summary = {s: sum(1 for c in checks if c["status"] == s) for s in (PASS, WARN, FAIL)}
    if args.json:
        print(json.dumps({"checks": checks, "summary": summary}, indent=2))
    else:
        print("AI-Forward doctor — install health\n")
        for c in checks:
            print(f"  {c['status']:5} {c['name']:24} {c['detail']}")
            if c["fix"] and c["status"] != PASS:
                print(f"        -> fix: {c['fix']}")
        print(f"\n  {summary[FAIL]} FAIL · {summary[WARN]} WARN · {summary[PASS]} PASS")
    return 1 if summary[FAIL] or (args.strict and summary[WARN]) else 0


if __name__ == "__main__":
    sys.exit(main())
