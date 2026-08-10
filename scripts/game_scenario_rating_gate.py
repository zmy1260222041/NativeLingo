#!/usr/bin/env python3
"""G3 measurement harness for R-14 (Survival module, scenario library quality).

WHAT THIS MEASURES
  R-14 §2 G3 fixes the criterion *before* implementation:
      scenarios >= 40, covering the first three needs-pyramid layers,
      human ratings of 日常常见度 (commonness) and 需求贴合度 (fitness),
      both on 1-5, both mean >= 4.0
  The first two halves are properties of the data and were cleared in an earlier
  round (45 scenarios; layers {1:18, 2:12, 3:12, 4:3}; provenance 45/45). This
  script is the *third* half: it emits a blank rating sheet, reads it back, and
  reports the two means overall and per tier.

WHY A HUMAN HAS TO FILL IT IN -- AND WHY NOT THE AUTHOR
  "This situation is common in real life" is an empirical claim about the world,
  not about the repo. Nothing in the scenario files can settle it. What *can* be
  checked mechanically was already checked: provenance completeness, tier
  admission reachability, NGSL rank citations.

  R-14 §2 G3 says plainly: 「agent 自评不算」. The 45 scenarios were written by an
  agent; that same agent scoring them reproduces the judgement it made while
  writing them, which measures nothing. This is the same failure mode R-14 §0
  was written against -- deciding a criterion after seeing the result makes the
  criterion meaningless.

THE RATER MUST NOT SEE `provenance.rationale` WHILE SCORING
  `rationale` is the author's *argument for why the scenario is common*. A rater
  who reads it first is grading that argument rather than the situation, which
  inflates commonness exactly where the author was most persuasive. So the sheet
  ships the six fields a rater needs and withholds rationale -- the same
  whitelist-not-blacklist reasoning as scripts/collect/serve.py::_strip, for the
  same reason: structural guarantee, not rendering discipline.

  G3 also requires a provenance audit ("逐条核"). That is a SEPARATE pass, run
  with --review after scoring is locked, so it cannot contaminate the scores.

WHY THIS LIVES IN scripts/ AND NOT core/
  Same precedent as the G1/G2 harnesses: gate prototypes live in scripts/ and
  product code follows the review (mdd_margin_sweep.py R-4, photo_gate.py R-13).

Usage::

    python3 scripts/game_scenario_rating_gate.py --emit        # blank sheet
    # fill commonness/fitness (1-5) in a spreadsheet, save as CSV
    python3 scripts/game_scenario_rating_gate.py               # verdict
    python3 scripts/game_scenario_rating_gate.py --review      # provenance pass
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SCENARIOS = REPO_ROOT / "desktop" / "backend" / "core" / "game_scenarios"
_DEFAULT_SHEET = REPO_ROOT / "scripts" / "fixtures" / "game_scenarios" / "ratings.csv"

# R-14 §2 G3, verbatim. Not adjustable by flag: §0 forbids relaxing a criterion
# to make it pass, and a --threshold flag is exactly that with extra steps.
GATE_MIN_SCENARIOS = 40
GATE_MEAN = 4.0
GATE_PYRAMID_LAYERS = (1, 2, 3)
SCALE_MIN, SCALE_MAX = 1, 5

TIERS = ("infant", "toddler", "youth", "professional")

# The rater sees these and nothing else. Adding a scenario field must not
# silently widen what a rater is shown, so this is a whitelist.
SHEET_COLUMNS = (
    "scenario_id",
    "tier",
    "need",
    "maslow_level",
    "situation_zh",
    "npc_greeting",
    "commonness",
    "fitness",
    "notes",
)

SELF_RATED_LABEL = "作者自评，不可回填 R-14"


def load_scenarios(directory: str | Path) -> tuple[list[dict], list[str]]:
    """Read scenario JSON files. Returns (scenarios, warnings)."""
    path = Path(directory)
    scenarios: list[dict] = []
    warnings: list[str] = []
    if not path.is_dir():
        return scenarios, [f"scenario directory not found: {path}"]
    for entry in sorted(path.glob("*.json")):
        try:
            raw = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"unreadable, skipped: {entry.name} ({exc})")
            continue
        if not raw.get("id"):
            warnings.append(f"no id, skipped: {entry.name}")
            continue
        scenarios.append(raw)
    return scenarios, warnings


def sheet_row(scenario: dict) -> dict:
    """Project a scenario onto the rater-visible whitelist.

    `provenance.rationale` is deliberately absent -- see the module docstring.
    """
    situation = scenario.get("situation") or {}
    npc = scenario.get("npc") or {}
    return {
        "scenario_id": scenario.get("id", ""),
        "tier": scenario.get("tier", ""),
        "need": scenario.get("need", ""),
        "maslow_level": scenario.get("maslow_level", ""),
        "situation_zh": situation.get("zh", ""),
        "npc_greeting": npc.get("greeting", ""),
        "commonness": "",
        "fitness": "",
        "notes": "",
    }


def emit_sheet(scenarios: list[dict], destination: Path, force: bool) -> int:
    if destination.exists() and not force:
        print(f"refusing to overwrite existing sheet: {destination}")
        print("  ratings are hand-entered and unrecoverable; pass --force to replace,")
        print("  or move the existing file aside first.")
        return 2
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Ordered by tier then need so a rater meets similar scenarios together and
    # applies a steadier bar; scoring order is not part of the criterion.
    ordered = sorted(
        scenarios,
        key=lambda s: (
            TIERS.index(s.get("tier", "")) if s.get("tier") in TIERS else len(TIERS),
            s.get("need", ""),
            s.get("id", ""),
        ),
    )
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(SHEET_COLUMNS))
        writer.writeheader()
        for scenario in ordered:
            writer.writerow(sheet_row(scenario))
    print(f"blank rating sheet written: {destination}")
    print(f"  {len(ordered)} scenario(s), two columns to fill")
    print()
    print("  encoding is UTF-8 with BOM so Excel opens the Chinese text correctly.")
    print("  Fill `commonness` and `fitness` with integers 1-5. `notes` is free text")
    print("  and is where a score below 4 should say what is wrong -- that note is")
    print("  what makes the scenario fixable.")
    print()
    print("  The sheet deliberately omits provenance.rationale: it is the author's")
    print("  argument for why the scenario is common, and reading it first turns the")
    print("  rating into a review of that argument. Audit provenance separately")
    print("  with --review, after the scores are locked.")
    return 0


def _parse_score(raw: str, field: str, row_id: str, problems: list[str]) -> float | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        problems.append(f"{row_id}: {field}={text!r} is not a number")
        return None
    if not SCALE_MIN <= value <= SCALE_MAX:
        problems.append(
            f"{row_id}: {field}={value:g} is outside the {SCALE_MIN}-{SCALE_MAX} scale"
        )
        return None
    return value


def _header_offset(text: str) -> int:
    """Index of the real header line.

    Numbers exports a CSV whose first line is the *sheet name* ("ratings"),
    which DictReader would take as the header -- every field then reads as None,
    every row is skipped for having no scenario_id, and the gate reports "no
    scores" for a fully filled sheet. Silently mistaking a filled sheet for an
    empty one is the failure mode worth spending code on, so the header is
    located rather than assumed to be line 1.
    """
    for index, line in enumerate(text.splitlines()):
        if line.lstrip("﻿").startswith("scenario_id"):
            return index
    return 0


def load_ratings(path: Path) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    problems: list[str] = []
    text = path.read_text(encoding="utf-8-sig")
    body = "\n".join(text.splitlines()[_header_offset(text) :])
    with io.StringIO(body, newline="") as handle:
        for raw in csv.DictReader(handle):
            scenario_id = (raw.get("scenario_id") or "").strip()
            if not scenario_id:
                continue
            rows.append(
                {
                    "scenario_id": scenario_id,
                    "tier": (raw.get("tier") or "").strip(),
                    "need": (raw.get("need") or "").strip(),
                    "commonness": _parse_score(
                        raw.get("commonness", ""), "commonness", scenario_id, problems
                    ),
                    "fitness": _parse_score(
                        raw.get("fitness", ""), "fitness", scenario_id, problems
                    ),
                    "notes": (raw.get("notes") or "").strip(),
                    "rater": (raw.get("rater") or "").strip(),
                }
            )
    return rows, problems


def summarise(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": float("nan")}
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "min": min(values),
        "max": max(values),
    }


def report(scenarios: list[dict], rows: list[dict], problems: list[str]) -> int:
    known_ids = {s["id"] for s in scenarios}
    rated_ids = {r["scenario_id"] for r in rows}

    unknown = sorted(rated_ids - known_ids)
    unrated = sorted(known_ids - rated_ids)
    scored = [r for r in rows if r["commonness"] is not None and r["fitness"] is not None]
    partial = [r for r in rows if r not in scored and (r["commonness"] or r["fitness"])]
    blank = [r for r in rows if r["commonness"] is None and r["fitness"] is None]

    print("== R-14 G3 -- 场景库人工评分 ==")
    print(f"  磁盘场景        {len(scenarios)}")
    print(f"  表内行          {len(rows)}")
    print(f"  两项都已评分    {len(scored)}")
    if partial:
        print(f"  只评了一项      {len(partial)}  <- 两项都需要,否则该场景不计入")
    if blank:
        print(f"  完全未评分      {len(blank)}")
    print()

    if problems:
        print("## 表格问题(必须先修)")
        for problem in problems[:20]:
            print(f"  ! {problem}")
        if len(problems) > 20:
            print(f"  ... 另有 {len(problems) - 20} 条")
        print()
    if unknown:
        print(f"## 表内有、磁盘上没有的 id({len(unknown)} 个)")
        for scenario_id in unknown[:10]:
            print(f"  ? {scenario_id}")
        print("  场景库改动后须重新生成表格,否则评的是已不存在的场景。")
        print()

    if not scored:
        print("## 结论")
        print("  ⬜ 不可判 —— 没有任何场景拿到两项完整评分。")
        print(f"  先跑 --emit 生成表格,填 commonness / fitness 两列(1-{SCALE_MAX})。")
        return 2

    commonness = [r["commonness"] for r in scored]
    fitness = [r["fitness"] for r in scored]
    c_stats, f_stats = summarise(commonness), summarise(fitness)

    print("## 两项均值(判据:均 >= 4.0)")
    for label, stats in (("日常常见度", c_stats), ("需求贴合度", f_stats)):
        flag = "ok" if stats["mean"] >= GATE_MEAN else "NO"
        print(
            f"  [{flag}] {label}  mean {stats['mean']:.2f}"
            f"  (n={stats['n']}, min {stats['min']:g}, max {stats['max']:g})"
        )
    print()

    print("## 逐 tier(不构成判据,但单档偏低会被总均值掩盖)")
    for tier in TIERS:
        subset = [r for r in scored if r["tier"] == tier]
        if not subset:
            print(f"  {tier:14} 无评分行")
            continue
        c_mean = statistics.fmean([r["commonness"] for r in subset])
        f_mean = statistics.fmean([r["fitness"] for r in subset])
        warn = "  <- 低于 4.0" if min(c_mean, f_mean) < GATE_MEAN else ""
        print(
            f"  {tier:14} n={len(subset):3}  常见度 {c_mean:.2f}  贴合度 {f_mean:.2f}{warn}"
        )
    print()

    below = sorted(
        [r for r in scored if min(r["commonness"], r["fitness"]) < GATE_MEAN],
        key=lambda r: min(r["commonness"], r["fitness"]),
    )
    if below:
        print(f"## 低于 4.0 的场景({len(below)} 个)—— 要么改写要么替换")
        for row in below:
            note = f"  — {row['notes']}" if row["notes"] else ""
            print(
                f"  {row['tier']:13} {row['scenario_id']:44}"
                f" 常{row['commonness']:g} 贴{row['fitness']:g}{note}"
            )
        missing_notes = [r for r in below if not r["notes"]]
        if missing_notes:
            print()
            print(
                f"  {len(missing_notes)} 个低分场景没有 notes —— 没有理由的低分改不动它,"
            )
            print("  补一句「哪里不常见 / 哪里不贴合」比分数本身有用。")
        print()

    print("== VERDICT ==")
    if problems:
        # A malformed cell is dropped from the mean by _parse_score. If the
        # dropped cell held a LOW score, the mean goes UP -- so a typo silently
        # makes the gate more optimistic, which is the one failure mode R-14 §0
        # forbids. No verdict until the sheet parses cleanly.
        print(f"  ⬜ 不可判 —— 表格有 {len(problems)} 处解析不了的格子(上面已列出)。")
        print("  解析不了的分数会被丢出均值:若丢掉的是低分,均值反而升高 ——")
        print("  一个因为打字错误而变宽松的判据。先把那几格改成 1-5 的整数,再重跑。")
        print("  NO PASS/FAIL IS ISSUED.")
        return 2

    raters = {r["rater"] for r in rows if r["rater"]}
    self_rated = any(r.lower() in {"agent", "claude", "author", "作者"} for r in raters)
    if self_rated:
        print(f"  {SELF_RATED_LABEL}")
        print("  R-14 §2 G3 明写「agent 自评不算」——场景由 agent 写,自评即重复写作时的判断。")
        print("  NO PASS/FAIL IS ISSUED.")
        return 1

    coverage_ok = len(scored) >= len(known_ids) and not unrated
    count_ok = len(scored) >= GATE_MIN_SCENARIOS
    c_ok = c_stats["mean"] >= GATE_MEAN
    f_ok = f_stats["mean"] >= GATE_MEAN

    layers = {int(s["maslow_level"]) for s in scenarios if str(s.get("maslow_level", "")).isdigit()}
    layers_ok = set(GATE_PYRAMID_LAYERS).issubset(layers)

    for label, ok in (
        (f"已评分场景 >= {GATE_MIN_SCENARIOS}", count_ok),
        ("场景库全部已评分(无遗漏)", coverage_ok),
        (f"需求金字塔前三层齐({sorted(layers)})", layers_ok),
        (f"日常常见度均值 >= {GATE_MEAN}", c_ok),
        (f"需求贴合度均值 >= {GATE_MEAN}", f_ok),
    ):
        print(f"  [{'ok' if ok else 'NO'}] {label}")
    if not coverage_ok:
        # Two distinct ways to fall short, and they need different fixes: a row
        # absent from the sheet vs a row present but missing one of the two
        # scores. Reporting only the first leaves the second unexplained.
        if unrated:
            print(f"       表内没有的场景 {len(unrated)} 个:{', '.join(unrated[:5])}")
        incomplete = sorted(r["scenario_id"] for r in rows if r not in scored)
        if incomplete:
            print(
                f"       表内有但两项没填齐的 {len(incomplete)} 个:"
                f"{', '.join(incomplete[:5])}"
            )

    passed = count_ok and coverage_ok and layers_ok and c_ok and f_ok
    print(f"\n  G3 评分侧: {'PASS' if passed else 'FAIL'}")
    if not passed:
        print(
            "  R-14 §0:不得为了通过而放宽阈值。低分场景要改写或替换,不是改判据。"
        )
    return 0 if passed else 1


def review_provenance(scenarios: list[dict], sheet: Path) -> int:
    """The separate provenance pass G3 also requires ("逐条核").

    Deliberately a different invocation from scoring: reading the author's
    rationale while scoring inflates commonness where the author argued best.
    """
    print("== R-14 G3 -- provenance 逐条核(评分之后单独跑)==")
    scores: dict[str, tuple] = {}
    if sheet.exists():
        rows, _ = load_ratings(sheet)
        # BOTH scores required, matching `scored` in report(): a half-filled row
        # is not a rating, and admitting one here puts a None into the sort key.
        scores = {
            r["scenario_id"]: (r["commonness"], r["fitness"])
            for r in rows
            if r["commonness"] is not None and r["fitness"] is not None
        }
        print(f"  已读入评分:{len(scores)} 个场景(低分优先列出)\n")
    else:
        print("  尚无评分表 —— 按 tier 顺序列出\n")

    missing: list[str] = []

    def sort_key(scenario: dict):
        pair = scores.get(scenario["id"])
        # Unrated sorts last (99 is above the 1-5 scale). Belt-and-braces on the
        # None filter above so a future change to `scores` cannot crash the sort.
        rank = min(pair) if pair and None not in pair else 99
        return (rank, scenario.get("tier", ""))

    for scenario in sorted(scenarios, key=sort_key):
        provenance = scenario.get("provenance") or {}
        rationale = (provenance.get("rationale") or "").strip()
        basis = (provenance.get("frequency_basis") or "").strip()
        if not rationale or not basis:
            missing.append(scenario["id"])
        pair = scores.get(scenario["id"])
        score_text = f"  [常{pair[0]:g} 贴{pair[1]:g}]" if pair else ""
        print(f"--- {scenario['id']}  ({scenario.get('tier')}){score_text}")
        print(f"    情境: {(scenario.get('situation') or {}).get('zh', '')}")
        print(f"    为何常见: {rationale or '(空 —— G3 不计入 40 个)'}")
        print(f"    依据: {basis or '(空)'}")
        print()

    print("== 结论 ==")
    print(f"  provenance 两字段齐全  {len(scenarios) - len(missing)}/{len(scenarios)}")
    if missing:
        print(f"  ! 空 provenance 的场景不计入 G3 的 40 个:{', '.join(missing)}")
        return 1
    print("  按 G3「空 provenance 的场景不计入 40 个」,本项成立。")
    print("  剩下的是人的工作:逐条判断 rationale 讲的理由是否站得住。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="R-14 G3 harness: human commonness/fitness ratings for the scenario library."
    )
    ap.add_argument("--scenarios", default=str(_DEFAULT_SCENARIOS))
    ap.add_argument("--sheet", default=str(_DEFAULT_SHEET))
    ap.add_argument("--emit", action="store_true", help="write a blank rating sheet")
    ap.add_argument("--force", action="store_true", help="allow --emit to overwrite")
    ap.add_argument(
        "--review",
        action="store_true",
        help="provenance audit pass; run AFTER scoring, not before",
    )
    args = ap.parse_args()

    scenarios, warnings = load_scenarios(args.scenarios)
    for warning in warnings:
        print(f"  ! {warning}")
    if not scenarios:
        return 2

    sheet = Path(args.sheet)
    if args.emit:
        return emit_sheet(scenarios, sheet, args.force)
    if args.review:
        return review_provenance(scenarios, sheet)

    if not sheet.exists():
        print(f"rating sheet not found: {sheet}")
        print("  run with --emit first, then fill commonness / fitness")
        return 2
    rows, problems = load_ratings(sheet)
    return report(scenarios, rows, problems)


if __name__ == "__main__":
    sys.exit(main())
