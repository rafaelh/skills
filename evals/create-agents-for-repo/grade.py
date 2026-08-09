#!/usr/bin/env python3
"""Grade one eval run of create-agents-for-repo against its assertions.

Usage: grade.py <run-dir> <fixture-dir> <eval-name>
Writes <run-dir>/grading.json.

Developer harness, not something an agent calls — see evals/README.md.
"""

# agent-tool: false

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
from typing import cast

VALIDATOR = (
    Path(__file__).resolve().parent.parent.parent
    / "skills"
    / "create-agents-for-repo"
    / "scripts"
    / "validate_agent_def.py"
)

Json = dict[str, object]

# Each fixture's real toolchain. An agent naming a command from the wrong column
# was written from a template rather than fitted to the repo.
TOOLCHAIN = {
    "rich-repo": {"expect": ["pyright", "pytest", "ruff"], "forbid": ["mypy"]},
    "reimport-repo": {"expect": ["pyright", "pytest", "ruff"], "forbid": ["mypy"]},
    "bare-repo": {"expect": ["mypy", "pytest", "ruff"], "forbid": ["pyright", "uv run"]},
}
ORIGINAL_AGENTS = {"build-green", "content-audit", "docs-drift", "test-scaffold"}


def parse_fm(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out: dict[str, str] = {}
    key = None
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s?(.*)$", line)
        if m:
            key = m.group(1)
            out[key] = m.group(2).strip().strip("\"'")
        elif key and line.startswith((" ", "\t")):
            out[key] += " " + line.strip()
    return out


def run_validator(args: list[str]) -> Json:
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), *args, "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}
    return cast("Json", payload) if isinstance(payload, dict) else {}


def findings_of(payload: Json) -> list[Json]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    found = cast("dict[str, object]", data).get("findings")
    return cast("list[Json]", found) if isinstance(found, list) else []


