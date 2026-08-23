# Trigger eval for `obsidian-metabind`

A **trigger** suite in the sense of [eval-approach.md](../eval-approach.md): a labeled query set,
no arms, no fixtures. It measures the one thing the other suites cannot — whether the skill's
`description` gets it loaded in the first place. A skill that never activates scores nothing on any
other rubric.

## Contents

| Path | What it is |
|---|---|
| `trigger-queries.json` | Queries paired with whether this skill should activate, and why that query is in the set |

Each entry is `{query, should_trigger, notes}`; `notes` says what the query is testing, which is
what tells you whether a failure is the description's fault or the query's. The set is deliberately
mixed: explicit syntax (`INPUT[toggle:done]`), the plugin by name, intent with no Meta Bind
vocabulary at all ("make this note interactive"), and near-misses that belong to the sibling
`obsidian` skill and must **not** trigger.

## Running it

The runner is `skill-audit`'s, not a script of this suite's:

```bash
python3 skills/skill-audit/scripts/eval_triggers.py \
  --queries evals/obsidian-metabind/trigger-queries.json \
  --skill-name obsidian-metabind --runs 3 --json
```

`--runs 3` because activation is not deterministic — a query that triggers once in three is a
different finding from one that triggers three times in three. Exit code 1 means at least one query
came out inverted from its label; 2 means the harness could not run.

Add `--train-split 0.6` when iterating on the description itself, and read the validation
pass rate rather than the train one. Tuning wording against every query in the set overfits to
these queries, which is exactly the failure this set exists to catch.

## When you change the description

`obsidian-metabind` and `obsidian` overlap by design, so the description ends with an explicit
disambiguator pointing Meta Bind syntax here and general vault work there. Both halves are measured
by this set: keep the negative queries passing, not just the positive ones. `detect_skill_overlap.py`
flags sibling pairs that lose their disambiguator.

Record a round in a `benchmark.md` beside this file, the way the other suites do — pass rates by
split, the description that produced them, and the date.
