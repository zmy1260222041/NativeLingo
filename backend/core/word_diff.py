"""Word-level pronunciation difference diagnosis (逐词读法改进方向).

The reverse-cloning insight made concrete. Cloning/expressive-TTS models work by
disentangling speech into *content / speaker / prosody*. To actually *improve* a
learner we do the inverse: hold content fixed (same words), discard the speaker
factor (different voice — irrelevant), and isolate the **prosodic delta** between
reference and learner on each word — where the stress sits, whether adjacent
words link, vowel length, pitch movement — then name that delta in words the
learner can act on. This is the thing they cannot hear themselves.

Inputs:
* the reference clip waveform + its per-word timestamps (clip-relative seconds)
* the learner recording + its independently-transcribed per-word timestamps

We match the two word sequences by text, then compare each flagged word
acoustically via short-time energy (stress location, vowel length) and
Parselmouth pitch (intonation movement), plus inter-word gaps (linking / 连读).

The output is a short, targeted Chinese coaching line per problem word, and the
learner's own word span so the frontend can play reference vs learner side by
side. A pluggable ``llm_rephrase`` hook can later turn the structured diff into
richer wording; the default rule verbaliser already points out the exact
difference.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

import numpy as np

try:  # pitch is optional — never let it break diagnosis
    import parselmouth
    _HAS_PRAAT = True
except Exception:  # noqa: BLE001
    _HAS_PRAAT = False

SR = 16000

# thresholds
_STRESS_POS_DELTA = 0.28        # normalized-position gap to call a stress shift
_LINK_REF_MAX_GAP = 0.06        # ref gap below this == words are linked
_LINK_EXTRA_GAP = 0.10          # learner gap this much larger == learner broke it
_SHORT_RATIO = 0.62             # learner/ref duration below this == clipped
_LONG_RATIO = 1.75              # ... above this == dragged out
_PITCH_MIN_SLOPE = 12.0         # Hz/word span to consider a real pitch move
_MIN_SPAN_S = 0.05              # ignore spans shorter than this


@dataclass
class WordDiff:
    si: int                     # sentence position within the selected range
    wi: int                     # word position within the sentence
    word: str
    tip: str                    # Chinese coaching line ("" if nothing notable)
    learner_start: float = 0.0  # learner-recording seconds (for replay)
    learner_end: float = 0.0
    tags: list[str] = field(default_factory=list)  # machine tags for the LLM hook


# --------------------------------------------------------------------------- #
# small acoustic helpers
# --------------------------------------------------------------------------- #
def _slice(wav: np.ndarray, start: float, end: float) -> np.ndarray:
    a = max(0, int(round(start * SR)))
    b = min(len(wav), int(round(end * SR)))
    return wav[a:b] if b > a else np.empty(0, dtype="float32")


def _rms_envelope(span: np.ndarray, frame: float = 0.025, hop: float = 0.005):
    """Short-time RMS energy envelope over a word span."""
    n = len(span)
    fl = max(1, int(frame * SR))
    hp = max(1, int(hop * SR))
    if n < fl:
        return None
    idx = range(0, n - fl + 1, hp)
    env = np.array([np.sqrt(np.mean(span[i:i + fl] ** 2) + 1e-9) for i in idx])
    if env.size < 3:
        return None
    return env


def _stress_pos(span: np.ndarray):
    """Normalized position [0,1] of the loudest part of a word (its stress).

    Returns None if the span is too short or too flat to judge.
    """
    env = _rms_envelope(span)
    if env is None:
        return None
    # smooth a touch to avoid picking a single spiky frame
    k = min(5, env.size)
    if k >= 3:
        env = np.convolve(env, np.ones(k) / k, mode="same")
    lo, hi = float(env.min()), float(env.max())
    if hi - lo < 0.02 * (hi + 1e-6):   # essentially flat -> no clear stress
        return None
    peak = int(np.argmax(env))
    return peak / max(env.size - 1, 1)


def _pitch_slope(span: np.ndarray):
    """Linear F0 slope (Hz across the word). +rising / -falling / None."""
    if not _HAS_PRAAT or len(span) < int(_MIN_SPAN_S * SR):
        return None
    try:
        snd = parselmouth.Sound(span.astype("float64"), sampling_frequency=SR)
        f0 = snd.to_pitch().selected_array["frequency"]
    except Exception:  # noqa: BLE001
        return None
    voiced_idx = np.where(f0 > 0)[0]
    if voiced_idx.size < 4:
        return None
    x = voiced_idx.astype("float64")
    y = f0[voiced_idx]
    slope, _ = np.polyfit(x, y, 1)
    return float(slope * f0.size)  # Hz across the whole span


# --------------------------------------------------------------------------- #
# syllable heuristics (no dictionary — good enough to anchor advice)
# --------------------------------------------------------------------------- #
def _syllables(word: str) -> list[str]:
    """Rough English syllable split by vowel groups. Not linguistically exact,
    but gives usable anchors like ['spe', 'cial'] for 'special'."""
    w = re.sub(r"[^a-zA-Z]", "", word)
    if not w:
        return [word]
    lw = w.lower()
    # find vowel-group boundaries
    vowels = "aeiouy"
    groups = []  # indices where each syllable nucleus (vowel run) starts
    i = 0
    n = len(lw)
    while i < n:
        if lw[i] in vowels:
            j = i
            while j < n and lw[j] in vowels:
                j += 1
            groups.append((i, j))
            i = j
        else:
            i += 1
    if len(groups) <= 1:
        return [w]
    # split points: midway between consecutive vowel groups
    cuts = [0]
    for (s0, e0), (s1, e1) in zip(groups, groups[1:]):
        mid = (e0 + s1) // 2
        mid = max(cuts[-1] + 1, min(mid, n - 1))
        cuts.append(mid)
    cuts.append(n)
    parts = [w[cuts[k]:cuts[k + 1]] for k in range(len(cuts) - 1)]
    return [p for p in parts if p] or [w]


def _emphasize(sylls: list[str], idx: int) -> str:
    """Render a word with one syllable upper-cased: spe-CIAL."""
    idx = max(0, min(idx, len(sylls) - 1))
    out = list(sylls)
    out[idx] = out[idx].upper()
    return "-".join(out)


def _syll_idx(pos: float, nsyll: int) -> int:
    return max(0, min(int(pos * nsyll), nsyll - 1))


def _norm(tok: str) -> str:
    return re.sub(r"[^a-z]", "", tok.lower())


# --------------------------------------------------------------------------- #
# per-word verbaliser
# --------------------------------------------------------------------------- #
def _describe_word(word: str, ref_span: np.ndarray, learner_span: np.ndarray,
                   ref_dur: float, learner_dur: float) -> tuple[str, list[str]]:
    """Return (chinese_tip, tags) for a single flagged word by comparing the two
    audio spans. Empty string if nothing specific stands out."""
    parts: list[str] = []
    tags: list[str] = []

    # --- stress location ---
    rp = _stress_pos(ref_span)
    lp = _stress_pos(learner_span)
    if rp is not None and lp is not None and abs(rp - lp) >= _STRESS_POS_DELTA:
        sylls = _syllables(word)
        n = len(sylls)
        if n >= 2:
            ri, li = _syll_idx(rp, n), _syll_idx(lp, n)
            if ri != li:
                parts.append(
                    f"重音位置不同：原声重读第 {ri + 1} 个音节（{_emphasize(sylls, ri)}），"
                    f"你却重读了第 {li + 1} 个音节（{_emphasize(sylls, li)}）。"
                    f"试着弱读其它音节、只把 “{sylls[ri]}” 读得更重更长。"
                )
                tags.append("stress_shift")
        if not tags:  # single-syllable or syllabifier gave one part
            where_ref = "后半部" if rp > 0.5 else "前半部"
            where_you = "后半部" if lp > 0.5 else "前半部"
            parts.append(
                f"用力点不同：原声把这个词的重音放在{where_ref}，你放在了{where_you}。"
            )
            tags.append("stress_half")

    # --- linking / vowel length via duration ---
    if ref_dur > 0 and learner_dur > 0:
        ratio = learner_dur / ref_dur
        if ratio < _SHORT_RATIO:
            parts.append(
                f"你把这个词读得太短（约为原声的 {ratio:.0%}），像是吞音了。"
                f"原声把元音拉得更长更饱满，放慢、把元音读足。"
            )
            tags.append("clipped")
        elif ratio > _LONG_RATIO:
            parts.append(
                f"你把这个词拖得过长（约为原声的 {ratio:.0%}），原声更干脆利落。"
            )
            tags.append("dragged")

    # --- pitch movement ---
    rs = _pitch_slope(ref_span)
    ls = _pitch_slope(learner_span)
    if rs is not None and abs(rs) >= _PITCH_MIN_SLOPE:
        ref_dir = "上扬" if rs > 0 else "下沉"
        if ls is None or abs(ls) < _PITCH_MIN_SLOPE or (ls > 0) != (rs > 0):
            you_dir = "偏平" if (ls is None or abs(ls) < _PITCH_MIN_SLOPE) else ("上扬" if ls > 0 else "下沉")
            parts.append(
                f"音高走向不同：原声在这个词上{ref_dir}，你读得{you_dir}。"
                f"跟着原声让音调{ref_dir}。"
            )
            tags.append("pitch")

    # keep it focused: at most two points
    return " ".join(parts[:2]), tags[:2]


def _describe_linking(w1: str, w2: str) -> str:
    return (
        f"连读处：原声把 “{w1}” 和 “{w2}” 连在一起、中间不停顿，"
        f"你却分开读了。把 “{w1}” 的词尾接到 “{w2}” 开头，连成一口气（{w1}‿{w2}）。"
    )


# --------------------------------------------------------------------------- #
# main entry
# --------------------------------------------------------------------------- #
def diagnose_words(
    ref_wav: np.ndarray,
    learner_wav: np.ndarray,
    ref_flat: list[dict],
    learner_flat: list[dict],
    llm_rephrase=None,
) -> dict:
    """Compare flagged reference words against the matched learner words.

    ``ref_flat``: [{si, wi, word, start, end, status}] clip-relative seconds.
    ``learner_flat``: [{word, start, end}] in learner-recording seconds.

    Returns {(si, wi): WordDiff} for every reference word we could match to a
    learner word and that is worth commenting on (flagged + a real difference,
    or a broken link at the junction).
    """
    out: dict[tuple[int, int], WordDiff] = {}
    if not ref_flat or not learner_flat:
        return out

    ref_tokens = [_norm(r["word"]) for r in ref_flat]
    learner_tokens = [_norm(l["word"]) for l in learner_flat]

    # align the two token sequences; matched blocks give ref_i <-> learner_j
    sm = difflib.SequenceMatcher(a=ref_tokens, b=learner_tokens, autojunk=False)
    ref_to_learner: dict[int, int] = {}
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            ref_to_learner[a + k] = b + k

    for ri, r in enumerate(ref_flat):
        status = r.get("status", "good")
        li = ref_to_learner.get(ri)

        # word-level pronunciation delta (only for flagged, matched words)
        if status in ("weak", "bad") and li is not None:
            lw = learner_flat[li]
            ref_span = _slice(ref_wav, r["start"], r["end"])
            learner_span = _slice(learner_wav, lw["start"], lw["end"])
            ref_dur = r["end"] - r["start"]
            learner_dur = lw["end"] - lw["start"]
            if ref_span.size and learner_span.size:
                tip, tags = _describe_word(r["word"], ref_span, learner_span,
                                           ref_dur, learner_dur)
                if tip:
                    out[(r["si"], r["wi"])] = WordDiff(
                        si=r["si"], wi=r["wi"], word=r["word"], tip=tip,
                        learner_start=round(lw["start"], 3),
                        learner_end=round(lw["end"], 3),
                        tags=tags,
                    )

        # linking at the junction to the next word in the SAME sentence
        if ri + 1 < len(ref_flat) and ref_flat[ri + 1]["si"] == r["si"]:
            nxt = ref_flat[ri + 1]
            ref_gap = nxt["start"] - r["end"]
            lj = ref_to_learner.get(ri + 1)
            if li is not None and lj is not None and ref_gap <= _LINK_REF_MAX_GAP:
                learner_gap = learner_flat[lj]["start"] - learner_flat[li]["end"]
                if learner_gap - ref_gap >= _LINK_EXTRA_GAP:
                    key = (r["si"], r["wi"])
                    link_tip = _describe_linking(r["word"], nxt["word"])
                    if key in out:
                        out[key].tip = (out[key].tip + " " + link_tip).strip()
                        out[key].tags.append("link")
                    else:
                        lw = learner_flat[li]
                        out[key] = WordDiff(
                            si=r["si"], wi=r["wi"], word=r["word"], tip=link_tip,
                            learner_start=round(lw["start"], 3),
                            learner_end=round(learner_flat[lj]["end"], 3),
                            tags=["link"],
                        )

    # optional richer phrasing from an external LLM (structured diff -> prose)
    if llm_rephrase is not None:
        for key, wd in out.items():
            try:
                better = llm_rephrase({"word": wd.word, "tags": wd.tags, "tip": wd.tip})
                if better:
                    wd.tip = better
            except Exception:  # noqa: BLE001 - never let the LLM break feedback
                pass

    return out
