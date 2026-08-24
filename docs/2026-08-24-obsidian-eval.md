# Obsidian skill — eval round and removal

`skills/obsidian` was removed on 2026-08-24. This is the measured round behind that call,
kept because it is the evidence, not because the skill is coming back. The harness that
produced it (`evals/obsidian/`: three fixture vaults, `prepare.py` / `run_case.py` /
`grade.py`, 66 mechanical checks) was removed with the skill and is recoverable from the
commit that deleted it.

## Rubric v1

66 mechanical checks over five cases — 14 rename, 13 audit, 13 frontmatter, 12 MOC, 14 canvas. No
grader model. Each case carries a floor (the file moved, a broken link was named, a journal note was
edited, a MOC exists, a canvas parses); a run that misses its floor fails that case's restraint
checks instead of collecting them, so an empty round scores 0/66 rather than 42/66.

The rubric was corrected twice while grading round 1, both times because a check was misreading a
*correct* report, and both before any score was recorded here:

- `exists` came out of the exoneration word list. A finding that explains itself — "note exists only
  in `.trash/`" — is not a retraction of that finding.
- Source paths are stripped from a line before it is searched for a reported target.
  ``| `notes/Zettelkasten Method.md` | `[[Old Method]]` |`` names one broken link, not two, and the
  un-stripped version scored every well-cited report as padded.

Validation before the round, and re-run after each correction: an ideal run scores 66/66, a
deliberately naive one 36/66, and a run that does nothing 0/66.

## Round 1 — 2026-08-24, sonnet

10 runs, one per cell, two arms.

| Eval | with_skill | without_skill |
|---|---|---|
| 0 rename-across-link-forms | 93% (13/14) | 93% (13/14) |
| 1 broken-link-audit | 100% (13/13) | 100% (13/13) |
| 2 bulk-frontmatter-tag | 100% (13/13) | 100% (13/13) |
| 3 moc-by-tag | 100% (12/12) | 100% (12/12) |
| 4 canvas-authoring | 100% (14/14) | 100% (14/14) |
| **Mean** | **98.5% (65/66)** | **98.5% (65/66)** |

**Not one of the 66 checks differed between the arms.**

| | with_skill | without_skill |
|---|---|---|
| Tokens, mean | 484,805 | 210,632 |
| Wall clock, mean | 67s | 61s |
| Tool calls, mean | 13.6 | 13.2 |
| Cost | $1.24 | $0.92 |

### What this round says

**The skill did not change what the model did, and cost 2.3× the tokens to not change it.** On
eval 0 the two arms produced vaults that differ only in the target note itself; every other file,
including all eight the rename touched, came out byte-identical. The baseline got the aliased link,
the block reference, the embed, the lowercase link, the frontmatter link, the near-name note and
`.trash/` right by reading the vault and reasoning about it — no scripts, no reference notes.

This is the failure mode `eval-approach.md` warns about, arriving all at once: a rubric where every
check passes in both arms has stopped measuring. The honest reading is that on a model this strong,
none of these five tasks needs the skill. What the round cannot tell us is whether the checks are
too easy or the skill is redundant — the naive-run validation (36/66) says the checks do have teeth,
which points at redundancy.

### The one shared failure is the interesting result

Both arms failed *"Wikilinks inside a code fence and an inline code span were left alone"*, and the
`with_skill` run failed it in a specific and fixable way:

1. It ran `rename_note.py`, which parsed with `links.py` and **correctly left both code samples
   alone** — exactly what the tool exists to do.
2. It then grepped the vault for remaining occurrences of the old name, found the two inside code,
   read them as links the tool had missed, and `Edit`ed them by hand.

The tool was right and the agent overruled it. `SKILL.md` tells the model to parse with `links.py`
rather than regex, but nothing tells it that a leftover `[[Old Name]]` **inside code or prose is the
expected result of a correct rename**, not a miss. The natural verification instinct — "check no
occurrences remain" — reproduces precisely the corruption `links.py` was written to prevent.

That is a skill change worth making, and the check that caught it is the one to watch next round.

### The two adverse checks both passed, for an unwelcome reason

Both checks written to expose places the skill's tools disagree with Obsidian passed in
`with_skill`, because the runs did not use those tool paths:

- *"It links Dial, whose tag is the nested `#project/active`"* — `vault_list.py --tag project`
  matches exactly and would have missed it. The run read `vault_list.py`'s source, grepped it for
  how tags are matched, and then scanned the vault itself.
- *"The attachment embed `[[forgetting-curve.png]]` is not reported broken"* — the recipe in
  `references/operations.md` builds its resolvable set from `.md` files only. The audit run did not
  follow it literally.

The gaps are still there; the model routed around them. A weaker model that followed the recipe as
written would fail both, so these stay in the rubric as the checks that would catch a regression in
the tools themselves.

### Next round

Do not add checks to make the skill look better. The two things worth doing:

1. **Fix the over-correction** — give the rename workflow an explicit note that occurrences left
   inside code and prose are correct — and re-run eval 0 with an `old_skill` arm to measure whether
   the wording moved the one check that failed.
2. **Raise the difficulty, or accept the finding.** These five cases are within a strong model's
   unaided reach. A round that separates the arms would need cases where the vault is large enough
   that reading it exhaustively is not an option, or where the rules are genuinely non-obvious
   (resolution ambiguity across many collisions, `.base` files, canvas edits that must preserve
   existing node geometry). If such cases still show no separation, the skill's body is not earning
   its context and should shrink to the parts that do.
