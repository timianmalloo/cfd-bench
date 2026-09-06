#!/usr/bin/env python3
"""pack-apply.py — apply the AI-Forward deployment map to a repo, mechanically and reversibly.

`/updatepack` and `/addpacktorepo` used to hand-apply INSTALL.md's deployment map, so every
step a person could forget - re-pasting a managed block, deleting the wrapped copy of a doc
whose load scope moved, converting CLAUDE.md to the `@AGENTS.md` import, retiring a parity
control that encoded the old invariant - was remembered or it was not. This script IS the
deployment map (INSTALL.md 1), run from the pack source against a target repo:

  pack-apply.py plan  --source <ai-forward clone> --target <repo>     # every action, no writes
  pack-apply.py apply --source <ai-forward clone> --target <repo>     # do it, idempotently

What it does, per artifact family (pack-owned names only - repo-local files are never touched):

  knowledge   -> .claude/knowledge/<name>.md verbatim; .github/instructions/<name>.instructions.md
                 (applyTo-wrapped) for load: always|glob; .github/knowledge/<name>.md for
                 load: skill|reference; the STALE copy in the other Copilot location is removed
                 (CTX-E: a doc re-scoped to on-demand must stop attaching).
  skills      -> .claude/skills/<name>/ (the whole directory: SKILL.md + reference/*.md);
                 .github/prompts/<name>.prompt.md
  agents      -> .claude/agents/ (both sets); .github/agents/<name>.agent.md (renamed, `tools:` stripped)
  bundle      -> docs/ai-forward-pack/{templates,scripts,hooks,README,OVERVIEW,research-synthesis,
                 INSTALL,context-budget.json}; .github/hooks/ai-forward.json; .claude/settings.json
                 (hooks merged, showThinkingSummaries set); .gitignore lines; docs/index.html only if
                 absent; docs/docs-index.js NEVER (V10)
  front doors -> AGENTS.md: the managed block replaced wholesale between markers (appended if absent).
                 CLAUDE.md: converted to `@AGENTS.md` + the addendum block (CTX-B); the old file is
                 backed up under docs/ai-forward-pack/retired/, and every paragraph that is NOT in
                 AGENTS.md (after toolchain-path normalisation) is kept above the addendum.
  controls    -> a repo-local parity test that asserts CLAUDE.md carries the standing-method block
                 (the OLD invariant) is rewritten into a shim asserting the NEW invariant through
                 pack-doctor, its other assertions carried over where they can be read; the original
                 is backed up beside the CLAUDE.md backup.

Repo-local deviations are honoured, not reverted: a destination that differs from the version the
repo received at its installed revision is three-way merged (`git merge-file`) against the pack's
old and new text; a clean merge lands as MERGE, a conflicting one is left untouched with the new
pack text written under docs/ai-forward-pack/conflicts/ and reported as CONFLICT for the skill to
reconcile. The installed revision advances only in `apply`. Re-running is a no-op.

Python 3.8+, stdlib only. Exit 0 = applied/clean, 1 = conflicts or errors reported, 2 = usage.
"""
import argparse
import datetime as _dt
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

MANIFEST = "FOUNDATION.md"
BEGIN = "<!-- AI-FORWARD-PACK:BEGIN"
END = "<!-- AI-FORWARD-PACK:END -->"
IMPORT_LINE = "@AGENTS.md"
GITIGNORE_LINES = ["*.jsonl.lock", "spikes/", "docs/audit/.run-starts.json", "docs/audit/.run-starts.json.tmp"]
PROTECTED = {"docs/docs-index.js"}
PATH_NORMALISERS = [
    (re.compile(r"\.github/instructions/([\w.-]+?)\.instructions\.md"), r"<doc:\1>"),
    (re.compile(r"\.claude/knowledge/([\w.-]+?)\.md"), r"<doc:\1>"),
    (re.compile(r"\.github/knowledge/([\w.-]+?)\.md"), r"<doc:\1>"),
    (re.compile(r"\.github/prompts/([\w-]+?)\.prompt\.md"), r"<skill:\1>"),
    (re.compile(r"\.claude/skills/([\w-]+?)/SKILL\.md"), r"<skill:\1>"),
    (re.compile(r"\.github/agents/"), "<agents>/"),
    (re.compile(r"\.claude/agents/"), "<agents>/"),
    (re.compile(r"\.github/instructions/"), "<docs>/"),
    (re.compile(r"\.claude/knowledge/"), "<docs>/"),
]


