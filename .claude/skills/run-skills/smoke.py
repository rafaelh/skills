#!/usr/bin/env python3
"""Smoke-drive every agent tool this marketplace ships.

The "app" here is the bundled scripts under skills/*/scripts/. This launches
each one for real and asserts the interface contract holds, then dogfoods the
repo's own validators against every published skill (`skills/*/` and the skills
inside `plugins/*/`), checks the marketplace agrees with what is on disk, and
holds each plugin bundle to its contents, references, overlap and version rules.

The validators always come from this script's own checkout; `--repo` only picks
which repo is checked, so tests can aim the sweep at a small fixture.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import functools
import json
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import cast

TOOLS = Path(__file__).resolve().parents[3]
TS_DIR = TOOLS / "skills" / "skill-audit-ts"
TSX = TS_DIR / "node_modules" / ".bin" / "tsx"
PY_VALIDATOR = TOOLS / "skills" / "skill-audit" / "scripts" / "validate_skill.py"
TS_VALIDATOR = TS_DIR / "scripts" / "validate_skill.ts"
AGENT_VALIDATOR = TOOLS / "skills" / "create-agents-for-repo" / "scripts" / "validate_agent_def.py"
OVERLAP = TOOLS / "skills" / "skill-audit" / "scripts" / "detect_skill_overlap.py"

GROUPS = ("python", "ts", "parity", "manifests", "bundle")
# What each group shells out to; `tsx` stands for the skill-audit-ts install, not a PATH binary.
NEEDS = {
    "python": ("uv",),
    "ts": ("uv", "node", "tsx"),
    "parity": ("uv", "node", "tsx"),
    "manifests": ("uv",),
    "bundle": ("uv", "claude", "git"),
    # Not a group: `--tests` runs pytest and then vitest through the skill-audit-ts install.
    "tests": ("uv", "node", "npm", "tsx"),
}
OVERLAP_THRESHOLD = 0.5
# A bundle ships skills and agents only; any of these in plugin.json or the marketplace entry
# would add a second inventory (or a component) that the bundle directory does not show.
COMPONENT_KEYS = {
    "skills",
    "agents",
    "commands",
    "hooks",
    "mcpServers",
    "lspServers",
    "outputStyles",
}
BUNDLE_TOP_LEVEL = {".claude-plugin", "skills", "agents"}
# Built into Claude Code, so a bundle skill may tell the user to type them without shipping them.
BUILTIN_COMMANDS = {"/simplify", "/clear", "/code-review"}
SLASH_COMMAND = re.compile(r"^/[a-z][a-z0-9-]*(:[a-z0-9-]+)?$")
QUALIFIED_NAME = re.compile(r"^[a-z0-9-]+:[a-z0-9-]+$")
BARE_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
BACKTICKED = re.compile(r"`([^`\n]+)`")
AGENT_WORDS = {"agent", "agents", "subagent", "subagents"}

# Not agent tools: shared library modules and test helpers the validators skip.
# Files carrying the `# agent-tool: false` marker are excluded too — see is_library().
NOT_TOOLS = {"agents_lib.py", "skill_lib.py", "skill_lib.ts", "test-helpers.ts"}

TIMEOUT = 120


Check = dict[str, object]


@dataclass
class Result:
    checks: list[Check] = field(default_factory=list[Check])

    def add(self, name: str, ok: bool, detail: str = "", **extra: object) -> None:
        self.checks.append({"check": name, "ok": ok, "detail": detail, **extra})

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c["ok"]]


def emit_error(code: str, message: str, hint: str) -> None:
    """Structured error on stderr, per the interface contract this repo enforces."""
    print(json.dumps({"error": message, "code": code, "hint": hint}), file=sys.stderr)


@dataclass(frozen=True)
class Skill:
    """A published skill; `bundle` names the `plugins/*/` it ships in, if any."""

    path: Path
    bundle: str | None = None

    @property
    def label(self) -> str:
        """What check names show: `plan`, or `ai-sdlc/spec-define`."""
        return f"{self.bundle}/{self.path.name}" if self.bundle else self.path.name


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd, cwd=cwd or TOOLS, capture_output=True, text=True, timeout=TIMEOUT, check=False
    )
    return proc.returncode, proc.stdout, proc.stderr


def git(target: Path, *args: str) -> tuple[int, str]:
    code, out, err = run(["git", *args], cwd=target)
    return code, out if code == 0 else err.strip()


def is_library(path: Path) -> bool:
    """True for modules opting out of the agent-tool contract.

    `validate_agent_tool.py` skips these; the driver has to agree or it demands
    a --help from modules that deliberately have no CLI.
    """
    if path.name in NOT_TOOLS:
        return True
    try:
        head = path.read_text(encoding="utf-8", errors="replace").splitlines()[:10]
    except OSError:
        return False
    return any("agent-tool: false" in line for line in head)


def tool_files(target: Path, suffix: str) -> list[Path]:
    return sorted(
        p
        for skill in published_skills(target)
        for p in (skill.path / "scripts").glob(f"*{suffix}")
        if not is_library(p) and not p.name.endswith(f".test{suffix}")
    )


def published_skills(target: Path) -> list[Skill]:
    """Every `skills/*/` plus every skill inside a `plugins/*/` bundle, each named individually."""
    flat = [Skill(p) for p in sorted(target.glob("skills/*")) if (p / "SKILL.md").is_file()]
    bundled = [
        Skill(p, bundle.name)
        for bundle in bundles(target)
        for p in sorted((bundle / "skills").glob("*"))
        if (p / "SKILL.md").is_file()
    ]
    return [*flat, *bundled]


def bundles(target: Path) -> list[Path]:
    return sorted(p for p in target.glob("plugins/*") if p.is_dir())


def check_toolchain(res: Result, groups: set[str]) -> bool:
    """Fail fast: the rest of the sweep is noise without these. Each group asks only for
    what it shells out to, so a machine without Node can still check manifests."""
    ok = True
    wanted = dict.fromkeys(
        tool for group, tools in NEEDS.items() if group in groups for tool in tools
    )
    for name in wanted:
        if name == "tsx":
            found = TSX.is_file()
            detail = (
                str(TSX.relative_to(TOOLS))
                if found
                else f"missing {TSX} — run `npm ci` in {TS_DIR}"
            )
        elif shutil.which(name) is None:
            found, detail = False, f"{name} not on PATH"
        else:
            found, detail = True, run([name, "--version"])[1].strip()
        res.add(f"toolchain/{name}", found, detail)
        ok = ok and found
    return ok


def check_help(res: Result, target: Path, tools: list[Path], runner: list[str], label: str) -> None:
    """Every agent tool must answer --help with exit 0 and a usage line."""
    for tool in tools:
        rel = tool.relative_to(target).as_posix()
        code, out, err = run([*runner, str(tool), "--help"])
        text = out + err
        ok = code == 0 and ("usage" in text.lower() or "Usage" in text)
        res.add(f"{label}/help/{rel}", ok, f"exit={code}", exit_code=code)


def check_json_stdout(
    res: Result, target: Path, tools: list[Path], runner: list[str], label: str
) -> None:
    """JSON mode must put parseable JSON on stdout with nothing else mixed in."""
    skills = published_skills(target)
    probe = skills[0].path.as_posix() if skills else target.as_posix()
    # Each tool takes a different positional; these are the ones that accept a skill dir.
    accepts_skill_dir = {"validate_skill", "analyze_skill", "audit_security", "recommend_scripts"}
    for tool in tools:
        if tool.stem not in accepts_skill_dir:
            continue
        rel = tool.relative_to(target).as_posix()
        code, out, _ = run([*runner, str(tool), probe, "--json"])
        try:
            payload = json.loads(out)
            ok = isinstance(payload, dict)
            detail = f"exit={code} keys={sorted(payload)[:4]}" if ok else "not a JSON object"
        except json.JSONDecodeError as exc:
            ok, detail = False, f"stdout is not JSON: {exc}"
        res.add(f"{label}/json/{rel}", ok, detail, exit_code=code)


def _summary_of(out: str) -> dict[str, object] | None:
    """Extract the `summary` object from a tool's --json output, or None if unparseable."""
    try:
        return json.loads(out)["summary"]
    except json.JSONDecodeError, KeyError:
        return None


