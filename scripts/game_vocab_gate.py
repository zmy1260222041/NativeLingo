#!/usr/bin/env python3
"""R-14 / G4 size + first-launch-latency gate for the graded wordlists (FR-20).

G4's criterion has two halves. The licence half is settled in
``docs/reviews/2026-08-08-survival-g4-wordlist.md``. This script measures the
other half, which that review records as having no numbers at all:

    解压后体积与首次启动延迟记录在案,不得违反 NFR-3

What it reports:
  * uncompressed bytes per asset (zip members expanded, not the archive size)
  * cold-start latency to build the runtime vocabulary index, repeated so the
    first (cold) reading is distinguishable from warm ones -- the first is the
    one NFR-3 cares about
  * index shape, including the homograph check that ``(headword, pos)`` keeps
    apart what ``headword`` alone would collapse

Why the index is built here rather than imported: ``core/game_vocab.py`` does
not exist. R-14's P0 gates (G1/G2/G3) are unmet, so product code must not be
written yet. This follows the repo's gate-script-before-product-code precedent
(``mdd_margin_sweep.py`` R-4, ``photo_gate.py`` R-13, ``ref_swap_experiment.py``
R-1): the loader here is review instrumentation and is expected to be
reimplemented in ``core/`` once the module is cleared.

xlsx parsing uses stdlib zipfile + ElementTree on purpose -- adding openpyxl for
a review script would be a dependency change, which this round excludes.

Usage:
  python scripts/game_vocab_gate.py [--assets DIR] [--repeat N] [--json-out F]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ASSETS = REPO_ROOT / "desktop" / "backend" / "assets" / "wordlists"

# NFR-3 governs perceived responsiveness; the wordlist load happens once on
# first entry to the module. Anything at or below this is comfortably inside the
# existing budget. Exceeding it is not an automatic fail -- it is a number that
# has to be argued against NFR-3 explicitly, which is what "记录在案" means.
LATENCY_BUDGET_MS = 1000.0

SPREADSHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# Homographs that must survive as separate records. CEFR-J splits rows by part
# of speech, so `headword` is not a unique key -- indexing by it alone lets one
# sense overwrite the other, and which one wins depends on file order.
HOMOGRAPH_PROBES = ("can", "please")

# Function words the request syntax in scenario `slots.accept` actually needs.
# Verified present in CEFR-J during G4; re-checked here against the real file.
FUNCTION_PROBES = ("can", "may", "must", "should", "need", "please", "want", "give")

CEFR_ORDER = ("A1", "A2", "B1", "B2", "C1", "C2")

# docs/survival-game.md §7.1: level decides admission, frequency only orders
# within a level. Kept here so the doc's table has one executable definition.
TIER_ADMITS = {
    "infant": {"A1"},
    "toddler": {"A1", "A2"},
    "youth": {"A1", "A2", "B1"},
    "professional": {"A1", "A2", "B1", "B2"},
}


def _easiest_level(index: dict, word: str) -> str | None:
    """Lowest CEFR level among a headword's senses, or None if ungraded.

    Lowest, not highest: admission asks whether the learner has *a* reading of
    the word within reach, and `can`#A1-modal is what an infant-tier request
    actually uses even though `can`#A2-noun exists.
    """
    for candidate in _inflection_variants(word):
        senses = [
            index["levels"][key]["cefr"]
            for key in index["by_headword"].get(candidate, [])
        ]
        graded = [s for s in senses if s in CEFR_ORDER]
        if graded:
            return min(graded, key=CEFR_ORDER.index)
    return None


def _inflection_variants(word: str):
    """word plus crude de-inflections, for lookup only.

    The wordlists are lemma-keyed, so `days` / `hurts` / `wrote` are absent as
    surface forms while their lemmas are graded. Without this, 58 required-slot
    words read as "ungraded" -- a lookup artefact, not scenario difficulty, the
    same class of false absence already handled in game_provenance_check.py.
    Deliberately crude: it only ever widens a lookup, and is never written back
    to scenario data.
    """
    yield word
    for suffix, stems in (
        ("ies", (word[:-3] + "y",)),
        ("es", (word[:-2],)),
        ("s", (word[:-1],)),
        ("ed", (word[:-2], word[:-1])),
        ("ing", (word[:-3], word[:-3] + "e")),
    ):
        if word.endswith(suffix):
            for stem in stems:
                if len(stem) > 1:
                    yield stem


def check_tier_reachability(index: dict, scenarios_dir: Path) -> dict:
    """Does every required slot keep at least one in-tier way to say it?

    This is the falsifiable form of §7.1's claim. A single over-tier synonym in
    an `accept` set is harmless -- the set holds alternatives, so the learner
    only needs one reachable path. The real defect would be a required slot
    where EVERY alternative sits above the tier's admission ceiling: that slot
    would be unsatisfiable by a learner who has exactly the tier's vocabulary,
    and no matcher tuning could fix it.
    """
    unreachable: list[tuple[str, str, str, list[str]]] = []
    indeterminate: list[tuple[str, str, str, list[str]]] = []
    checked = 0
    for path in sorted(scenarios_dir.glob("*.json")):
        try:
            scenario = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        admit = TIER_ADMITS.get(scenario.get("tier", ""))
        if not admit:
            continue
        for slot in scenario.get("slots", []):
            if not slot.get("required"):
                continue
            checked += 1
            accepts = slot.get("accept", []) or []
            verdicts = [_phrase_verdict(index, phrase, admit) for phrase in accepts]
            row = (
                scenario.get("tier", ""),
                scenario.get("id", path.stem),
                slot.get("key", "?"),
                accepts,
            )
            if "within" in verdicts:
                continue
            if "above" in verdicts:
                unreachable.append(row)
            else:
                # Every phrase was entirely ungraded: no evidence either way.
                indeterminate.append(row)
    return {
        "required_slots": checked,
        "unreachable": unreachable,
        "indeterminate": indeterminate,
    }


def _phrase_verdict(index: dict, phrase: str, admit: set[str]) -> str:
    """"within" | "above" | "ungraded" for one accept phrase.

    Ungraded *words* abstain rather than fail their phrase -- six words
    (`porridge`, `cord`, `walkway`, `pills`, `tablets`, `aches`) are in neither
    wordlist, and treating absence as "too hard" would invent findings out of
    coverage gaps.

    But a phrase in which NO word is graded is a third thing: zero evidence, not
    evidence of reachability. Folding it in with "within" is what let this check
    pass a deliberately unsatisfiable slot during its own negative control, so
    the three outcomes stay separate.
    """
    worst: str | None = None
    for word in re.findall(r"[a-z']+", phrase.lower()):
        if len(word) < 2:
            continue
        level = _easiest_level(index, word)
        if level is None:
            continue
        if worst is None or CEFR_ORDER.index(level) > CEFR_ORDER.index(worst):
            worst = level
    if worst is None:
        return "ungraded"
    return "within" if worst in admit else "above"


# --------------------------------------------------------------------------
# xlsx reading (stdlib only)
# --------------------------------------------------------------------------
def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        raw = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    strings: list[str] = []
    for si in ET.fromstring(raw).iter(f"{SPREADSHEET_NS}si"):
        strings.append("".join(t.text or "" for t in si.iter(f"{SPREADSHEET_NS}t")))
    return strings


def _sheet_paths(archive: zipfile.ZipFile) -> list[str]:
    return sorted(
        name
        for name in archive.namelist()
        if name.startswith("xl/worksheets/") and name.endswith(".xml")
    )


PACKAGE_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def sheet_name_to_path(archive: zipfile.ZipFile) -> dict[str, str]:
    """Sheet display name -> worksheet part path.

    Needed because worksheetN.xml ordering does NOT match the workbook's sheet
    order, so a positional guess picks the wrong sheet.
    """
    try:
        rels_raw = archive.read("xl/_rels/workbook.xml.rels")
        book_raw = archive.read("xl/workbook.xml")
    except KeyError:
        return {}
    target_of: dict[str, str] = {}
    for rel in ET.fromstring(rels_raw).iter(f"{PACKAGE_REL_NS}Relationship"):
        rel_id, target = rel.get("Id"), rel.get("Target") or ""
        if rel_id and target.startswith("worksheets/"):
            target_of[rel_id] = f"xl/{target}"
    mapping: dict[str, str] = {}
    rel_attr = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    for sheet in ET.fromstring(book_raw).iter(f"{SPREADSHEET_NS}sheet"):
        path = target_of.get(sheet.get(rel_attr) or "")
        name = sheet.get("name")
        if path and name:
            mapping[name] = path
    return mapping


def _cell_column(ref: str) -> int:
    letters = re.match(r"([A-Z]+)", ref or "A")
    if not letters:
        return 0
    index = 0
    for char in letters.group(1):
        index = index * 26 + (ord(char) - 64)
    return index - 1


def read_xlsx_rows(archive: zipfile.ZipFile, sheet_path: str) -> list[list[str]]:
    strings = _shared_strings(archive)
    rows: list[list[str]] = []
    for row in ET.fromstring(archive.read(sheet_path)).iter(f"{SPREADSHEET_NS}row"):
        cells: dict[int, str] = {}
        for cell in row.iter(f"{SPREADSHEET_NS}c"):
            column = _cell_column(cell.get("r", ""))
            value_node = cell.find(f"{SPREADSHEET_NS}v")
            inline = cell.find(f"{SPREADSHEET_NS}is")
            if cell.get("t") == "s" and value_node is not None:
                try:
                    text = strings[int(value_node.text or "0")]
                except (ValueError, IndexError):
                    text = ""
            elif inline is not None:
                text = "".join(t.text or "" for t in inline.iter(f"{SPREADSHEET_NS}t"))
            else:
                text = (value_node.text or "") if value_node is not None else ""
            cells[column] = text.strip()
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(i, "") for i in range(width)])
    return rows


# --------------------------------------------------------------------------
# asset discovery
# --------------------------------------------------------------------------
def find_cefrj(assets: Path) -> Path | None:
    for pattern in ("CEFRJ*.zip", "CEFR-J*.zip", "CEFRJ*.xlsx", "CEFR-J*.xlsx"):
        matches = sorted(assets.glob(pattern))
        if matches:
            return matches[0]
    return None


def uncompressed_bytes(path: Path) -> tuple[int, list[tuple[str, int]]]:
    """Uncompressed size. For a zip, the sum of its members -- G4 asks for the
    size after extraction, not the archive size."""
    if path.suffix.lower() != ".zip":
        return path.stat().st_size, []
    with zipfile.ZipFile(path) as archive:
        members = [
            (info.filename, info.file_size)
            for info in archive.infolist()
            if not info.is_dir()
        ]
    return sum(size for _, size in members), members


# --------------------------------------------------------------------------
# index build (the thing being timed)
# --------------------------------------------------------------------------
def _norm_pos(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def load_cefrj(path: Path) -> list[tuple[str, str, str]]:
    """-> [(headword, pos, cefr)] from the v1.6 archive or a bare xlsx."""
    entries: list[tuple[str, str, str]] = []

    VALID_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}

    def ingest_rows(rows: list[list[str]]) -> None:
        if not rows:
            return
        header = [c.strip().lower() for c in rows[0]]

        def column_of(*names: str) -> int | None:
            for name in names:
                if name in header:
                    return header.index(name)
            return None

        head_i = column_of("headword", "word", "lemma")
        pos_i = column_of("pos", "part of speech")
        cefr_i = column_of("cefr", "level")
        # Skip sheets that don't have the required columns (README, doc sheets).
        if head_i is None or pos_i is None or cefr_i is None:
            return
        for row in rows[1:]:
            if head_i >= len(row):
                continue
            headword = row[head_i].strip()
            if not headword:
                continue
            pos = row[pos_i].strip() if pos_i < len(row) else ""
            cefr = row[cefr_i].strip() if cefr_i < len(row) else ""
            # Drop rows where the CEFR level is not a recognized level — this
            # filters out documentation rows that leak into columns.
            if cefr not in VALID_LEVELS:
                continue
            entries.append((headword, pos, cefr))

    def ingest_book(book: zipfile.ZipFile) -> None:
        """v1.6 ships the same vocabulary in three overlapping shapes: `ALL`,
        the per-level subsets `A1`..`B2`, and their `_sep` variants. Reading
        every sheet triple-counts every entry. We read `ALL_sep` only: it is the
        one-headword-per-row form, whereas `ALL` packs spelling variants into a
        single cell (`adviser/advisor`), which a (headword, pos) index cannot key.
        """
        by_name = sheet_name_to_path(book)
        for preferred in ("ALL_sep", "ALL"):
            if preferred in by_name:
                ingest_rows(read_xlsx_rows(book, by_name[preferred]))
                return
        # No recognizable sheet name: fall back to every sheet. The header and
        # CEFR-level checks in ingest_rows still keep documentation rows out.
        for sheet in _sheet_paths(book):
            ingest_rows(read_xlsx_rows(book, sheet))

    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as outer:
            for name in outer.namelist():
                lowered = name.lower()
                if lowered.endswith(".xlsx"):
                    with zipfile.ZipFile(io.BytesIO(outer.read(name))) as book:
                        ingest_book(book)
                elif lowered.endswith(".csv"):
                    text = outer.read(name).decode("utf-8-sig", errors="replace")
                    ingest_rows(list(csv.reader(io.StringIO(text))))
    else:
        with zipfile.ZipFile(path) as book:
            ingest_book(book)
    return entries


def load_csv_profile(path: Path) -> list[tuple[str, str, str]]:
    """Octanove C1/C2: headword,pos,CEFR,notes"""
    entries: list[tuple[str, str, str]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            headword = (row.get("headword") or "").strip()
            if headword:
                entries.append(
                    (headword, (row.get("pos") or "").strip(), (row.get("CEFR") or "").strip())
                )
    return entries


def load_ngsl(path: Path) -> dict[str, int]:
    """NGSL stats -> {lemma: SFI rank}. Lemma only; NGSL carries no POS."""
    ranks: dict[str, int] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            lemma = (row.get("Lemma") or "").strip().lower()
            raw_rank = (row.get("SFI Rank") or "").strip()
            if not lemma or not raw_rank:
                continue
            try:
                ranks[lemma] = int(float(raw_rank))
            except ValueError:
                continue
    return ranks


def build_index(assets: Path, cefrj_path: Path | None) -> dict:
    """The whole runtime load, as one timed unit.

    Key is ``(headword_lower, pos_normalised)``. Not ``headword`` -- CEFR-J
    splits homographs by part of speech, so a bare-headword key silently loses
    one sense.
    """
    levels: dict[tuple[str, str], dict] = {}
    by_headword: dict[str, list[tuple[str, str]]] = defaultdict(list)

    # Precedence is CEFR-J over Octanove, and it is load-bearing rather than
    # incidental: 95 (headword, pos) pairs are graded by BOTH files, at
    # conflicting levels (`battery` A2 in CEFR-J vs C1 in Octanove, `agency`
    # A2 vs C2). Level decides tier admission (§7.1), so whichever source wins
    # decides whether `infant` can say the word. CEFR-J wins because it is the
    # A1-B2 skeleton graded by teaching-acquisition order; Octanove's remit here
    # is only to extend coverage upward into C1/C2, not to re-grade words that
    # CEFR-J already places in a learner's reach.
    sources: list[tuple[str, list[tuple[str, str, str]]]] = []
    if cefrj_path is not None:
        sources.append(("cefrj", load_cefrj(cefrj_path)))
    octanove = assets / "octanove-vocabulary-profile-c1c2-1.0.csv"
    if octanove.exists():
        sources.append(("octanove", load_csv_profile(octanove)))

    # (headword, pos) pairs both files grade, and how many differ on the level.
    regrade_conflicts: list[tuple[str, str, str, str]] = []
    conflict_seen: set[tuple[str, str]] = set()

    for source_name, graded in sources:
        for headword, pos, cefr in graded:
            key = (headword.lower(), _norm_pos(pos))
            existing = levels.get(key)
            if existing is not None:
                if (
                    source_name != existing["source"]
                    and existing["cefr"] != cefr.upper()
                    and key not in conflict_seen
                ):
                    # Deduped by key: Octanove repeats some (headword, pos) rows
                    # within its own file, and counting those twice would inflate
                    # a figure that is meant to read as "this many distinct words".
                    conflict_seen.add(key)
                    regrade_conflicts.append(
                        (headword, pos, existing["cefr"], cefr.upper())
                    )
                continue
            levels[key] = {
                "headword": headword,
                "pos": pos,
                "cefr": cefr.upper(),
                "source": source_name,
            }
            by_headword[headword.lower()].append(key)

    ngsl = assets / "NGSL_12_stats.csv"
    ranks = load_ngsl(ngsl) if ngsl.exists() else {}

    # lemma -> (headword, pos) is one-to-many: a single NGSL rank attaches to
    # every part-of-speech sense sharing that lemma. Fanning it out here keeps
    # the ambiguity in the data instead of resolving it arbitrarily.
    attached = 0
    for key, record in levels.items():
        rank = ranks.get(key[0])
        if rank is not None:
            record["ngsl_rank"] = rank
            attached += 1

    return {
        "levels": levels,
        "by_headword": dict(by_headword),
        "ngsl_ranks": ranks,
        "ngsl_attached": attached,
        "regrade_conflicts": regrade_conflicts,
    }


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--repeat", type=int, default=3, help="index builds to time")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    assets: Path = args.assets
    if not assets.is_dir():
        print(f"asset directory not found: {assets}", file=sys.stderr)
        print("run scripts/fetch_game_wordlists.py first", file=sys.stderr)
        return 2

    print("R-14 / G4 —— 分级词表体积与首启延迟")
    print(f"assets: {assets}")
    print()

    cefrj_path = find_cefrj(assets)
    tracked = [
        ("CEFR-J Wordlist v1.6", cefrj_path),
        ("Octanove C1/C2 v1.0", assets / "octanove-vocabulary-profile-c1c2-1.0.csv"),
        ("NGSL 1.2 stats", assets / "NGSL_12_stats.csv"),
    ]

    print("## 体积(解压后)")
    total = 0
    sizes: dict[str, int] = {}
    missing: list[str] = []
    for name, path in tracked:
        if path is None or not path.exists():
            print(f"  {name:26} MISSING")
            missing.append(name)
            continue
        size, members = uncompressed_bytes(path)
        sizes[name] = size
        total += size
        note = f"  ({len(members)} members expanded)" if members else ""
        print(f"  {name:26} {size:>10,} bytes  [{path.name}]{note}")
    print(f"  {'合计':26} {total:>10,} bytes  ({total / 1024 / 1024:.2f} MiB)")
    print()

    if missing:
        print("体积不完整,以下资产缺失:")
        for name in missing:
            print(f"  - {name}")
        if cefrj_path is None:
            print()
            print(
                "CEFR-J 需人工下载(下载页须先同意使用許諾,直链 404)。"
                "见 scripts/fetch_game_wordlists.py 的指引。"
            )
        print()
        print("G4 体积/延迟半边**仍未记录在案**。补齐资产后重跑本脚本。")
        print()

    print("## 首启延迟(冷启动构建索引)")
    timings: list[float] = []
    index: dict = {}
    for attempt in range(max(1, args.repeat)):
        started = time.perf_counter()
        index = build_index(assets, cefrj_path)
        elapsed = (time.perf_counter() - started) * 1000.0
        timings.append(elapsed)
        label = "cold" if attempt == 0 else f"warm {attempt}"
        print(f"  {label:8} {elapsed:8.1f} ms")
    cold = timings[0]
    print()
    print(f"  NFR-3 参考预算 {LATENCY_BUDGET_MS:.0f} ms —— 冷启动 {cold:.1f} ms", end="")
    print("  ✅ 在预算内" if cold <= LATENCY_BUDGET_MS else "  ⚠️ 超出,需对 NFR-3 单独论证")
    print()

    levels = index["levels"]
    print("## 索引形状")
    print(f"  词条(以 (headword, pos) 为键)  {len(levels):,}")
    print(f"  不同 headword                   {len(index['by_headword']):,}")
    print(f"  NGSL rank 已附着                {index['ngsl_attached']:,}")
    print(f"  NGSL 频次表词条                 {len(index['ngsl_ranks']):,}")
    collapsed = len(levels) - len(index["by_headword"])
    print(
        f"  同形词(若以 headword 为键会丢)  {collapsed:,}"
        + ("  <- 正是必须用复合键的理由" if collapsed else "")
    )
    if levels:
        by_level = Counter(r["cefr"] for r in levels.values() if r["cefr"])
        print("  等级分布  " + "  ".join(f"{k}={v}" for k, v in sorted(by_level.items())))
        by_pos = Counter(r["pos"].lower() for r in levels.values() if r["pos"])
        print("  词性 top8 " + "  ".join(f"{k}={v}" for k, v in by_pos.most_common(8)))
        by_source = Counter(r["source"] for r in levels.values())
        print("  来源      " + "  ".join(f"{k}={v}" for k, v in sorted(by_source.items())))
    print()

    conflicts = index["regrade_conflicts"]
    if conflicts:
        print("## 两份词表给出不同等级的词条(CEFR-J 优先)")
        print(f"  重叠且等级冲突  {len(conflicts):,} 条")
        print("  等级决定 tier 准入(§7.1),因此这里的优先级不是实现细节:")
        print("  CEFR-J 作 A1-B2 骨架按教学习得顺序定级,Octanove 只负责向上补 C1/C2,")
        print("  不重新给 CEFR-J 已判定为学习者可及的词升级。样例:")
        for headword, pos, kept, dropped in conflicts[:6]:
            print(f"    {headword:16} {pos:12} 采用 {kept}  (Octanove 记 {dropped})")
        print()

    if levels:
        print("## 同形词探针(必须各自独立成条)")
        for probe in HOMOGRAPH_PROBES:
            keys = index["by_headword"].get(probe, [])
            if not keys:
                print(f"  {probe:8} 未收录")
                continue
            senses = ", ".join(
                f"{levels[k]['cefr'] or '?'} {levels[k]['pos'] or 'n/a'}" for k in keys
            )
            flag = "✅" if len(keys) > 1 else "—"
            print(f"  {probe:8} {len(keys)} 条  {flag}  [{senses}]")
        print()

        print("## 功能词覆盖(请求构式所需)")
        for probe in FUNCTION_PROBES:
            keys = index["by_headword"].get(probe, [])
            rank = index["ngsl_ranks"].get(probe)
            rank_text = f"NGSL rank {rank}" if rank else "NGSL 未收录"
            if keys:
                best = sorted(levels[k]["cefr"] or "ZZ" for k in keys)[0]
                print(f"  {probe:8} ✅ {best:3} ({len(keys)} 条)   {rank_text}")
            else:
                print(f"  {probe:8} ❌ 等级表未收录          {rank_text}")
        print()

    scenarios_dir = REPO_ROOT / "desktop" / "backend" / "core" / "game_scenarios"
    reach = None
    if levels and scenarios_dir.is_dir():
        reach = check_tier_reachability(index, scenarios_dir)
        print("## §7.1 准入自检:每个必需槽位是否留有该 tier 可达的说法")
        print(f"  受检必需槽位  {reach['required_slots']}")
        if reach["unreachable"]:
            print(f"  ⚠️ 全部选项都超出准入上限的槽位  {len(reach['unreachable'])} 个")
            print("     该 tier 的学习者按定义说不出这个槽位 —— 属场景 schema 缺陷,")
            print("     调匹配器参数无解,须改 accept 集合或改该场景的 tier。")
            for tier, scenario_id, slot_key, accepts in reach["unreachable"][:10]:
                print(f"       {tier:12} {scenario_id} / {slot_key}  {accepts}")
        else:
            print("  ✅ 0 个 —— 每个必需槽位都至少有一条该 tier 词汇可达的说法")
            print("     注:accept 集合是「多选一」,单个超纲同义说法不构成缺陷;")
            print("     判据是「是否存在可达路径」,而不是「是否每条说法都在纲内」。")
        if reach["indeterminate"]:
            print(f"  ⬜ 无法判定的槽位  {len(reach['indeterminate'])} 个"
                  " —— 全部 accept 说法都不在两份词表内,既非通过也非失败")
            for tier, scenario_id, slot_key, accepts in reach["indeterminate"][:10]:
                print(f"       {tier:12} {scenario_id} / {slot_key}  {accepts}")
        print()

    if args.json_out:
        payload = {
            "gate": "R-14/G4 size+latency",
            "assets_dir": str(assets),
            "uncompressed_bytes": sizes,
            "uncompressed_total_bytes": total,
            "missing_assets": missing,
            "cold_build_ms": round(cold, 2),
            "all_build_ms": [round(t, 2) for t in timings],
            "latency_budget_ms": LATENCY_BUDGET_MS,
            "index_entries": len(levels),
            "distinct_headwords": len(index["by_headword"]),
            "homographs_collapsed_by_bare_headword": collapsed,
            "ngsl_ranks": len(index["ngsl_ranks"]),
            "regrade_conflicts": len(index["regrade_conflicts"]),
            "tier_reachability": (
                {
                    "required_slots": reach["required_slots"],
                    "unreachable_slots": len(reach["unreachable"]),
                }
                if reach
                else None
            ),
            "complete": not missing,
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"JSON written: {args.json_out}")

    if missing:
        print("结论:**部分记录** —— 授权侧已通过,体积侧待补齐资产,延迟数字仅覆盖已有资产。")
        return 1
    print("结论:体积与冷启动延迟均已记录。可回填 G4 的体积/延迟行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
