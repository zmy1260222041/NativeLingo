"""Phoneme-level mispronunciation diagnosis (FR-11, MDD track).

Word-level diff (word_diff.py) can say *how* a word's prosody differs (stress,
length, pitch). This module answers the complementary question — *which sound*
was substituted: "the /θ/ in 'think' came out as /s/".

Method (hypothesis-comparison MDD):
* decode the REFERENCE word span into a canonical IPA sequence with a
  phoneme-CTC wav2vec2 (facebook/wav2vec2-lv-60-espeak-cv-ft). Reference
  speech is clean, so this decode is trustworthy; it also captures the
  anchor's actual pronunciation (fits shadowing: imitate this speaker)
* NEVER decode the learner (CTC greedy decodes of ~0.3 s spans are too noisy
  to compare). Instead score the canonical sequence against the learner's CTC
  emissions by forced Viterbi alignment, then test every single-phoneme
  substitution / deletion variant: if a variant beats the canonical by a clear
  margin, that substitution is what the learner really said
* diagnoses are only emitted for words already flagged weak/bad by the
  calibrated DTW path, and only past a gain margin, to keep noise out
"""
from __future__ import annotations

import difflib
import functools
import re
from dataclasses import dataclass, field

import numpy as np

from .audio_io import TARGET_SR

MODEL_NAME = "facebook/wav2vec2-lv-60-espeak-cv-ft"

# only accept a diagnosis when the phoneme-string similarity is at least this
# (below that, decode noise dominates on short spans)
_MIN_SEQ_RATIO = 0.5
_MAX_SUBS_PER_WORD = 2


@functools.lru_cache(maxsize=1)
def _load():
    """Load the espeak CTC model (server variant: int8 ONNX export, R-7).

    The desktop loads torch fp32 weights via transformers (~2.4 GB); this
    deployment runs ``espeak_cv_ft_int8.onnx`` (317 MB) through onnxruntime —
    the same export the Android catalog pinned. The graph omits the feature
    extractor's normalization, so [onnx_runtime.normalize_wav2vec2] is applied
    before the run; the vocab (id → IPA token) is loaded from the HF repo's
    ``vocab.json`` (mirrors what ``AutoProcessor`` would provide without the
    phonemizer dependency).
    """
    import json
    import os

    from huggingface_hub import hf_hub_download

    from .onnx_runtime import model_path, session

    sess = session(model_path("espeak_cv_ft_int8.onnx"))
    input_name = sess.get_inputs()[0].name
    output_name = sess.get_outputs()[0].name

    # manual id<->IPA maps: avoids the phonemizer/espeak dependency that
    # AutoProcessor pulls in (only needed for text->phonemes, not audio decode).
    # Prefer a bundled vocab.json in the models dir — the deploy box cannot
    # reach huggingface.co (China network), so the vocab ships with the models.
    vocab_path = os.environ.get("NATIVELINGO_ESPEAK_VOCAB") or model_path("vocab.json")
    if not os.path.exists(vocab_path):
        vocab_path = hf_hub_download(MODEL_NAME, "vocab.json")
    with open(vocab_path) as f:
        vocab = json.load(f)
    id2tok = {v: k for k, v in vocab.items()}
    pad_id = vocab.get("<pad>", 0)
    return sess, input_name, output_name, id2tok, vocab, pad_id


def is_available() -> bool:
    try:
        _load()
        return True
    except Exception:  # noqa: BLE001
        return False


def decode_phonemes(wav: np.ndarray) -> str:
    """Decode a 16 kHz mono span into an IPA phoneme string (CTC greedy)."""
    from .onnx_runtime import normalize_wav2vec2

    sess, input_name, output_name, id2tok, _vocab, pad_id = _load()
    if wav.size == 0:
        return ""
    normalized = normalize_wav2vec2(np.asarray(wav, dtype="float32"))
    logits = sess.run([output_name], {input_name: normalized[None, :]})[0][0]
    ids = logits.argmax(axis=-1).tolist()
    # CTC collapse: drop consecutive duplicates and padding
    out = []
    prev = None
    for i in ids:
        if i != prev and i != pad_id:
            out.append(id2tok.get(i, ""))
        prev = i
    return "".join(out)


def _emissions(wav: np.ndarray) -> np.ndarray:
    """CTC log-softmax emissions (T, V) for a 16 kHz mono span."""
    from .onnx_runtime import log_softmax, normalize_wav2vec2

    sess, input_name, output_name, _i2t, _v, _p = _load()
    if wav.size == 0:
        return np.zeros((0, 392), dtype="float32")
    normalized = normalize_wav2vec2(np.asarray(wav, dtype="float32"))
    logits = sess.run([output_name], {input_name: normalized[None, :]})[0][0]
    return log_softmax(logits).astype("float32")