def changed_paths(repo: Path, fixture: Path) -> list[str]:
    # Caches are created by simply running the repo's tools, which every run does.
    proc = subprocess.run(
        [
            "diff",
            "-rq",
            "--exclude=.git",
            "--exclude=__pycache__",
            "--exclude=.pytest_cache",
            "--exclude=.ruff_cache",
            "--exclude=.mypy_cache",
            "--exclude=*.pyc",
            "--exclude=.coverage",
            str(fixture),
            str(repo),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    paths: list[str] = []
    for line in proc.stdout.splitlines():
        m = re.search(rf"{re.escape(str(repo))}/(\S+)", line)
        if m:
            paths.append(m.group(1))
        else:
            m2 = re.search(r"Files .* and .* differ", line)
            if m2:
                paths.append(line)
    return paths


def grade(run_dir: Path, fixture: Path, eval_name: str) -> Json:
    repo = run_dir / "repo"
    agents_dir = repo / ".claude" / "agents"
    agent_files = sorted(agents_dir.glob("*.md")) if agents_dir.is_dir() else []
    frontmatters = {p.stem: parse_fm(p.read_text(encoding="utf-8")) for p in agent_files}
    bodies = {p.stem: p.read_text(encoding="utf-8") for p in agent_files}
    fixture_key = fixture.name
    claude_md = repo / "CLAUDE.md"
    claude_text = claude_md.read_text(encoding="utf-8") if claude_md.exists() else ""

    expectations: list[Json] = []

    def add(text: str, passed: bool, evidence: str) -> None:
        expectations.append({"text": text, "passed": bool(passed), "evidence": evidence})

    # 1. Something was actually created — except on the re-import case, where the
    # repo already has four agents and "add nothing, wire what exists" is a correct
    # answer. Punishing that would reward padding.
    new_agents = [n for n in frontmatters if n not in ORIGINAL_AGENTS]
    proposal = run_dir / "outputs" / "proposal.md"
    ptext = proposal.read_text(encoding="utf-8").lower() if proposal.exists() else ""
    if eval_name.startswith("eval-2"):
        justified = bool(re.search(r"no new agent|nothing new|adding none|no additional", ptext))
        add(
            "Added a new agent, or justified adding none",
            bool(new_agents) or justified,
            f"new agents: {new_agents or 'none'}; no-op justified in proposal: {justified}",
        )
    else:
        add(
            "Wrote at least one new agent definition to .claude/agents/",
            bool(new_agents),
            f"new agents: {new_agents or 'none'}; total on disk: {sorted(frontmatters)}",
        )

    # 2. Frontmatter is spec-valid (no FAIL findings, references aside)
    payload = run_validator([str(agents_dir)]) if agent_files else {}
    fails = [f for f in findings_of(payload) if f.get("severity") == "fail"]
    add(
        "Every agent passes frontmatter validation (no FAIL findings)",
        bool(agent_files) and not fails,
        f"{len(fails)} fail finding(s): {[f['code'] for f in fails][:6]}",
    )

    # 3. The point of the whole exercise: every agent is invoked from somewhere
    ref_payload = (
        run_validator([str(agents_dir), "--check-references", str(repo)]) if agent_files else {}
    )
    unreferenced = [
        f["agent"] for f in findings_of(ref_payload) if f.get("code") == "agent.refs.unreferenced"
    ]
    add(
        "Every agent on disk is referenced from CLAUDE.md or a skill (none orphaned)",
        bool(agent_files) and not unreferenced,
        f"unreferenced: {unreferenced or 'none'}",
    )

    # 4. Cheap tier actually used
    haiku = [n for n, fm in frontmatters.items() if fm.get("model") == "haiku"]
    add(
        "At least one agent is assigned model: haiku",
        bool(haiku),
        f"haiku agents: {haiku or 'none'}; models: "
        f"{ {n: fm.get('model', 'UNSET') for n, fm in frontmatters.items()} }",
    )

    # 5. Tool grants narrowed
    unrestricted = [
        n for n, fm in frontmatters.items() if not fm.get("tools") and not fm.get("disallowedTools")
    ]
    add(
        "Every agent declares a tool allowlist (or disallowedTools)",
        bool(frontmatters) and not unrestricted,
        f"unrestricted: {unrestricted or 'none'}",
    )

    # 6. Return contract — the mechanism that makes isolation pay
    contract_re = re.compile(
        r"^#{1,4}\s*(report|output|return|deliverable)\b", re.IGNORECASE | re.MULTILINE
    )
    no_contract = [n for n, b in bodies.items() if not contract_re.search(b)]
    add(
        "Every agent body states a return contract (Report/Output section)",
        bool(bodies) and not no_contract,
        f"missing contract: {no_contract or 'none'}",
    )

    # 7. Fitted to THIS repo's toolchain, not a generic template
    spec = TOOLCHAIN[fixture_key]
    all_bodies = "\n".join(bodies.values()).lower()
    wrong = [c for c in spec["forbid"] if c.lower() in all_bodies]
    right = [c for c in spec["expect"] if c.lower() in all_bodies]
    add(
        f"Agent commands match this repo's real toolchain ({'/'.join(spec['expect'])}) "
        f"and avoid {'/'.join(spec['forbid'])}",
        bool(right) and not wrong,
        f"found expected: {right}; found forbidden: {wrong or 'none'}",
    )

    # 8. CLAUDE.md routing exists and names agents
    named = [
        n for n in frontmatters if re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", claude_text)
    ]
    heading = re.search(r"##+\s*\w*\s*(delegat|agent|routing)", claude_text, re.IGNORECASE)
    add(
        "CLAUDE.md carries a routing entry naming at least one agent",
        bool(named) and bool(heading),
        f"agents named in CLAUDE.md: {named or 'none'}",
    )

    # 9. Scope discipline — no drive-by edits to source
    changed = changed_paths(repo, fixture)
    out_of_scope = [
        c for c in changed if not any(marker in c for marker in (".claude", ".agents", "CLAUDE.md"))
    ]
    add(
        "Changes confined to .claude/ and CLAUDE.md (no source files touched)",
        not out_of_scope,
        f"out-of-scope changes: {out_of_scope[:6] or 'none'}",
    )

    # 10. Proposal with rejected candidates — evidence the bar was applied
    add(
        "Wrote a proposal that names candidates it rejected and why",
        bool(ptext) and bool(re.search(r"reject|not creat|ruled out|considered and", ptext)),
        f"proposal.md {'present' if ptext else 'MISSING'}"
        f"{', mentions rejections' if re.search(r'reject|not creat|ruled out', ptext) else ''}",
    )

    # --- Discriminators. The checks above saturated at iteration 1 (100% with the
    # skill, 97% without), so they no longer separate the two arms. These target the
    # judgement the skill actually teaches, which an unaided run has no reason to do.

    # 11. Tier correctness. Haiku is for mechanical work whose output another step
    # checks. An agent that reviews, audits or judges has nothing downstream to catch
    # it being subtly wrong — miscasting it cheap is the failure model-tiers.md warns
    # about, and the one an unaided run walks into chasing token savings.
    # Only agents this run authored are in scope. rich-repo and reimport-repo ship
    # four agents of their own; rewriting those is scope creep, so grading the run on
    # their tiers and phrasing would punish the correct behaviour.
    fixture_agents = fixture / ".claude" / "agents"
    authored = {
        n
        for n, body in bodies.items()
        if not (fixture_agents / f"{n}.md").is_file()
        or (fixture_agents / f"{n}.md").read_text(encoding="utf-8") != body
    }

    judgment_re = re.compile(r"audit|review|critiqu|assess|analy|design|decid|judg", re.IGNORECASE)
    miscast = [
        n
        for n in authored
        if frontmatters[n].get("model") == "haiku"
        and judgment_re.search(
            n + " " + frontmatters[n].get("description", "") + " " + bodies[n][:400]
        )
    ]
    add(
        "No judgment-shaped agent (audit/review/analyse) is assigned model: haiku",
        not miscast,
        f"miscast as haiku: {miscast or 'none'}",
    )

    # 12. A cheap model with an open-ended loop is the expensive failure. Every haiku
    # agent should carry a cap.
    uncapped = [
        n
        for n in authored
        if frontmatters[n].get("model") == "haiku"
        and not (frontmatters[n].get("maxTurns") or frontmatters[n].get("effort"))
    ]
    add(
        "Every haiku agent it wrote caps its work (maxTurns or effort)",
        bool(frontmatters) and not uncapped,
        f"uncapped haiku agents: {uncapped or 'none'} (of {len(authored)} authored)",
    )

    # 13. "Measure, do not estimate." A candidate justified by a real line or token
    # count was verified; one justified by adjectives was guessed.
    measured = re.search(r"[\d,]{2,}\s*(lines|tokens)|(lines|tokens)[:\s]+[\d,]{2,}", ptext)
    add(
        "Proposal justifies at least one candidate with a measured line/token count",
        bool(measured),
        f"measurement found: {measured.group(0).strip() if measured else 'none'}",
    )

    # 14. The adversarial review pays off when it replaces an agent with something
    # smaller — a flag, a config line — not when it merely says no.
    simpler = re.search(
        r"(simpler|instead of an agent|no agent needed|not worth an agent|replace[d]? with)"
        r"[^\n]{0,120}(`[^`]+`|--?[a-z][\w-]+|\w+\.(md|toml|json|ya?ml))",
        ptext,
    )
    add(
        "Proposal names a concrete simpler alternative for at least one rejected candidate",
        bool(simpler),
        f"alternative found: {simpler.group(0)[:90].strip() if simpler else 'none'}",
    )

    # 15. A subagent starts cold: "run the tests" is not a procedure, `uv run pytest -q`
    # is. Any agent holding Bash must spell the command out.
    command_re = re.compile(r"`[^`\n]*\b(pytest|ruff|mypy|pyright|npm|uv|python)\b[^`\n]*`")
    vague = [
        n
        for n in authored
        if "bash" in frontmatters[n].get("tools", "").lower() and not command_re.search(bodies[n])
    ]
    add(
        "Every Bash-holding agent it wrote spells out its exact command line in backticks",
        not vague,
        f"agents describing commands instead of naming them: {vague or 'none'}",
    )

    # 11. Re-import case: extend, do not duplicate or clobber
    if eval_name.startswith("eval-2"):
        kept = ORIGINAL_AGENTS & set(frontmatters)
        add(
            "Preserved all four pre-existing agents without duplicating them",
            kept == ORIGINAL_AGENTS and len(agent_files) == len(frontmatters),
            f"kept: {sorted(kept)}; missing: {sorted(ORIGINAL_AGENTS - set(frontmatters))}",
        )
        add(
            "Kept the pre-existing build-green / docs-drift routing rows in CLAUDE.md",
            "build-green" in claude_text and "docs-drift" in claude_text,
            f"build-green present: {'build-green' in claude_text}; "
            f"docs-drift present: {'docs-drift' in claude_text}",
        )

    passed = sum(1 for e in expectations if e["passed"])
    return {
        "run": str(run_dir),
        "expectations": expectations,
        "passed": passed,
        "total": len(expectations),
        "pass_rate": round(passed / len(expectations), 3) if expectations else 0.0,
    }


def main() -> int:
    run_dir, fixture, eval_name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    result = grade(run_dir, fixture, eval_name)
    (run_dir / "grading.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{run_dir.parent.name}/{run_dir.name}: {result['passed']}/{result['total']}")
    for e in cast("list[Json]", result["expectations"]):
        print(f"  [{'PASS' if e['passed'] else 'FAIL'}] {e['text']}")
        if not e["passed"]:
            print(f"         {e['evidence']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
