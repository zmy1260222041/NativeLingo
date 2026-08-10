#!/usr/bin/env python3
"""R-14 / G3: check every scenario's ``provenance.frequency_basis`` against real
NGSL ranks (FR-20).

Why this script exists. The 42 scenarios were authored *before* the wordlist was
chosen, so every "最低频段" / "中低频段" / "高频词" claim was the author's
judgement, not a table lookup. Bundling NGSL makes those claims *checkable*;
it does not make them *checked*. This is the lookup.

``please`` at NGSL rank 471 is the standing warning: a word that feels maximally
basic is not necessarily in the lowest band.

Two word sources per scenario, deliberately kept apart in the report:
  * words named inline in ``frequency_basis`` -- the claim's own evidence, so a
    miss here is the claim contradicting itself
  * ``accept`` terms of **required** slots -- what the player must actually
    produce. Optional slots are excluded: failing them costs nothing, so their
    vocabulary is not what the difficulty claim is about.

Multi-word ``accept`` entries ("can i have", "something to eat") are scored by
their worst constituent word -- a phrase is no easier than its hardest token.

Band thresholds are read off the NGSL SFI rank distribution and stated here
rather than inferred, so a reviewer can disagree with the boundary rather than
with a hidden constant. Out-of-NGSL words are **not** silently treated as rare:
NGSL is 2,809 lemmas and stops there, so absence means "outside this list",
which is reported as its own category.

Usage:
  python scripts/game_provenance_check.py [--assets DIR] [--scenarios DIR]
                                          [--json-out F] [--verbose]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ASSETS = REPO_ROOT / "desktop" / "backend" / "assets" / "wordlists"
DEFAULT_SCENARIOS = REPO_ROOT / "desktop" / "backend" / "core" / "game_scenarios"

# Band boundaries over NGSL SFI rank. NGSL is ordered by frequency, so a rank
# ceiling is the natural reading of "频段". These two numbers are the only
# judgement calls in the script; everything else is lookup.
BAND_LOWEST = 1000       # 最低频段 / 首千词
BAND_LOWER_MID = 2000    # 中低频段

# Claim classes, matched against the Chinese wording actually used in the 42
# files. Ordered most-specific first -- "最低频段" must beat the looser
# "高频/常用" catch-all.
CLAIM_PATTERNS = [
    ("lowest", BAND_LOWEST, ("最低频段", "首千词", "最低频")),
    ("lower_mid", BAND_LOWER_MID, ("中低频段", "中低频")),
    ("common", None, ("高频词", "常用词", "常用职场词", "高频生活词", "高频职场词",
                      "最常用", "常用的", "高频的", "日常高频")),
]

# NGSL's own structural gaps, confirmed by probing the staged file rather than
# assumed. NGSL is a *general service* list built for reading coverage, so it
# omits three classes this module leans on heavily:
#   * cardinal numerals beyond `one` (two/three/four/five/ten all absent, while
#     one#35 / first#78 / second#226 are present)
#   * weekday and month names (all absent)
#   * low-frequency concrete household objects (toilet, soap, towel, blanket,
#     apple, soup, porridge, basin absent -- while bread#2262, cup#1491,
#     coat#1863 are present but late)
# A word landing here is **not** evidence the scenario is too hard. It means
# NGSL cannot grade it, so the level list must. Reporting it as "over band"
# would be the frequency table's blind spot masquerading as scenario difficulty.
NGSL_BLIND_SPOTS = {
    "numeral": {"two", "three", "four", "five", "six", "seven", "eight", "nine",
                "ten", "twenty", "thirty", "hundred"},
    "weekday_month": {"monday", "tuesday", "wednesday", "thursday", "friday",
                      "saturday", "sunday", "january", "february", "march",
                      "april", "june", "july", "august", "september", "october",
                      "november", "december"},
}


# Function words and inflections NGSL lists under a different lemma, or not at
# all because they are grammatical rather than lexical. Excluding them keeps the
# report about content vocabulary; each is listed explicitly rather than hidden
# behind a stopword library, because "which words don't count" is a reviewable
# decision.
GRAMMATICAL = {
    "a", "an", "the", "i", "me", "my", "you", "your", "it", "is", "am", "are",
    "was", "were", "be", "to", "of", "and", "or", "not", "no", "do", "does",
    "did", "have", "has", "had", "there", "this", "that", "these", "those",
    "ok", "okay", "please", "yes",
    # Object and possessive pronouns. NGSL ranks the subject form only
    # (they#13 / we#16 / he#11 / she#24) and stores no entry for them / their /
    # us / him / her, so leaving these in would report pronouns as vocabulary
    # NGSL cannot grade -- which is a lookup artefact, not scenario difficulty.
    "them", "their", "theirs", "us", "him", "her", "hers", "his", "we", "they",
}

# Irregular forms NGSL stores only under the base lemma. Without these the
# script reports false absences (`lost`, `broken`, `teeth`, `made` are all in
# NGSL under `lose` #305 / `break` #368 / `tooth` #2026 / `make` #48), which
# would overstate how much scenario vocabulary sits outside the list.
IRREGULAR = {
    "lost": "lose", "broken": "break", "broke": "break", "made": "make",
    "teeth": "tooth", "feet": "foot", "went": "go", "gone": "go", "came": "come",
    "ate": "eat", "eaten": "eat", "drank": "drink", "drunk": "drink",
    "slept": "sleep", "took": "take", "taken": "take", "gave": "give",
    "given": "give", "got": "get", "said": "say", "told": "tell",
    "bought": "buy", "paid": "pay", "left": "leave", "felt": "feel",
    "wrote": "write", "written": "write", "sent": "send",
    "spoke": "speak", "spoken": "speak", "knew": "know", "known": "know",
    "thought": "think", "meant": "mean", "built": "build",
    "held": "hold", "kept": "keep", "lent": "lend", "sold": "sell",
    "worse": "bad", "worst": "bad", "better": "good", "best": "good",
    "fell": "fall", "fallen": "fall", "forgot": "forget", "forgotten": "forget",
    "swam": "swim", "sat": "sit", "stood": "stand", "found": "find",
    "heard": "hear", "read": "read", "understood": "understand",
    # derived forms NGSL lists only under the base
    "later": "late", "latest": "late", "yours": "you", "mine": "my",
    "unsafe": "safe", "unwell": "well",
    # Contractions and negated modals: NGSL lists the bare modal. Both the
    # apostrophe and apostrophe-less spellings appear in `accept` on purpose --
    # ASR output routinely drops the apostrophe, so the scenarios list `cant`
    # beside `can't`. Both must resolve, or the bare spellings read as words
    # NGSL does not contain.
    "cannot": "can", "can't": "can", "cant": "can",
    "won't": "will", "wont": "will",
    "don't": "do", "dont": "do", "doesn't": "do", "doesnt": "do",
    "didn't": "do", "didnt": "do",
    "isn't": "be", "isnt": "be", "aren't": "be", "arent": "be",
    "i'm": "be", "im": "be", "it's": "be", "its": "be",
    "what's": "what", "whats": "what",
    "i've": "have", "ive": "have", "haven't": "have", "havent": "have",
    "wouldn't": "will", "wouldnt": "will",
    "couldn't": "can", "couldnt": "can",
    "shouldn't": "shall", "shouldnt": "shall",
}


# NGSL lists only base lemmas. These suffix rules are the minimum needed to look
# up scenario wording; they are not a general lemmatiser and are applied only as
# a fallback after an exact hit fails.
def _lemma_candidates(word: str) -> list[str]:
    out = [word]
    if word in IRREGULAR:
        out.append(IRREGULAR[word])
    for suffix, replacement in (
        ("ies", "y"),   # cities -> city
        ("ied", "y"),   # studied -> study
        ("ier", "y"),   # easier -> easy
        ("iest", "y"),  # easiest -> easy
        ("ing", ""), ("es", ""), ("ed", ""), ("er", ""), ("est", ""), ("s", ""),
    ):
        if word.endswith(suffix) and len(word) > len(suffix) + 1:
            stem = word[: -len(suffix)] + replacement
            out.append(stem)
            out.append(stem + "e")          # hoping -> hope
            if stem and stem[-1] == stem[-2:-1]:
                out.append(stem[:-1])        # stopped -> stop
    return out


def load_ngsl(path: Path) -> dict[str, int]:
    ranks: dict[str, int] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            lemma = (row.get("Lemma") or "").strip().lower()
            raw = (row.get("SFI Rank") or "").strip()
            if not lemma or not raw:
                continue
            try:
                ranks[lemma] = int(float(raw))
            except ValueError:
                continue
    return ranks


def rank_of(word: str, ranks: dict[str, int]) -> int | None:
    for candidate in _lemma_candidates(word):
        if candidate in ranks:
            return ranks[candidate]
    return None


def words_in(text: str) -> list[str]:
    """Latin-script word tokens, lowercased. Chinese is skipped by the regex."""
    return [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'-]*", text)]


def named_words(frequency_basis: str) -> list[str]:
    """Words the claim itself puts forward as evidence.

    The files name them as ``a / b / c`` runs or inline in quoted rough forms.
    Only the slash-separated runs are taken: the quoted 「粗糙形式」 examples are
    illustrations of tolerated learner output, not vocabulary claims.
    """
    stripped = re.sub(r"[「『][^」』]*[」』]", " ", frequency_basis)
    out: list[str] = []
    for run in re.findall(r"[A-Za-z][A-Za-z'\- ]*(?:/[A-Za-z'\- ]+)+", stripped):
        for part in run.split("/"):
            out.extend(words_in(part))
    seen: set[str] = set()
    return [w for w in out if not (w in seen or seen.add(w))]


def required_accept_words(scenario: dict) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for slot in scenario.get("slots", []):
        if not slot.get("required"):
            continue
        for phrase in slot.get("accept", []):
            for word in words_in(phrase):
                if word not in seen:
                    seen.add(word)
                    out.append(word)
    return out


RANK_CITATION = re.compile(r"[A-Za-z][A-Za-z'-]*#\d+")


def classify_claim(frequency_basis: str) -> tuple[str, int | None]:
    """Classify what kind of frequency claim the wording makes.

    A basis citing explicit ``word#rank`` figures is a **per-word measured**
    statement, not a blanket band assertion -- "cover#424 在最低频段" says
    something about `cover`, not about every word in the scenario. Applying a
    band ceiling to all required words there would manufacture failures out of
    wording that is already precise. Those citations are validated against NGSL
    by ``reword_frequency_basis.py``, which refuses to write a wrong rank.
    """
    if RANK_CITATION.search(frequency_basis):
        return "measured", None
    for name, ceiling, needles in CLAIM_PATTERNS:
        if any(needle in frequency_basis for needle in needles):
            return name, ceiling
    return "unstated", None


def asserted_absent(frequency_basis: str) -> set[str]:
    """Words the wording itself declares absent from NGSL.

    Reporting these as "absent" would flag the text for saying something true.
    """
    out: set[str] = set()
    # Greedy over the Latin run so slash-lists are captured whole: a lazy match
    # stops at the last two items and leaves the earlier ones looking unreported.
    for pattern in (r"不在 NGSL", r"无一在 NGSL"):
        for chunk in re.findall(
            r"([A-Za-z][A-Za-z' /]*?)(?:[^。;a-zA-Z]{0,18})?" + pattern, frequency_basis
        ):
            for word in re.findall(r"[A-Za-z][A-Za-z'-]*", chunk):
                out.add(word.lower())
    # Also take every slash-run that appears anywhere in a sentence asserting
    # absence -- the wording puts the list before the assertion, sometimes with
    # intervening Chinese ("五种说法无一在 …").
    for sentence in re.split(r"[。;]", frequency_basis):
        if "不在 NGSL" in sentence or "无一在 NGSL" in sentence:
            for run in re.findall(r"[A-Za-z][A-Za-z'-]*(?:\s*/\s*[A-Za-z][A-Za-z'-]*)+", sentence):
                for word in re.findall(r"[A-Za-z][A-Za-z'-]*", run):
                    out.add(word.lower())
    out.discard("ngsl")
    out.discard("cefr")
    return out


def blind_spot_of(word: str) -> str | None:
    for name, members in NGSL_BLIND_SPOTS.items():
        if word in members:
            return name
    return None


def assess(words: list[str], ranks: dict[str, int], ceiling: int | None) -> dict:
    """-> worst rank among looked-up content words, plus the offenders.

    ``absent`` is split three ways because the three mean different things:
    a numeral or weekday NGSL structurally omits is not the same finding as a
    content word NGSL simply ranks beyond 2,809.
    """
    graded: list[tuple[str, int]] = []
    blind: list[tuple[str, str]] = []
    absent: list[str] = []
    for word in words:
        if word in GRAMMATICAL:
            continue
        rank = rank_of(word, ranks)
        if rank is not None:
            graded.append((word, rank))
            continue
        spot = blind_spot_of(word)
        if spot is not None:
            blind.append((word, spot))
        else:
            absent.append(word)
    over = (
        sorted(((w, r) for w, r in graded if r > ceiling), key=lambda p: -p[1])
        if ceiling is not None
        else []
    )
    return {
        "checked": len(graded),
        "worst": max(graded, key=lambda p: p[1]) if graded else None,
        "over_band": over,
        "blind_spot": blind,
        "absent": absent,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true", help="list every offender")
    args = parser.parse_args(argv)

    ngsl_path = args.assets / "NGSL_12_stats.csv"
    if not ngsl_path.exists():
        print(f"NGSL stats not found: {ngsl_path}", file=sys.stderr)
        print("run scripts/fetch_game_wordlists.py first", file=sys.stderr)
        return 2
    if not args.scenarios.is_dir():
        print(f"scenario directory not found: {args.scenarios}", file=sys.stderr)
        return 2

    ranks = load_ngsl(ngsl_path)
    files = sorted(args.scenarios.glob("*.json"))

    print("R-14 / G3 —— frequency_basis 逐条核对(NGSL 1.2 实际排名)")
    print(f"NGSL 词条 {len(ranks):,} —— 频段口径:最低 ≤{BAND_LOWEST} / 中低 ≤{BAND_LOWER_MID}")
    print(f"场景 {len(files)} 个,来源 {args.scenarios.relative_to(REPO_ROOT)}")
    print()

    rows: list[dict] = []
    for path in files:
        scenario = json.loads(path.read_text(encoding="utf-8"))
        basis = scenario["provenance"]["frequency_basis"]
        claim, ceiling = classify_claim(basis)
        declared = asserted_absent(basis)
        named = [w for w in named_words(basis) if w not in declared]
        named_view = assess(named, ranks, ceiling)
        required_view = assess(required_accept_words(scenario), ranks, ceiling)
        # A word the text already reports as absent is not an unreported gap.
        for view in (named_view, required_view):
            view["absent"] = [w for w in view["absent"] if w not in declared]
        rows.append(
            {
                "file": path.name,
                "id": scenario["id"],
                "tier": scenario["tier"],
                "claim": claim,
                "ceiling": ceiling,
                "named": named_view,
                "required": required_view,
                "named_count": len(named),
                "declared_absent": sorted(declared),
            }
        )

    by_claim: dict[str, int] = {}
    for row in rows:
        by_claim[row["claim"]] = by_claim.get(row["claim"], 0) + 1
    print("## 声明分类")
    labels = {
        "measured": "已逐词标注实测 rank(无需按 band 核)",
        "lowest": f"最低频段 (≤{BAND_LOWEST})",
        "lower_mid": f"中低频段 (≤{BAND_LOWER_MID})",
        "common": "高频/常用(无明确上限,只核是否在 NGSL 内)",
        "unstated": "未声明频段",
    }
    for name in ("measured", "lowest", "lower_mid", "common", "unstated"):
        if name in by_claim:
            print(f"  {labels[name]:44} {by_claim[name]:2} 个")
    print()

    # A claim that names its own evidence and then misses is the sharper finding:
    # it is internally inconsistent, independent of how the player answers.
    named_fail = [
        r
        for r in rows
        if r["named"]["over_band"] or r["named"]["absent"] or r["named"]["blind_spot"]
    ]
    print("## ① 声明自列词越界(声明的自证据不成立)")
    if not named_fail:
        print("  无 —— 所有 frequency_basis 自列的词都落在其声明的频段内。")
    for row in named_fail:
        bits = []
        if row["named"]["over_band"]:
            bits.append(
                "超band " + ", ".join(f"{w}#{r}" for w, r in row["named"]["over_band"])
            )
        if row["named"]["absent"]:
            bits.append("NGSL 未收: " + ", ".join(row["named"]["absent"]))
        if row["named"]["blind_spot"]:
            bits.append(
                "盲区: " + ", ".join(w for w, _ in row["named"]["blind_spot"])
            )
        print(f"  {row['id']:34} [{row['claim']}] {'; '.join(bits)}")
    print()

    req_fail = [r for r in rows if r["required"]["over_band"]]
    print("## ② 必需槽位 accept 词越界")
    if not req_fail:
        print("  无。")
    for row in req_fail:
        listed = row["required"]["over_band"]
        shown = listed if args.verbose else listed[:4]
        tail = "" if len(shown) == len(listed) else f" (+{len(listed) - len(shown)} 更多)"
        print(
            f"  {row['id']:34} [{row['claim']} ≤{row['ceiling']}] "
            + ", ".join(f"{w}#{r}" for w, r in shown)
            + tail
        )
    print()

    # Reported separately from ②: these are NGSL's gaps, not scenario difficulty.
    # Folding them into the over-band count would let the frequency table's blind
    # spot read as evidence that the scenarios are too hard.
    spot_rows = [r for r in rows if r["required"]["blind_spot"]]
    print("## ②b NGSL 结构性盲区(不计为越界 —— 频次表本身不收这类词)")
    if not spot_rows:
        print("  无。")
    spot_totals: dict[str, set[str]] = {}
    for row in spot_rows:
        for word, spot in row["required"]["blind_spot"]:
            spot_totals.setdefault(spot, set()).add(word)
    for spot, words in sorted(spot_totals.items()):
        print(f"  {spot:14} {', '.join(sorted(words))}")
    if spot_rows:
        print(f"  涉及场景 {len(spot_rows)} 个 —— 这些词只能由 CEFR-J 等级侧定级。")
    print()

    # Words NGSL genuinely does not rank (beyond its 2,809 lemmas), excluding the
    # structural blind spots above. These are the ones that need the level list.
    absent_rows = [r for r in rows if r["required"]["absent"]]
    all_absent: set[str] = set()
    for row in absent_rows:
        all_absent.update(row["required"]["absent"])
    print(f"## ②c NGSL 未收录的内容词({len(all_absent)} 个,需靠 CEFR-J 定级)")
    if all_absent:
        words = sorted(all_absent)
        shown = words if args.verbose else words[:24]
        print("  " + ", ".join(shown) + ("" if len(shown) == len(words) else f" ... (+{len(words) - len(shown)})"))
        print("  NGSL 是 general service list(2,809 lemma),为阅读覆盖率而建,")
        print("  低频具体物件(toilet / soap / towel / apple)与病症词(fever / sore)本就不在其中。")
    else:
        print("  无。")
    print()

    print("## ③ 各场景必需槽位的最差排名")
    for row in sorted(
        rows, key=lambda r: -(r["required"]["worst"][1] if r["required"]["worst"] else 0)
    )[: (len(rows) if args.verbose else 12)]:
        worst = row["required"]["worst"]
        worst_text = f"{worst[0]}#{worst[1]}" if worst else "n/a"
        absent = row["required"]["absent"]
        absent_text = f"   NGSL 无 {len(absent)}: " + ", ".join(absent[:5]) if absent else ""
        print(f"  {row['tier']:13} {row['id']:34} {worst_text:20}{absent_text}")
    if not args.verbose and len(rows) > 12:
        print(f"  ... 其余 {len(rows) - 12} 个见 --verbose")
    print()

    if args.json_out:
        payload = {
            "gate": "R-14/G3 frequency_basis vs NGSL",
            "ngsl_entries": len(ranks),
            "band_lowest": BAND_LOWEST,
            "band_lower_mid": BAND_LOWER_MID,
            "scenarios": len(rows),
            "claim_distribution": by_claim,
            "named_word_failures": [
                {
                    "id": r["id"],
                    "claim": r["claim"],
                    "over_band": r["named"]["over_band"],
                    "absent": r["named"]["absent"],
                }
                for r in named_fail
            ],
            "required_slot_failures": [
                {"id": r["id"], "claim": r["claim"], "over_band": r["required"]["over_band"]}
                for r in req_fail
            ],
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"JSON written: {args.json_out}")

    print("## 结论")
    print(f"  声明自列词越界 {len(named_fail)} 个;必需槽位词越界 {len(req_fail)} 个。")
    print("  按 G3「逐条核 provenance」,越界项须按实际数据改写 frequency_basis 措辞;")
    print("  **只改描述字段,不动 slots / npc / reward** —— 后三者已通过结构核对。")
    if named_fail or req_fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