# --------------------------------------------------------------------------- io helpers
def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace", newline="") as fh:
            return fh.read()
    except OSError:
        return None


def norm_nl(text):
    return text.replace("\r\n", "\n").replace("\r", "\n") if text is not None else None


def same(a, b):
    """Equal after newline normalisation and a stripped BOM - a CRLF checkout is not a drift."""
    if a is None or b is None:
        return a is b
    return norm_nl(a).lstrip("﻿").rstrip() == norm_nl(b).lstrip("﻿").rstrip()


def frontmatter(text):
    m = re.match(r"^﻿?---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        kv = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if kv:
            val = kv.group(2).strip()
            meta[kv.group(1)] = val.strip('"').strip("'") if not val.startswith("[") else val
    return meta, text[m.end():]


def git(args, cwd):
    try:
        p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


# --------------------------------------------------------------------------- the applier
class Applier(object):
    def __init__(self, source, target, dry, project=None, install=False, force=False, baselines=True):
        self.source = os.path.abspath(source)
        self.pack = os.path.join(self.source, "pack")
        self.target = os.path.abspath(target)
        self.dry = dry
        self.project = project
        self.install = install
        self.force = force
        self.baselines = baselines
        self.rows = []
        self.old_pack_sha = None
        self.source_rev, self.source_meta = self._source_revision()
        self.target_rev = self._target_revision()

    # ---- bookkeeping
    def row(self, area, path, action, status="ok", note=""):
        self.rows.append({"area": area, "path": path.replace("\\", "/"), "action": action, "status": status, "note": note})

    def rel(self, path):
        return os.path.relpath(path, self.target).replace("\\", "/")

    def _source_revision(self):
        text = read(os.path.join(self.pack, "adapters", "INSTALL.md")) or ""
        meta, _ = frontmatter(text)
        rev = re.search(r"^revision:\s*(\d+)", text, re.M)
        return (int(rev.group(1)) if rev else None), meta

    def _target_revision(self):
        text = read(os.path.join(self.target, "docs", "ai-forward-pack", "INSTALL.md"))
        if text is None:
            return None
        rev = re.search(r"^revision:\s*(\d+)", text, re.M)
        return int(rev.group(1)) if rev else None

    def _old_pack_text(self, rel):
        """The pack file as it was at the target's installed revision, from the source's history.
        None when unresolvable (no git, revision unknown, file did not exist) - then no merge base."""
        if self.target_rev is None or self.target_rev == self.source_rev:
            return None
        if self.old_pack_sha is None:
            rc, out = git(["log", "--format=%H", "-S", "revision: {0}".format(self.target_rev), "--",
                           "pack/adapters/INSTALL.md"], self.source)
            shas = out.split()
            self.old_pack_sha = shas[-1] if rc == 0 and shas else ""
        if not self.old_pack_sha:
            return None
        rc, out = git(["show", "{0}:pack/{1}".format(self.old_pack_sha, rel.replace("\\", "/"))], self.source)
        return out if rc == 0 else None

    # ---- primitive writes
    def _write(self, dest, text):
        if self.dry:
            return
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(norm_nl(text))

    def _remove(self, dest):
        if self.dry:
            return
        try:
            os.remove(dest)
        except OSError:
            pass

    def place(self, area, rel_src, dest, text, transform_note=""):
        """Land `text` at dest, honouring a repo-local deviation with a three-way merge."""
        drel = self.rel(dest)
        if drel in PROTECTED:
            self.row(area, drel, "SKIP", "ok", "protected (V10)")
            return
        current = read(dest)
        if current is None:
            self._write(dest, text)
            self.row(area, drel, "ADD", "ok", transform_note)
            return
        if same(current, text):
            self.row(area, drel, "UNCHANGED", "ok")
            return
        old = self._old_pack_text(rel_src) if rel_src else None
        if old is not None and same(current, self._transform_like(rel_src, old, dest)):
            self._write(dest, text)  # the repo had the pack's old text verbatim: a plain update
            self.row(area, drel, "UPDATE", "ok", transform_note)
            return
        if old is None and self.target_rev == self.source_rev:
            # same revision, different text: a repo-local deviation over an unchanged pack file - keep it
            self.row(area, drel, "KEEP", "ok", "repo-local deviation over an unchanged pack file")
            return
        base = self._transform_like(rel_src, old, dest) if old is not None else None
        merged = self._merge(current, base, text) if base is not None else None
        if merged is not None:
            self._write(dest, merged)
            self.row(area, drel, "MERGE", "ok", "repo-local deviation carried over (three-way merge)")
            return
        # conflict or no merge base: leave the file, park the new text, report
        park = os.path.join(self.target, "docs", "ai-forward-pack", "conflicts", drel)
        self._write(park, text)
        self.row(area, drel, "CONFLICT", "fail",
                 "repo-local changes could not be merged; new pack text at " + self.rel(park) + " - reconcile, then delete it")

    def _transform_like(self, rel_src, old_text, dest):
        """Apply the same deploy transform to the old pack text that `text` received (wrap / strip)."""
        drel = self.rel(dest)
        if drel.startswith(".github/instructions/") and not drel.endswith(MANIFEST):
            meta, body = frontmatter(old_text)
            pattern = "**" if meta.get("load", "always") == "always" else meta.get("applyTo", "**")
            return '---\napplyTo: "{0}"\n---\n'.format(pattern) + body
        if drel.startswith(".github/agents/"):
            return strip_tools(old_text)
        return old_text

    @staticmethod
    def _merge(current, base, new):
        """git merge-file current base new; returns merged text or None on conflict."""
        tmp = tempfile.mkdtemp()
        try:
            paths = []
            for name, text in (("current", current), ("base", base), ("new", new)):
                p = os.path.join(tmp, name)
                with open(p, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(norm_nl(text))
                paths.append(p)
            rc, out = git(["merge-file", "-p", "-L", "repo", "-L", "pack@installed", "-L", "pack@source"] + paths, tmp)
            if rc == 0:
                return out
            return None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---- families
    def knowledge(self):
        kdir = os.path.join(self.pack, "knowledge")
        names = sorted(n for n in os.listdir(kdir) if n.endswith(".md"))
        inst = os.path.join(self.target, ".github", "instructions")
        know = os.path.join(self.target, ".github", "knowledge")
        cc = os.path.join(self.target, ".claude", "knowledge")
        for name in names:
            src = os.path.join(kdir, name)
            text = read(src)
            stem = name[:-3]
            self.place("knowledge", "knowledge/" + name, os.path.join(cc, name), text)
            if name == MANIFEST:
                self.place("knowledge", "knowledge/" + name, os.path.join(inst, name), text)
                continue
            meta, body = frontmatter(text)
            load = meta.get("load", "")
            if load in ("always", "glob"):
                pattern = "**" if load == "always" else meta.get("applyTo", "")
                wrapped = '---\napplyTo: "{0}"\n---\n'.format(pattern) + body
                self.place("knowledge", "knowledge/" + name, os.path.join(inst, stem + ".instructions.md"), wrapped, "wrapped applyTo")
                stale = os.path.join(know, name)
            elif load in ("skill", "reference"):
                self.place("knowledge", "knowledge/" + name, os.path.join(know, name), text)
                stale = os.path.join(inst, stem + ".instructions.md")
            else:
                self.row("knowledge", "pack/knowledge/" + name, "ERROR", "fail", "no load: scope declared")
                continue
            if os.path.isfile(stale):
                self._remove(stale)
                self.row("knowledge", self.rel(stale), "REMOVE", "ok", "stale copy: the doc's load scope moved (CTX-E)")

    def skills(self):
        cdir = os.path.join(self.pack, "commands")
        pdir = os.path.join(self.pack, "adapters", "copilot", "prompts")
        for name in sorted(os.listdir(cdir)):
            sdir = os.path.join(cdir, name)
            if not os.path.isfile(os.path.join(sdir, "SKILL.md")):
                continue
            for base, _dirs, files in os.walk(sdir):
                for f in sorted(files):
                    src = os.path.join(base, f)
                    rel_in_skill = os.path.relpath(src, sdir)
                    dest = os.path.join(self.target, ".claude", "skills", name, rel_in_skill)
                    self.place("skills", "commands/{0}/{1}".format(name, rel_in_skill.replace("\\", "/")), dest, read(src))
            prompt = os.path.join(pdir, name + ".prompt.md")
            if os.path.isfile(prompt):
                self.place("skills", "adapters/copilot/prompts/{0}.prompt.md".format(name),
                           os.path.join(self.target, ".github", "prompts", name + ".prompt.md"), read(prompt))

    def agents(self):
        cc = os.path.join(self.pack, "adapters", "claude-code", "agents")
        cop = os.path.join(self.pack, "adapters", "copilot", "agents")
        for name in sorted(os.listdir(cc)):
            if name.endswith(".md"):
                text = read(os.path.join(cc, name))
                self.place("agents", "adapters/claude-code/agents/" + name, os.path.join(self.target, ".claude", "agents", name), text)
                self.place("agents", "adapters/claude-code/agents/" + name,
                           os.path.join(self.target, ".github", "agents", name[:-3] + ".agent.md"), strip_tools(text), "tools: stripped")
        for name in sorted(os.listdir(cop)):
            if name.endswith("_agent.md"):
                text = read(os.path.join(cop, name))
                self.place("agents", "adapters/copilot/agents/" + name, os.path.join(self.target, ".claude", "agents", name), text)
                self.place("agents", "adapters/copilot/agents/" + name,
                           os.path.join(self.target, ".github", "agents", name[:-len("_agent.md")] + ".agent.md"), text, "renamed .agent.md")

    def bundle(self):
        dp = os.path.join(self.target, "docs", "ai-forward-pack")
        for sub in ("templates", "scripts"):
            src_dir = os.path.join(self.pack, sub)
            for base, _dirs, files in os.walk(src_dir):
                if "__pycache__" in base:
                    continue
                for f in sorted(files):
                    if f.endswith(".pyc"):
                        continue
                    src = os.path.join(base, f)
                    rel = os.path.relpath(src, src_dir)
                    self.place("bundle", "{0}/{1}".format(sub, rel.replace("\\", "/")), os.path.join(dp, sub, rel), read(src))
        for f in ("README.md", "OVERVIEW.md", "research-synthesis.md", "context-budget.json"):
            self.place("bundle", f, os.path.join(dp, f), read(os.path.join(self.pack, f)))
        hooks = os.path.join(self.pack, "adapters", "hooks")
        for f in ("reread-guard.py", "README.md"):
            self.place("hooks", "adapters/hooks/" + f, os.path.join(dp, "hooks", f), read(os.path.join(hooks, f)))
        self.place("hooks", "adapters/hooks/copilot.ai-forward-hooks.json",
                   os.path.join(self.target, ".github", "hooks", "ai-forward.json"), read(os.path.join(hooks, "copilot.ai-forward-hooks.json")))
        self._settings(read(os.path.join(hooks, "claude-code.settings.hooks.json")))
        self._gitignore()
        explorer = os.path.join(self.target, "docs", "index.html")
        if not os.path.isfile(explorer):
            tpl = read(os.path.join(self.pack, "templates", "docs-explorer.template.html")) or ""
            self._write(explorer, tpl.replace("__PROJECT__", self.project or os.path.basename(self.target)))
            self.row("bundle", "docs/index.html", "ADD", "ok", "Docs Explorer instantiated (one-time)")
        else:
            self.row("bundle", "docs/index.html", "SKIP", "ok", "exists - never overwritten")
        self.row("bundle", "docs/docs-index.js", "SKIP", "ok", "never created or overwritten (V10)")

    def _settings(self, snippet_text):
        dest = os.path.join(self.target, ".claude", "settings.json")
        try:
            snippet = json.loads(snippet_text or "{}")
        except ValueError:
            self.row("hooks", ".claude/settings.json", "ERROR", "fail", "pack snippet is not valid JSON")
            return
        current_text = read(dest)
        try:
            current = json.loads(current_text) if current_text else {}
        except ValueError:
            self.row("hooks", ".claude/settings.json", "CONFLICT", "fail", "existing settings.json is not valid JSON - merge by hand")
            return
        merged = json.loads(json.dumps(current))
        hooks = merged.setdefault("hooks", {})
        for event, entries in (snippet.get("hooks") or {}).items():
            have = hooks.setdefault(event, [])
            for entry in entries:
                wanted = {h.get("command") for h in entry.get("hooks", [])}
                if not any(wanted & {h.get("command") for h in e.get("hooks", [])} for e in have):
                    have.append(entry)
        for k, v in snippet.items():
            if k != "hooks" and k not in merged:
                merged[k] = v
        if merged == current:
            self.row("hooks", ".claude/settings.json", "UNCHANGED", "ok")
            return
        self._write(dest, json.dumps(merged, indent=2) + "\n")
        self.row("hooks", ".claude/settings.json", "ADD" if current_text is None else "MERGE", "ok",
                 "hooks + showThinkingSummaries merged; other keys untouched")

    def _gitignore(self):
        dest = os.path.join(self.target, ".gitignore")
        current = read(dest) or ""
        have = {l.strip() for l in norm_nl(current).splitlines()}
        missing = [l for l in GITIGNORE_LINES if l not in have]
        if not missing:
            self.row("bundle", ".gitignore", "UNCHANGED", "ok")
            return
        text = norm_nl(current)
        if text and not text.endswith("\n"):
            text += "\n"
        text += "\n# AI-Forward Pack (INSTALL 2): local coordination and per-run state, never committed\n" + "\n".join(missing) + "\n"
        self._write(dest, text)
        self.row("bundle", ".gitignore", "UPDATE", "ok", "added " + ", ".join(missing))

    # ---- front doors
    def front_doors(self):
        agents_block = read(os.path.join(self.pack, "adapters", "managed-blocks", "AGENTS.block.md"))
        claude_block = read(os.path.join(self.pack, "adapters", "managed-blocks", "CLAUDE.block.md"))
        agents_path = os.path.join(self.target, "AGENTS.md")
        claude_path = os.path.join(self.target, "CLAUDE.md")
        agents = read(agents_path)
        claude = read(claude_path)
        # AGENTS.md: replace the block wholesale (append if absent); create the file if missing.
        if agents is None:
            starter = "# {0}\n\nProject conventions live here. The AI-Forward Pack's reasoning stack is wired in below.\n\n".format(
                self.project or os.path.basename(self.target))
            self._write(agents_path, starter + agents_block)
            self.row("front-doors", "AGENTS.md", "ADD", "ok", "created with the managed block")
            agents = starter + agents_block
        else:
            new_agents = replace_block(agents, agents_block)
            if same(new_agents, agents):
                self.row("front-doors", "AGENTS.md", "UNCHANGED", "ok")
            else:
                self._write(agents_path, new_agents)
                self.row("front-doors", "AGENTS.md", "UPDATE", "ok", "managed block re-pasted wholesale")
            agents = new_agents
        # CLAUDE.md: the import form.
        if claude is None:
            self._write(claude_path, "# CLAUDE.md\n\n" + IMPORT_LINE + "\n\n" + claude_block)
            self.row("front-doors", "CLAUDE.md", "ADD", "ok", "@AGENTS.md import + addendum")
            return
        if re.search(r"^\s*@AGENTS\.md\s*$", claude, re.M):
            new_claude = replace_block(claude, claude_block)
            if same(new_claude, claude):
                self.row("front-doors", "CLAUDE.md", "UNCHANGED", "ok", "import form")
            else:
                self._write(claude_path, new_claude)
                self.row("front-doors", "CLAUDE.md", "UPDATE", "ok", "addendum block re-pasted")
            return
        # A copy-style CLAUDE.md: back it up, keep what is unique, convert.
        backup = os.path.join(self.target, "docs", "ai-forward-pack", "retired",
                              "CLAUDE.md.rev{0}.md".format(self.target_rev if self.target_rev is not None else "pre"))
        self._write(backup, claude)
        unique = unique_paragraphs(claude, agents)
        kept = ""
        if unique:
            kept = ("<!-- retained from the previous CLAUDE.md on {0}: these paragraphs were not in AGENTS.md. Move them into AGENTS.md above its managed block (both hosts read it) and delete them here. -->\n\n".format(_dt.date.today().isoformat())
                    + "\n\n".join(unique) + "\n\n")
        new_claude = "# CLAUDE.md\n\n" + IMPORT_LINE + "\n\n" + kept + claude_block
        self._write(claude_path, new_claude)
        self.row("front-doors", "CLAUDE.md", "CONVERT", "ok",
                 "now @AGENTS.md + addendum (CTX-B); previous file backed up at {0}; {1} repo-local paragraph(s) retained above the addendum".format(
                     self.rel(backup), len(unique)))
        self._retire_parity_controls(backup)

    def _retire_parity_controls(self, backup_dir_hint):
        """A repo-local control that asserts CLAUDE.md carries the standing-method block encodes
        the invariant this conversion retires. It is rewritten into a shim that asserts the NEW
        invariant via pack-doctor and carries over the assertions that do not depend on CLAUDE.md;
        the original is backed up. Only PowerShell/Python files outside the pack's own directories
        are considered, and only when their text names CLAUDE.md together with a parity marker."""
        skip = (".git", "node_modules", "docs/ai-forward-pack", ".claude", ".github/instructions", ".github/knowledge")
        for base, dirs, files in os.walk(self.target):
            rel_base = self.rel(base)
            if any(rel_base == s or rel_base.startswith(s + "/") for s in skip):
                dirs[:] = []
                continue
            for f in files:
                if not f.endswith((".ps1", ".py", ".sh")):
                    continue
                path = os.path.join(base, f)
                text = read(path) or ""
                if "CLAUDE.md" not in text or not re.search(r"standing-method|parity", text, re.I):
                    continue
                if "pack-apply shim" in text:
                    self.row("controls", self.rel(path), "UNCHANGED", "ok", "already the new-invariant shim")
                    continue
                if not f.endswith(".ps1"):
                    self.row("controls", self.rel(path), "REVIEW", "fail",
                             "asserts the old CLAUDE.md/AGENTS.md parity; not rewritten automatically (not PowerShell) - update it to the import invariant")
                    continue
                bak = os.path.join(self.target, "docs", "ai-forward-pack", "retired", f)
                self._write(bak, text)
                self._write(path, parity_shim(text, self.rel(bak)))
                self.row("controls", self.rel(path), "REWRITE", "ok",
                         "old parity invariant retired: now asserts CLAUDE.md = @AGENTS.md + addendum via pack-doctor; original at " + self.rel(bak))

    # ---- finish
    def advance(self):
        dest = os.path.join(self.target, "docs", "ai-forward-pack", "INSTALL.md")
        text = read(os.path.join(self.pack, "adapters", "INSTALL.md"))
        if same(read(dest), text):
            self.row("meta", "docs/ai-forward-pack/INSTALL.md", "UNCHANGED", "ok", "revision {0}".format(self.source_rev))
        else:
            self._write(dest, text)
            self.row("meta", "docs/ai-forward-pack/INSTALL.md", "UPDATE", "ok",
                     "revision {0} -> {1}".format(self.target_rev, self.source_rev))

    def run_baselines(self):
        if self.dry or not self.baselines:
            self.row("meta", "context-budget baselines", "SKIP", "ok", "plan mode" if self.dry else "--no-baselines")
            return
        script = os.path.join(self.target, "docs", "ai-forward-pack", "scripts", "context-budget.py")
        for args in (["gate", "--update-baseline"], ["prefix", "--update-baseline"], ["skills", "--update-baseline"]):
            try:
                p = subprocess.run([sys.executable, script] + args, cwd=self.target, capture_output=True, text=True, timeout=120)
                self.row("meta", "context-budget {0}".format(args[0]), "BASELINE", "ok" if p.returncode == 0 else "fail",
                         (p.stdout.strip().splitlines() or [""])[-1][:120])
            except (OSError, subprocess.SubprocessError) as exc:
                self.row("meta", "context-budget {0}".format(args[0]), "BASELINE", "fail", str(exc)[:120])

    def run(self):
        if self.source_rev is None:
            self.row("meta", "pack/adapters/INSTALL.md", "ERROR", "fail", "source revision unreadable - is --source an ai-forward clone?")
            return self.rows
        if self.target_rev is None and not self.install:
            self.row("meta", "docs/ai-forward-pack/INSTALL.md", "ERROR", "fail",
                     "no installed pack found; pass --install for a fresh install (/addpacktorepo)")
            return self.rows
        if self.target_rev is not None and self.target_rev > self.source_rev:
            self.row("meta", "revision", "ERROR", "fail",
                     "target is at revision {0}, ahead of the source {1} - refusing".format(self.target_rev, self.source_rev))
            return self.rows
        if self.target_rev == self.source_rev and not self.force:
            self.row("meta", "revision", "UNCHANGED", "ok", "already at revision {0} (use --force to re-apply)".format(self.source_rev))
        self.knowledge()
        self.skills()
        self.agents()
        self.bundle()
        self.front_doors()
        self.advance()
        self.run_baselines()
        return self.rows


# --------------------------------------------------------------------------- pure helpers
def strip_tools(text):
    """Drop the frontmatter `tools:` line and its indented continuation (INSTALL 1.2)."""
    out, in_tools = [], False
    for line in norm_nl(text).split("\n"):
        if re.match(r"^tools:", line):
            in_tools = True
            continue
        if in_tools and re.match(r"^\s+\S", line):
            continue
        in_tools = False
        out.append(line)
    return "\n".join(out)


def replace_block(text, block):
    """Replace the AI-FORWARD-PACK region wholesale (markers included); append if absent. The
    blank line that separated the block from what follows is preserved."""
    text = norm_nl(text)
    block = norm_nl(block).rstrip(chr(10)) + chr(10)
    b = text.find(BEGIN)
    e = text.find(END)
    if b >= 0 and e > b:
        rest = text[e + len(END):]
        rest = (chr(10) + rest.lstrip(chr(10))) if rest.strip() else ''
        return text[:b] + block + rest
    return text.rstrip(chr(10)) + chr(10) + chr(10) + block

def normalise(text):
    for rx, rep in PATH_NORMALISERS:
        text = rx.sub(rep, text)
    return re.sub(r"\s+", " ", text).strip()


def _outside_block(text):
    text = norm_nl(text)
    b = text.find(BEGIN)
    e = text.find(END)
    if b >= 0 and e > b:
        return text[:b] + "\n\n" + text[e + len(END):]
    return text


def unique_paragraphs(claude, agents):
    """Paragraphs of CLAUDE.md (outside the managed block) with no counterpart in AGENTS.md after
    toolchain-path normalisation; the title line and the import line are never 'unique'."""
    have = {normalise(p) for p in re.split(r"\n\s*\n", _outside_block(agents)) if p.strip()}
    out = []
    for p in re.split(r"\n\s*\n", _outside_block(claude)):
        if not p.strip():
            continue
        n = normalise(p)
        if n in have or re.match(r"^#\s*CLAUDE\.md\s*$", p.strip()) or p.strip() == IMPORT_LINE:
            continue
        out.append(p.strip("\n"))
    return out


def parity_shim(original, backup_rel):
    """A PowerShell shim asserting the import invariant through pack-doctor, carrying over the
    original's skill-surface needles and required-phrase checks where they can be read."""
    needles = re.findall(r"Path\s*=\s*'([^']+)'\s*;\s*Needle\s*=\s*'([^']+)'", original)
    phrases = []
    m = re.search(r"foreach\s*\(\$required\s+in\s+([^)]+)\)", original)
    if m:
        phrases = [p.replace("''", "'") for p in re.findall(r"'((?:[^']|'')*)'", m.group(1))]
    lines = [
        "#requires -Version 7.0",
        "<#",
        ".SYNOPSIS",
        "    pack-apply shim: the front doors are checked for the IMPORT invariant (CLAUDE.md = `@AGENTS.md` + the",
        "    Claude Code addendum), not for a duplicated standing-method block.",
        ".DESCRIPTION",
        "    Rewritten by pack-apply.py when CLAUDE.md was converted (AI-Forward revision 60+, class CTX-B): Copilot",
        "    CLI loads AGENTS.md and CLAUDE.md both, so a byte-identical copy paid the block twice per request;",
        "    Claude Code expands the @AGENTS.md import in place. Parity is now by construction. The original",
        "    control is preserved at " + backup_rel + ". Assertions that did not depend on CLAUDE.md carrying",
        "    the block were carried over below.",
        "#>",
        "[CmdletBinding()]",
        "param([string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot))",
        "Set-StrictMode -Version Latest",
        "$ErrorActionPreference = 'Stop'",
        "$script:failures = 0",
        "function Assert-True { param([Parameter(Mandatory)][bool]$Condition, [Parameter(Mandatory)][string]$Message)",
        "    if ($Condition) { Write-Host \"  PASS $Message\" } else { Write-Host \"  FAIL $Message\" -ForegroundColor Red; $script:failures++ } }",
        "",
        "$claude = Get-Content -LiteralPath (Join-Path $RepositoryRoot 'CLAUDE.md') -Raw",
        "$agents = Get-Content -LiteralPath (Join-Path $RepositoryRoot 'AGENTS.md') -Raw",
        "Assert-True ($claude -match '(?m)^\\s*@AGENTS\\.md\\s*$') 'CLAUDE.md imports AGENTS.md (the one instruction set for every harness).'",
        "Assert-True (($agents -split 'AI-FORWARD-PACK:BEGIN').Count -eq 2) 'AGENTS.md carries exactly one managed block.'",
        "Assert-True (($claude -split 'STANDING-METHOD:BEGIN').Count -le 1) 'CLAUDE.md no longer duplicates the standing-method block.'",
        "if ($agents -match 'STANDING-METHOD:BEGIN') {",
        "    Assert-True (($agents -split 'STANDING-METHOD:BEGIN').Count -eq 2) 'AGENTS.md carries exactly one standing-method block.'",
        "}",
        "$py = if (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { 'python3' }",
        "$doctor = Join-Path $RepositoryRoot 'docs/ai-forward-pack/scripts/pack-doctor.py'",
        "if (Test-Path -LiteralPath $doctor) {",
        "    $report = & $py $doctor --root $RepositoryRoot --json | ConvertFrom-Json",
        "    $imp = $report.checks | Where-Object { $_.name -eq 'claude-md import' }",
        "    Assert-True ($null -ne $imp -and $imp.status -eq 'PASS') \"pack-doctor: claude-md import ($($imp.detail))\"",
        "}",
    ]
    if phrases:
        lines.append("$block = $agents")
        lines.append("foreach ($required in " + ", ".join("'" + p.replace("'", "''") + "'" for p in phrases) + ") {")
        lines.append("    Assert-True ($block.Contains($required)) \"AGENTS.md states '$required'.\"")
        lines.append("}")
    if needles:
        lines.append("$surfaces = @(")
        for path, needle in needles:
            lines.append("    @{ Path = '" + path + "'; Needle = '" + needle.replace("'", "''") + "' }")
        lines.append(")")
        lines.append("foreach ($surface in $surfaces) {")
        lines.append("    $full = Join-Path $RepositoryRoot $surface.Path")
        lines.append("    $present = (Test-Path -LiteralPath $full) -and ((Get-Content -LiteralPath $full -Raw).Contains($surface.Needle))")
        lines.append("    Assert-True $present \"$($surface.Path) carries '$($surface.Needle)'.\"")
        lines.append("}")
    lines += [
        "if ($script:failures -gt 0) { Write-Host \"Front-door invariant FAILED: $script:failures assertion(s).\" -ForegroundColor Red; exit 1 }",
        "Write-Host 'Front-door invariant passed: CLAUDE.md imports AGENTS.md; the standing method lives once.'",
        "exit 0",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- report
def render_table(rows):
    out = ["| Area | Artifact | Action | Status | Note |", "|---|---|---|---|---|"]
    for r in rows:
        out.append("| {0} | `{1}` | {2} | {3} | {4} |".format(r["area"], r["path"], r["action"],
                                                             "OK" if r["status"] == "ok" else "FAIL", r["note"].replace("|", "/")))
    return "\n".join(out)


def summarize(rows):
    counts = {}
    for r in rows:
        counts[r["action"]] = counts.get(r["action"], 0) + 1
    return ", ".join("{0} {1}".format(v, k) for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pack-apply.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    for name in ("plan", "apply"):
        p = sub.add_parser(name, help="every action, no writes" if name == "plan" else "apply the map idempotently")
        p.add_argument("--source", required=True, help="an ai-forward clone (holds pack/)")
        p.add_argument("--target", default=os.getcwd(), help="the repo to update (default: cwd)")
        p.add_argument("--project", help="project name for docs/index.html on a fresh install")
        p.add_argument("--install", action="store_true", help="fresh install: allow a target with no installed pack")
        p.add_argument("--force", action="store_true", help="re-apply even when the revisions match")
        p.add_argument("--no-baselines", action="store_true", help="do not run context-budget --update-baseline after applying")
        p.add_argument("--json", action="store_true", help="emit the action rows as JSON")
        p.add_argument("--quiet", action="store_true", help="only the UNCHANGED rows are hidden")
    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 2
    if not os.path.isfile(os.path.join(args.source, "pack", "adapters", "INSTALL.md")):
        print("pack-apply: --source must be an ai-forward clone containing pack/adapters/INSTALL.md", file=sys.stderr)
        return 2
    app = Applier(args.source, args.target, dry=(args.cmd == "plan"), project=args.project, install=args.install,
                  force=args.force, baselines=not args.no_baselines)
    rows = app.run()
    if args.json:
        print(json.dumps({"mode": args.cmd, "source_revision": app.source_rev, "target_revision": app.target_rev, "rows": rows}, indent=2))
    else:
        shown = [r for r in rows if not (args.quiet and r["action"] == "UNCHANGED")]
        print("pack-apply {0}: source revision {1}, target revision {2}{3}".format(
            args.cmd, app.source_rev, app.target_rev, "" if args.cmd == "apply" else " (no writes)"))
        print(render_table(shown))
        print("\n" + summarize(rows))
    return 1 if any(r["status"] == "fail" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
