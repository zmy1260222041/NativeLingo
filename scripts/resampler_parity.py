"""Gate E evidence: does the *choice of resampler* move a NativeLingo score?

Background. On macOS every path into the pipeline goes through libswresample
(PyAV's ``av.AudioResampler``) — see ``backend/core/video.py``. The Android plan
(docs/android-migration.md 发现②) therefore proposed building FFmpeg from source
with the NDK so the same resampler runs on device, and Gate E was written as
"sample error ≤1 LSB vs ``ffmpeg -ar 16000``".

That gate is only reachable if we ship FFmpeg. The alternative — MediaExtractor
+ MediaCodec for decode, plus a polyphase resampler in ``:core-scoring`` — can
never be 1-LSB-identical, because a different filter kernel produces different
samples by construction. So the ±1 LSB criterion silently *presupposes* the
FFmpeg route rather than justifying it.

This script measures what actually matters instead: given the same decoded
audio, how far apart are the pipeline's outputs under different resamplers?

  A  swresample 48k→16k          (macOS truth, what the golden was captured with)
  B  polyphase windowed-sinc     (scipy.signal.resample_poly ≈ what Kotlin would do)
  C  soxr_hq                     (librosa.resample — already used by audio_io.py
                                  for uploads, so macOS is *itself* not internally
                                  consistent about this)
  D  B, but from int16 PCM       (MediaCodec's default output encoding)

Reported per pair: waveform SNR, then the two numbers the gates are written in —
per-frame cosine of the CMVN'd 6–9-layer wav2vec2 embedding (Layer-2 criterion
≥0.995) and the DTW path cost + calibrated accuracy of A-vs-X treated as a
reference/learner pair (Gate A criterion: cost ±0.02, accuracy ±2.0).

Usage:  .venv/bin/python scripts/resampler_parity.py [video] [start] [dur]
"""
from __future__ import annotations

import sys

import av
import librosa
import numpy as np
from scipy.signal import resample_poly

sys.path.insert(0, "backend")

from core.align import dtw_align  # noqa: E402
from core.score_b import score_accuracy  # noqa: E402
from core.speaker_norm import normalize_pair  # noqa: E402
from core.ssl_encoder import SSLEncoder  # noqa: E402

TARGET_SR = 16_000


def decode(path: str, rate: int | None, start: float, dur: float) -> tuple[np.ndarray, int]:
    """Decode a [start, start+dur] slice to mono float32, resampled to `rate`
    by libswresample, or at the stream's native rate when `rate` is None."""
    with av.open(path) as c:
        stream = next(s for s in c.streams if s.type == "audio")
        native = stream.rate
        c.seek(int(start / stream.time_base), stream=stream)
        rs = av.AudioResampler(format="flt", layout="mono", rate=rate or native)
        chunks, t0 = [], None
        for frame in c.decode(stream):
            if frame.time is None:
                continue
            if t0 is None:
                t0 = frame.time
            if frame.time > start + dur:
                break
            if frame.time < start:
                continue
            for rf in rs.resample(frame):
                chunks.append(np.asarray(rf.to_ndarray()).reshape(-1))
        for rf in rs.resample(None):
            chunks.append(np.asarray(rf.to_ndarray()).reshape(-1))
    return np.concatenate(chunks).astype("float32"), native


