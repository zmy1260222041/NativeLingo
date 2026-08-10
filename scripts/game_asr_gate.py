#!/usr/bin/env python3
"""R-14 gate **G2** —— `base.en` 在 L2 短语上的关键词召回测量脚手架.

G2 的判据(2026-08-09 修订,用户批准;见
`docs/reviews/2026-08-08-survival-game-fit.md` §2):

    faster-whisper `base.en` 在 infant / toddler 级短句(2–6 词、L2 口音、
    可能语法不全)上、**对发音合格的词**的**关键词召回 ≥0.85**。

「发音合格」= 人类评分者判定该词发音可辨(speechocean762 口径:五位专家的词级
accuracy ≥8/10)。判定结果写在 manifest 的 `well_pronounced` 字段里,标注规格见
`scripts/fixtures/game_asr/README.md` §4.1。

**为什么口径要分层 —— 这是收紧而不是放宽。**原判据把两件因果不同的事混成一个数:

    (A) 学习者**确实没把这个词说出来**   代理实测 recall 0.333
    (B) 学习者说清楚了、**仪器没听见**   代理实测 recall 0.876 / 0.917

(A) 类漏词**不是缺陷**:声音里没有那个音,任何模型都听不到,NPC 因此不给物资 ——
这与 `docs/survival-game.md` §6.1 的意图一致。把它算进仪器指标,判据就变成「要求
模型听见没说出来的词」,不可满足,并会诱导用「换更大模型」去追一个物理上限
(实测 `base.en`→`small.en` 对 (A) 只从 0.300 到 0.333,对 (B) 才有 0.876→0.917)。
分子分母同时收紧到「人耳能听出来的词」,(B) 类失效仍按原阈值 0.85 全额受门 ——
**及格线一位没动**,变的是测量口径的因果正确性(R-14 §0 因此成立)。

**没有 `well_pronounced` 标注时,本脚本同时报合并数与分层数,并把裁决标为退化口径。**
只报有利的那一个是评审文档明令禁止的。

被测函数是 `backend.core.transcribe.transcribe_waveform`(`transcribe.py:255`),
即 `/game/attempt` 将来实际调用的那一个。本脚本不重实现 whisper,直接 import 它,
这样测到的就是生产路径。

只统计关键词召回,**不统计整句 WER**
--------------------------------------
G2 明确写了这一条,原因在 `docs/survival-game.md` §6.1:下游消费转写文本的方式是
对 `slots[].accept` 做词边界匹配,而不是比对整句。整句 WER 会把「a / the / 时态」
这类 delivery 判定根本不看的错误算进去,给出一个与判准链路无关的数字。因此本脚本
用与 `core/scenario.py:223` **同一个正则写法**
``(?<![A-Za-z])…(?![A-Za-z])``(IGNORECASE)去匹配,量到的就是槽位匹配器会看到的
东西 —— 多词短语按空白归一后整体匹配(§6.1)。

诚实交代三个缺口(不要在回填 R-14 时把它们当成已解决)
------------------------------------------------------
1. **仓库里没有 L2 口音短语语料。**R-10 实测的归一化 WER 4.01% 是在**新闻播报**
   语料(`videos/7.1.mp4`,演播室音质、母语播报腔、完整句子)上测的。G2 自己写明
   该数字**不可外推**到本模块的分布(L2 口音、2–6 词、语法不全、可能有环境噪声),
   必须单独测。本脚本只是量具,**语料仍然缺失** ——
   采集规格见 `scripts/fixtures/game_asr/README.md`。
2. **Piper 合成音不能替代 L2 真人录音。**合成语音没有 L2 口音、没有 disfluency、
   没有环境噪声,在它上面测会得到一个系统性偏乐观的数字,等于悄悄作废这道门。
   因此 `--synthetic-smoke` **仅用于证明脚手架能跑通**:该模式下脚本拒绝给出
   PASS 结论,并把所有数字标注为「冒烟,不可回填 R-14」。
3. **`--dry-run` 不是测量。**它吃预先给定的转写文本,只验证打分逻辑,同样不产出
   可回填的裁决。

`--proxy-corpus` —— 只能证伪,不能证实
--------------------------------------
公开 L2 语料(如 speechocean762,OpenSLR SLR101,CC BY 4.0)是**真人 L2 口音录音**,
因此不受上面第 2 条的合成音禁令约束。但它与 G2 的目标分布有三处差异,而**三处全都
让代理语料更容易**:

    词汇    代理是 bear / elephant 这类常见词;本模块要的是 bread / blanket /
            toilet / soap —— G4 实测其中 25 个内容词根本不在 NGSL 2,809 内
    语音    代理是**照稿朗读**;本模块是**自发应答**(朗读更流畅、发音更清晰)
    L1      代理仅普通话一种;G2 要求 >=3 种(这一条是覆盖缺口,不是乐观偏差)

代理比目标系统性更容易,于是推论是**不对称的**:

    代理 recall <  0.85  ->  真实语料只会更差  ->  **FAIL 是可靠结论**
    代理 recall >= 0.85  ->  对真实分布什么都没证明  ->  **不得算 PASS**

因此本模式的裁决只有两种:`PROXY-FAIL`(可靠,且足以驳回「转写默认完美」这一假设)
与 `PROXY-INCONCLUSIVE`(高于阈值,但不构成 G2 通过)。**永不产出 PASS。**

用法
----
真实测量(需要语料):
    GGML_METAL_NO_RESIDENCY=1 .venv/bin/python -m scripts.game_asr_gate \
        --clips scripts/fixtures/game_asr/clips \
        --manifest scripts/fixtures/game_asr/manifest.json \
        --scenarios desktop/backend/core/game_scenarios

只验打分逻辑(不加载 whisper):
    .venv/bin/python -m scripts.game_asr_gate \
        --manifest some_manifest_with_transcripts.json --dry-run

只证明脚手架跑通(Piper 合成,永不 PASS):
    GGML_METAL_NO_RESIDENCY=1 .venv/bin/python -m scripts.game_asr_gate \
        --manifest smoke.json --synthetic-smoke

manifest 格式(JSON 列表 / {"clips": [...]} / CSV,同名字段):
    clip                音频文件名(相对 --clips)。--dry-run / --synthetic-smoke 下可省
    scenario            场景 id,用于取 slots[].accept 做校验
    tier                infant / toddler / youth / professional(缺省时从场景取)
    expected_keywords   本条录音**意思上确实包含**的关键词列表(JSON 数组或 ; 分隔)
    well_pronounced     上面这些词里**人耳判定发音可辨**的子集(判据口径的分母)。
                        缺省则本条只能进合并口径,裁决降级 —— 见 README §4.1
    intended            (可选)说话人实际想说的粗糙原话,只用于报告可读性
    transcript          (仅 --dry-run)预先给定的转写文本
    say                 (仅 --synthetic-smoke)交给 Piper 合成的文本
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

# allow running from the repo root without installing the package
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)
_DESKTOP = os.path.join(_REPO, "desktop")
if os.path.isdir(_DESKTOP):
    sys.path.insert(0, _DESKTOP)

GATE_RECALL = 0.85
GATE_TIERS = ("infant", "toddler")  # G2 只对这两级设判据
AUDIO_EXTS = (".wav", ".flac", ".ogg", ".mp3", ".m4a", ".aiff", ".aif", ".webm")


# --------------------------------------------------------------------------- #
# 场景库
# --------------------------------------------------------------------------- #
def load_scenarios(path: str | None) -> tuple[dict, list[str]]:
    """Load ``game_scenarios/*.json`` tolerantly.

    The scenario library is being authored concurrently, so an absent, empty or
    partially-broken directory must not crash the harness — it degrades to
    "manifest keywords unverified" and says so.
    """
    notes: list[str] = []
    if not path:
        notes.append("未指定 --scenarios:manifest 的 expected_keywords 无法与 accept 集合对照")
        return {}, notes
    if not os.path.isdir(path):
        notes.append(f"--scenarios 目录不存在:{path}(场景库尚未编写?)")
        return {}, notes

    scenarios: dict = {}
    files = sorted(glob.glob(os.path.join(path, "*.json")))
    if not files:
        notes.append(f"--scenarios 目录为空:{path}(G3 的场景库尚未编写)")
    for f in files:
        try:
            with open(f, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            notes.append(f"跳过无法解析的场景文件 {os.path.basename(f)}: {exc}")
            continue
        sid = data.get("id") or os.path.splitext(os.path.basename(f))[0]
        if not isinstance(data.get("slots"), list):
            notes.append(f"场景 {sid} 缺少 slots 数组,accept 校验对它不可用")
            data["slots"] = []
        scenarios[sid] = data
    return scenarios, notes


def _accept_index(scenario: dict) -> dict[str, dict]:
    """``{normalised accept phrase: {slot, required}}`` for one scenario."""
    out: dict[str, dict] = {}
    for slot in scenario.get("slots") or []:
        key = slot.get("key", "?")
        required = bool(slot.get("required", False))
        for phrase in slot.get("accept") or []:
            norm = _norm_phrase(phrase)
            if norm and norm not in out:
                out[norm] = {"slot": key, "required": required}
    return out


# --------------------------------------------------------------------------- #
# 匹配 —— 与 core/scenario.py:223 同一写法
# --------------------------------------------------------------------------- #
def _norm_phrase(text: str) -> str:
    return " ".join(str(text).split()).strip()


def keyword_pattern(keyword: str) -> re.Pattern:
    """Word-boundary matcher for a keyword or multi-word phrase.

    Same idiom as ``core/scenario.py:223`` — ``(?<![A-Za-z])…(?![A-Za-z])`` with
    IGNORECASE, so "bus" cannot satisfy "business". Multi-word phrases are
    whitespace-normalised and matched as a whole (docs/survival-game.md §6.1);
    inner whitespace becomes ``\\s+`` so a transcript's line breaks or double
    spaces do not defeat the match.
    """
    tokens = [re.escape(t) for t in _norm_phrase(keyword).split()]
    body = r"\s+".join(tokens)
    return re.compile(rf"(?<![A-Za-z]){body}(?![A-Za-z])", re.IGNORECASE)


def matches(keyword: str, transcript: str) -> bool:
    return bool(keyword_pattern(keyword).search(_norm_phrase(transcript)))


# --------------------------------------------------------------------------- #
# 「whisper 反而写成了什么」—— 为降级路径 (b) 提供可操作线索
# --------------------------------------------------------------------------- #
_WORD_RE = re.compile(r"[A-Za-z']+")


def wrong_forms(keyword: str, transcript: str, limit: int = 3) -> list[str]:
    """Candidate mis-transcription forms for a missed keyword.

    G2's degradation path (b) is "add common mis-transcription forms to the
    `accept` set", which is only actionable if the gate reports the actual wrong
    forms. We slide a window of the keyword's token count over the transcript and
    keep the most similar spans by character-level ratio.
    """
    import difflib

    target = _norm_phrase(keyword).lower()
    tokens = _WORD_RE.findall(transcript)
    if not tokens:
        return []
    n = max(1, len(target.split()))
    spans: list[str] = []
    for width in {max(1, n - 1), n, n + 1}:
        for i in range(0, max(0, len(tokens) - width + 1)):
            spans.append(" ".join(tokens[i:i + width]))
    scored = []
    for span in dict.fromkeys(spans):
        ratio = difflib.SequenceMatcher(None, target, span.lower()).ratio()
        if ratio >= 0.45:  # below this it is not a plausible mis-transcription
            scored.append((ratio, span))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [f"{span} ({ratio:.2f})" for ratio, span in scored[:limit]]


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
def _split_keywords(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [_norm_phrase(k) for k in raw if _norm_phrase(k)]
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            return _split_keywords(json.loads(text))
        except json.JSONDecodeError:
            pass
    return [_norm_phrase(k) for k in re.split(r"[;|]", text) if _norm_phrase(k)]


def load_manifest(path: str) -> list[dict]:
    if not os.path.exists(path):
        # The G2 corpus does not exist yet, so this is the expected state rather
        # than a bug -- a traceback here reads as a broken script and hides what
        # is actually missing.
        raise SystemExit(
            f"manifest not found: {path}\n"
            "  G2 的语料尚不存在 —— 这是 R-14 记录的状态,不是脚本故障。\n"
            "  采集规格见 scripts/fixtures/game_asr/README.md:\n"
            "    infant >=60 + toddler >=60 + youth / professional 各 >=20,\n"
            "    >=8 位说话人、>=3 种母语。\n"
            "  Piper 合成音明确禁止充当替代(无 L2 口音、无不流畅、无环境噪声,\n"
            "  测出的数字会系统性偏乐观)。仅验证 harness 通路可用时加 --synthetic-smoke。"
        )
    with open(path, encoding="utf-8") as handle:
        if path.lower().endswith(".csv"):
            rows = list(csv.DictReader(handle))
        else:
            data = json.load(handle)
            rows = data.get("clips", data) if isinstance(data, dict) else data
    entries = []
    for i, row in enumerate(rows):
        entries.append({
            "clip": (row.get("clip") or "").strip(),
            "scenario": (row.get("scenario") or "").strip(),
            "tier": (row.get("tier") or "").strip(),
            "expected": _split_keywords(row.get("expected_keywords")),
            # Absent (not empty) means "unlabelled" -- distinct from "labelled, and
            # none of the words were well pronounced". Conflating the two would let
            # a missing column silently zero out the criterion's denominator.
            "well_pronounced": (
                None if row.get("well_pronounced") is None
                else _split_keywords(row.get("well_pronounced"))
            ),
            "intended": (row.get("intended") or "").strip(),
            "transcript": (row.get("transcript") or "").strip(),
            "say": (row.get("say") or "").strip(),
            "row": i,
        })
    return entries


# --------------------------------------------------------------------------- #
# 转写
# --------------------------------------------------------------------------- #
def transcribe_file(path: str) -> str:
    """Load a clip the same way the app does, then run the production function."""
    from backend.core.audio_io import load_audio
    from backend.core.transcribe import transcribe_waveform

    wav = load_audio(path)  # 16 kHz mono float32, peak-normalised
    sentences = transcribe_waveform(wav)
    return _norm_phrase(" ".join(s.get("text", "") for s in sentences))


def _load_smoke_voice() -> str:
    """Load *some* TTS voice for --synthetic-smoke. Returns a label.

    Mirrors ``main.py:721`` ``_ensure_piper_ready`` without importing the FastAPI
    app. Falls back to the macOS ``say`` voice when the Piper model is not
    available offline — for a smoke test any voice will do, because **no number
    from this mode is admissible for G2 either way**.
    """
    from backend.core import piper_tts

    if piper_tts.is_loaded():
        return "already-loaded"
    try:
        from backend.core import model_assets

        onnx = model_assets.download_verified(
            model_assets.PIPER_REPO,
            model_assets.PIPER_FILENAME,
            model_assets.PIPER_REVISION,
            model_assets.PIPER_SIZE,
            model_assets.PIPER_SHA256,
        )
        if not os.path.exists(onnx + ".json"):
            from huggingface_hub import hf_hub_download

            hf_hub_download(
                model_assets.PIPER_REPO,
                model_assets.PIPER_CONFIG_FILENAME,
                revision=model_assets.PIPER_REVISION,
            )
        piper_tts.load(onnx)
        return "piper libritts_r"
    except Exception as exc:  # noqa: BLE001
        if sys.platform != "darwin":
            raise
        print(f"  ! Piper 不可用({type(exc).__name__}: {exc});冒烟改用 macOS say")
        piper_tts._voice = piper_tts._SYSTEM_SAY_VOICE
        piper_tts._voice_sr = 16000
        piper_tts._SYNTH_CONFIG = None
        return "macOS say"


def synth_transcribe(text: str) -> str:
    from backend.core import piper_tts
    from backend.core.transcribe import transcribe_waveform

    wav = piper_tts.synth_wav(text)
    sentences = transcribe_waveform(wav)
    return _norm_phrase(" ".join(s.get("text", "") for s in sentences))


# --------------------------------------------------------------------------- #
# 统计
# --------------------------------------------------------------------------- #
def wilson_lower(hits: int, total: int, z: float = 1.96) -> float:
    """Wilson 95% lower bound — printed so a 5-clip point estimate cannot be
    mistaken for a measurement."""
    if total == 0:
        return 0.0
    p = hits / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return max(0.0, (centre - margin) / denom)


def score(entries: list[dict], scenarios: dict, transcripts: dict[int, str]) -> dict:
    per_clip = []
    misses = []
    warnings: list[str] = []
    wrong_by_keyword: dict[str, Counter] = defaultdict(Counter)

    labelled_clips = 0

    for entry in entries:
        scenario = scenarios.get(entry["scenario"])
        accept = _accept_index(scenario) if scenario else {}
        tier = entry["tier"] or (scenario or {}).get("tier") or "unknown"
        transcript = transcripts.get(entry["row"], "")

        wp_raw = entry["well_pronounced"]
        labelled = wp_raw is not None
        labelled_clips += 1 if labelled else 0
        wp_set = {_norm_phrase(k).lower() for k in (wp_raw or [])}
        if labelled:
            expected_lower = {_norm_phrase(k).lower() for k in entry["expected"]}
            stray = sorted(wp_set - expected_lower)
            if stray:
                label = entry["clip"] or "row{}".format(entry["row"])
                warnings.append(
                    f"{label}: well_pronounced 含不在 expected_keywords 里的词 "
                    f"{stray} —— 判据的分母是 expected 的子集(README §4.1),"
                    "该词按未标注处理,请修 manifest"
                )

        checked = []
        for keyword in entry["expected"]:
            info = accept.get(_norm_phrase(keyword).lower()) or accept.get(_norm_phrase(keyword))
            if info is None and accept:
                # case-insensitive lookup over the accept index
                for phrase, meta in accept.items():
                    if phrase.lower() == _norm_phrase(keyword).lower():
                        info = meta
                        break
            if info is None:
                label = entry["clip"] or "row{}".format(entry["row"])
                warnings.append(
                    f"{label}: 期望关键词 "
                    f"{keyword!r} 不在场景 {entry['scenario'] or '(未指定)'} 的任何 "
                    "slots[].accept 里 —— G2 只统计 accept 集合内的关键词,该条按"
                    "「无槽位归属」计入但需人工复核 manifest 或场景库"
                )
            hit = matches(keyword, transcript)
            checked.append({
                "keyword": keyword,
                "hit": hit,
                "slot": (info or {}).get("slot", "?"),
                "required": (info or {}).get("required"),
                # True  -> (B) 类候选:人耳听得出,漏了就是仪器的锅,受判据约束
                # False -> (A) 类:学习者没说清楚,漏了是正确行为,不受判据约束
                # None  -> 未标注:只能进合并口径
                "well_pronounced": (
                    (_norm_phrase(keyword).lower() in wp_set) if labelled else None
                ),
            })
            if not hit:
                forms = wrong_forms(keyword, transcript)
                misses.append({
                    "clip": entry["clip"] or f"row{entry['row']}",
                    "scenario": entry["scenario"],
                    "tier": tier,
                    "keyword": keyword,
                    "slot": (info or {}).get("slot", "?"),
                    "required": (info or {}).get("required"),
                    "intended": entry["intended"],
                    "transcript": transcript,
                    "wrong_forms": forms,
                    "well_pronounced": (
                        (_norm_phrase(keyword).lower() in wp_set) if labelled else None
                    ),
                })
                for form in forms:
                    wrong_by_keyword[keyword][form.split(" (")[0]] += 1

        per_clip.append({
            "clip": entry["clip"] or f"row{entry['row']}",
            "scenario": entry["scenario"],
            "tier": tier,
            "transcript": transcript,
            "intended": entry["intended"],
            "keywords": checked,
            "labelled": labelled,
            "hits": sum(1 for c in checked if c["hit"]),
            "total": len(checked),
            # (B) 类:判据口径的分子分母
            "wp_hits": sum(1 for c in checked if c["well_pronounced"] and c["hit"]),
            "wp_total": sum(1 for c in checked if c["well_pronounced"]),
            # (A) 类:并列报告,**不受判据约束**
            "poor_hits": sum(1 for c in checked if c["well_pronounced"] is False and c["hit"]),
            "poor_total": sum(1 for c in checked if c["well_pronounced"] is False),
        })

    def _empty_bucket() -> dict:
        return {
            "hits": 0, "total": 0, "clips": 0,
            "wp_hits": 0, "wp_total": 0,
            "poor_hits": 0, "poor_total": 0,
        }

    by_tier: dict[str, dict] = defaultdict(_empty_bucket)
    for clip in per_clip:
        bucket = by_tier[clip["tier"]]
        bucket["clips"] += 1
        for key in ("hits", "total", "wp_hits", "wp_total", "poor_hits", "poor_total"):
            bucket[key] += clip[key]

    def _sum(keys, tiers) -> dict:
        out = {k: sum(by_tier[t][k] for t in tiers if t in by_tier) for k in keys}
        return out

    keys = ("hits", "total", "clips", "wp_hits", "wp_total", "poor_hits", "poor_total")
    gate = _sum(keys, GATE_TIERS)

    return {
        "per_clip": per_clip,
        "misses": misses,
        "warnings": warnings,
        "wrong_by_keyword": {k: dict(v) for k, v in wrong_by_keyword.items()},
        "by_tier": dict(by_tier),
        "overall": _sum(keys, list(by_tier)),
        "gate": gate,
        # How many clips carry the labelling the revised criterion needs. Partial
        # labelling is the dangerous case: the criterion would be computed over a
        # self-selected subset without saying so.
        "labelling": {
            "labelled_clips": labelled_clips,
            "total_clips": len(per_clip),
        },
    }


def _recall(bucket) -> float:
    return bucket["hits"] / bucket["total"] if bucket["total"] else 0.0


def _wp_recall(bucket) -> float:
    """Recall over words a human ear judged recognisable -- the criterion's 口径."""
    return bucket["wp_hits"] / bucket["wp_total"] if bucket["wp_total"] else 0.0


def _poor_recall(bucket) -> float:
    """Recall over words the learner did not pronounce clearly -- **not** gated."""
    return bucket["poor_hits"] / bucket["poor_total"] if bucket["poor_total"] else 0.0


# --------------------------------------------------------------------------- #
# 报告
# --------------------------------------------------------------------------- #
def report(result: dict, mode: str, min_clips: int) -> str:
    per_clip = result["per_clip"]
    print(f"== 逐条转写({len(per_clip)} 条)==")
    print(f"{'clip':28} {'tier':13} {'recall':>7}  transcript")
    for clip in per_clip:
        rec = f"{clip['hits']}/{clip['total']}"
        print(f"{clip['clip'][:27]:28} {clip['tier'][:12]:13} {rec:>7}  {clip['transcript'][:60]!r}")

    print("\n== 关键词召回 ==")
    overall = result["overall"]
    print(f"overall  合并口径 recall = {_recall(overall):.3f}  "
          f"({overall['hits']}/{overall['total']} 关键词)")
    print(f"{'tier':16} {'clips':>5} {'keywords':>9} {'合并':>7} "
          f"{'发音合格':>9} {'wilson95_lo':>12} {'(A)类':>7}")
    for tier in sorted(result["by_tier"], key=lambda t: (t not in GATE_TIERS, t)):
        bucket = result["by_tier"][tier]
        flag = "  <- G2 判据覆盖" if tier in GATE_TIERS else ""
        wp = f"{_wp_recall(bucket):.3f}" if bucket["wp_total"] else "—"
        poor = f"{_poor_recall(bucket):.3f}" if bucket["poor_total"] else "—"
        wl = wilson_lower(bucket["wp_hits"], bucket["wp_total"]) if bucket["wp_total"] else None
        wl_txt = f"{wl:.3f}" if wl is not None else "—"
        print(
            f"{tier:16} {bucket['clips']:>5} {bucket['total']:>9} "
            f"{_recall(bucket):>7.3f} {wp:>9} {wl_txt:>12} {poor:>7}{flag}"
        )
    print("  注:wilson95_lo 是**发音合格词**口径的下界(判据就走这个口径);"
          "「(A)类」列是学习者本就没说清楚的词,**不受判据约束**,并列报告用。")

    gate = result["gate"]
    gate_recall = _recall(gate)
    labelling = result["labelling"]
    fully_labelled = (
        labelling["total_clips"] > 0
        and labelling["labelled_clips"] == labelling["total_clips"]
    )
    # Zero labelling and partial labelling are different failures. With none, the
    # review doc permits falling back to the merged 口径 (loudly marked). With
    # some, the criterion would be computed over whichever clips happened to get
    # labelled -- a self-selected subset -- so no verdict is defensible.
    partly_labelled = 0 < labelling["labelled_clips"] < labelling["total_clips"]
    print(
        f"\n合并口径(infant + toddler,含学习者本就没说出的词):recall = {gate_recall:.3f}  "
        f"({gate['hits']}/{gate['total']} 关键词,{gate['clips']} 条录音)"
    )
    if gate["wp_total"]:
        print(
            f"**G2 判据口径(仅发音合格的词)**:recall = {_wp_recall(gate):.3f}  "
            f"({gate['wp_hits']}/{gate['wp_total']} 关键词)  判据 >= {GATE_RECALL}"
        )
    if gate["poor_total"]:
        print(
            f"并列参照 (A) 类(学习者没说清楚的词,**不是缺陷、不受判据约束**):"
            f"recall = {_poor_recall(gate):.3f}  ({gate['poor_hits']}/{gate['poor_total']})"
        )
    print(
        f"well_pronounced 标注覆盖:{labelling['labelled_clips']}/{labelling['total_clips']} 条录音"
    )
    if not fully_labelled:
        if partly_labelled:
            # Worse than none: the criterion would silently be computed over
            # whichever clips happened to get labelled.
            print("  ! 标注不完整 —— 判据口径只能在已标注子集上算,而那是个自选择子集。")
        else:
            print("  ! 全无标注 —— 判据口径不可算,只能退回合并口径(裁决已标为退化)。")
        print("    评审文档明令:此时**必须同时报告合并数与分层数**,不得只报有利的那个。")
        print("    标注规格见 scripts/fixtures/game_asr/README.md §4.1。")
    for tier in GATE_TIERS:
        bucket = result["by_tier"].get(tier)
        if bucket is None:
            print(f"  ! {tier} 级样本缺失 —— 该级未被测到")
            continue
        if bucket["wp_total"] and _wp_recall(bucket) < GATE_RECALL:
            print(f"  ! {tier} 级判据口径单独看 {_wp_recall(bucket):.3f} < {GATE_RECALL}"
                  "(合并数字掩盖了它)")
        elif not bucket["wp_total"] and _recall(bucket) < GATE_RECALL:
            print(f"  ! {tier} 级合并口径单独看 {_recall(bucket):.3f} < {GATE_RECALL}"
                  "(合并数字掩盖了它;该级无 well_pronounced 标注)")

    if result["misses"]:
        print(f"\n== 未命中明细({len(result['misses'])} 条)——「whisper 反而写成了什么」==")
        print("(降级路径 (b) 要往 accept 补的常见错形,从 wrong_forms 里挑)")
        for miss in result["misses"]:
            req = {True: "required", False: "optional", None: "无槽位归属"}[miss["required"]]
            cls = {
                True: "(B) 人耳听得出 —— **仪器的锅,受判据约束**",
                False: "(A) 学习者没说清楚 —— 不给物资是正确行为,不受判据约束",
                None: "未标注 well_pronounced —— 无法归类,只进合并口径",
            }[miss["well_pronounced"]]
            print(f"\n  clip      : {miss['clip']}  [{miss['tier']}] {miss['scenario']}")
            print(f"  期望关键词: {miss['keyword']!r}  (slot={miss['slot']}, {req})")
            print(f"  归类      : {cls}")
            if miss["intended"]:
                print(f"  说话人原话: {miss['intended']!r}")
            print(f"  whisper   : {miss['transcript']!r}")
            print(f"  近似错形  : {', '.join(miss['wrong_forms']) or '(转写里没有形近片段 —— 整词丢失)'}")

        if result["wrong_by_keyword"]:
            print("\n  -- 错形汇总(keyword -> 出现次数)--")
            for keyword, forms in sorted(result["wrong_by_keyword"].items()):
                top = ", ".join(f"{f}×{n}" for f, n in sorted(forms.items(), key=lambda kv: -kv[1]))
                print(f"    {keyword!r}: {top}")
    else:
        print("\n== 未命中明细:无 ==")

    if result["warnings"]:
        print(f"\n== 警告({len(result['warnings'])} 条)==")
        for warning in dict.fromkeys(result["warnings"]):
            print(f"  ! {warning}")

    # ---- 裁决 ---------------------------------------------------------- #
    # The criterion is defined over well-pronounced words. Fall back to the merged
    # figure only when the corpus lacks the labelling, and say so in the verdict --
    # a degraded 口径 that reads like the real one is exactly what the review doc
    # forbids.
    if gate["wp_total"]:
        judged_recall = _wp_recall(gate)
        judged_hits, judged_total = gate["wp_hits"], gate["wp_total"]
        judged_label = (
            "发音合格词口径(**仅已标注子集,不构成裁决**)" if partly_labelled
            else "发音合格词口径"
        )
    else:
        judged_recall = gate_recall
        judged_hits, judged_total = gate["hits"], gate["total"]
        judged_label = "合并口径(**退化** —— 语料无 well_pronounced 标注)"

    print("\n== 裁决 ==")
    print(f"  口径:{judged_label}  recall = {judged_recall:.3f} "
          f"({judged_hits}/{judged_total})  判据 >= {GATE_RECALL}")
    if mode == "synthetic-smoke":
        print("  **冒烟,不可回填 R-14**")
        print("  以上数字来自 Piper 合成语音:没有 L2 口音、没有 disfluency、没有环境噪声。")
        print("  在合成音上测会系统性偏乐观,等于悄悄作废这道门。本模式**不产出 PASS**。")
        print("  作用仅限于:证明 clip -> transcribe_waveform -> 槽位匹配这条量具能跑通。")
        return "SMOKE"
    if mode == "dry-run":
        print("  **打分逻辑自检,不可回填 R-14**")
        print("  转写文本由 manifest 预先给定,whisper 没有参与。本模式**不产出 PASS**。")
        return "DRY-RUN"
    if gate["total"] == 0:
        print("  **无数据** —— 受门 tier 没有任何期望关键词,G2 未被测量。")
        return "NO-DATA"
    if partly_labelled:
        # Applies to the proxy path too: a wp figure computed over whichever clips
        # happened to get labelled is a self-selected subset, not the criterion's
        # 口径. Zero labelling is a different case -- the review doc permits the
        # merged fallback, so it falls through and is judged, loudly marked.
        print("  **不出裁决** —— 判据口径要求逐词的 well_pronounced 标注,"
              f"现有覆盖 {labelling['labelled_clips']}/{labelling['total_clips']} 条,"
              "在这个自选择子集上算出来的数字不是判据。")
        print("  已按评审文档要求同时给出合并数与分层数(见上),两者都不构成裁决。")
        print("  补齐标注后重跑;标注规格见 scripts/fixtures/game_asr/README.md §4.1。")
        return "INCONCLUSIVE"
    if mode == "proxy-corpus":
        # The proxy is systematically EASIER than the target distribution on all
        # three axes (see module docstring), so the inference is one-directional:
        # falling short here is conclusive, clearing the bar here proves nothing.
        # Emitting PASS would silently substitute an easier distribution for the
        # one G2 names -- the same failure mode as the Piper ban, one step up.
        print("  **公开代理语料,不可回填 G2 的 PASS**")
        print("  代理在三个维度上都比目标分布更容易(词汇更常见、照稿朗读而非自发应答、")
        print("  仅普通话一种 L1),因此推论是单向的。")
        if judged_recall < GATE_RECALL:
            print(f"\n  PROXY-FAIL:代理 recall {judged_recall:.3f} < {GATE_RECALL}。")
            print("  这个结论**是可靠的** —— 更容易的分布上都没过,真实语料只会更差。")
            print("  直接后果:「转写默认完美」这一假设被实测驳回,降级路径必须启动。")
            print("    (a) 换更大的 whisper 档位 —— 需重新核 NFR-3 的延迟与体积")
            print("        注:实测只对 (B) 类有效(0.876→0.917);(A) 类是物理上限(0.300→0.333)")
            print("    (b) 往 accept 集合补入常见转写错形 —— 用上面的「错形汇总」")
            print("    (c) 解码配置:beam_size=5 + 场景 accept 作 hotwords(零体积零延迟)")
            return "PROXY-FAIL"
        print(f"\n  PROXY-INCONCLUSIVE:代理 recall {judged_recall:.3f} >= {GATE_RECALL},")
        print("  但这**不构成 G2 通过** —— 在更容易的分布上达标对目标分布无推论力。")
        print("  可以据此说「base.en 在照稿朗读的普通话 L2 短句上不丢词」,")
        print("  不能据此说「它在自发应答的多 L1 生存短语上不丢词」。")
        print(f"  Wilson 95% 下界 {wilson_lower(judged_hits, judged_total):.3f}。")
        return "PROXY-INCONCLUSIVE"
    if min_clips and gate["clips"] < min_clips:
        print(f"  **数据不足,暂不回填** —— infant + toddler 仅 {gate['clips']} 条"
              f"(脚手架下限 {min_clips},可用 --min-clips 调整)。")
        print(f"  点估计 {judged_recall:.3f},Wilson 95% 下界仅 "
              f"{wilson_lower(judged_hits, judged_total):.3f} —— 这个区间宽到无法支撑裁决。")
        print("  注:样本量下限是本脚手架的护栏,不是对 G2 判据的放宽或收紧。")
        return "INCONCLUSIVE"
    verdict = "PASS" if judged_recall >= GATE_RECALL else "FAIL"
    print(f"  G2 {verdict}:infant+toddler 关键词召回 {judged_recall:.3f} "
          f"{'>=' if verdict == 'PASS' else '<'} {GATE_RECALL}  [{judged_label}]")
    if not fully_labelled:
        print("  ! 该裁决走的是**退化口径** —— 语料无 well_pronounced 标注,"
              "(A)/(B) 两类漏词混在一个数里,判据的因果口径未成立。")
    if gate["poor_total"]:
        print(f"  (并列:(A) 类 {_poor_recall(gate):.3f} —— 学习者没说清楚的词,"
              "不参与裁决,出路见 FR-27 分诊)")
    if verdict == "FAIL":
        print("  降级路径(R-14 §2 G2,**不允许放宽判据**):")
        print("    (a) 换更大的 whisper 档位 —— 需重新核 NFR-3 的延迟与体积")
        print("    (b) 往 accept 集合补入常见转写错形 —— 用上面的「错形汇总」")
        print("    (c) 解码配置:beam_size=5 + 场景 accept 作 hotwords")
    return verdict


# --------------------------------------------------------------------------- #
# 裁决逻辑的回归自检
# --------------------------------------------------------------------------- #
# The four verdict branches differ only in the labelling coverage of the manifest,
# and three of them exist to *withhold* a number. A regression that silently turns
# INCONCLUSIVE into PASS would look like progress, so the branches are pinned here.
# Fixture transcripts are hand-written: this proves the scoring/verdict logic, and
# **no number from it is admissible for R-14** (same rule as --synthetic-smoke).
_SELF_TEST_CASES = (
    ("labelled-full.json", "PASS"),
    ("labelled-full-fail.json", "FAIL"),
    ("labelled-none.json", "FAIL"),          # 退化口径也必须能出 FAIL
    ("labelled-partial.json", "INCONCLUSIVE"),
)


def self_test(scenarios_dir: str) -> int:
    here = os.path.join(_REPO, "scripts", "fixtures", "game_asr", "verdict_cases")
    scenarios, notes = load_scenarios(scenarios_dir)
    for note in notes:
        print(f"  ! {note}")
    failures = []
    for name, expected in _SELF_TEST_CASES:
        entries = load_manifest(os.path.join(here, name))
        transcripts = {e["row"]: e["transcript"] for e in entries}
        print(f"\n{'=' * 78}\n== self-test: {name}(期望 {expected})\n{'=' * 78}")
        # mode="measure" on purpose -- dry-run short-circuits before the verdict,
        # so it cannot exercise what this test is for. min_clips=0 because the
        # fixtures are 2-5 clips by design; the sample-size guard is scaffolding,
        # not one of the branches under test.
        verdict = report(score(entries, scenarios, transcripts), "measure", 0)
        ok = verdict == expected
        print(f"\n>>> {name}: {verdict}  {'ok' if ok else f'!! 期望 {expected}'}")
        if not ok:
            failures.append((name, expected, verdict))
    print(f"\n{'=' * 78}")
    if failures:
        print(f"self-test FAILED（{len(failures)}/{len(_SELF_TEST_CASES)}）:")
        for name, expected, got in failures:
            print(f"  {name}: 期望 {expected},实得 {got}")
        return 1
    print(f"self-test ok（{len(_SELF_TEST_CASES)}/{len(_SELF_TEST_CASES)} 条裁决分支符合预期）")
    print("注:fixture 的 transcript 是手写的,**没有任何真实录音** ——")
    print("    本模式只证明打分与裁决逻辑没写错,数字一律不可回填 R-14。")
    return 0


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(
        description="R-14 G2:base.en 在 L2 短语上的关键词召回(不算整句 WER)",
    )
    ap.add_argument("--manifest", help="JSON 或 CSV,见模块 docstring")
    ap.add_argument("--clips", help="音频目录(manifest 的 clip 字段相对于它)")
    ap.add_argument(
        "--scenarios",
        default=os.path.join(_DESKTOP, "backend", "core", "game_scenarios"),
        help="场景库目录;缺失或为空时降级为「关键词未经 accept 校验」",
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="用 manifest 里的 transcript 字段,不加载 whisper(只验打分逻辑)")
    ap.add_argument("--synthetic-smoke", action="store_true",
                    help="用 Piper 合成音跑通量具。**永不产出 PASS**,数字标注为冒烟")
    ap.add_argument("--proxy-corpus", action="store_true",
                    help="公开 L2 语料(真人录音,非合成)。只能证伪:低于阈值 -> "
                         "PROXY-FAIL(可靠);高于阈值 -> PROXY-INCONCLUSIVE。**永不 PASS**")
    ap.add_argument("--min-clips", type=int, default=30,
                    help="infant+toddler 合计低于此数只报 INCONCLUSIVE(0 关闭)")
    ap.add_argument("--json-out", help="把完整结果写成 JSON,便于回填评审文档")
    ap.add_argument("--self-test", action="store_true",
                    help="用 scripts/fixtures/game_asr/verdict_cases/ 的 fixture 检查四条"
                         "裁决分支(不加载 whisper、不需要语料)。**数字不可回填 R-14**")
    args = ap.parse_args()

    if args.self_test:
        return self_test(args.scenarios)
    if not args.manifest:
        ap.error("需要 --manifest(或用 --self-test 只跑裁决分支自检)")

    exclusive = [args.dry_run, args.synthetic_smoke, args.proxy_corpus]
    if sum(bool(flag) for flag in exclusive) > 1:
        ap.error("--dry-run / --synthetic-smoke / --proxy-corpus 三者互斥")
    mode = (
        "dry-run" if args.dry_run
        else "synthetic-smoke" if args.synthetic_smoke
        else "proxy-corpus" if args.proxy_corpus
        else "measure"
    )

    entries = load_manifest(args.manifest)
    if not entries:
        print(f"manifest 为空:{args.manifest}", file=sys.stderr)
        return 2

    scenarios, notes = load_scenarios(args.scenarios)
    print(f"== 场景库:{len(scenarios)} 个场景 ==")
    for note in notes:
        print(f"  ! {note}")
    missing = sorted({e["scenario"] for e in entries if e["scenario"] and e["scenario"] not in scenarios})
    if missing:
        print(f"  ! manifest 引用了未找到的场景:{', '.join(missing)}")

    if mode == "measure":
        print("\n注意:R-10 的 4.01% 归一化 WER 是新闻播报语料上的数字,与本分布无关"
              "(G2 已写明不可外推)。以下数字必须来自真人 L2 录音。")
    elif mode == "proxy-corpus":
        print("\n代理语料模式:录音是真人 L2(不受合成音禁令约束),但分布比目标更容易 ——"
              "\n低于阈值可下 FAIL,高于阈值不构成 PASS。详见模块 docstring。")

    transcripts: dict[int, str] = {}
    if mode == "dry-run":
        for entry in entries:
            transcripts[entry["row"]] = entry["transcript"]
        blank = [e["clip"] or f"row{e['row']}" for e in entries if not e["transcript"]]
        if blank:
            print(f"  ! --dry-run:这些条目没有 transcript 字段,按空转写计:{blank}")
    else:
        print(f"\n== 加载 faster-whisper base.en(transcribe.py:255)==", flush=True)
        try:
            from backend.core import transcribe  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            print(f"无法 import backend.core.transcribe: {exc}", file=sys.stderr)
            print("改用 --dry-run 只验打分逻辑(但那不是 G2 的测量)。", file=sys.stderr)
            return 3
        if mode == "synthetic-smoke":
            print("== 加载 TTS(仅冒烟用)==", flush=True)
            print(f"  voice = {_load_smoke_voice()}", flush=True)
        for entry in entries:
            label = entry["clip"] or entry["say"] or f"row{entry['row']}"
            try:
                if mode == "synthetic-smoke":
                    text = entry["say"] or entry["intended"]
                    if not text:
                        raise ValueError("--synthetic-smoke 需要 say(或 intended)字段")
                    transcripts[entry["row"]] = synth_transcribe(text)
                else:
                    path = os.path.join(args.clips or "", entry["clip"])
                    if not os.path.isfile(path):
                        raise FileNotFoundError(path)
                    transcripts[entry["row"]] = transcribe_file(path)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {label}: 转写失败 {type(exc).__name__}: {exc}")
                transcripts[entry["row"]] = ""
            else:
                print(f"  {label} -> {transcripts[entry['row']]!r}", flush=True)

    print()
    result = score(entries, scenarios, transcripts)
    verdict = report(result, mode, args.min_clips)

    if args.json_out:
        payload = dict(result)
        payload["mode"] = mode
        payload["verdict"] = verdict
        payload["gate_criterion"] = {"recall": GATE_RECALL, "tiers": list(GATE_TIERS)}
        payload["caveat"] = (
            "关键词召回口径,不含整句 WER(R-14 G2)。"
            "mode != measure 时数字不可回填 R-14。"
        )
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        print(f"\n完整结果 -> {args.json_out}")

    print("\n下一步:把 recall / 逐 tier 数字与裁决抄进 "
          "docs/reviews/2026-08-08-survival-game-fit.md §2 的 G2 行。")
    print("语料仍缺的部分见 scripts/fixtures/game_asr/README.md。")
    # PROXY-INCONCLUSIVE exits 0 like the other non-verdicts: the harness ran and
    # produced no verdict, which is not a failure. PROXY-FAIL exits 1 because it
    # IS a conclusion -- the easier distribution already fell short.
    return 0 if verdict in ("PASS", "SMOKE", "DRY-RUN", "PROXY-INCONCLUSIVE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