def _viterbi_avg(em: np.ndarray, seq_ids: list[int], blank: int = 0) -> float:
    """Forced-align a phoneme id sequence to CTC emissions; mean logprob/frame.

    Classic CTC alignment DP over the blank-extended sequence. Comparing this
    score between competing phoneme hypotheses (canonical vs substituted) is
    the MDD trick — no learner-side decode needed, so it's robust to the CTC
    decoder's flakiness on short spans.
    """
    score, _ = _viterbi_align(em, seq_ids, blank)
    return score


def _viterbi_align(
    em: np.ndarray, seq_ids: list[int], blank: int = 0
) -> tuple[float, list[tuple[int, int, int]]]:
    """CTC forced alignment with backpointers.

    Returns (mean logprob/frame, [(ext_pos, first_frame, last_frame)]) where
    ext_pos indexes the blank-extended sequence — used to attribute canonical
    phonemes to frame ranges so neighbour phonemes leaking into a padded
    decode can be cropped back to the target word.
    """
    T = em.shape[0]
    ext = [blank]
    for s in seq_ids:
        ext += [s, blank]
    S = len(ext)
    NEG = -1e30
    dp = np.full((T, S), NEG, dtype="float64")
    bp = np.full((T, S), -1, dtype="int16")
    dp[0, 0] = em[0, blank]
    if S > 1:
        dp[0, 1] = em[0, ext[1]]
        bp[0, 1] = 0
    for t in range(1, T):
        row = em[t]
        for s in range(S):
            cands = [(dp[t - 1, s], s)]
            if s - 1 >= 0:
                cands.append((dp[t - 1, s - 1], s - 1))
            if s - 2 >= 0 and ext[s] != blank and ext[s] != ext[s - 2]:
                cands.append((dp[t - 1, s - 2], s - 2))
            val, src = max(cands)
            if val <= NEG:
                continue
            dp[t, s] = row[ext[s]] + val
            bp[t, s] = src
    last = S - 1 if dp[T - 1, S - 1] >= (dp[T - 1, S - 2] if S > 1 else NEG) else S - 2
    final = dp[T - 1, last]

    # walk back; collect frame range per ext position
    ranges: dict[int, list[int]] = {}
    t, s = T - 1, last
    while t >= 0 and s >= 0:
        ranges.setdefault(s, []).append(t)
        s = bp[t, s]
        t -= 1
    spans = [(s, min(ts), max(ts)) for s, ts in sorted(ranges.items())]
    return float(final / max(T, 1)), spans


def _tokens(phones: str) -> list[str]:
    """Split an IPA string into comparison units: base char + length mark."""
    # keep long-vowel mark ː attached to its vowel; strip spaces/stress/boundary
    phones = (phones.replace(" ", "").replace(".", "")
              .replace("ˈ", "").replace("ˌ", ""))
    out = []
    for ch in phones:
        if ch == "ː" and out:
            out[-1] += ch
        else:
            out.append(ch)
    return out


@dataclass
class PhoneSub:
    ref: str            # intended phoneme (from the reference decode)
    observed: str       # what the learner produced ("" = dropped)
    kind: str           # "substitute" | "delete" | "insert"


@dataclass
class PhoneDiag:
    subs: list[PhoneSub] = field(default_factory=list)
    ref_phones: str = ""
    learner_phones: str = ""


def diff_phonemes(ref_phones: str, learner_phones: str) -> PhoneDiag | None:
    """Align two IPA strings and extract the salient substitution(s).

    Returns None when the decodes are too different to trust (noise) or
    identical (nothing to say).
    """
    ref_tok, lrn_tok = _tokens(ref_phones), _tokens(learner_phones)
    if not ref_tok or not lrn_tok:
        return None
    sm = difflib.SequenceMatcher(a=ref_tok, b=lrn_tok, autojunk=False)
    if sm.ratio() < _MIN_SEQ_RATIO:
        return None
    subs: list[PhoneSub] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            for r, l in zip(ref_tok[i1:i2], lrn_tok[j1:j2]):
                subs.append(PhoneSub(r, l, "substitute"))
            # unpaired tails of a replace block
            if (i2 - i1) > (j2 - j1):
                for r in ref_tok[i1 + (j2 - j1):i2]:
                    subs.append(PhoneSub(r, "", "delete"))
            elif (j2 - j1) > (i2 - i1):
                for l in lrn_tok[j1 + (i2 - i1):j2]:
                    subs.append(PhoneSub("", l, "insert"))
        elif tag == "delete":
            for r in ref_tok[i1:i2]:
                subs.append(PhoneSub(r, "", "delete"))
        elif tag == "insert":
            for l in lrn_tok[j1:j2]:
                subs.append(PhoneSub("", l, "insert"))
    if not subs:
        return None
    return PhoneDiag(subs=subs[:_MAX_SUBS_PER_WORD],
                     ref_phones=ref_phones, learner_phones=learner_phones)


