#!/usr/bin/env python3
"""One-shot rewrite of ``provenance.frequency_basis`` for the scenarios whose
band claims ``game_provenance_check.py`` found unsupported (R-14 / G3).

The old wording asserted bands ("全在最低频段") that were authored before the
wordlist was chosen. The new wording cites **measured NGSL SFI ranks**. To keep
this from swapping a vague claim for a wrong number, every ``word#rank`` token in
every replacement string below is validated against the staged NGSL file before
anything is written -- a mismatch aborts the whole run.

Only ``provenance.frequency_basis`` is touched. ``slots`` / ``npc`` / ``reward``
already passed G3's structural check and are left byte-identical.

Usage:
  python scripts/reword_frequency_basis.py [--dry-run] [--scenarios DIR]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from game_provenance_check import rank_of  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCENARIOS = REPO_ROOT / "desktop" / "backend" / "core" / "game_scenarios"
NGSL = REPO_ROOT / "desktop" / "backend" / "assets" / "wordlists" / "NGSL_12_stats.csv"

# Scenarios flagged by ① (claim's own named words miss) or ② (required-slot
# accept words over band). Keyed by scenario id.
REWORDED: dict[str, str] = {
    "food-ask-bread": (
        "需求金字塔第 1 层;请求构式 can#38 / want#76 / give#77 / need#90 全在 NGSL 首百词,"
        "food#367 与 eat#476 亦在首五百;但具体物名 bread#2262 落在第三千段,hungry 不在 "
        "NGSL 2,809 词内 —— 实测表明本场景的难点不在句法而在具体物名,该两词须由 CEFR-J "
        "等级侧定级。"
    ),
    "food-ask-soft-food": (
        "需求金字塔第 1 层;实测 pain#1150 / hurt#1421 / soft#1601 / tooth#2026 / bread#2262 / "
        "bite#2663 依次落在 NGSL 第二至三千段,porridge 与 soup 不在 NGSL 2,809 词内 —— "
        "原措辞「均在最低频段」不成立,已按实测改写;引入 X hurts 这一固定构式,"
        "是幼儿级典型的身体状态表达。"
    ),
    "food-buy-market-portion": (
        "需求金字塔第 1 层;day#85 / cheapest#1095 / bag#1252 在 NGSL 前 1,300,"
        "但 bread#2262 与 rice#2695 落在第三千段,beans 不在 NGSL 内 —— 主食名反而是最低频的"
        "一类,原措辞「全在中低频段」不成立;新增的是数量与限制表达,现实购物对话里出现频率极高。"
    ),
    "food-point-fruit": (
        "需求金字塔第 1 层;one#35 / want#76 与 food#367 / eat#476 均在 NGSL 首五百,"
        "但 fruit#1640 在第二千段,apple 不在 NGSL 2,809 词内 —— apple 属仓库内 "
        "yoloe_everyday_labels 已覆盖的日常物,与 FR-24 照片扩词直接衔接,"
        "其等级须由 CEFR-J 给出而非频次表。"
    ),
    "shelter-ask-sit-inside": (
        "需求金字塔第 1 层;in#7 / come#65 / let#174 / inside#660 确在最低频段,"
        "但 dry#1135 与 rain#1232 已入第二千段,hut 不在 NGSL 内 —— 天气词并不比空间介词更高频,"
        "原措辞已按实测收窄;本场景仍是介词类功能词的最早使用场合。"
    ),
    "shelter-ask-toilet": (
        "需求金字塔第 1 层;go#31 / where#86 / need#90 均在 NGSL 首百词,"
        "首次引入 where 疑问词这一高复用功能词;但 toilet / bathroom / restroom / washroom / wc "
        "**五种说法无一在 NGSL 2,809 词内** —— 这是频次表用于日常生存场景时最典型的盲区,"
        "该槽位只能由 CEFR-J 等级侧定级。"
    ),
    "shelter-ask-wash": (
        "需求金字塔第 1 层;hands#198 / water#322 / clean#842 在最低频段,"
        "但 wash#1368 与 dirty#2255 分别在第二、三千段,soap 与 basin 不在 NGSL 内 —— "
        "soap 与 towel 均在检测器日常物词表覆盖范围内,可由生活照片扩词补入,"
        "其等级须由 CEFR-J 给出。"
    ),
    "shelter-rent-room-night": (
        "需求金字塔第 1 层(居所);day#85 / expensive#1061 / cheap#1095 在中低频段,"
        "但 tonight#1414 与 coin#2609 更晚,原措辞已按实测补上后两词;"
        "数量词 + 时长 + 价格三类信息同时出现,是日常交易对话的标准信息量。"
    ),
    "warmth-ask-coat": (
        "需求金字塔第 1 层;can#38 / want#76 / give#77 在首百词,clothes#956 亦在首千内,"
        "但 warm#1021 / coat#1863 / jacket#2253 逐级更晚 —— coat 属检测器实体词表可覆盖的日常物,"
        "便于照片扩词,其等级由 CEFR-J 给出。"
    ),
    "warmth-ask-fire-seat": (
        "需求金字塔第 1 层;can#38 / need#90 / here#98 / sit#356 / fire#613 / cold#867 "
        "均在最低频段,仅 warm#1021 略过千词线;句式仅需 can I + 动词,不引入时态变化。"
    ),
    "warmth-ask-shoes": (
        "需求金字塔第 1 层;broken#368(NGSL 收于 break)/ feet#576 / cold#867 / fix#973 "
        "在最低频段,但 dry#1135 / shoe#1476 / hole#1515 / wet#2084 在第二千段,"
        "mend 与 socks 不在 NGSL 内 —— shoe 属检测器日常物词表可覆盖项,支持照片扩词。"
    ),
    "water-ask-clean-water": (
        "需求金字塔第 1 层;water#322 / clean#842 在最低频段,"
        "safe#1027 / river#1176 / sick#1716 / dirty#2255 依次更晚,boiled 与 thirsty 不在 NGSL 内;"
        "仍复用 water-ask-hot-water 已建立的形容词修饰结构,构成同一句式的第二次曝光。"
    ),
    "water-ask-hot-water": (
        "需求金字塔第 1 层;water#322 / drink#655 / cold#867 / hot#885 确在最低频段,"
        "但 warm#1021 / tea#1599 / freezing#1856 在其后,thirsty 不在 NGSL 内;"
        "新增的是形容词 + 名词的修饰结构,是幼儿级的合理增量。"
    ),
    "water-refill-cup": (
        "需求金字塔第 1 层;more#42 / water#322 / drink#655 / fill#845 在最低频段,"
        "但 cup#1491 与 empty#1592 在第二千段 —— cup 也是 yoloe_everyday_labels 中的日常物,"
        "支持照片扩词接入,其等级由 CEFR-J 给出。"
    ),
    "water-report-broken-tap": (
        "需求金字塔第 1 层;broken#368(NGSL 收于 break)与 fix#973 在最低频段,"
        "yard#1667 在中低频段,但 tap#2297 已过第二千线,downstairs 不在 NGSL 内 —— "
        "原措辞「全在中低频段」对 tap 不成立;新增的是描述故障与指明位置这两类表达,"
        "在租住与维修场景中复用率很高。"
    ),
    "shelter-ask-sleep-spot": (
        "需求金字塔第 1 层;go#31 / here#98 / place#114 / inside#660 / sleep#827 / dark#923 "
        "均在最低频段,仅否定构式 nowhere#2638 落在第三千段;no + 名词与 nowhere "
        "属幼儿级可承担的增量。"
    ),
    "shelter-ask-place-to-sleep": (
        "需求金字塔第 2 层(居所)。stay#345 / bed#694 / sleep#827 在最低频段,"
        "但 somewhere#1320 与 tonight#1414 在第二千段,原措辞「都在最低频段」对后两词不成立;"
        "「sleep + tonight + can I」三个词就足以传达意思,不要求语序正确。"
    ),
    "shelter-ask-shelter-from-rain": (
        "需求金字塔第 2 层(基本庇护)。wait#403 与 inside#660 在最低频段,"
        "但 dry#1135 与 rain#1232 已入第二千段 —— 与 shelter-ask-sit-inside 同因:"
        "天气词并不在最低频段;意思可由「here, please」加上下雨的语境传达,不要求 until 从句。"
    ),
    "belonging-ask-sit-with-group": (
        "需求金字塔第 3 层(归属)。can#38 / here#98 / free#395 / seat#852 全在最低频段,"
        "仅 chair#1060 略过千词线;「sit here ok?」即算传达到。"
    ),
    "belonging-small-talk-waiting-line": (
        "需求金字塔第 3 层(归属)。time#49 / people#57 / wait#403 在最低频段,"
        "slow#1118 与 busy#1233 稍晚;youth 级的难度是必须把话轮交回对方,"
        "一个粗糙的「and you?」即满足该槽位。"
    ),
    "belonging-decline-and-offer-another-time": (
        "需求金字塔第 3 层(归属)。cannot#38(NGSL 收于 can)/ busy#1233 / tonight#1414 / "
        "sick#1716 均在 NGSL 内,但 **Thursday 等星期名整类不在 NGSL 2,809 词中** —— "
        "频次表不收星期与月份,这类词只能由 CEFR-J 定级;youth 级难度在于三个意思单元的组合,"
        "「no tonight, mother sick, thursday ok?」即算传达到。"
    ),
    "belonging-invite-neighbour-tea": (
        "需求金字塔第 3 层(归属)。like#45 与 come#65 在首百词,"
        "coffee#1395 / cup#1491 / tea#1599 在第二千段,而 **Saturday 等星期名整类不在 NGSL 内** "
        "—— 与 belonging-decline-and-offer-another-time 同因;youth 级难度在于邀请必须带上时间"
        "才算完整,而不要求情态动词或条件句正确。"
    ),
    # Not a band-claim failure -- a clarity fix. 「低频段」without 最/中 is
    # ambiguous in Chinese (低频 normally means *infrequent*, i.e. the opposite of
    # what was meant). The measured data also happens to be worth stating: the
    # scenario's central noun is absent from NGSL entirely.
    "warmth-ask-blanket": (
        "需求金字塔第 1 层;cover#424 / cold#867 在最低频段,warm#1021 略过千词线,"
        "freezing#1856 在第二千段,而 blanket / cloth / shivering 三词均不在 NGSL 2,809 词内 —— "
        "原措辞「词汇仍在低频段」歧义(低频通常指罕见),已按实测改写;"
        "本场景引入状态描述槽位。"
    ),
}


def load_ranks() -> dict[str, int]:
    ranks: dict[str, int] = {}
    with NGSL.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            lemma = (row.get("Lemma") or "").strip().lower()
            raw = (row.get("SFI Rank") or "").strip()
            if lemma and raw:
                try:
                    ranks[lemma] = int(float(raw))
                except ValueError:
                    pass
    return ranks


def validate(ranks: dict[str, int]) -> list[str]:
    """Every ``word#rank`` in every replacement must match NGSL exactly."""
    problems: list[str] = []
    for scenario_id, text in REWORDED.items():
        for word, claimed in re.findall(r"([A-Za-z][A-Za-z'-]*)#(\d+)", text):
            actual = rank_of(word.lower(), ranks)
            if actual is None:
                problems.append(f"{scenario_id}: {word}#{claimed} -- NGSL 未收录")
            elif actual != int(claimed):
                problems.append(f"{scenario_id}: {word}#{claimed} -- 实际 #{actual}")
        # Words asserted absent must really be absent.
        for phrase in re.findall(r"([A-Za-z][A-Za-z /]*?)\s*(?:三词均)?不在 NGSL", text):
            for word in re.findall(r"[A-Za-z][A-Za-z'-]*", phrase):
                lowered = word.lower()
                if lowered in {"ngsl", "cefr", "j"}:
                    continue
                if rank_of(lowered, ranks) is not None:
                    problems.append(
                        f"{scenario_id}: 断言 {word} 不在 NGSL,实际 #{rank_of(lowered, ranks)}"
                    )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not NGSL.exists():
        print(f"NGSL not staged: {NGSL}", file=sys.stderr)
        return 2

    ranks = load_ranks()
    problems = validate(ranks)
    print(f"校验 {len(REWORDED)} 条改写里引用的每个 word#rank …")
    if problems:
        print("引用与 NGSL 不符,已中止,未写入任何文件:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("  全部与 NGSL 1.2 实测排名一致。")
    print()

    by_id = {}
    for path in sorted(args.scenarios.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        by_id[data["id"]] = (path, data)

    unknown = set(REWORDED) - set(by_id)
    if unknown:
        print(f"未找到这些场景 id: {sorted(unknown)}", file=sys.stderr)
        return 2

    changed = 0
    for scenario_id, new_text in REWORDED.items():
        path, data = by_id[scenario_id]
        old = data["provenance"]["frequency_basis"]
        if old == new_text:
            continue
        print(f"{path.name}")
        print(f"  - {old}")
        print(f"  + {new_text}")
        if not args.dry_run:
            data["provenance"]["frequency_basis"] = new_text
            # Preserve the repo's 2-space JSON style and keep CJK readable.
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        changed += 1
        print()

    verb = "待改写" if args.dry_run else "已改写"
    print(f"{verb} {changed} 个场景的 frequency_basis。slots / npc / reward 未触碰。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