def snr_db(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    n = min(a.size, b.size)
    a, b = a[:n], b[:n]
    err = a - b
    denom = float(np.sum(err**2))
    snr = 10 * np.log10(float(np.sum(a**2)) / denom) if denom > 0 else float("inf")
    return snr, float(np.max(np.abs(err)))


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "videos/7.1.mp4"
    start = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
    dur = float(sys.argv[3]) if len(sys.argv) > 3 else 25.0

    a, native = decode(path, TARGET_SR, start, dur)          # swresample direct
    nat, _ = decode(path, None, start, dur)                  # MediaCodec-like PCM
    print(f"{path}  [{start}, {start + dur}]s   native={native}Hz  "
          f"A={a.size} samples  native={nat.size} samples")

    up, down = TARGET_SR // np.gcd(TARGET_SR, native), native // np.gcd(TARGET_SR, native)
    b = resample_poly(nat, up, down).astype("float32")
    c = librosa.resample(nat, orig_sr=native, target_sr=TARGET_SR, res_type="soxr_hq")
    i16 = np.round(np.clip(nat, -1.0, 1.0) * 32767.0).astype("int16")
    d = resample_poly(i16.astype("float32") / 32768.0, up, down).astype("float32")

    variants = {"B poly(float)": b, "C soxr_hq": c, "D poly(int16 PCM)": d}

    enc = SSLEncoder()
    n = min(a.size, *(v.size for v in variants.values()))
    emb_a = enc.encode(a[:n])

    print(f"\n{'pair':<22} {'SNR dB':>8} {'maxΔ':>10} {'cos.mean':>9} {'cos.min':>9} "
          f"{'DTWcost':>8} {'acc':>7}")
    print("-" * 78)
    acc_a = score_accuracy(dtw_align(*normalize_pair(emb_a, emb_a)))
    print(f"{'A vs A (floor)':<22} {'inf':>8} {0.0:>10.2e} {1.0:>9.4f} {1.0:>9.4f} "
          f"{0.0:>8.4f} {acc_a:>7.1f}")
    for name, v in variants.items():
        snr, mx = snr_db(a[:n], v[:n])
        emb_v = enc.encode(v[:n])
        m = min(emb_a.shape[0], emb_v.shape[0])
        na, nv = normalize_pair(emb_a[:m], emb_v[:m])
        cos = np.sum(na * nv, axis=1) / (
            np.linalg.norm(na, axis=1) * np.linalg.norm(nv, axis=1) + 1e-8
        )
        res = dtw_align(*normalize_pair(emb_a, emb_v))
        print(f"{name:<22} {snr:>8.1f} {mx:>10.2e} {cos.mean():>9.4f} {cos.min():>9.4f} "
              f"{res.normalized_cost:>8.4f} {score_accuracy(res):>7.1f}")
        # Where does the worst frame sit? A lone low-cosine frame in silence is
        # CMVN amplifying nothing; one in the middle of speech would be real.
        k = int(np.argmin(cos))
        hop = a[:n].size / max(m, 1)
        s0, s1 = int(k * hop), int((k + 1) * hop)
        rms = float(np.sqrt(np.mean(a[s0:s1] ** 2))) if s1 > s0 else 0.0
        loud = float(np.sqrt(np.mean(a[:n] ** 2)))
        print(f"{'  worst frame':<22} #{k}/{m} @ {k * 0.02:.2f}s  rms={rms:.5f} "
              f"({rms / (loud + 1e-9):.2f}× clip rms)  "
              f"cos<0.99 on {int((cos < 0.99).sum())}/{m} frames")

    print("\nGate references: Layer-2 cosine ≥0.995 | Gate A cost ±0.02, accuracy ±2.0 "
          "| speaker-invariance cost ≤0.18")

    # The table above compares near-identical signals, so its DTW cost sits at
    # the floor where the calibration curve is flat — a favourable regime. The
    # question that decides the score is different: on Android the *learner*
    # never gets resampled (AudioRecord captures at 16 kHz), only the *reference*
    # does. So hold one learner fixed and swap the reference's resampler, in the
    # cost regime a real imperfect read produces.
    print("\nreference-swap, fixed learner (cost regime of a real read)")
    print(f"{'learner':<20} {'ref=A':>16} {'ref=B poly':>16} {'ref=C soxr':>16} "
          f"{'max Δcost':>10} {'max Δacc':>9}")
    print("-" * 92)
    for label, learner in (
        ("time-stretch 1.08", librosa.effects.time_stretch(a[:n], rate=1.08)),
        ("time-stretch 0.92", librosa.effects.time_stretch(a[:n], rate=0.92)),
        ("pitch +2 semitones", librosa.effects.pitch_shift(a[:n], sr=TARGET_SR, n_steps=2)),
    ):
        emb_l = enc.encode(learner.astype("float32"))
        row = []
        for ref in (a[:n], b[:n], c[:n]):
            r = dtw_align(*normalize_pair(enc.encode(ref), emb_l))
            row.append((r.normalized_cost, score_accuracy(r)))
        dc = max(abs(x[0] - row[0][0]) for x in row[1:])
        da = max(abs(x[1] - row[0][1]) for x in row[1:])
        cells = "".join(f"{v:>10.4f}/{s:<5.1f}" for v, s in row)
        print(f"{label:<20} {cells} {dc:>10.4f} {da:>9.2f}")


if __name__ == "__main__":
    main()