@functools.cache
def audit_summary(
    runner: tuple[str, ...], validator: Path, skill: Path
) -> tuple[int, dict[str, object] | None]:
    """One validator run per skill, shared by self-audit and parity."""
    code, out, _ = run([*runner, str(validator), str(skill), "--json", "--quiet"])
    return code, _summary_of(out)


def check_self_audit(
    res: Result, target: Path, runner: list[str], validator: Path, label: str
) -> None:
    """The marketplace must pass its own spec validator.

    Held to fail=0 *and* warn=0: every shipped skill is clean today, so any warn
    is drift. The validator's own `ok` flag is laxer — it tolerates warnings.
    """
    for skill in published_skills(target):
        code, summary = audit_summary(tuple(runner), validator, skill.path)
        if summary is None:
            res.add(f"{label}/self-audit/{skill.label}", False, f"unparseable output (exit={code})")
            continue
        res.add(
            f"{label}/self-audit/{skill.label}",
            summary.get("fail") == 0 and summary.get("warn") == 0,
            f"fail={summary.get('fail')} warn={summary.get('warn')}",
        )


def check_parity(res: Result, target: Path) -> None:
    """CLAUDE.md requires the Python and TypeScript twins to behave identically."""
    for skill in published_skills(target):
        _, sa = audit_summary((sys.executable,), PY_VALIDATOR, skill.path)
        _, sb = audit_summary((str(TSX),), TS_VALIDATOR, skill.path)
        if sa is None or sb is None:
            res.add(f"parity/{skill.label}", False, "one side produced unparseable JSON")
            continue
        res.add(f"parity/{skill.label}", sa == sb, f"py={sa} ts={sb}")


