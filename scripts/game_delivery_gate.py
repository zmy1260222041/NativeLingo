#!/usr/bin/env python3
"""G1 measurement harness for R-14 (Survival module, FR-22 delivery judgement).

WHAT THIS MEASURES
  R-14 §2 G1 fixes the criterion *before* implementation:
      >= 200 hand-labelled learner responses (>= 50 per tier),
      deterministic slot matching vs human `delivered`:
      precision >= 0.85 / recall >= 0.70
  This script is that measurement. It implements the deterministic matcher of
  docs/survival-game.md §6.1 (word-boundary `accept` matching, no grammar
  checking), scores `delivery`, predicts `delivered`, and reports
  precision/recall against a hand-labelled CSV -- overall and per tier.

THE HONEST GAP -- READ THIS BEFORE QUOTING ANY NUMBER
  The 200 hand-labelled *real learner* responses G1 requires DO NOT EXIST in
  this repo and cannot be manufactured. scripts/fixtures/game_delivery/ ships a
  ~35-row SMOKE sample that the author of this script wrote by hand; every such
  row carries `origin=synthetic`. When any synthetic row is present this script
  REFUSES to print a PASS/FAIL verdict and labels its own output
      冒烟样本，不可回填 R-14
  Synthetic numbers say whether the harness works. They say nothing about
  whether G1 passes. See the fixtures README for how the real set must be
  collected.

WHY THIS LIVES IN scripts/ AND NOT core/
  docs/survival-game.md says "R-14 未通过前不得进入实现", but G1 cannot be
  measured without a matcher. Repo precedent is that gate prototypes live in
  scripts/ and product code follows the review: mdd_margin_sweep.py (R-4),
  photo_gate.py (R-13), ref_swap_experiment.py (R-1). So the matcher is
  implemented *inside this script*, deliberately not as a core module.

PRECISION IS THE ASYMMETRIC SIDE (R-14 §2 G1 "方法")
  A false "delivered" teaches the learner a wrong expression. A false "not
  delivered" only costs a retry, and §4 of the design makes retries free. So
  this script leads with precision, lists false positives before false
  negatives, and defaults to the strictest delivered-rule (every required slot
  must hit). --min-required-rate loosens it; the threshold sweep shows what
  that trade costs.

Usage:
  python scripts/game_delivery_gate.py                       # smoke fixture
  python scripts/game_delivery_gate.py --labels my.csv \
      --scenarios desktop/backend/core/game_scenarios \
      --out-csv /tmp/g1_audit.csv

Standard library only. No model loading -- G1 operates on text, not audio.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_SCENARIOS = os.path.join(_REPO, "desktop", "backend", "core", "game_scenarios")
_DEFAULT_LABELS = os.path.join(
    _REPO, "scripts", "fixtures", "game_delivery", "responses.csv"
)

TIERS = ("infant", "toddler", "youth", "professional")
GATE_PRECISION = 0.85
GATE_RECALL = 0.70
GATE_PER_TIER = 50
GATE_TOTAL = 200
SYNTHETIC_LABEL = "冒烟样本，不可回填 R-14"

# The two filled-in examples of docs/survival-game.md §5.5, copied verbatim so
# the harness can run before the scenario library lands. They are a FALLBACK
# for ids missing from --scenarios, never an override, and every use is printed.
DOC_EXAMPLE_SCENARIOS = [
    {
        "id": "food-ask-bread",
        "version": 1,
        "tier": "infant",
        "need": "food",
        "maslow_level": 1,
        "slots": [
            {
                "key": "need_object",
                "required": True,
                "accept": ["bread", "food", "something to eat", "eat", "hungry"],
            },
            {
                "key": "request_act",
                "required": True,
                "accept": [
                    "want",
                    "need",
                    "give me",
                    "can i have",
                    "may i have",
                    "please",
                ],
            },
            {
                "key": "politeness",
                "required": False,
                "accept": ["please", "thank you", "thanks"],
            },
        ],
    },
    {
        "id": "warmth-ask-blanket",
        "version": 1,
        "tier": "toddler",
        "need": "warmth",
        "maslow_level": 1,
        "slots": [
            {
                "key": "need_object",
                "required": True,
                "accept": ["blanket", "something warm", "cloth", "cover"],
            },
            {
                "key": "reason_state",
                "required": True,
                "accept": ["cold", "freezing", "i am cold", "shivering"],
            },
            {
                "key": "request_act",
                "required": False,
                "accept": [
                    "can i have",
                    "may i",
                    "could you",
                    "please",
                    "need",
                    "want",
                ],
            },
        ],
    },
]


# --------------------------------------------------------------------------
# §6.1 deterministic matcher
# --------------------------------------------------------------------------

def normalise(text: str) -> str:
    """Whitespace normalisation only (§6.1). Curly quotes folded to ASCII so a
    transcript artefact does not masquerade as a matcher failure. No stemming,
    no contraction expansion, no article/tense repair -- §6.1 forbids grammar
    checking, and silently normalising morphology would hide real recall gaps
    that belong in the `accept` sets instead."""
    return " ".join(str(text or "").replace("’", "'").replace("‘", "'").split())


def accept_pattern(term: str) -> re.Pattern[str]:
    """Word-boundary pattern for one `accept` entry.

    Reuses the in-production idiom of core/scenario.py:223 --
    `(?<![A-Za-z])...(?![A-Za-z])` with re.IGNORECASE -- so "bus" cannot hit
    "business". Multi-word phrases are matched as a whole after whitespace
    normalisation, with `\\s+` between tokens so "give  me" still matches.
    """
    tokens = [t for t in normalise(term).split(" ") if t]
    if not tokens:
        raise ValueError("empty accept term")
    body = r"\s+".join(re.escape(t) for t in tokens)
    return re.compile(rf"(?<![A-Za-z]){body}(?![A-Za-z])", re.IGNORECASE)


def match_slot(slot: dict, text: str) -> tuple[bool, list[str]]:
    """Return (hit, matched accept terms) for one slot against a response."""
    matched = []
    for term in slot.get("accept") or []:
        try:
            pattern = accept_pattern(term)
        except ValueError:
            continue
        if pattern.search(text):
            matched.append(term)
    return bool(matched), matched


def evaluate(scenario: dict, response: str, min_required_rate: float = 1.0) -> dict:
    """Deterministic delivery scoring for one response.

    delivery: required-slot hit rate is the body (0..85); optional slots add up
    to 15 on top. Optional slots therefore move the reward band of §5.4 but can
    never decide whether the meaning got across -- `delivered` reads required
    slots only, per §5.3.
    """
    text = normalise(response)
    slots = []
    for slot in scenario.get("slots") or []:
        hit, matched = match_slot(slot, text)
        slots.append(
            {
                "key": slot.get("key", "?"),
                "required": bool(slot.get("required")),
                "hit": hit,
                "matched": matched,
                "accept": list(slot.get("accept") or []),
            }
        )
    required = [s for s in slots if s["required"]]
    optional = [s for s in slots if not s["required"]]
    req_rate = (
        sum(1 for s in required if s["hit"]) / len(required) if required else 0.0
    )
    opt_rate = (
        sum(1 for s in optional if s["hit"]) / len(optional) if optional else 0.0
    )
    return {
        "text": text,
        "slots": slots,
        "required_rate": req_rate,
        "optional_rate": opt_rate,
        "delivery": round(85.0 * req_rate + 15.0 * opt_rate, 1),
        "delivered": req_rate >= min_required_rate - 1e-9,
    }


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def load_scenarios(path: str) -> tuple[dict[str, dict], list[str]]:
    """Load `*.json` scenarios. Tolerant by design: the library is being
    authored in parallel, so a missing directory, an empty one, and a malformed
    file are all reported rather than fatal."""
    notes: list[str] = []
    scenarios: dict[str, dict] = {}
    if not os.path.isdir(path):
        notes.append(f"scenario dir not found: {path}")
        return scenarios, notes
    names = sorted(n for n in os.listdir(path) if n.endswith(".json"))
    if not names:
        notes.append(f"scenario dir is empty: {path}")
    for name in names:
        full = os.path.join(path, name)
        try:
            with open(full, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            notes.append(f"unreadable scenario {name}: {exc}")
            continue
        sid = data.get("id")
        if not sid:
            notes.append(f"scenario {name} has no id, skipped")
            continue
        if not [s for s in (data.get("slots") or []) if s.get("required")]:
            notes.append(f"scenario {sid} has no required slot, skipped")
            continue
        if sid in scenarios:
            notes.append(f"duplicate scenario id {sid} ({name}), keeping the first")
            continue
        scenarios[sid] = data
    return scenarios, notes


def load_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = {"scenario_id", "response_text", "delivered"} - set(
            reader.fieldnames or []
        )
        if missing:
            raise SystemExit(f"{path}: missing required column(s): {sorted(missing)}")
        rows = []
        for line, raw in enumerate(reader, start=2):
            truth = (raw.get("delivered") or "").strip().lower()
            if truth in ("1", "true", "yes", "y"):
                delivered = True
            elif truth in ("0", "false", "no", "n"):
                delivered = False
            else:
                print(f"  ! line {line}: unlabelled `delivered`={truth!r}, row skipped")
                continue
            rows.append(
                {
                    "response_id": (raw.get("response_id") or f"L{line}").strip(),
                    "scenario_id": (raw.get("scenario_id") or "").strip(),
                    "tier": (raw.get("tier") or "").strip(),
                    "response_text": raw.get("response_text") or "",
                    "delivered": delivered,
                    "origin": (raw.get("origin") or "unspecified").strip().lower(),
                    "notes": (raw.get("notes") or "").strip(),
                }
            )
        return rows


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------

def prf(tp: int, fp: int, fn: int) -> tuple[float, float]:
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    return precision, recall


def confusion(results: list[dict]) -> dict:
    tp = sum(1 for r in results if r["pred"] and r["truth"])
    fp = sum(1 for r in results if r["pred"] and not r["truth"])
    fn = sum(1 for r in results if not r["pred"] and r["truth"])
    tn = sum(1 for r in results if not r["pred"] and not r["truth"])
    precision, recall = prf(tp, fp, fn)
    return {
        "n": len(results),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
    }


def _fmt(value: float) -> str:
    return "  n/a" if value != value else f"{value:.3f}"


def score_rows(rows, scenarios, min_required_rate):
    results, skipped = [], []
    for row in rows:
        scenario = scenarios.get(row["scenario_id"])
        if scenario is None:
            skipped.append(row)
            continue
        outcome = evaluate(scenario, row["response_text"], min_required_rate)
        tier = scenario.get("tier") or row["tier"] or "?"
        results.append(
            {
                "row": row,
                "tier": tier,
                "tier_mismatch": bool(
                    row["tier"] and scenario.get("tier") and row["tier"] != scenario["tier"]
                ),
                "pred": outcome["delivered"],
                "truth": row["delivered"],
                "delivery": outcome["delivery"],
                "required_rate": outcome["required_rate"],
                "slots": outcome["slots"],
            }
        )
    return results, skipped


def slot_trace(result: dict) -> str:
    parts = []
    for slot in result["slots"]:
        mark = "HIT " if slot["hit"] else "MISS"
        tag = "req" if slot["required"] else "opt"
        detail = f"<-{slot['matched'][0]!r}" if slot["matched"] else ""
        parts.append(f"{slot['key']}[{tag}]={mark}{detail}")
    return "  ".join(parts)


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def report_disagreements(results: list[dict]) -> None:
    """Precision-hurting errors first: a bare precision number is not
    reviewable, the reviewer needs to see WHY each call was wrong."""
    groups = (
        (
            "FALSE POSITIVES -- matcher said delivered, human said not "
            "(these are the costly ones: the learner is taught a wrong expression)",
            [r for r in results if r["pred"] and not r["truth"]],
        ),
        (
            "FALSE NEGATIVES -- matcher said not delivered, human said delivered "
            "(cost is one free retry; usually a hole in `accept`)",
            [r for r in results if not r["pred"] and r["truth"]],
        ),
    )
    for title, bad in groups:
        print(f"\n-- {title}")
        if not bad:
            print("   (none)")
            continue
        for r in bad:
            row = r["row"]
            print(f"   [{row['response_id']}] {row['scenario_id']} / {r['tier']}")
            print(f"     text     : {row['response_text']!r}")
            print(
                f"     matcher  : delivery={r['delivery']:.1f} "
                f"required_rate={r['required_rate']:.2f} -> "
                f"delivered={r['pred']}   human={r['truth']}"
            )
            print(f"     slots    : {slot_trace(r)}")
            if row["notes"]:
                print(f"     labeller : {row['notes']}")


def report_threshold_sweep(rows, scenarios) -> None:
    print("\n== delivered-rule sensitivity (required-slot hit rate needed) ==")
    print("   rule   n    tp  fp  fn  precision  recall")
    for threshold in (0.5, 0.67, 1.0):
        results, _ = score_rows(rows, scenarios, threshold)
        c = confusion(results)
        print(
            f"  >={threshold:.2f} {c['n']:>4}  {c['tp']:>4}{c['fp']:>4}{c['fn']:>4}"
            f"     {_fmt(c['precision'])}   {_fmt(c['recall'])}"
        )
    print("   Looser rules buy recall with precision. G1 ranks precision first,")
    print("   so the default rule is the strictest one (>=1.00).")


def write_audit_csv(results, skipped, path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "response_id",
                "scenario_id",
                "tier",
                "origin",
                "response_text",
                "human_delivered",
                "predicted_delivered",
                "delivery",
                "required_rate",
                "outcome",
                "slot_trace",
                "reviewer_verdict(agree/matcher_wrong/label_wrong)",
            ]
        )
        for r in results:
            row = r["row"]
            if r["pred"] and r["truth"]:
                outcome = "TP"
            elif r["pred"]:
                outcome = "FP"
            elif r["truth"]:
                outcome = "FN"
            else:
                outcome = "TN"
            writer.writerow(
                [
                    row["response_id"],
                    row["scenario_id"],
                    r["tier"],
                    row["origin"],
                    row["response_text"],
                    int(r["truth"]),
                    int(r["pred"]),
                    f"{r['delivery']:.1f}",
                    f"{r['required_rate']:.2f}",
                    outcome,
                    slot_trace(r),
                    "",
                ]
            )
        for row in skipped:
            writer.writerow(
                [
                    row["response_id"],
                    row["scenario_id"],
                    row["tier"],
                    row["origin"],
                    row["response_text"],
                    int(row["delivered"]),
                    "",
                    "",
                    "",
                    "SKIPPED_NO_SCENARIO",
                    "",
                    "",
                ]
            )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="R-14 G1 harness: deterministic slot matching precision/recall."
    )
    ap.add_argument(
        "--scenarios",
        default=_DEFAULT_SCENARIOS,
        help="directory of scenario JSON files (default: core/game_scenarios)",
    )
    ap.add_argument(
        "--labels",
        default=_DEFAULT_LABELS,
        help="hand-labelled response CSV (default: the smoke fixture)",
    )
    ap.add_argument(
        "--min-required-rate",
        type=float,
        default=1.0,
        help="required-slot hit rate needed to predict delivered (default 1.0)",
    )
    ap.add_argument(
        "--no-doc-examples",
        action="store_true",
        help="do not fall back to the §5.5 doc examples for missing scenario ids",
    )
    ap.add_argument("--out-csv", help="write a per-response audit CSV here")
    args = ap.parse_args()

    print("== R-14 G1 -- deterministic slot matching vs human `delivered` ==")
    print(f"scenarios : {args.scenarios}")
    print(f"labels    : {args.labels}")

    scenarios, notes = load_scenarios(args.scenarios)
    for note in notes:
        print(f"  ! {note}")
    print(f"  loaded {len(scenarios)} scenario(s) from disk")

    if not args.no_doc_examples:
        added = [
            s["id"] for s in DOC_EXAMPLE_SCENARIOS if s["id"] not in scenarios
        ]
        for scenario in DOC_EXAMPLE_SCENARIOS:
            scenarios.setdefault(scenario["id"], scenario)
        if added:
            print(
                "  ! using docs/survival-game.md §5.5 example scenario(s) as a "
                f"fallback for: {', '.join(added)}"
            )
            print(
                "    (fallback keeps the harness runnable before the library "
                "lands; disk scenarios always win)"
            )

    if not os.path.exists(args.labels):
        print(f"\nlabel CSV not found: {args.labels}")
        return 2
    rows = load_rows(args.labels)
    if not rows:
        print("\nno labelled rows, nothing to measure")
        return 2

    origins = {}
    for row in rows:
        origins[row["origin"]] = origins.get(row["origin"], 0) + 1
    synthetic = sum(count for origin, count in origins.items() if origin != "real")
    print(
        "  labelled rows: "
        + ", ".join(f"{count} {origin}" for origin, count in sorted(origins.items()))
    )

    results, skipped = score_rows(rows, scenarios, args.min_required_rate)
    if skipped:
        print(f"\n  ! {len(skipped)} row(s) skipped -- no scenario for their id:")
        for sid in sorted({r["scenario_id"] for r in skipped}):
            n = sum(1 for r in skipped if r["scenario_id"] == sid)
            print(f"      {sid or '(blank)'} x{n}")
    for r in results:
        if r["tier_mismatch"]:
            print(
                f"  ! tier mismatch on {r['row']['response_id']}: CSV says "
                f"{r['row']['tier']}, scenario says {r['tier']} (scenario wins)"
            )
    if not results:
        print("\nno row could be scored, nothing to measure")
        return 2

    overall = confusion(results)
    print(f"\n== OVERALL (delivered rule: required_rate >= {args.min_required_rate:.2f}) ==")
    print(
        f"  n={overall['n']}  tp={overall['tp']} fp={overall['fp']} "
        f"fn={overall['fn']} tn={overall['tn']}"
    )
    print(
        f"  precision = {_fmt(overall['precision'])}   (G1 needs >= {GATE_PRECISION:.2f}"
        "  <- the binding one)"
    )
    print(f"  recall    = {_fmt(overall['recall'])}   (G1 needs >= {GATE_RECALL:.2f})")

    print("\n== PER TIER ==")
    print("  tier          n  (need>=50)   tp  fp  fn  precision  recall")
    for tier in TIERS:
        subset = [r for r in results if r["tier"] == tier]
        if not subset:
            print(f"  {tier:<12} {0:>3}  SHORT BY 50    --  --  --      n/a     n/a")
            continue
        c = confusion(subset)
        short = "" if c["n"] >= GATE_PER_TIER else f"  SHORT BY {GATE_PER_TIER - c['n']}"
        print(
            f"  {tier:<12} {c['n']:>3}{short:<15}{c['tp']:>4}{c['fp']:>4}{c['fn']:>4}"
            f"     {_fmt(c['precision'])}   {_fmt(c['recall'])}"
        )
    other = sorted({r["tier"] for r in results} - set(TIERS))
    for tier in other:
        c = confusion([r for r in results if r["tier"] == tier])
        print(f"  {tier:<12} {c['n']:>3}  (not a G1 tier)")

    report_disagreements(results)
    report_threshold_sweep(rows, scenarios)

    if args.out_csv:
        write_audit_csv(results, skipped, args.out_csv)
        print(f"\nwrote per-response audit CSV -> {args.out_csv}")

    print("\n== VERDICT ==")
    if synthetic:
        print(f"  {SYNTHETIC_LABEL}")
        print(
            f"  {synthetic}/{len(rows)} labelled row(s) are not real learner "
            "responses (origin != real)."
        )
        print("  NO PASS/FAIL IS ISSUED. The numbers above only show that the")
        print("  harness runs end to end; they are not G1's measured result and")
        print("  must not be written into the R-14 review or the PRD.")
        print("\n  Outstanding for G1:")
        print(
            f"    - {GATE_TOTAL} hand-labelled REAL learner responses "
            f"(>= {GATE_PER_TIER} per tier). Collection protocol: "
            "scripts/fixtures/game_delivery/README.md"
        )
        print("    - re-run with --labels pointing at that set; a verdict is")
        print("      issued only when every row has origin=real")
        return 1

    coverage_ok = all(
        sum(1 for r in results if r["tier"] == tier) >= GATE_PER_TIER for tier in TIERS
    )
    total_ok = overall["n"] >= GATE_TOTAL
    precision_ok = overall["precision"] >= GATE_PRECISION
    recall_ok = overall["recall"] >= GATE_RECALL
    for label, ok in (
        (f"total >= {GATE_TOTAL}", total_ok),
        (f"every tier >= {GATE_PER_TIER}", coverage_ok),
        (f"precision >= {GATE_PRECISION:.2f}", precision_ok),
        (f"recall >= {GATE_RECALL:.2f}", recall_ok),
    ):
        print(f"  [{'ok' if ok else 'NO'}] {label}")
    passed = total_ok and coverage_ok and precision_ok and recall_ok
    print(f"\n  G1: {'PASS' if passed else 'FAIL'}")
    if not passed:
        print(
            "  R-14 §0: thresholds may not be relaxed to pass. Fix the `accept` "
            "sets or the sample, not the criterion."
        )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
