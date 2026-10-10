#!/usr/bin/env python3
"""Cloud TTS acceptance check — run once after creating the service account.

Answers the four questions that decide whether Cloud TTS can back the graded
speech-rate design:

  1. Does the service account authenticate, and does every cast voice exist?
  2. Does ``speakingRate`` actually change duration, and by the requested amount?
  3. Are the requested step sizes separable from run-to-run noise? Measured on a
     single sample this looks random, so every rate is sampled repeatedly and
     compared against its own spread.
  4. Does slowing down preserve pitch, or does it collapse like a resampled
     tape? The design forbids slowing audio by lowering the playback pitch.

Measured behaviour on ``en-US-Chirp3-HD-Fenrir`` (2026-09-17, 27-word sentence,
8 runs per rate):

  * pitch is preserved — F0 stayed within 2.4% across 0.75-1.00, and even the
    worst single reading never showed the proportional drop a resampled
    slowdown would produce (0.75 would land near 99 Hz; it measured ~135 Hz);
  * ratio accuracy is good: 0.90 -> 1.12x observed against 1.11x requested,
    0.75 -> 1.39x against 1.33x;
  * the noise floor is ~6-8% of duration, so **0.05 steps are not separable**,
    0.10 steps are marginal (1.00 vs 0.90 overlapped: gap 1.03s against a
    2x-sd of 1.22s), and **0.15 steps separate cleanly** (0.90 vs 0.75:
    gap 2.30s, no overlap between the runs).

So a tier ladder needs roughly 0.15 spacing (e.g. 1.00 / 0.85 / 0.70), not the
0.05 the design currently specifies. Short utterances are worse still: on a
10-word line the spread exceeded the effect at every step, so tiering is only
perceptible on longer lines.

Usage::

    export GOOGLE_TTS_CREDENTIALS=/path/to/service-account.json
    .venv/bin/python game/speech_service/verify_cloud_tts.py

Writes WAV samples to ``--out`` (default /tmp/cloud-tts-check) so the numbers
can be confirmed by ear. Exits non-zero when a gate fails.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402  (path set above)


## A short line's duration is dominated by variable prosody rather than by the
## rate scale, which makes the measurement meaningless. This is long enough that
## the rate effect dominates.
SENTENCE = (
    "Vesh does not say much, even to people he knows. I usually start with one "
    "clear question, because that gets me further than small talk ever does."
)
RATES = (1.0, 0.90, 0.85, 0.80, 0.75)
## Praat needs a plausible human range; Charon and Kore both sit inside this.
PITCH_FLOOR_HZ = 60.0
PITCH_CEILING_HZ = 400.0
## A resampled slowdown drops F0 by exactly the speed ratio; a synthesised one
## barely moves. 3% separates the two cases with room to spare.
PITCH_TOLERANCE = 0.03


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if width != 2:
        raise SystemExit(f"unexpected sample width {width} in {path}")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float64)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples / 32768.0, rate


def median_f0(samples: np.ndarray, rate: int) -> float | None:
    """Median voiced F0 via Praat's autocorrelation pitch tracker."""
    import parselmouth

    if samples.size < rate // 4:
        return None
    sound = parselmouth.Sound(samples, sampling_frequency=rate)
    pitch = sound.to_pitch(
        time_step=0.01, pitch_floor=PITCH_FLOOR_HZ, pitch_ceiling=PITCH_CEILING_HZ
    )
    voiced = pitch.selected_array["frequency"]
    voiced = voiced[voiced > 0]
    if voiced.size < 5:
        return None
    return float(statistics.median(voiced))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="/tmp/cloud-tts-check", help="sample output directory")
    parser.add_argument("--voice", default="", help="cast voice id (default: the Vesh voice)")
    parser.add_argument("--repeat", type=int, default=4, help="runs per rate (default 4)")
    parser.add_argument("--sentence", default=SENTENCE, help="override the probe sentence")
    parser.add_argument(
        "--skip-cast-check", action="store_true", help="skip the all-voice validation pass"
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    repeats = max(1, args.repeat)

    if server.TTS_PROVIDER != "cloud":
        print(f"! STRANGER_TTS_PROVIDER is {server.TTS_PROVIDER!r}; the check targets 'cloud'.")
        print("  Re-run with STRANGER_TTS_PROVIDER=cloud")
        return 2

    credentials = server._cloud_tts_credentials_path()
    if not credentials:
        print("! No service account found.")
        print("  Set GOOGLE_TTS_CREDENTIALS=/path/to/service-account.json")
        print("  or place CloudTTS.json beside speech_service/server.py")
        return 2

    print("=" * 74)
    print("Cloud TTS acceptance check")
    print("=" * 74)
    print(f"credentials : {credentials}")
    print(f"locale      : {server.CLOUD_TTS_LOCALE}")
    print(f"output      : {out_dir}")
    print()

    # ── 1. Authentication ────────────────────────────────────────────────────
    print("[1/4] service account authentication")
    try:
        token = server._cloud_tts_access_token()
        project = server._cloud_tts_project() or "unset"
        print(f"      OK    access token minted ({len(token)} chars), project={project}")
    except RuntimeError as exc:
        print(f"      FAIL  {exc}")
        print("      Check: Text-to-Speech API enabled, billing active,")
        print("      and the key is a service-account JSON (not an API key).")
        return 1
    print()

    # ── 2. Every cast voice must exist ───────────────────────────────────────
    voice = args.voice or server.NPC_TTS_VOICES.get("vesh", "")
    if not args.skip_cast_check:
        print("[2/4] cast voice validation")
        failures = []
        for npc_id in sorted(server.NPC_TTS_VOICES):
            cast_voice = server.NPC_TTS_VOICES[npc_id]
            name = server._cloud_tts_voice_name(cast_voice)
            try:
                server._synthesize_speech("Hello.", cast_voice, 1.0)
                print(f"      OK    {npc_id:10s} {name}")
            except RuntimeError as exc:
                failures.append(npc_id)
                print(f"      FAIL  {npc_id:10s} {name}: {str(exc)[:90]}")
        if failures:
            print()
            print("      Fix the names in server.CLOUD_TTS_VOICES and re-run.")
            return 1
        print()

    # ── 3. Pace sweep, repeated so noise and effect can be told apart ────────
    print(f"[3/4] pace sweep   voice={voice}  ({server._cloud_tts_voice_name(voice)})")
    print(f"      {repeats} runs per rate; sentence is {len(args.sentence.split())} words")
    print()

    durations: dict[float, list[float]] = {}
    pitches: dict[float, list[float]] = {}
    for rate in RATES:
        runs: list[float] = []
        f0s: list[float] = []
        for index in range(repeats):
            try:
                body = server._synthesize_speech(args.sentence, voice, rate)
            except RuntimeError as exc:
                print(f"      {rate:>6.2f}  FAILED: {str(exc)[:60]}")
                return 1
            path = out_dir / f"rate-{rate:.2f}-run{index + 1}.wav"
            path.write_bytes(body)
            samples, rate_hz = read_wav(path)
            runs.append(samples.size / rate_hz)
            f0 = median_f0(samples, rate_hz)
            if f0 is not None:
                f0s.append(f0)
        durations[rate] = runs
        pitches[rate] = f0s
        shown = " ".join(f"{value:.2f}" for value in runs)
        print(
            f"      {rate:>6.2f}  {shown:>34}   mean={statistics.mean(runs):.2f}s"
            f"  sd={statistics.stdev(runs) if len(runs) > 1 else 0.0:.2f}"
        )

    baseline = statistics.mean(durations[RATES[0]])
    print()
    print("      achieved ratio vs requested:")
    print(f"      {'rate':>6}  {'mean':>8}  {'observed':>9}  {'requested':>10}  {'error':>7}")
    for rate in RATES:
        mean = statistics.mean(durations[rate])
        observed = mean / baseline
        requested = 1.0 / rate
        print(
            f"      {rate:>6.2f}  {mean:>7.2f}s  {observed:>8.2f}x  {requested:>9.2f}x"
            f"  {observed - requested:>+6.2f}"
        )

    print()
    print("      separation between adjacent steps (needs |gap| > 2x pooled sd):")
    print(f"      {'pair':>14}  {'|gap|':>8}  {'2x sd':>8}  {'separated':>10}")
    separable: list[tuple[float, float, bool]] = []
    for index in range(len(RATES) - 1):
        fast, slow = RATES[index], RATES[index + 1]
        gap = abs(statistics.mean(durations[fast]) - statistics.mean(durations[slow]))
        spreads = [
            statistics.stdev(durations[fast]) if len(durations[fast]) > 1 else 0.0,
            statistics.stdev(durations[slow]) if len(durations[slow]) > 1 else 0.0,
        ]
        pooled = sum(spreads) / 2
        ok = gap > 2 * pooled
        separable.append((fast, slow, ok))
        print(f"      {fast:>5.2f} vs {slow:<5.2f}  {gap:>7.2f}s  {2*pooled:>7.2f}s  {('YES' if ok else 'no'):>10}")

    # A step size only counts if EVERY adjacent pair at that spacing separates.
    # One lucky pair does not make a ladder.
    step_sizes = sorted({round(RATES[i] - RATES[i + 1], 4) for i in range(len(RATES) - 1)})
    consistent: list[float] = []
    for size in step_sizes:
        pairs = [
            ok
            for index, (_, _, ok) in enumerate(separable)
            if round(RATES[index] - RATES[index + 1], 4) == size
        ]
        if pairs and all(pairs):
            consistent.append(size)
    print()
    if not separable:
        print("      WARN  no steps measured")
    elif not consistent:
        print("      WARN  no step size separated consistently at this sample count;")
        print("            coarsen the tiers, raise --repeat, or lengthen --sentence.")
    else:
        finest = min(consistent)
        print(f"      OK    finest step separable at every pair: {finest:.2f}")
        if min(step_sizes) < finest:
            print(f"      WARN  the design's {min(step_sizes):.2f} steps are below that: some will")
            print("            read as the same speed. Coarsen the tiers to the step above,")
            print("            or accept that only longer lines carry a perceptible difference.")
    print()

    # ── 4. Pitch preservation — the design's hard requirement ───────────────
    print("[4/4] pitch preservation (design forbids lowering pitch to fake slow speech)")
    baseline_f0 = statistics.median(pitches[RATES[0]]) if pitches[RATES[0]] else None
    if baseline_f0 is None:
        print("      SKIP  Praat found no voiced frames in the baseline samples")
    else:
        print(f"      baseline median F0 at {RATES[0]:.2f}x: {baseline_f0:.1f} Hz  (from {repeats} runs)")
        print()
        print(f"      {'rate':>6}  {'median F0':>10}  {'vs base':>9}  {'verdict':>10}")
        worst = 0.0
        resampled = False
        for rate in RATES:
            if not pitches[rate]:
                print(f"      {rate:>6.2f}  {'no voiced frames':>10}")
                continue
            f0 = statistics.median(pitches[rate])
            drift = f0 / baseline_f0 - 1.0
            if rate >= 0.999:
                # The baseline cannot be a resampled version of itself; testing
                # it here would compare zero against zero and always "pass".
                print(f"      {rate:>6.2f}  {f0:>9.1f} Hz  {drift:>+8.1%}  {'baseline':>10}")
                continue
            worst = max(worst, abs(drift))
            here = abs(drift + (1.0 - rate)) < PITCH_TOLERANCE
            resampled = resampled or here
            verdict = "resampled" if here else ("ok" if abs(drift) <= PITCH_TOLERANCE else "DRIFT")
            print(f"      {rate:>6.2f}  {f0:>9.1f} Hz  {drift:>+8.1%}  {verdict:>10}")
        print()
        if resampled:
            print("      FAIL  pitch tracks the rate: this is resampling, not slower speech.")
            print("            Do not ship graded speed on this voice.")
            return 1
        if worst <= PITCH_TOLERANCE:
            print(f"      PASS  pitch held within {PITCH_TOLERANCE:.0%} across the whole range")
        else:
            print(f"      WARN  worst pitch drift {worst:+.1%} exceeds {PITCH_TOLERANCE:.0%}; check the samples")
    print()
    print("=" * 74)
    print(f"Listen to the samples:  open {out_dir}")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