def _normalize(source: str) -> str:
    return posixpath.normpath(source).removeprefix("./")


def _json_object(text: str) -> dict[str, object] | None:
    """`text` parsed as a JSON object; bad JSON or any other JSON value (`[]`, `"x"`) is None."""
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError:
        return None
    return cast("dict[str, object]", data) if isinstance(data, dict) else None


def _read_json_object(path: Path) -> dict[str, object] | None:
    try:
        return _json_object(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def _plugin_name(plugin_json: Path) -> str | None:
    name = (_read_json_object(plugin_json) or {}).get("name")
    return name if isinstance(name, str) else None


def read_marketplace(target: Path) -> list[dict[str, object]] | None:
    data = _read_json_object(target / ".claude-plugin" / "marketplace.json")
    plugins = data.get("plugins") if data else None
    if not isinstance(plugins, list):
        return None
    return [p for p in plugins if isinstance(p, dict)]  # pyright: ignore[reportUnknownVariableType]


def check_manifests(res: Result, target: Path) -> None:
    """Adding or renaming a skill means editing two manifests; catch the half-done edit.

    A bundle has no per-skill manifest, so the marketplace entry and the bundle's own
    plugin.json are what must agree, and nothing on disk may be left unlisted.
    """
    entries = read_marketplace(target)
    if entries is None:
        res.add(
            "manifests/marketplace", False, "missing or unparseable .claude-plugin/marketplace.json"
        )
        return
    listed: set[str] = set()
    for entry in entries:
        name, source = entry.get("name"), entry.get("source")
        check = f"manifests/entry/{name}"
        if not isinstance(source, str):
            res.add(check, False, "entry has no `source`")
            continue
        normalized = _normalize(source)
        listed.add(normalized)
        plugin_json = target / source / ".claude-plugin" / "plugin.json"
        if not plugin_json.is_file():
            res.add(check, False, f"{source} has no .claude-plugin/plugin.json")
            continue
        found = _plugin_name(plugin_json)
        # A skill's directory name is its identity (validate_skill.py holds SKILL.md to it), so
        # renaming both manifests together must not pass.
        ok = found == name
        if normalized.startswith("skills/"):
            ok = ok and found == posixpath.basename(normalized)
        res.add(check, ok, f"source={source} plugin.json name={found!r}")

    on_disk = {f"skills/{s.path.name}" for s in published_skills(target) if s.bundle is None}
    on_disk |= {f"plugins/{b.name}" for b in bundles(target)}
    stray_manifest, stray_dir = sorted(listed - on_disk), sorted(on_disk - listed)
    res.add(
        "manifests/marketplace-covers-disk",
        not stray_manifest and not stray_dir,
        f"only-in-marketplace={stray_manifest} only-on-disk={stray_dir}",
    )


def _marketplace_entry(target: Path, bundle: Path) -> dict[str, object]:
    for entry in read_marketplace(target) or []:
        source = entry.get("source")
        if isinstance(source, str) and _normalize(source) == f"plugins/{bundle.name}":
            return entry
    return {}


def check_contents(res: Result, target: Path, bundle: Path) -> None:
    """The bundle's directory is its listing, so it may hold only skills and agents."""
    if not (bundle / "skills").is_dir() and not (bundle / "agents").is_dir():
        # A mod (hooks, status line) ships no skills or agents; the bundle shape doesn't apply.
        res.add(f"bundle/{bundle.name}/contents", True, "mod, not a skill bundle")
        return
    problems = [
        f"unexpected top-level entry {p.name!r}"
        for p in sorted(bundle.iterdir())
        if p.name not in BUNDLE_TOP_LEVEL
    ]
    problems += [
        f"skills/{p.name}/ has no SKILL.md"
        for p in sorted((bundle / "skills").glob("*"))
        if not (p / "SKILL.md").is_file()
    ]
    problems += [
        f"agents/{p.name} is not an .md file"
        for p in sorted((bundle / "agents").glob("*"))
        if p.suffix != ".md"
    ]
    manifest = bundle / ".claude-plugin" / "plugin.json"
    data = _read_json_object(manifest)
    if data is None:
        problems.append("plugin.json is missing, unreadable or not a JSON object")
    manifest_keys = set(data or {})
    for where, keys in (
        ("plugin.json", manifest_keys),
        ("marketplace entry", set(_marketplace_entry(target, bundle))),
    ):
        problems += [f"{where} has component key {k!r}" for k in sorted(keys & COMPONENT_KEYS)]
    res.add(
        f"bundle/{bundle.name}/contents",
        not problems,
        "; ".join(problems) or "skills and agents only",
    )


def check_plugin_validate(res: Result, target: Path, bundle: Path) -> None:
    code, out, _ = run(
        ["claude", "plugin", "validate", "--strict", "--json", str(bundle)], cwd=target
    )
    try:
        report = json.loads(out)
        ok, detail = bool(report["success"]) and code == 0, f"strict exit={code}"
    except json.JSONDecodeError, KeyError, TypeError:
        ok, detail = False, f"unparseable `claude plugin validate` output (exit={code})"
    res.add(f"bundle/{bundle.name}/plugin-validate", ok, detail)


def check_agents(res: Result, bundle: Path) -> None:
    check = f"bundle/{bundle.name}/agents"
    agents = bundle / "agents"
    if not agents.is_dir():
        res.add(check, True, "no agents")
        return
    code, out, _ = run([sys.executable, str(AGENT_VALIDATOR), str(agents), "--json", "--quiet"])
    try:
        meta = json.loads(out)["meta"]
        fail, warn = meta["fail"], meta["warn"]
    except json.JSONDecodeError, KeyError, TypeError:
        res.add(check, False, f"unparseable output (exit={code})")
        return
    res.add(check, fail == 0 and warn == 0, f"fail={fail} warn={warn}")


def _agent_context(text: str, span: re.Match[str]) -> bool:
    """True when the span sits within a few words of the word "agent"."""
    near = text[: span.start()].split()[-3:] + text[span.end() :].split()[:3]
    return any(word.strip(".,;:()*_").lower() in AGENT_WORDS for word in near)


def _span_problem(
    text: str, span: re.Match[str], bundle: str, skills: set[str], agents: set[str]
) -> str | None:
    """Why one backticked span names something this bundle does not provide, or None."""
    word = span.group(1)
    if SLASH_COMMAND.match(word):
        prefix, _, skill = word.removeprefix("/").partition(":")
        if word in BUILTIN_COMMANDS or (prefix == bundle and skill in skills):
            return None
        return f"{word} is neither a bundle skill nor built in"
    if QUALIFIED_NAME.match(word):
        prefix, _, agent = word.partition(":")
        if prefix == bundle and agent in agents:
            return None
        return f"{word} is not an agent this bundle provides"
    if BARE_NAME.match(word) and _agent_context(text, span) and word not in agents:
        return f"{word} is named as an agent but the bundle has none"
    return None


def reference_problems(bundle: Path) -> list[str]:
    """Slash commands and agents a bundle skill names must exist once only this bundle is installed.

    Only backticked spans are read: every hand-off in the workflow is backticked, and scanning
    prose for commands would flag ordinary sentences.
    """
    skills = {p.name for p in (bundle / "skills").glob("*")}
    agents = {p.stem for p in (bundle / "agents").glob("*.md")}
    problems: list[str] = []
    for skill_md in sorted(bundle.glob("skills/*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        for span in BACKTICKED.finditer(text):
            problem = _span_problem(text, span, bundle.name, skills, agents)
            if problem:
                problems.append(f"{skill_md.parent.name}: {problem}")
    return problems


def check_refs(res: Result, bundle: Path) -> None:
    problems = reference_problems(bundle)
    res.add(
        f"bundle/{bundle.name}/refs", not problems, "; ".join(problems) or "all references resolve"
    )


def check_overlap(res: Result, target: Path, bundle: Path) -> None:
    """Compare each bundle skill with every other published skill.

    The overlap tool keys its pairs by skill name, so two skills sharing a name would
    silently shadow each other in the comparison; that is reported instead.
    """
    check = f"bundle/{bundle.name}/overlap"
    skills = published_skills(target)
    names = [s.path.name for s in skills]
    clashes = sorted({n for n in names if names.count(n) > 1})
    if clashes:
        res.add(check, False, f"skill names are not unique across skills/ and plugins/: {clashes}")
        return
    mine = {s.path.name for s in skills if s.bundle == bundle.name}
    with tempfile.TemporaryDirectory() as tmp:
        for skill in skills:
            (Path(tmp) / skill.path.name).symlink_to(skill.path)
        _, out, _ = run(
            [
                sys.executable,
                str(OVERLAP),
                tmp,
                "--threshold",
                str(OVERLAP_THRESHOLD),
                "--json",
                "--quiet",
            ]
        )
    try:
        pairs = json.loads(out)["pairs"]
    except json.JSONDecodeError, KeyError:
        res.add(check, False, "unparseable overlap output")
        return
    hits = [f"{p['a']} vs {p['b']} ({p['similarity']})" for p in pairs if {p["a"], p["b"]} & mine]
    res.add(check, not hits, "; ".join(hits) or f"no pair at or above {OVERLAP_THRESHOLD}")


def _version(text: str) -> tuple[int, ...] | None:
    raw = (_json_object(text) or {}).get("version")
    parts = re.findall(r"\d+", raw) if isinstance(raw, str) else []
    return tuple(int(p) for p in parts) or None


def _version_at(target: Path, commit: str, manifest: str) -> tuple[int, ...] | None:
    code, out = git(target, "show", f"{commit}:{manifest}")
    return _version(out) if code == 0 else None


def _is_shallow_boundary(target: Path, commit: str) -> bool:
    code, out = git(target, "rev-parse", "--is-shallow-repository")
    if code != 0 or out.strip() != "true":
        return False
    code, out = git(target, "rev-parse", "--git-path", "shallow")
    try:
        grafts = (target / out.strip()).read_text(encoding="utf-8").split()
    except OSError:
        return False
    return code == 0 and commit in grafts


def version_problem(target: Path, bundle: Path) -> str | None:
    """Why this bundle's content changed without a higher version, or None when it is fine."""
    rel = bundle.relative_to(target).as_posix()
    manifest = f"{rel}/.claude-plugin/plugin.json"
    if git(target, "rev-parse", "--git-dir")[0] != 0:
        return "not a git repository, so the last version change cannot be found"
    if git(target, "cat-file", "-e", f"HEAD:{manifest}")[0] != 0:
        return None
    try:
        here = _version((target / manifest).read_text(encoding="utf-8"))
    except OSError:
        return "plugin.json is in HEAD but missing or unreadable in the working tree"
    if here is None:
        return "plugin.json has no readable version"
    committed = _version_at(target, "HEAD", manifest)
    if committed is not None and here > committed:
        return None
    if committed is not None and here < committed:
        return f"version lowered from {committed} to {here}"
    code, log = git(target, "log", "-2", "--format=%H", "-G", '"version"', "--", manifest)
    commits = log.split() if code == 0 else []
    if not commits:
        return "cannot find the commit that last changed the version (shallow clone?)"
    baseline = commits[0]
    if _is_shallow_boundary(target, baseline):
        # A shallow clone's oldest commit diffs as if it added every file, so `-G` matches it
        # whether or not it changed the version; the real version change is out of reach.
        return (
            f"shallow clone: history stops at {baseline[:8]} before the last version change; "
            "run `git fetch --unshallow`"
        )
    if len(commits) == 2:
        before = _version_at(target, commits[1], manifest)
        if before is not None and here < before:
            return f"version lowered from {before} to {here} in {baseline[:8]}"
    _, changed = git(target, "diff", "--name-only", baseline, "--", rel, f":(exclude){manifest}")
    _, untracked = git(target, "ls-files", "--others", "--exclude-standard", "--", rel)
    files = [*changed.split(), *untracked.split()]
    if files:
        return f"changed since the version last changed ({baseline[:8]}): {', '.join(files)}"
    return None


def check_version(res: Result, target: Path, bundle: Path) -> None:
    problem = version_problem(target, bundle)
    res.add(f"bundle/{bundle.name}/version", problem is None, problem or "version is current")


def check_bundle(res: Result, target: Path, bundle: Path) -> None:
    check_contents(res, target, bundle)
    check_plugin_validate(res, target, bundle)
    check_agents(res, bundle)
    check_refs(res, bundle)
    check_overlap(res, target, bundle)
    check_version(res, target, bundle)


def check_tests(res: Result) -> None:
    code, out, _ = run([sys.executable, "-m", "pytest", "-q"])
    summary = out.strip().splitlines()[-1] if out.strip() else f"exit={code}"
    res.add("tests/pytest", code == 0, summary)
    code, out, err = run(["npm", "test", "--silent"], cwd=TS_DIR)
    tail = [ln for ln in (out + err).splitlines() if "Tests" in ln or "failed" in ln]
    res.add("tests/vitest", code == 0, tail[-1].strip() if tail else f"exit={code}")


def check_language(
    res: Result,
    target: Path,
    label: str,
    tools: list[Path],
    runner: list[str],
    validator: Path,
    lang: str,
) -> int | None:
    """Run the --help/--json/self-audit group for one language. Returns a fatal
    exit code if no tools were found, else None to continue the sweep."""
    if not tools:
        emit_error(
            "smoke.tools.none-found",
            f"no {lang} agent tools found under any published skill's scripts/",
            "check that the repo is intact and you are pointing at the right checkout",
        )
        return 3
    check_help(res, target, tools, runner, label)
    check_json_stdout(res, target, tools, runner, label)
    check_self_audit(res, target, runner, validator, label)
    return None


def emit(res: Result, fmt: str, elapsed: float) -> None:
    """Render the report. Must honour `fmt` on every exit path — an agent
    running --json parses stdout, so leaking the text table there breaks it."""
    if fmt == "json":
        summary = {
            "total": len(res.checks),
            "failed": len(res.failed),
            "ok": not res.failed,
            "elapsed_s": round(elapsed, 2),
        }
        print(json.dumps({"checks": res.checks, "summary": summary}, indent=2))
        return
    for c in res.checks:
        mark = "PASS" if c["ok"] else "FAIL"
        print(f"  [{mark}] {c['check']}  {c['detail']}")
    total, bad = len(res.checks), len(res.failed)
    print(f"\n{total - bad}/{total} checks passed in {elapsed:.1f}s")
    if bad:
        print(f"\n{bad} failing:")
        for c in res.failed:
            print(f"  - {c['check']}: {c['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-drive every agent tool in this marketplace.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  smoke.py                       # full sweep, no test suites\n"
            "  smoke.py --tests               # also run pytest + vitest\n"
            "  smoke.py --only python --json  # Python tools only, machine-readable\n"
            "  smoke.py --only bundle         # plugin bundles under plugins/\n"
            "  smoke.py --repo ../other       # check another checkout with these validators\n"
        ),
    )
    parser.add_argument(
        "--only",
        choices=GROUPS,
        help="Restrict the sweep to one group (default: all groups).",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=TOOLS,
        help="Repo to check (default: this script's own checkout). The validators always come "
        "from this checkout.",
    )
    parser.add_argument(
        "--tests", action="store_true", help="Also run the pytest and vitest suites."
    )
    parser.add_argument("--format", choices=["json", "text"], default="text", help="Output format.")
    parser.add_argument("--json", action="store_true", help="Alias for --format json.")
    parser.add_argument("--quiet", action="store_true", help="Suppress informational stderr.")
    args = parser.parse_args()

    fmt = "json" if args.json else args.format
    target = args.repo.resolve()
    res = Result()
    started = time.monotonic()

    if not target.is_dir():
        emit_error(
            "smoke.repo.not-found",
            f"--repo {args.repo} is not a directory",
            "pass the root of a skills marketplace checkout",
        )
        return 3
    if not args.quiet:
        print(f"repo: {target}", file=sys.stderr)

    groups: set[str] = {args.only} if args.only else set(GROUPS)
    if args.only is None and not bundles(target):
        # Nothing for the bundle group to check, so don't demand `claude` and `git` for it.
        groups.discard("bundle")
    if not check_toolchain(res, (groups | {"tests"}) if args.tests else groups):
        # Everything downstream shells out to these; reporting 40 cascading
        # failures would bury the one that matters.
        emit(res, fmt, time.monotonic() - started)
        emit_error(
            "smoke.toolchain.missing",
            "required toolchain is incomplete",
            f"run `uv sync` at {TOOLS} and `npm ci` in {TS_DIR}; the bundle group also needs "
            "`claude` and `git` on PATH, and --tests needs `npm`",
        )
        return 2

    if "python" in groups:
        code = check_language(
            res,
            target,
            "python",
            tool_files(target, ".py"),
            [sys.executable],
            PY_VALIDATOR,
            "Python",
        )
        if code is not None:
            return code
    if "ts" in groups:
        code = check_language(
            res,
            target,
            "ts",
            tool_files(target, ".ts"),
            [str(TSX)],
            TS_VALIDATOR,
            "TypeScript",
        )
        if code is not None:
            return code
    if "parity" in groups:
        check_parity(res, target)
    if "manifests" in groups:
        check_manifests(res, target)
    if "bundle" in groups:
        found = bundles(target)
        if not found and args.only == "bundle":
            emit_error(
                "smoke.bundle.none-found",
                "no plugin bundles found under plugins/",
                "a bundle is a directory plugins/<name>/ with a .claude-plugin/plugin.json",
            )
            return 3
        for bundle in found:
            check_bundle(res, target, bundle)
    if args.tests:
        check_tests(res)

    emit(res, fmt, time.monotonic() - started)

    if res.failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
