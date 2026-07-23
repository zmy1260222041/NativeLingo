"""News-domain audit (PRD §7 appendix, paving FR-M2).

Runs two checks on the real broadcast material (7.1.mp4, CBS News):

* **whisper**: transcription quality of faster-whisper base.en on fast
  broadcast speech. Two signals: (a) per-segment confidence (avg_logprob,
  no_speech_prob, compression_ratio), (b) cross-model agreement with the
  stronger small.en — disagreement spots mark where base.en is unreliable
  (no ground truth available; small.en ≈ reference).
* **mms**: forced-alignment robustness on the cached word grid: duration
  anomalies (collapsed <50 ms / stretched >1.5 s), overlaps, gap outliers,
  plus a re-alignment consistency check on sampled sentences.

Usage:
    .venv/bin/python -m scripts.news_domain_audit --part whisper
    .venv/bin/python -m scripts.news_domain_audit --part mms
"""
from __future__ import annotations

import argparse
import difflib
import json
import re

import numpy as np

VIDEO = "videos/7.1.mp4"
SENTS = "videos/7.1.sentences.json"


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", " ".join(t.split()).lower())


# --------------------------------------------------------------------------- #
# part 1: whisper quality
# --------------------------------------------------------------------------- #
def _transcribe(model_size: str):
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        VIDEO, language="en", vad_filter=True, beam_size=1,
        word_timestamps=True,
    )
    return list(segments), info


def part_whisper() -> None:
    print("transcribing with base.en ...", flush=True)
    base_segs, _ = _transcribe("base.en")

    conf = [(s.avg_logprob, s.no_speech_prob, s.compression_ratio)
            for s in base_segs]
    lp = np.array([c[0] for c in conf])
    ns = np.array([c[1] for c in conf])
    cr = np.array([c[2] for c in conf])
    print(f"\n== base.en segment confidence ({len(base_segs)} segments) ==")
    print(f"  avg_logprob      mean {lp.mean():+.3f}  p10 {np.percentile(lp, 10):+.3f}"
          f"  min {lp.min():+.3f}")
    print(f"  no_speech_prob   mean {ns.mean():.3f}  p90 {np.percentile(ns, 90):.3f}")
    print(f"  compression_ratio mean {cr.mean():.2f}  p90 {np.percentile(cr, 90):.2f}")
    low = [(s.start, s.end, s.avg_logprob, s.text)
           for s in base_segs if s.avg_logprob < -0.7]
    print(f"  low-confidence segments (avg_logprob < -0.7): {len(low)}")
    for st, en, lp_, t in low[:8]:
        print(f"    [{st:7.2f}-{en:7.2f}] {lp_:+.2f} {t.strip()[:70]}")

    print("\ntranscribing with small.en (cross-check) ...", flush=True)
    small_segs, _ = _transcribe("small.en")

    def words_of(segs):
        out = []
        for s in segs:
            if s.words:
                out.extend((w.start, w.end, w.word) for w in s.words)
            else:
                out.append((s.start, s.end, s.text))
        return out

    bw, sw = words_of(base_segs), words_of(small_segs)

    # text-level agreement: align the two word sequences globally
    bt = [_norm(w[2]).replace(" ", "") for w in bw]
    st = [_norm(w[2]).replace(" ", "") for w in sw]
    bt = [t for t in bt if t]
    st = [t for t in st if t]
    sm = difflib.SequenceMatcher(None, bt, st, autojunk=False)
    match = sum(b.size for b in sm.get_matching_blocks())
    agree = 2 * match / max(len(bt) + len(st), 1)
    subs = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete", "insert"):
            subs.append((tag, " ".join(bt[i1:i2]), " ".join(st[j1:j2])))

    print(f"\n== cross-model text agreement (base vs small) ==")
    print(f"  words base {len(bt)} / small {len(st)}  "
          f"identical-aligned {match}  agreement {agree * 100:.1f}%")
    print(f"  differing spans: {len(subs)}; sample:")
    for tag, b, s in subs[:15]:
        print(f"    {tag:<8} base: {b:<40} small: {s}")


# --------------------------------------------------------------------------- #
# part 2: MMS alignment audit (on the cached word grid)
# --------------------------------------------------------------------------- #
def part_mms() -> None:
    data = json.load(open(SENTS))
    sents = data["sentences"]
    words = [w for s in sents for w in s["words"]]
    durs = np.array([w["end"] - w["start"] for w in words])
    gaps = np.array([
        words[i + 1]["start"] - words[i]["end"] for i in range(len(words) - 1)
    ])
    print(f"== MMS word grid audit ({len(sents)} sentences, {len(words)} words) ==")
    print(f"  word duration: median {np.median(durs):.3f}s  "
          f"p1 {np.percentile(durs, 1):.3f}  p99 {np.percentile(durs, 99):.3f}")
    print(f"  collapsed (<50ms): {(durs < 0.05).sum()}  "
          f"stretched (>1.5s): {(durs > 1.5).sum()}  "
          f"zero/negative: {(durs <= 0).sum()}")
    print(f"  inter-word gap: median {np.median(gaps):.3f}s  "
          f"p99 {np.percentile(gaps, 99):.3f}  "
          f"overlaps (<-50ms): {(gaps < -0.05).sum()}")
    bad = [(w["word"], round(d, 3)) for w, d in zip(words, durs)
           if d < 0.05 or d > 1.5]
    if bad:
        print(f"  anomalous words: {bad[:15]}")

    # consistency: re-align 6 sampled sentences and compare boundaries
    from backend.core import forced_align
    from backend.core.video import extract_audio

    rng = np.random.RandomState(0)
    idxs = rng.choice(len(sents), size=min(6, len(sents)), replace=False)
    diffs = []
    for i in idxs:
        s = sents[i]
        clip = extract_audio(VIDEO, s["start"], s["end"])
        spans = forced_align.align_words([w["word"] for w in s["words"]], clip)
        if spans is None:
            print(f"  sentence {i}: re-align FAILED")
            continue
        for w, sp in zip(s["words"], spans):
            if sp is None:
                diffs.append(None)
                continue
            # stored boundaries are video-relative; re-aligned are clip-relative
            diffs.append(abs((s["start"] + sp[0]) - w["start"]))
            diffs.append(abs((s["start"] + sp[1]) - w["end"]))
    none_n = sum(1 for d in diffs if d is None)
    d = np.array([x for x in diffs if x is not None])
    print(f"  re-alignment consistency ({len(idxs)} sentences): "
          f"None spans {none_n}, boundary |diff| median {np.median(d):.3f}s  "
          f"p90 {np.percentile(d, 90):.3f}s")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["whisper", "mms"], required=True)
    args = ap.parse_args()
    {"whisper": part_whisper, "mms": part_mms}[args.part]()


if __name__ == "__main__":
    main()
