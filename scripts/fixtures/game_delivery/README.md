# G1 delivery-judgement fixtures (R-14)

Input for `scripts/game_delivery_gate.py`, which measures gate **G1** of
`docs/reviews/2026-08-08-survival-game-fit.md`:

> 手标 ≥200 条学习者应答(四个 tier 各 ≥50 条),确定性槽位匹配对「意思是否传达到」的
> **precision ≥0.85 / recall ≥0.70**

## Status: the real labelled set does not exist yet

`responses.csv` is a **smoke sample of 46 rows that the harness author wrote by
hand**. Every row carries `origin=synthetic`. It exists to prove the harness
runs end to end and to exercise the failure shapes the matcher is expected to
have (negation, past-tense report, single-noun answers). It is **not** a
measurement of G1.

The script refuses to issue a PASS/FAIL while any row is non-`real`, and labels
its own output `冒烟样本，不可回填 R-14`. Do not copy numbers produced from this
file into the R-14 review or into `docs/PRD.md`.

**Outstanding for G1: 200 hand-labelled real learner responses, ≥50 per tier.**
R-14 §4 张力 4 already flags the risk: a hand-labelled set that misses real
learners' rough forms gives G1 an optimistic number. Which is exactly what a
self-authored sample does — the author knows what the `accept` sets contain.

## CSV schema

| column | required | meaning |
|---|---|---|
| `response_id` | no | stable id for the row; auto-filled as `L<line>` if blank |
| `scenario_id` | **yes** | must match a scenario `id` in `core/game_scenarios/` |
| `tier` | no | cross-check only; the scenario's own `tier` wins and a mismatch is printed |
| `response_text` | **yes** | the transcript the matcher sees, verbatim from `transcribe_waveform` |
| `delivered` | **yes** | human ground truth, `1/0` (`true/false`, `yes/no` also accepted). Unlabelled rows are skipped with a warning |
| `origin` | **yes in practice** | `real` or `synthetic`. Anything other than `real` blocks the verdict |
| `notes` | no | why the labeller judged as they did; printed next to every disagreement |

## How the real 200 must be collected

**Who says what.** Real adult L2 learners, not the team and not an LLM. Show
the learner only what the game shows: the scenario `situation.zh` and the NPC
`greeting`. Never show `slots.accept` or `reference_answer` — a learner who has
seen the accept list produces text that trivially matches it, and the resulting
precision is measuring the prompt, not the matcher.

Record audio and transcribe with the production path
(`transcribe.py:258` `transcribe_waveform`, `base.en`) so `response_text` carries
real ASR error. Labelling clean text a human typed would silently measure the
matcher on an input distribution the product never sees — that gap is G2's
subject, and letting it leak into G1 double-counts the optimism.

**Tier coverage (≥50 each).** Tiers are properties of scenarios, so cover them
by sampling scenarios across all four. G1 needs ≥50 rows per tier; `youth` and
`professional` scenarios must therefore exist before G1 can be measured at all,
which couples this to G3. Aim for ≥6 responses per scenario and ≥8 scenarios per
tier so no single scenario's `accept` set dominates a tier's number.

Within each tier keep the natural mix, including the rough forms §5.3 calls out
("me hungry", "want eat") and cases where the meaning genuinely does not land.
A set of only good attempts inflates precision; a set of only failures inflates
nothing but produces useless recall. Roughly balanced `delivered` truth is the
target, but do not resample to hit a ratio — take what learners actually say.

**How `delivered` is judged.** One question, and only this one:

> Would a tolerant native speaker in this situation understand what this person
> wants, well enough to hand over the right thing?

Judge as the NPC of §2: patient, cooperative, not grading. Explicitly **do not**
penalise word order, missing articles, wrong tense, or missing copula (§6.1
forbids grammar checking; G7 requires inclusivity). Also judge on the scenario
context, not on the sentence in isolation — "bread" after "Are you hungry?" does
land.

Two labellers independently, disagreements resolved by discussion, and record
the pre-discussion agreement rate. If labellers cannot agree, precision against
their labels is not a meaningful number. Fill `notes` while labelling, not after:
the disagreement listing is the reviewable part of the output, and it is only
reviewable if it says why the human decided as they did.

**Then** re-run with `--labels` pointing at the real set. A verdict is issued
only when every row is `origin=real`.
