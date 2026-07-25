"""R-10 / Gate F —— sherpa-onnx Whisper 转写文本 vs faster-whisper 金标准.

评审:``docs/reviews/2026-07-26-android-gate-f-asr-text.md``

为什么需要这道门:Whisper 在这条流水线上**只贡献文本**(词边界一律走 MMS,
见 android-migration §4 发现⑤),而文本里的**标点决定练习单元的切分**
(FR-2/FR-M3 按 ``[.!?]`` 切句)。少一个句号就把两个练习单元合成一个,**即使
每个词都对** —— 标准 ASR 评测剥掉标点,给不出这个数,所以得自己量。

Android 的 sherpa-onnx AAR 与 PyPI 的 ``sherpa-onnx`` 是同一份 C++ 实现,所以
这道门在 macOS 上就能量,不必等设备(arm64 手机的 int8 kernel 仍需 Tier 3 复测)。

**两个 venv**,因为两侧的依赖装在一起会打架:

    # 识别侧
    python3 -m venv /tmp/sherpa-venv
    /tmp/sherpa-venv/bin/pip install sherpa-onnx==1.13.4 numpy
    # 模型(int8 + fp32 都在同一个 tarball 里)
    mkdir -p /tmp/sherpa-models && cd /tmp/sherpa-models
    curl -sL -O https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-base.en.tar.bz2
    tar xf sherpa-onnx-whisper-base.en.tar.bz2
    curl -sL -O https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx

用法:

    ffmpeg -v error -y -i videos/7.1.mp4 -vn -ac 1 -ar 16000 /tmp/7.1.16k.wav

    # 识别(sherpa venv)—— strategy: longform | vad | window
    /tmp/sherpa-venv/bin/python scripts/asr_text_parity.py transcribe \\
        /tmp/7.1.16k.wav /tmp/out.json --strategy longform --precision int8

    # 比较(项目 venv,需要 backend.core.transcribe 来复用真实的切句函数)
    .venv/bin/python scripts/asr_text_parity.py compare \\
        videos/7.1.sentences.json /tmp/out.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import wave

SR = 16000
MODELS_DIR = os.environ.get("SHERPA_MODELS", "/tmp/sherpa-models")
WHISPER_DIR = os.path.join(MODELS_DIR, "sherpa-onnx-whisper-base.en")

# sherpa-onnx 的离线 Whisper 对 >=30s 的输入直接截断并打印警告,所以窗口留 1s 余量。
WIN_S = 29.0


# --------------------------------------------------------------------------
# 识别侧(需要 sherpa_onnx)
# --------------------------------------------------------------------------

def _read_wav(path):
    import numpy as np
    with wave.open(path) as w:
        if w.getframerate() != SR or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit(f"expect 16k mono s16 wav, got {w.getparams()}")
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0


def _recognizer(precision, segment_timestamps):
    import sherpa_onnx
    suffix = ".int8" if precision == "int8" else ""
    return sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=f"{WHISPER_DIR}/base.en-encoder{suffix}.onnx",
        decoder=f"{WHISPER_DIR}/base.en-decoder{suffix}.onnx",
        tokens=f"{WHISPER_DIR}/base.en-tokens.txt",
        language="en",
        num_threads=4,
        enable_segment_timestamps=segment_timestamps,
    )


def _decode(rec, samples):
    st = rec.create_stream()
    st.accept_waveform(SR, samples)
    rec.decode_stream(st)
    return st.result


def strategy_longform(samples, precision, verbose):
    """Whisper 自己的长音频循环 —— **参考路径该用的那个**(R-10 结论)。

    解一个 29s 窗 → **丢掉最后一个 segment**(它是被窗口切断的那个)→ 把游标推进到
    倒数第二个 segment 的结尾 → 下一窗从那里重开。切口因此落在 Whisper 自己认为的
    短语边界上,不发明任何边界 —— 这正是 faster-whisper 内部在做的事。

    够不到的一项:faster-whisper 默认 ``condition_on_previous_text=True``,而
    ``from_whisper`` 没有 prompt/prefix 参数,**没有办法开**。残余 WER 里它占多少
    在不改 sherpa-onnx 的前提下拆不开。
    """
    rec = _recognizer(precision, segment_timestamps=True)
    win = int(WIN_S * SR)
    out, p = [], 0
    while p < len(samples):
        chunk = samples[p:p + win]
        if len(chunk) < SR // 10:          # <0.1s 尾巴,没东西可识别
            break
        r = _decode(rec, chunk)
        base = p / SR
        segs = list(zip(r.segment_timestamps, r.segment_durations, r.segment_texts))
        advance = len(chunk)
        if len(segs) > 1 and len(chunk) == win:
            segs = segs[:-1]
            # 从下一窗的开头重新解码被切断的那一段,那里它是完整的
            advance = max(int(round((segs[-1][0] + segs[-1][1]) * SR)), SR)
        for t, d, txt in segs:
            out.append({"start": round(base + t, 3), "end": round(base + t + d, 3),
                        "text": txt})
        if verbose:
            print(f"[{base:7.2f}] +{advance / SR:5.2f}s {len(segs):2d} segs  "
                  f"{segs[0][2][:60] if segs else ''}", flush=True)
        p += advance
    return out


def strategy_vad(samples, precision, verbose):
    """Silero VAD 分段 —— android-migration §4 的**原**选型,R-10 实测最差。

    VAD 在句子中间下刀,而 Whisper 会给它拿到的任何一段结尾加标点,于是每个切口都
    变成一个假句末:标点分歧 3.17%、练习单元 172 vs 金标准 159。保留在这里是为了让
    这个结论可复现,不是备选方案。VAD 在 Android 上的正当用途是学习者录音(单句、
    几秒、一段)和"有没有人在说话"。
    """
    import sherpa_onnx
    rec = _recognizer(precision, segment_timestamps=False)
    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = os.path.join(MODELS_DIR, "silero_vad.onnx")
    cfg.silero_vad.threshold = 0.5
    cfg.silero_vad.min_silence_duration = 0.25
    cfg.silero_vad.min_speech_duration = 0.25
    cfg.silero_vad.max_speech_duration = 25.0      # 留在 30s 感受野内
    cfg.sample_rate = SR
    vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=100)

    spans, window = [], cfg.silero_vad.window_size
    for i in range(0, len(samples), window):
        vad.accept_waveform(samples[i:i + window])
        while not vad.empty():
            spans.append((vad.front.start, vad.front.samples))
            vad.pop()
    vad.flush()
    while not vad.empty():
        spans.append((vad.front.start, vad.front.samples))
        vad.pop()

    out = []
    for offset, seg in spans:
        r = _decode(rec, seg)
        out.append({"start": round(offset / SR, 3),
                    "end": round((offset + len(seg)) / SR, 3), "text": r.text})
        if verbose:
            print(f"[{out[-1]['start']:7.2f}] {out[-1]['text'][:80]}", flush=True)
    return out


def strategy_window(samples, precision, verbose):
    """固定 29s 窗 —— 切在**词中间**,丢词(1879 vs 1944),WER 靠删除撑着。对照用。"""
    rec = _recognizer(precision, segment_timestamps=False)
    win = int(WIN_S * SR)
    out = []
    for i in range(0, len(samples), win):
        chunk = samples[i:i + win]
        if len(chunk) < SR // 10:
            break
        r = _decode(rec, chunk)
        out.append({"start": round(i / SR, 3),
                    "end": round((i + len(chunk)) / SR, 3), "text": r.text})
        if verbose:
            print(f"[{out[-1]['start']:7.2f}] {out[-1]['text'][:80]}", flush=True)
    return out


STRATEGIES = {"longform": strategy_longform, "vad": strategy_vad,
              "window": strategy_window}


def cmd_transcribe(args):
    samples = _read_wav(args.wav)
    segs = STRATEGIES[args.strategy](samples, args.precision, not args.quiet)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"strategy": args.strategy, "precision": args.precision,
                   "segments": segs}, f, ensure_ascii=False, indent=1)
    tokens = sum(len(s["text"].split()) for s in segs)
    print(f"\n{args.strategy}/{args.precision}: {len(segs)} segments, "
          f"{tokens} whitespace tokens -> {args.out}")


# --------------------------------------------------------------------------
# 比较侧(需要 backend.core.transcribe)
# --------------------------------------------------------------------------

_END = re.compile(r"[.!?]['\")\]]?$")


def _norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def _wer(ref, hyp):
    """Levenshtein over token lists —— 常规的 (S+D+I)/N。"""
    m = len(hyp)
    prev = list(range(m + 1))
    for i in range(1, len(ref) + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1,
                         prev[j - 1] + (ref[i - 1] != hyp[j - 1]))
        prev = cur
    return prev[m] / len(ref)


def cmd_compare(args):
    from difflib import SequenceMatcher
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from backend.core import transcribe as T

    gold_doc = json.load(open(args.gold, encoding="utf-8"))
    gold = [w["word"].strip() for s in gold_doc["sentences"] for w in s["words"]]
    hyp_doc = json.load(open(args.hyp, encoding="utf-8"))
    hyp = [t for s in hyp_doc["segments"] for t in s["text"].split()]

    g_n, h_n = [_norm(w) for w in gold], [_norm(w) for w in hyp]
    print(f"gold {len(gold)} tokens / hyp {len(hyp)} tokens "
          f"({hyp_doc.get('strategy')}/{hyp_doc.get('precision')})")
    print(f"WER (normalised, punctuation- and case-insensitive): {_wer(g_n, h_n):.4f}")

    sm = SequenceMatcher(None, g_n, h_n, autojunk=False)
    ops = sm.get_opcodes()
    diffs = [op for op in ops if op[0] != "equal"]
    print(f"\n{len(diffs)} differing regions:")
    for _tag, i1, i2, j1, j2 in diffs[:args.max_regions]:
        ctx = " ".join(gold[max(0, i1 - 3):i1])
        print(f"  ...{ctx} | gold[{i1}:{i2}]={' '.join(gold[i1:i2])!r}"
              f"  ->  hyp={' '.join(hyp[j1:j2])!r}")

    # 标点只在两侧词相同处比,否则一个识别错误会被重复计成一个标点错误。
    matched, mismatch = 0, []
    for tag, i1, i2, j1, j2 in ops:
        if tag != "equal":
            continue
        for k in range(i2 - i1):
            g, h = gold[i1 + k], hyp[j1 + k]
            matched += 1
            if bool(_END.search(g)) != bool(_END.search(h)):
                mismatch.append((i1 + k, g, h))
    print(f"\nterminal punctuation over the {matched} matched tokens: "
          f"{len(mismatch)} disagreements ({len(mismatch) / max(matched, 1):.4%})")
    for idx, g, h in mismatch[:args.max_regions]:
        print(f"  [{idx}] gold {g!r} vs hyp {h!r}")

    # 下游影响:同一套切句函数、统一的假时间戳,所以只有**文本**在驱动切分。
    def units(tokens):
        words = [{"word": w, "start": i * 0.3, "end": i * 0.3 + 0.25}
                 for i, w in enumerate(tokens)]
        return T._merge_words_into_sentences(words)

    print(f"\npractice units (uniform synthetic timings, so only the *text* drives "
          f"the split): gold {len(units(gold))} vs hyp {len(units(hyp))}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("transcribe", help="run sherpa-onnx Whisper (sherpa venv)")
    t.add_argument("wav")
    t.add_argument("out")
    t.add_argument("--strategy", choices=sorted(STRATEGIES), default="longform")
    t.add_argument("--precision", choices=("int8", "fp32"), default="int8")
    t.add_argument("--quiet", action="store_true")
    t.set_defaults(func=cmd_transcribe)

    c = sub.add_parser("compare", help="compare against the macOS gold (project venv)")
    c.add_argument("gold", help="videos/<name>.sentences.json")
    c.add_argument("hyp", help="output of `transcribe`")
    c.add_argument("--max-regions", type=int, default=40)
    c.set_defaults(func=cmd_compare)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