# --------------------------------------------------------------------------- #
# verbalisation (Chinese coaching line)
# --------------------------------------------------------------------------- #
# articulation hints for frequent learner confusions; generic fallback below
_HINTS: dict[tuple[str, str], str] = {
    ("θ", "s"): "/θ/ 要把舌尖伸到上下牙之间送气,不要读成 /s/(舌尖收回齿龈)。",
    ("θ", "t"): "/θ/ 是摩擦音,舌尖伸到牙间送气,不要读成塞音 /t/。",
    ("ð", "z"): "/ð/ 舌尖伸到牙间振动声带,不要读成 /z/。",
    ("ð", "d"): "/ð/ 是摩擦音,舌尖伸到牙间,不要读成塞音 /d/。",
    ("ɪ", "i"): "/ɪ/ 短促放松(如 ship),不要拉长成 /iː/(sheep)。",
    ("i", "ɪ"): "/iː/ 要读足长度并绷紧(如 sheep),不要读成短松的 /ɪ/。",
    ("æ", "e"): "/æ/ 嘴张得更大、舌位更低(如 bad),不要读成 /e/(bed)。",
    ("e", "æ"): "/e/ 开口比 /æ/ 小,不要把 bed 读成 bad。",
    ("v", "w"): "/v/ 上齿轻咬下唇振动,不要读成圆唇的 /w/。",
    ("w", "v"): "/w/ 双唇收圆,不要咬唇读成 /v/。",
    ("ŋ", "n"): "/ŋ/ 舌根抬起(如 sing 词尾),不要读成舌尖 /n/。",
    ("l", "r"): "/l/ 舌尖抵上齿龈,不要卷舌读成 /r/。",
    ("r", "l"): "/r/ 舌尖卷起不碰上颚,不要读成 /l/。",
    ("ʃ", "s"): "/ʃ/ 舌面抬起、唇略圆(如 ship),不要读成 /s/。",
    ("tʃ", "ʃ"): "/tʃ/ 先塞后擦(如 church),不要读成纯摩擦 /ʃ/。",
}


def verbalize(diag: PhoneDiag, word: str) -> str:
    """Turn a PhoneDiag into a short Chinese coaching line."""
    parts: list[str] = []
    for sub in diag.subs:
        if sub.kind == "substitute":
            hint = _HINTS.get((sub.ref, sub.observed))
            base = f"原声这里是 /{sub.ref}/,你读成了 /{sub.observed}/"
            parts.append(f"{base}。{hint}" if hint else f"{base}。")
        elif sub.kind == "delete":
            parts.append(f"/{sub.ref}/ 被吞掉了,要补出来。")
        else:
            parts.append(f"多读了一个 /{sub.observed}/,原声里没有这个音。")
    if not parts:
        return ""
    if diag.learner_phones:
        phones_info = f"(原声音标 /{diag.ref_phones}/,你的 /{diag.learner_phones}/)"
    else:
        phones_info = f"(原声音标 /{diag.ref_phones}/)"
    return " ".join(parts[:2]) + " " + phones_info


def _slice_with_context(wav: np.ndarray, start: float, end: float,
                        ctx: float = 0.25) -> np.ndarray:
    """Word span padded with acoustic context. CTC phoneme models are trained
    on continuous speech and fall apart on bare ~0.3 s word clips (onset
    fricatives like /θ/ get dropped); ±0.25 s of context restores them. The
    same window is used for reference and learner, so neighbour phonemes
    entering both decodes cancel out in the diff."""
    a = max(0, int(round((start - ctx) * TARGET_SR)))
    b = min(len(wav), int(round((end + ctx) * TARGET_SR)))
    return wav[a:b] if b > a else np.empty(0, dtype="float32")


# phoneme pool for substitution hypotheses (common English IPA in this vocab)
_CANDIDATES = "θðsztdɪiæevwŋnlrʃɔɑʊuəɛɹjhkɡmpbf"
# min per-frame logprob gain (vs the canonical hypothesis) to accept a
# substitution — below this the evidence is decode noise
_MARGIN = 0.15
# canonical-quality gate: the same sweep on the reference's own emissions must
# come back near-zero, i.e. the canonical decode fits the reference almost
# perfectly. Precision-first: MDD fires rarely, but is right when it fires
# (tuned on the think/sink suite: perfect canonicals gate ≤0.04, junk ≥0.09).
_GATE_MAX = 0.05


def _best_sub_gain(em: np.ndarray, ids: list[int], chars: list[str],
                   vocab: dict, pad_id: int) -> tuple[float, PhoneSub | None]:
    """Best single-phoneme substitution/deletion gain over the canonical."""
    base = _viterbi_avg(em, ids, pad_id)
    best_gain, best_sub = 0.0, None
    for i, p in enumerate(chars):
        if p == "ː":
            continue
        for c in _CANDIDATES:
            if c == p or c not in vocab:
                continue
            ids2 = ids[:i] + [vocab[c]] + ids[i + 1:]
            gain = _viterbi_avg(em, ids2, pad_id) - base
            if gain > best_gain:
                best_gain, best_sub = gain, PhoneSub(p, c, "substitute")
        ids2 = ids[:i] + ids[i + 1:]
        if ids2:
            gain = _viterbi_avg(em, ids2, pad_id) - base
            if gain > best_gain:
                best_gain, best_sub = gain, PhoneSub(p, "", "delete")
    return best_gain, best_sub


def diagnose_word_span(
    ref_wav: np.ndarray,
    ref_start: float,
    ref_end: float,
    learner_wav: np.ndarray,
    learner_start: float,
    learner_end: float,
    word: str,
) -> str:
    """MDD for one flagged word via competing-hypothesis CTC scoring.

    Steps: decode the padded reference span -> canonical IPA; Viterbi-align
    the canonical back to the reference emissions and CROP it to phonemes
    whose frames fall inside the target word (otherwise neighbour words bleed
    into the canonical and substitutions get misattributed); gate the cropped
    canonical on the reference itself (a canonical that doesn't even fit the
    reference is a broken decode -> stay silent); finally sweep
    substitution/deletion hypotheses against the learner's emissions.
    """
    try:
        CTX = 0.25
        a = max(0, int(round((ref_start - CTX) * TARGET_SR)))
        b = min(len(ref_wav), int(round((ref_end + CTX) * TARGET_SR)))
        if b - a < TARGET_SR // 4:
            return ""
        ref_span = ref_wav[a:b]
        learner_span = _slice_with_context(learner_wav, learner_start, learner_end)
        if learner_span.size == 0:
            return ""

        ref_phones = decode_phonemes(ref_span)
        _, _, _, _, vocab, pad_id = _load()
        chars = [c for c in ref_phones.replace(" ", "") if c in vocab]
        if not chars:
            return ""
        ids = [vocab[c] for c in chars]

        # crop canonical to the target word via alignment back to the reference
        ref_em = _emissions(ref_span)
        _, spans = _viterbi_align(ref_em, ids, pad_id)
        spf = TARGET_SR / 50.0  # samples per frame
        # MMS word boundaries and CTC phoneme placement disagree by ~1 frame at
        # onsets — tolerate a few frames on the LEFT so onset phonemes aren't
        # cropped away. The right side is strict: trailing neighbour phonemes
        # (the next word's onset) are the main misattribution source.
        TOL_L = 3.0
        wf0 = (ref_start * TARGET_SR - a) / spf - TOL_L
        wf1 = (ref_end * TARGET_SR - a) / spf
        keep = [
            (p - 1) // 2
            for p, f0, f1 in spans
            if p % 2 == 1 and wf0 <= (f0 + f1) / 2.0 <= wf1
        ]
        if len(keep) < 2:  # single-phoneme canonicals are too unstable
            return ""
        c_ids = [ids[k] for k in keep]
        c_chars = [chars[k] for k in keep]

        # gate: cropped canonical must fit the reference audio almost perfectly
        gate_gain, _ = _best_sub_gain(ref_em, c_ids, c_chars, vocab, pad_id)
        if gate_gain > _GATE_MAX:
            return ""  # canonical decode untrustworthy — stay silent

        learner_em = _emissions(learner_span)
        gain, sub = _best_sub_gain(learner_em, c_ids, c_chars, vocab, pad_id)
        if sub is None or gain <= _MARGIN:
            return ""
        diag = PhoneDiag(subs=[sub], ref_phones="".join(c_chars))
        return verbalize(diag, word)
    except Exception:  # noqa: BLE001 - phoneme track must never break analysis
        return ""
