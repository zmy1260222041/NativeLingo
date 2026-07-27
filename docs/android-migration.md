# Android 端完整迁移方案

> 版本:v0.1(2026-07-25)
> 关联 PRD:`docs/PRD.md` v0.3(NFR-2 双平台、NFR-4 移动端约束、FR-12 in-scope、§7 R-5..R-12)
> 状态:**方案已批准,Phase-0 spike 待执行**。本文件是迁移的正式落地点,后续每个 Phase 门结果回写于此 + `docs/reviews/`。

## 1. 背景与目标

NativeLingo 当前是 macOS Tauri v2 + Python FastAPI sidecar(v0.5 已发布)。本方案把应用**完整迁移到 Android**:

- **端侧推理** —— 守 PRD NFR-1(录音不出设备、全离线、隐私)。模型 int8 量化后端侧运行,无任何云调用。
- **原生 Kotlin** —— Jetpack Compose + Media3 + sherpa-onnx + ONNX Runtime Mobile。
- **一步到位全功能** —— 含音素 MDD(FR-11)+ 学习记录(FR-12),目标与 macOS 版功能对等。

**这不是移植,是重写。** Python 后端 + PyInstaller + Tauri-sidecar 架构在 Android 结构性不兼容:PyInstaller 不支持 Android;bionic libc ≠ glibc;torch/torchaudio/transformers/faster-whisper/av/librosa/numba 全部无法在 Android 运行。4 个 ML 模型(~4GB 原始)必须用 Android 原生运行时重新实现。

**能复用的(少但关键):**
- 评分契约与数据流 —— 从 HTTP loopback 变为进程内 Kotlin 调用,语义不变。
- 纯 numpy 评分算法(DTW / CMVN / 校准插值 / detail 投影)→ Kotlin `FloatArray` 1:1 移植。
- `calibration.json` / phoneme `vocab.json` / `_CANDIDATES` 音素表 → 原样作为 Android asset。
- `backend/tests/` 的 fixture → Android 金标准测试基线。
- **macOS 版继续维护,作为 Android 数值对齐的"金标准源"。**

新工程 `NativeLingoAndroid/` 与现有 macOS 代码并存于 `android` 分支(不替换 main)。

## 2. 架构现实:什么死、什么活

| 组件 | macOS 现状 | Android 去向 |
|---|---|---|
| Python 后端(FastAPI/uvicorn) | sidecar 二进制 | **废除** → 进程内 Kotlin 协程,无 HTTP server |
| 前端(HTML/JS/CSS,~750 行) | vanilla JS | **废除** → Jetpack Compose 重写 |
| 4 个 ML 模型(torch/transformers/CTranslate2) | PyTorch | **重实现** → ONNX Mobile + sherpa-onnx,int8 量化 |
| DTW/CMVN/score/detail(numpy) | numpy | **1:1 移植** → Kotlin FloatArray |
| `calibration.json`/`vocab.json`/音素表 | 随包 | **原样复用** → Android asset |
| 录音(MediaRecorder) | WebView | **AudioRecord** 16kHz 单声,`UNPROCESSED` |
| 视频解码(PyAV) | ffmpeg lib | **`MediaExtractor` + `MediaCodec`**(R-9 改判,原为 FFmpeg NDK 源码构建) |
| 打包(.dmg/codesign/notarytool) | macOS | **APK/AAB + Play 签名** |

## 3. 需求追溯矩阵(确保满足产品需求)

每条 PRD 需求 → Android 实现 → Kotlin 模块。**全功能对等 = 下表全覆盖。**

| 需求 | Android 实现 | 模块 |
|---|---|---|
| FR-1 视频浏览 | 视频列表 + 选中 | `:app` VideoRepository + Compose |
| FR-2 转写+句/词切分 | Whisper 转写 + MMS 强制对齐词边界 + 长句二级切分 | core-asr + core-align |
| FR-3 跟读录音 | AudioRecord 16kHz 单声 `UNPROCESSED` + 无声视频同步播放 | `:app` audio |
| FR-4 准确度评分 | wav2vec2 int8 编码 + DTW + CMVN + isotonic 校准;说话人不变性 | core-embed + core-scoring |
| FR-5 流畅度评分 | fluency GAM(path_dev/lograte/pause_ratio) | core-scoring |
| FR-6 句/词定位 | DTW 路径投影到词网格 | core-scoring/detail |
| FR-7 词级改进方向 | stress/length/pitch/linking diff + 规则措辞 | core-scoring/worddiff |
| FR-8 A/B 回放 | 原声/学习者均采样级 WAV 切片 + Media3 播放 | `:app` RecordingsRepository |
| FR-9 教学反馈 | 规则引擎(`llm_hook` no-op,守 NFR-1) | core-scoring/feedback |
| FR-10 反复练习 | Compose 重练流程 | `:app` |
| **FR-11 音素诊断** | espeak int8 假设打分式 MDD + 三重门控 | core-mdd(Gate C/R-7) |
| **FR-12 学习记录/进度** | Room 本地存储,历史成绩/进步曲线(macOS 亦补) | `:app` data |
| FR-M1 真实视频素材 | MediaCodec 解码,不用合成参考音 | core-audio |
| FR-M2 素材获取 | videos 目录 + 用户导入(Android 走 SAF/content URI) | `:app` |
| FR-M3 难度适配 | whisper 句切分 + >8s / >20 词从句边界二级切分 | core-asr |
| **NFR-1 本地/离线/隐私** | 全端侧推理,录音不出设备,RECORD_AUDIO;无任何云调用 | Gate A/R-5 保证 |
| **NFR-2 平台** | macOS + Android(原生 Kotlin) | — |
| NFR-3 性能 | 单句分析秒级(设备实测);转写后台+缓存 | 设备验证 |
| NFR-4 移动端约束 | API 28+ / **仅 arm64-v8a** / RAM / 包体 **935 MiB(asset pack)** / UNPROCESSED / 数值对齐 | Gate D/R-8 等;① ② 已落 PRD v0.2,包体经 R-12 修正(v0.3) |
| NFR-Q1 评分质量 | `calibration.json` 原样;PCC 0.60/0.43 保持;说话人不变性 | Layer2 验证 |

## 4. 已验证的运行时选型(每项一个,含 5 个重塑假设的发现)

| 决策 | 选型 | 关键依据 / 发现 |
|---|---|---|
| Whisper 转写+VAD | **sherpa-onnx Android AAR**;参考路径走 **VAD 段合并成 ≤29s 连续窗**(`:core-scoring/.../segment/AsrWindowPlanner.kt`),Silero VAD 另用于学习者录音与"有无人声" | 预编译 AAR、JNI 已通、arm64-v8a/armeabi-v7a 二进制俱全。**发现⑤**:Whisper 词时间戳不可靠(`forced_align.py` 注释明示会切尾/塌缩短词)→ Whisper 仅出**转写文本**,词边界一律走 MMS 对齐,与 macOS 同构。**发现⑥(R-10 实测修正本行)**:离线 Whisper 一次最多吃 30s,长音频必须自己切,而**怎么切是分歧的主因** —— Whisper 给拿到的任何一段结尾加标点,每个切口都可能成为假句末。四种策略:VAD 分段(原选型)5.56%/3.17%/172 单元、固定 29s 窗 5.56%/1.25%/162、Whisper 长音频循环 3.14%/1.01%/162、**VAD 合并窗 4.01%/1.65%/158**(金标准 159)。**发现⑦(同日补记)**:长音频循环最好但**在 Android 上写不出来** —— v1.13.4 AAR 的 `OfflineRecognizerResult` 没有 `segmentTimestamps`(Kotlin binding 落后于 Python;`javap` 已核),token 时间戳也恒为空(模型未导出 attention 输出),**Android 侧只拿得到 `text`** → 选合并窗。**发现⑧(R-11)**:换 `tiny.en` 档位省 57MB、快 1.67×,三条判据也都过(4.89%/1.88%/162)—— 但余量只剩 0.11pp,且**新增 `terror-frueling` 这类非词**,而 MMS 强制对齐没有拒绝路径,必须把从未说出的字符铺到真实音频上 → **base.en 保留为发布档,tiny.en 仅作低端设备速度降级**。详见 `docs/reviews/2026-07-26-android-gate-f-asr-text.md` 与 `docs/reviews/2026-07-26-android-r11-whisper-tier.md` |
| 强制对齐(MMS CTC) | **ONNX Mobile + 手写 Kotlin CTC Viterbi** | **发现①**:sherpa-onnx **不提供**强制对齐(Issue #3536 仍 open,无 PR)。torchaudio 的 `get_aligner()` 是教科书级 CTC Viterbi(~100 行),算法已逐行捕获(见 §5) |
| SSL 编码器(wav2vec2-base-960h, 6–9 层) | **ONNX Mobile,自定义导出 4 个 hidden-state 输出节点** | **发现④**:`output_hidden_states=True` 不会让 Optimum 默认导出中间层 → 必须 Optimum 导出后用 `onnx` 库把第 6–9 个 transformer block 的残差 `Add` 输出节点标为 graph output 再导出 |
| 音素 MDD(espeak-cv-ft) | **ONNX Mobile,动态 int8(318MB),惰性加载** | **发现③**:PyTorch ckpt ~2.4GB,但 `onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX` 动态 int8 = **318MB**(fp32 1.26GB)。可载入 6GB 手机但 RAM 紧张 → 按词批惰性加载、句间释放 session |
| 视频音轨解码 | ~~FFmpeg NDK 源码构建 + 薄 JNI~~ → **`MediaExtractor` + `MediaCodec` + `:core-scoring` 里的纯 Kotlin 多相重采样器** | ~~**发现②**:**ffmpeg-kit 已退役**(2025-01-06,二进制下架,不兼容 Android 16KB 页大小)。MediaCodec 对 WebM/Opus 覆盖不全~~ ⚠️ **R-9 推翻本行后半句**:①**学习者路径根本不产生编码音频**(AudioRecord 直采 16kHz PCM),webm/opus 是 WebView `MediaRecorder` 的产物,随 WebView 一起消失,只剩视频音轨要解;②对照官方 *Supported media formats*,**Opus 解码自 API 21 起是平台强制项**(容器 Ogg/MP4/Matroska),远低于 minSdk 28 —— "覆盖不全"不成立,唯一缺口是 `.avi`(FR-M2 导入面,非正确性)。ffmpeg-kit 退役属实,但不再相关。详见 `docs/reviews/2026-07-26-android-gate-e-audio-decode.md` |
| F0/音高/能量 | **TarsosDSP(st-h fork 2.4.1)** 纯 Java YIN | 仅用于 word_diff 音高斜率提示(低风险);强度/停顿用自写 RMS |
| 重采样 | **AudioRecord 原生 16kHz 采集(免重采样)**;视频音轨走 `:core-scoring/.../resample/PolyphaseResampler.kt`(纯 Kotlin windowed-sinc) | 录音路径直接 16kHz,无需 librosa/soxr。**R-9 实测**:重采样核的选择在分数域上是零 —— 多相 sinc / soxr_hq / int16-PCM 输入,相对 libswresample 的样本 SNR 只有 30–43dB(≈数百 LSB,原 Gate E 的 ≤1 LSB 由构造不可达),但 CMVN 后逐帧嵌入余弦 0.9983–0.9998、固定学习者只换参考解码路径的 **DTW cost 差 ≤0.0011、accuracy 差 0.00**(Gate A 容差 ±0.02/±2.0,余量 18×)。脚本 `scripts/resampler_parity.py` |
| WAV I/O | **手写 44 字节头读写**(~30 行) | soundfile 唯一用途是 clip WAV 切片 |
| numpy/scipy | **Kotlin FloatArray** | scipy 运行时根本没 import → 弃 |

**int8 导出路径(统一):** Optimum `main_export` → `onnx` 库加 hidden-state 输出节点(仅 wav2vec2-base 需要)→ `onnxruntime.quantization.quantize_dynamic(weight_type=QInt8)`。编码器嵌入事后 L2/CMVN 归一化,可吸收 int8 尺度误差(待 R-5/Gate A 验证)。

## 5. 两个必须 1:1 复刻的算法

### (A) CTC 强制对齐 Viterbi(`forced_align.py` → `core-scoring/.../viterbi/CtcViterbi.kt`)

**forced_align 与 phoneme MDD 共用此实现。**

```
输入:emission (T×V) log-probs(V 含 blank=0 在 id 0),tokens = 一词的清洗净化字符 id 序列

1. blank 填充扩展序列:ext = [blank, tok[0], blank, tok[1], blank, …, tok[n-1], blank],S = 2n+1
2. DP 表 dp[T][S](Float64, init -1e30)+ 回溯指针 bp[T][S]:
     dp[0][0] = emission[0][blank]
     dp[0][1] = emission[0][ext[1]]   (若 S>1)
3. 对 t in 1..T-1, s in 0..S-1:
     cands = [ (dp[t-1][s], s) ]
     若 s-1 ≥ 0:                  cands += (dp[t-1][s-1], s-1)
     若 s-2 ≥ 0 且 ext[s]!=blank 且 ext[s]!=ext[s-2]:
                                   cands += (dp[t-1][s-2], s-2)   # CTC 跳 blank 转移
     (val, src) = max(cands)
     dp[t][s] = emission[t][ext[s]] + val ;  bp[t][s] = src
4. 末列取 last = S-1 if dp[T-1][S-1] ≥ dp[T-1][S-2] else S-2 ;score = dp[T-1][last] / T
5. 回溯:从 (T-1, last) 逐帧记 ext 位 s,每帧 s = bp[t][s],t -= 1
6. 按 ext 位归组 → 每个奇数 ext 位 2k+1(第 k 个真 token)得该词帧范围 [min,max]
   → 词 [start,end] 秒 = (首帧·spf, (末帧+1)·spf),spf = 音频时长 / T
```

**Float 用 Double(与 Python `np.float64` 一致)。** torchaudio `aligner` 返回 `TokenSpan(.token,.start,.end)`(帧号,start 含、end 含,`forced_align.py` 末尾有 `+1`)。

### (B) 音素 MDD 替换搜索(`phoneme.py` → `core-mdd/.../PhonemeMdd.kt`)

```
diagnose_word_span(ref_wav, ref_start, ref_end, learner_wav, l_start, l_end, word):
  CTX = 0.25s
  ref_span    = ref_wav    [ref_start-CTX .. ref_end+CTX]   (clip)
  learner_span= learner_wav[l_start -CTX .. l_end +CTX]
  ref_phones  = CTC 贪解(ref_span)            # greedy collapse
  chars = [c for c in ref_phones if c in vocab]; ids = [vocab[c] for c in chars]

  # 把 canonical 裁剪到目标词(防邻词渗入):
  ref_em = emissions(ref_span);  _, spans = viterbi_align(ref_em, ids, pad)
  wf0 = (ref_start·SR - a)/spf - 3.0 ;  wf1 = (ref_end·SR - a)/spf
  keep = [ (p-1)//2 for (p,f0,f1) in spans  if p%2==1 and wf0 ≤ (f0+f1)/2 ≤ wf1 ]
  if len(keep) < 2: return ""
  c_ids, c_chars = [ids[k] for k in keep], [chars[k] for k in keep]

  # 门控:canonical 须能自拟合参考
  if best_sub_gain(ref_em, c_ids, c_chars,…).gain > 0.05: return ""   # 坏解码静默

  # 学习者段打分
  learner_em = emissions(learner_span)
  gain, sub = best_sub_gain(learner_em, c_ids, c_chars,…)
  if sub is None or gain ≤ 0.15: return ""
  return verbalize(sub, word)            # "/θ/ 要把舌尖伸到上下牙之间送气,别读成 /s/"

best_sub_gain(em, ids, chars, vocab, pad):
  base = viterbi_avg(em, ids, pad);  best_gain, best_sub = 0.0, None
  for i,p in enumerate(chars):
    if p == "ː": continue
    for c in _CANDIDATES:                 # 31 音素池
      if c == p or c not in vocab: continue
      ids2 = ids[:i] + [vocab[c]] + ids[i+1:]           # 替换
      gain = viterbi_avg(em, ids2, pad) - base
      if gain > best_gain: best_gain, best_sub = gain, PhoneSub(p,c,"substitute")
    ids2 = ids[:i] + ids[i+1:]                           # 删除
    if ids2:
      gain = viterbi_avg(em, ids2, pad) - base
      if gain > best_gain: best_gain, best_sub = gain, PhoneSub(p,"","delete")
  return best_gain, best_sub
```

**`_CANDIDATES` 与 `vocab.json` 原样随包(不重生成 tokenizer)。** 两个门控阈值(`0.05`/`0.15`)是 fp32 调出来的,int8 可能漂移 → R-7/Gate C 验证/重调。

## 6. 模块移植映射(`backend/core/*.py` → Kotlin)

| Python 模块 | Kotlin 模块 | 运行时 | 风险 |
|---|---|---|---|
| `align.py` | `:core-scoring/.../align/DtwAlign.kt` | 纯 Kotlin | 低(直接移植,Sakoe-Chiba 20% 带状 DTW) |
| `speaker_norm.py` | `.../norm/Cmvn.kt` | 纯 Kotlin | 低 |
| `score_b.py` | `.../score/{ScoreB,Calibration}.kt` | 纯 Kotlin + `calibration.json` asset | 低–中(校准保真) |
| `detail.py` | `.../detail/Detail.kt` | 纯 Kotlin | 低 |
| `word_diff.py` | `.../worddiff/{WordDiff,Pitch}.kt` | Kotlin + TarsosDSP | 中(F0 算法差异需容差) |
| `feedback.py` | `.../feedback/Feedback.kt` | 纯 Kotlin(`llm_hook` no-op,NFR-1) | 低 |
| `audio_io.py` | `:core-scoring/.../audio/AudioPreproc.kt` + `.../io/WavIo.kt`(纯 Kotlin,已落地);重采样 → `.../resample/PolyphaseResampler.kt`(同样纯 Kotlin,理由同下);解码留在 `:core-audio` | Kotlin + MediaCodec | 低–中(**R-9 后降级**:无 JNI;重采样器可 JVM 金标准测) |
| `transcribe.py` | 句/词切分 → `:core-scoring/.../segment/SentenceSegmenter.kt`、长音频切窗 → `.../segment/AsrWindowPlanner.kt`(均纯 Kotlin,已落地);识别本体 → `:core-asr/.../WhisperTranscriber.kt`(薄适配层) | Kotlin + sherpa-onnx | 中(**R-10 实测:风险在切窗策略,不在输出格式** —— 已移出 `:core-asr` 并锁金标准) |
| `ssl_encoder.py` | `:core-embed/.../Wav2Vec2Encoder.kt` | ONNX Mobile(4 输出图) | 中–高(发现④ 图编辑) |
| **`forced_align.py`** | `:core-align/.../ForcedAligner.kt` + `CtcViterbi.kt` | ONNX Mobile + 手写 Viterbi | **高**(最难单点) |
| **`phoneme.py`** | `:core-mdd/.../PhonemeMdd.kt`(复用 `CtcViterbi`) | ONNX Mobile(int8 318MB,惰性) | **高**(最重模型) |
| `pipeline.py` | `:app/.../AnalyzePipeline.kt` | Kotlin 协程编排 | 低 |
| `video.py`/`warmup.py`/`main.py` | `:app/.../repo/{Video,Recordings}Repository.kt`,`Warmup.kt`,无 server;音轨抽取 → `:core-audio/.../MediaAudioDecoder.kt`,**切片语义(seek 到前一关键帧、保留 pre-start 样本,`video.py:88`)归 `:core-scoring`** | Kotlin + Media3 + MediaCodec | 中 |

## 7. Phase 0 — 风险 spike 门(go/no-go,先过完才动其他)

仿 macOS freeze-spike 门模式。5 个 make-or-break 风险,按序验证(每门即一份 fit-review,落 `docs/reviews/`,延续 R-1..R-4 编号)。**R-10 / Gate F 是实施中补的第六道**,原计划没有它 —— 见本节末。

- **R-5 / Gate A —— int8 下数值评分对齐(最高风险,项目存在性证明):** 导出 wav2vec2-base(6–9 层)+ int8 → Android ONNX,同一对 ref/learner 走 macOS PyTorch 与 Android,**accuracy ±2.0 / fluency ±3.0 / DTW cost ±0.02**,跨嗓音 `test_speaker_invariance` cost ≤0.18。**No-go 兜底:** int8 若破坏说话人不变性 → 退 **fp16**(~190MB);再不行 → 端侧全功能前提失败,须战略回桌。**这条兜底在 R-12 被真的触发了**(arm64 int8 kernel 不变性 0.18323 > 0.18),且发现兜底本身此前根本载入不了 —— 判据未改,模型换成 fp16(实测 139.7MB,不是估的 190MB)。
- **R-6 / Gate B —— Viterbi 正确性:** 手写 `CtcViterbi.kt`,同一 MMS emission 走 torchaudio 与 Kotlin,每词 `[start,end]` 误差 ≤1 帧(20ms)。
- **R-7 / Gate C —— 音素 MDD 自拟合门控 int8 下仍成立:** espeak int8(318MB)重跑 think/sink 套件,canonical 自拟合 ≤0.04、垃圾 ≥0.09;若 int8 压缩增益域致误过门 → 设备上重调 `0.05`/`0.15`(数据在 `backend/tests/`)或退 fp16(635MB)。
- **R-8 / Gate D —— 6GB 设备 RAM 预算:** Pixel 4a 级设备全流程 `analyze` 30s 片段,峰值 RSS <3.5GB、20 连续无 OOM。兜底:espeak 按词批惰性 `OrtSession.close()`;仍紧 → MDD 按 `ActivityManager.MemoryInfo` 在低内存设备降级。
- **R-9 / Gate E —— 音频解码/重采样对齐(判据已改写,桌面侧 PASS):** ~~WebM/Opus blob 经 FFmpeg-NDK 解码 vs macOS `ffmpeg -ar 16000 -ac 1 -f f32le`,样本误差 ≤1 LSB~~ —— **原判据只有在"已经选了 FFmpeg"的前提下才可能通过**(换重采样核就必然换样本值),它不是在检验路线而是在假设路线。改为分数域判据:①同一片段 Android 解码+重采样 vs macOS `extract_audio()`,CMVN 后逐帧嵌入余弦均值 **≥0.995**;②固定学习者、只换参考解码路径,**DTW cost 差 ≤0.005、accuracy 差 ≤0.5**(Gate A 容差的 1/4);③目标格式集在设备上 `findDecoderForFormat` 全部命中。**桌面侧实测 PASS**(0.9983–0.9998 / ≤0.0011 / 0.00),据此改走 `MediaExtractor`+`MediaCodec` 路线,**Phase 2 不再需要 NDK**。设备侧留一项:多机解码一致性(系统解码器是各家 OEM 实现,不像 FFmpeg 处处同一份)。详见 `docs/reviews/2026-07-26-android-gate-e-audio-decode.md`。

- **R-10 / Gate F —— 转写文本分歧(实施中新增,原计划漏掉):** 原计划把 ASR 当"输出格式对齐"的中风险机械活(§6),漏了一条:**FR-2/FR-M3 按 `[.!?]` 切句,少一个句号就把两个练习单元合成一个,即使每个词都对** —— 标准 ASR 评测剥掉标点,给不出这个数。判据(实测后定,如实标注):归一化 WER ≤5%、**仅在两侧词相同处**统计的终止标点分歧 ≤2%、练习单元数 ±5%。**实测 PASS**:最好的策略 3.14% / 1.01% / 162 vs 159;但那条(Whisper 长音频循环)Android AAR 实现不了,**实际采用的 VAD 合并窗 4.01% / 1.65% / 158,同样过三条判据**。**判据不是文本相等** —— 两个 int8 base.en 解码器的分歧不可消除(fp32 只买回 0.11pp),但它不改变分数(分数是学习者与*同一段*参考音频的比较)。详见 `docs/reviews/2026-07-26-android-gate-f-asr-text.md`。

**Gate A+B 是生死对。A 连 fp16 都失败 → "端侧全功能"不可达,须在投入更多前降级到"准确度/流畅度/word-diff、不含音素 MDD"。**

## 8. 工程 / 模块结构(Gradle 多模块)

硬规则:**一切影响校准分数的代码在 `:core-scoring`,零 Android 依赖**,可在 JVM 用 macOS 金标准文件单测。

```
NativeLingoAndroid/
├── app/                    :app — Compose UI / ViewModel / DI / AudioRecord / Media3 / Warmup / Repo
├── core-scoring/           :core-scoring — 纯 JVM(DTW/CMVN/Score/Detail/WordDiff/Feedback/CtcViterbi/AudioPreproc/SentenceSegmenter)+ 金标准测试
├── core-embed/             :core-embed — ONNX wav2vec2-base(4 输出图)
├── core-align/             :core-align — ONNX MMS CTC + ForcedAligner(用 core-scoring 的 CtcViterbi)
├── core-mdd/               :core-mdd — ONNX espeak-cv-ft int8 + PhonemeMdd
├── core-asr/               :core-asr — sherpa-onnx Whisper + Silero VAD(句切分已归 :core-scoring,见 §12)
├── core-audio/             :core-audio — MediaExtractor/MediaCodec 解码(裁剪/归一化/WAV I/O/重采样均归 :core-scoring,见 §12)
├── core-models/            :core-models — ModelRegistry(whisper 打包进 APK;余下首启下载)
└── buildSrc/               约定插件(R-9 之后不再有 NDK FFmpeg 构建)
```

模块不变量:`:core-scoring` 只依赖 Kotlin stdlib;`:core-embed/align/mdd/asr` 依赖 `:core-scoring`(共用 `CtcViterbi`)+ `onnxruntime-android`;`:app` 依赖全部。

## 9. 分阶段交付(全功能目标,按风险排序;单人工程师估)

| 阶段 | 内容 | 估时 |
|---|---|---|
| **0** | spike 门 A–E(R-5..R-9),逐项 go/no-go | 3–4 周(**未过不进下阶段**) |
| **1** | `:core-scoring` + 金标准测试框架(JVM,过 Layer1+2) | 3–4 周 |
| **2** | `:core-embed/asr/audio/align` 接 ONNX/sherpa/MediaCodec,设备端跑通 | 4–5 周(R-9 免掉 NDK 工具链后偏下限)—— ✅ **已完成,设备侧 22/22 见 R-12** |
| **3** | `:core-mdd` + RAM 收紧 | 2–3 周(Gate C/D 失败可跳) |
| **4** | Compose UI / ExoPlayer 跟读 / A/B 回放 / 录音 Repo / 首启下载 / FR-12 Room | 4–5 周 |
| **5** | 仪器化诊断 / beta / OEM 调音 | 2–3 周 |

**合计 ~18–24 周(单人);第二人 Day-1 起并行 Phase 4(UI)→ ~14–16 周。** UI 侧可与算法侧并行。

## 10. 验证策略(证明 Android == macOS,三层)

- **Layer 1 金标准 fixture(JVM,`:core-scoring:test`):** 迁移前先从 macOS 后端抓 golden —— 固定语料跑 `analyze_full`/`analyze_arrays`,落 `{accuracy, fluency, path_cost}` 元组、每词状态、DTW path、对齐时间、MDD 文本到 `core-scoring/src/test/resources/golden/`(由 `scripts/capture_golden.py` 产出)。Android CI 同算法同输入,**容差内**断言:cost ±0.02 / accuracy ±2.0 / fluency ±3.0 / 词状态精确 / 对齐 ±20ms / think-sink 文本精确。**容差即 int8 漂移的捕获点。**
- **Layer 2 emission 级对齐(int8 真相):** 同一波形走 macOS PyTorch fp32 与 Android ONNX int8,逐帧比 layers 6–9 均值嵌入余弦 ≥0.995(CMVN 后)。MMS emission 余弦 ≥0.995;espeak 贪解串在干净参考上精确一致。**此层过,下游 DTW/分数对齐即机械。**
- **Layer 3 设备仪器化:** debug 构建每次 `analyze` 落 JSON 边车(各中间张量 hash),用户报评分偏差时可与 macOS golden diff。beta 随包。
- **说话人不变性 / 校准 PCC:** 不变性测试变 `:core-scoring` JVM 测试(跑在 golden 嵌入上,测试时无需模型);校准 PCC **不在设备重算**——`calibration.json` 原样随包,测试只断言 `accuracy_from_cost` 在 100 个采样 cost 上与 macOS `np.interp` 逐位一致。

## 11. 诚实评估 & 降级候选

**机械的(大部分 LOC):** `align/speaker_norm/score/detail/feedback` 直移(~30% 工);`audio_io/pipeline/UI/HTTP→进程内`(~30%,中风险在 AudioRecord 与 MediaCodec 的 OEM 怪癖 —— R-9 之后不再有 FFmpeg JNI)。

**真难的:** ① CTC Viterbi(~100 行,forced_align 与 MDD 共用,一个 off-by-one 全毁,Gate B/R-6 捕);② wav2vec2 hidden-state 自定义图导出(R-5/Gate A,1–3 天 Python+验证);③ **int8 评分保真(项目存在性证明,R-5/Gate A,1–2 周)**;④ 318MB espeak 在 6GB 手机(R-8/Gate D,~1 周);⑤ AudioRecord OEM 一致性(用 `UNPROCESSED`,API≥25,3–5 设备调音,~3 天)。

**降级候选(仅当对应 Gate 失败时触发,不违背"全功能"初衷):**
1. **音素 MDD(FR-11)** —— R-7/R-8 失败时,仅 `ActivityManager.lowMemory==true` 设备降级(其余仍全功能)。MDD 本就门控在 weak/bad 词后、`return ""` 静默降级,切口干净。
2. **espeak 退 fp16(635MB)** —— R-7 失败时,首 MDD 延迟 +~6s,可接受。
3. **学习记录(FR-12)** —— Room 本地存储,无模型依赖,永不降级。
4. **Whisper 档位** —— 设备上首次转写太慢时降 `tiny.en`(**R-11 已量**:102.8MB、快 1.67×,代价是 WER 4.01%→4.89% 且新增 MMS 无法拒绝的非词 → **只作速度降级,不作体积手段**)。降档判据待设备数据。

**唯一不可降级的是 R-5/Gate A**:int8 破坏校准且 fp16 亦破 → 端侧全功能前提失败,须回桌(重校准会作废 macOS 随包的 `calibration.json`,或对 SSL 编码器单项放松 NFR-1 走云——后者须用户决策)。

## 12. 当前进度

- [x] PRD 修订至 v0.1(NFR-2 双平台 / NFR-4 移动端 / FR-12 in-scope / §6 Android 映射 / §7 R-5..R-9 计划)。
- [x] 本迁移文档落地(`docs/android-migration.md`)。
- [x] macOS 金标准抓取脚本 `scripts/capture_golden.py` —— 已产出 baseline 并提交(说话人不变性 cost **0.1714** ≤0.18,acc 95.0;Gate A/B/C fixture 齐备)。
- [x] `NativeLingoAndroid/` Gradle 多模块骨架 + `:core-scoring`。
- [x] **本地工具链打通**:JDK 17(openjdk@17)+ Gradle wrapper(8.9);`:core-scoring:test` 在 JVM 跑通。
- [x] **Phase 1 评分核心移植(JVM 数值对齐验证)**:
  - Gate A · 成本对齐:`DtwAlign.kt` + `Cmvn.kt` —— 复现 macOS 成本(samevoice 0.0 / 说话人不变性 0.1714 / wrongtext 0.6568,±0.02)。
  - Gate B · CTC 对齐:`CtcViterbi.kt` —— 手写 CTC 强制对齐复现 torchaudio 每字符帧边界(±1 帧)。
  - `:core-scoring` 测试 8/8 全绿。
- [x] Phase 1 余项:校准映射(cost→accuracy/fluency,对齐 95.0/74.5)、detail 投影、word_diff、feedback。
- [x] **R-5 / Gate A(Python 侧)PASS** —— `scripts/onnx_export_spike.py` 证:int8 仅 transformer(CNN 留 fp32,95MB)守住说话人不变性(cost 0.1773 ≤ 0.18,acc 95.0);全量 int8 失效(cost 0.2789)。SSL 编码器定为此策略,fp16(139MB)兜底。详见 `docs/reviews/2026-07-25-android-gate-a-onnx-int8.md`。⚠️ **R-12 推翻了「定为此策略」**:同一份 int8 导出在 arm64 上过不了同一条线(0.18323),已换成那个 fp16 兜底 —— **桌面 PASS 与设备 PASS 不是同一件事**,这是本项目最贵的一次教训。
- [x] **R-7 / Gate C(espeak)PASS** —— int8 全量 303MB,CTC 贪解串精确,余弦 0.9946(`scripts/onnx_gate_bc_spike.py`,`docs/reviews/2026-07-25-android-gate-bc-onnx.md`)。
- [x] **R-6 / Gate B 算法 PASS**(CtcViterbi JVM 复现 torchaudio ±1 帧);emission int8 导出当时受阻于 torchaudio `List[int]` 图怪癖 —— **已在 Phase 2 解掉,见下**。
- [x] **Phase 1 收尾:评分层全部移植完毕(2026-07-25)** —— `:core-scoring` **21/21 全绿**,`:core-embed` 3/3 全绿,macOS 后端 `pytest backend/tests/` 12/12 不受影响(`backend/` 未改动,金标准源保持权威)。
  - 开工前对照 Python 逐函数核查后发现,**实际缺口比上一条勾选项记录的更宽**:除 word_diff / feedback 外,`find_problem_regions`、`score_track_b`、`compute_sentence_details` 也未移植。四项一并补齐:
    - **FR-4 问题区间**:`ScoreB.kt` 新增 `findProblemRegions` + `scoreTrackB`(`ProblemRegion` / `TrackBResult`)。macOS 的"无校准兜底分支"**刻意不移植** —— `calibration.json` 恒随包,兜底分支在 Android 不可达,移植它等于引入无法被金标准覆盖的死代码(源码内已注明)。
    - **FR-6 句级**:`Detail.kt` 新增 `computeSentenceDetails`(句 accuracy/fluency + 学习者回放区间)。金标准**特意以非零 `learner_offset`(0.137s)抓取**,否则"偏移未施加"这类 bug 会被零偏移的 fixture 掩盖。
    - **FR-7 词级改进方向**:新增 `worddiff/WordDiff.kt`(~340 行),含 difflib `SequenceMatcher.get_matching_blocks()` 的忠实重写。
    - **FR-9 反馈**:新增 `feedback/Feedback.kt` 规则引擎;`llm_hook` 在 Android 恒为 no-op(NFR-1:任何内容不出设备,只有本地模型才可能填这个槽)。
  - **移植中确认的 4 个 Python↔Kotlin 数值陷阱**(均已在测试中锁死):① `np.convolve(..., mode="same")` 的**零填充边界衰减**会压低首尾帧,朴素滑动平均会选中不同的重音峰;② Python `f"{x:.0%}"`/`:.1f`/`:.2f` 是**四舍六入五成双**,须用 `Math.rint`,Kotlin `round` 是五入;③ numpy `mean` 即便对 float32 数组也按 float64 累加;④ difflib 是**最左最长递归而非 LCS**,配对结果可能少于 LCS,近似实现会与 macOS 分歧。
  - **FR-7 音高项的诚实边界**:Praat 自相关跟踪器在 JVM 无逐位等价实现(Android 走 TarsosDSP YIN,见 §4)。故音高源做成可注入的 `PitchEstimator`,金标准同时抓 `_tips`(含 Praat)与 `_tips_nopitch` 两份,JVM 测试对**可精确复现的子集**(重音/时长/连读,占诊断主体)逐字断言中文提示串,而不是把整体断言放宽成容差。音高提示的等价性留待 Tier 3 设备侧与 TarsosDSP 一并验证。
- [x] **R-6 / Gate B 补完 + Phase 2 `:core-align` 落地(2026-07-25)** —— emission 导出 **PASS**,`:core-align` **8/8 全绿**(`:core-scoring` 21/21、`:core-embed` 3/3 不受影响)。详见 `docs/reviews/2026-07-25-android-gate-b-mms-rehost.md`。
  - **解法:state-dict 载重。** `scripts/onnx_export_mms.py` 把 MMS_FA 的 **423 个张量**全部搬到 HF `Wav2Vec2ForCTC`(无缺失、无多余),再走 Gate A/C 已验证的导出+量化路径:**fp32 1203MB → int8 仅 transformer 338.6MB**。真正的阻塞点不是 `List[int]`(可绕),而是绕过后 `quantize_dynamic` 对 torchaudio 图**体积零变化**(1204MB→1204MB,linear op 不匹配量化 pattern),1.2GB 首启下载不可发布。
  - **一个会静默出错的坑**:bundle 声明 `encoder_layer_norm_first=True`,但 torchaudio 把**取反值**传给 `Transformer` 包装层(读到 `False`)。真实拓扑是 pre-norm + 尾部 layer_norm = HF `do_stable_layer_norm=True`。若照包装层的 flag 设成 `False`,**权重会无报错全部载入**、模型正常跑、对齐结果是垃圾 —— 无异常可依赖,故 `verify_parity` 前置于任何导出动作。
  - **判据本身改过一次**:初版 `max|Δ| < 1e-3` 对**正确**映射报 FAIL(1.03e-3),诊断发现最大偏差落在 log p = **−13.75**(p≈1e-6)的深负尾部(fp32 累积 + HF sdpa vs torchaudio 手写 matmul),而余弦 1.000000、逐帧 argmax 100% 一致。绝对上界被强制对齐根本不消费的尾部主导 → 改判**余弦 + 逐帧 argmax**;错误映射会把余弦打到远低于 1,新判据更严不更松。
  - **实测**:fp32 余弦 1.00000 / 字符帧误差 **0**;int8 余弦 **0.99896** / 字符帧误差 **1**(Gate B 判据 ≤1)。legacy exporter 对 sdpa `is_causal` 的 TracerWarning 未靠"应该恒为 False"打发 —— 加了 `verify_generalizes`,3 段非 dummy 长度(130/132/148 帧)余弦 1.000000。
  - **三个动态 shape 算子外置到 Kotlin**(`MmsEmitter.kt`):整段波形 `layer_norm`(**eps 1e-5、无 affine**,与 `:core-embed` 特征提取的 **1e-7** 不同 —— 看着可互换,实则各对齐各自上游)、star 通配列(全零第 29 列,log 域 0 即 p=1)、以及保留在图内的 `log_softmax`。
  - **帧→秒约定逐字复刻**:torchaudio `TokenSpan.end` 是开区间,macOS `align_words` 再 `+1` 帧;这一帧**原样保留**,因为金标准词边界就是这么产生的且 FR-8 回放 seek 到它们,"更正确"只会与 macOS 失同步。`:core-scoring` 升为 `java-test-fixtures` 以共享金标准 JSON 读取器(每模块各写一份解析器正是漂移的起点)。
- [x] **`audio_io.py` 移植(2026-07-26)** —— `:core-scoring` **33/33 全绿**(新增 12 项:6 `AudioPreproc` + 6 `WavIo`)。
  - **放在 `:core-scoring` 而非计划中的 `:core-audio`,是有意偏离**:§8 的模块不变量要求"影响校准分数的代码零 Android 依赖、免设备可测",而静音裁剪正是此类 —— 它决定哪些采样进 DTW,其前导偏移就是 FR-8 回放要加回的 `learner_offset`。`:core-audio` 保留给真正需要 NDK 的解码/文件 I/O。
  - **`librosa.effects.trim` 被逐链复刻**(0.11):中心零填充 `frame_length//2` → 2048/512 分帧 RMS → `amplitude_to_db(ref=np.max, amin=1e-5)`(功率域,即 `amin²=1e-10`)→ `> -30dB` → `frame*hop` 回采样。裁剪边界**逐采样精确断言**(8 个用例),不给容差 —— 容差正是系统性差一帧藏身之处。
  - **金标准是特意造的,不是捡的**:macOS `say` 几乎不带前导静音(裁掉 ~10 采样),所以除 5 条真实语料外补了 3 个合成用例 —— 零填充(真实场景:录音键延迟)、以及**故意卡在 -30dB 阈值两侧 ±4dB** 的音调填充。零填充在任何 dB 实现下都是 -100dB,单靠它无法证明 `amin`/`ref` 正确;`pad_above`(start=0,整段保留)与 `pad_below`(start=4096)一起才真正锁死阈值链。另有一条测试**守护 fixture 本身**:若这两个用例哪天裁剪结果相同,阈值就等于没测。
  - **两个反直觉行为已核实而非推断**:① **全静音不被裁剪**(librosa 返回 `[0, 8000]`)—— dB 相对最响帧,静音对静音时全部并列 0dB 算作信号;死录音因此按原长进编码器并得低分,与 macOS 一致。② 真正会返回 `[0,0]` 的是 **NaN 路径**(与 NaN 的比较恒假),坏解码可达,此时回退到未裁剪原信号(空波形会让下游编码器崩,而不是给出一个差分)。两条均在 Python 侧实测确认后才写进断言 —— 初版断言按"应该是 -100dB / 全静音应裁空"写,**测试红了两次,错的是断言不是移植**。
  - **`WavIo` 与 soundfile 逐字节相同**(整文件 32044 字节,含头)。float→int16 的转换是 **`floor(x * 32768)`**,不是凭记忆会写的那个:在金标准 clip 的 16000 个采样上,`floor` 失配 **0**,`rint(x*32768)` 失配 7983,`trunc` 失配 9165(全在负样本),`rint(x*32767)` 失配 8184。所有错法都只差 1 个 LSB —— 听不出来,所以永远不会有人报 bug,只会让 Android 的回放切片悄悄不再是 macOS 的切片。libsndfile 内部机制未查证,fixture 即契约。
- [x] **`transcribe.py` 句/词切分移植(2026-07-26)** —— `:core-scoring` **42/42 全绿**(新增 9 项 `SegmentationParityTest`)。FR-2 的句边界 + FR-M3 的长句二级切分落在 `segment/SentenceSegmenter.kt`;`:core-asr` 只剩 sherpa-onnx 识别本体。
- [x] **长音频切窗移植(2026-07-26,R-10 的产物)** —— `segment/AsrWindowPlanner.kt` + 6 项 `AsrWindowPlannerParityTest`,`:core-scoring` **48/48 全绿**。金标准 `golden/asr/vadwin_trace.json` 记的是实测那次运行的 77 个 VAD 段 → 27 个窗,Kotlin 必须逐窗复现。测试还锁死两件事实而非直觉:**超长窗真的存在**(`max_speech_duration` 不是硬约束),以及**合并永远不会造出超长窗**。
  - **同 `audio_io` 的定位理由**:句边界决定哪一段参考音被裁出来送进 DTW、也决定 FR-8 回放的区间,属"影响校准分数"的代码 → 必须免设备可测。`normalizeToken` 一并导出给 `:core-asr` 复用,避免两侧各写一份 token 清洗。
  - **金标准不是合成的,是真的**:`videos/7.1.sentences.json` 里那份缓存转写(**1944 词 → 164 句**)被反向拆回词序列作为输入 —— 因为 `emit` 原样透传词,把缓存里各句的词拼起来恰好就是当初喂给 merge 的输入,capture 脚本内部断言"重跑 merge 能逐字节复现缓存"来证明这一点。它一次性覆盖 62 次切分(47 标点 / 12 连词 / **4 次中点并列** / 3 次放弃),以及 whisper 真实吐出的脏 token(`long -considered`、前导连字符、引号收尾)。合成用例(15 条)是在**先给 Python 函数打桩量过分支覆盖**之后补的,只补语料没覆盖到的分支,不重复。
  - **三个新的 Python↔Kotlin 陷阱(全部与直觉相反,已测试锁死)**:① `round(x, 3)` 是对**二进制精确值**四舍六入五成双 → 忠实写法是 `BigDecimal(x).setScale(3, HALF_EVEN)`;两个顺手会写的形式(`Math.round(x*1000)/1000.0`、`"%.3f"`)都是五入,对 0.0625 给 0.063 而 Python 给 0.062。**40 万随机值找不出一处分歧** —— 只有二进制精确的并列值才能区分,所以随机测试在这里等于没测。② Java 的 `$` 在结尾的 `\r`/`\u0085`/`\u2028`/`\u2029` 前也匹配,Python 只在 `\n` 前 → 两个正则加内联 `(?d)`(UNIX_LINES),否则 `".`\u2028`"` 结尾的 token 在 Android 断句、在 macOS 不断。③ Python `str.isspace()` 认 **29 个 BMP 码点**,Java 三种说法没有一种吻合:`isWhitespace()` 特意排除不换行空格(`\xa0`/`\u2007`/`\u202f`),`isSpaceChar()` 排除制表/换行,NEL(`\u0085`)两者都不认 → 谓词取 `isWhitespace() || isSpaceChar() || =='`\u0085`'`,并**在全 65536 码点上双向比对** Python 实测集合,而不是相信这个并集。
  - **两条路径的不对称是刻意的,且被双向断言**:参考路径切,学习者路径(`_merge_into_sentences`)不切 —— 学习者录的就是他选的那一句,按*他自己*的从句结构再切会破坏与参考块的 1:1 对应。测试对同一超长词表同时断言"学习者=1 句"和"参考>1 句",这样将来任何"统一两条路径"的重构会在此处红掉,而不是悄悄改变评分单元。
- [x] **R-10 / Gate F(2026-07-26,新增门)—— 转写文本分歧 PASS**,详见 `docs/reviews/2026-07-26-android-gate-f-asr-text.md`。macOS arm64 上用 PyPI `sherpa-onnx==1.13.4` 直接实测,不必等设备。
  - **原计划漏了这道门**,因为 §6 把 ASR 记成"输出格式对齐"的中风险机械活。漏掉的那一条是:Whisper 在这条流水线上**只贡献文本**,而文本里的**标点决定练习单元的切分**(FR-2/FR-M3),少一个句号就合并两个单元 —— 而标准 ASR 评测剥掉标点,给不出这个数。另两条下游:文本错 → MMS 被要求对齐从未说出的字符 → 词边界任意(FR-8/FR-6);canonical 音素错 → FR-11 诊断错。
  - **主因是我们的切块选择,不是 sherpa-onnx / ONNX / int8。** 离线 Whisper 一次最多 30s,长音频必须自己切。同模型同权重、四种策略(WER / 标点分歧 / 练习单元,金标准 159):**VAD 分段**(§4 原选型)5.56% / 3.17% / 172;**固定 29s 窗** 5.56% / 1.25% / 162(丢 65 词,WER 靠删除撑);**Whisper 长音频循环** **3.14% / 1.01% / 162**;**VAD 段合并成 29s 窗** 4.01% / 1.65% / **158**。机制:**VAD 在句中下刀,Whisper 给拿到的任何一段结尾加标点**,每个切口都成了假句末。
  - **但最好的那条在 Android 上写不出来(同日补记,决定 1 被推翻)。** 长音频循环要读回 segment 时间戳来推游标,而 **v1.13.4 AAR 的 `OfflineRecognizerResult` 没有这些字段**(`javap` 已核:只有 `text/tokens/timestamps/durations/lang/emotion/event`;`enableSegmentTimestamps` 开关有,读不回来)。两条退路都死:v1.13.4 已是最新 release;token 时间戳恒为空(现成模型未导出 attention 输出)。**Android 侧只拿得到 `text`。** 从源码构建 sherpa-onnx 能解,但为 0.9pp WER 再开一个 NDK 工程不值 —— **等 `:core-audio` 的 FFmpeg NDK 工具链就绪后再重估**。
  - **改用 `vadwin`:VAD 找语音段,再贪心合并成 ≤29s 的连续窗**(含段内静音,不是拼接 —— 拼接会造出真实语流里没有的衔接)。过全部三条判据,且**切口既少又落在静音里**:77 个 VAD 段 → 27 个窗,切口数比 VAD 分段少 2.8 倍,也不像固定窗那样切在词中间。**切块逻辑落在 `:core-scoring/.../segment/AsrWindowPlanner.kt`**(纯 Kotlin,金标准 `golden/asr/vadwin_trace.json`,6 项断言,48/48 绿)—— 因为切口位置决定练习单元切分。这么划之后 **`:core-asr` 只剩"喂 VAD、按边界调 recognizer、收 text",没有值得测的东西**,原先"`:core-asr` 无 JVM 对齐故事"的顾虑不成立。
  - **顺带:`max_speech_duration = 25.0` 是建议值不是约束** —— 77 段里两段超 29s(29.91 / 30.17),一段超 30s 被 sherpa 静默截断,636s 里丢 0.166s(0.03%,已含在 4.01% 内)。合并不会造出超长窗(边界相对窗首判),超长窗只可能是单个超长 VAD 段直通 → `AsrWindowPlanner.overlong()` 报给 `:core-asr` 记日志,**C++ 那句警告在 Android 上没人看得见**。
  - **两条与 Gate A/B/C 相反的结论**:① **int8 不是问题** —— fp32 只把 WER 从 3.14% 买到 3.03%(0.11pp)却要多付 132MB;Gate A 那里 int8 是会**破坏**说话人不变性的(0.1773→0.2789),这里的损失是噪声级,**转写不需要 fp32 退路**。② **int8 一点也不更快**(RTF 0.081 vs 0.083)—— 自回归解码器受内存带宽限制,瓶颈是 51864×512 的 embedding 表而非算力;**设备上若转写太慢,量化不是杠杆,换 `tiny.en` 档位才是。**
  - **包体估算错了 2.3 倍**:whisper base.en int8 实测 **159.8MB**(encoder 29.1 + decoder 130.7),不是记了两版的 ~70MB。decoder 量化率只有 1.5×,因为 token embedding 表按 fp32 保留(单这一项 106MB)。连带:首启下载 → **~827MB**;且 160MB **进不了 base APK**(Play 压缩后上限 150MB),whisper 从"打包 APK"改为首启下载或 asset pack —— 要落 PRD NFR-4②。
  - ~~**两处待用户拍板**~~ ✅ **已拍板(2026-07-26)**:预置语料**随包分发 `videos/*.sentences.json`**,导入素材仍走端侧转写(落 PRD FR-2);whisper 分发改**安装时 asset pack** —— 详见下方 R-11。
  - **一个顺带的观察**:38 处差异里 11 处只是分词不同而**金标准是难看的那一方**(`U .S.` / `long -held` / `the 250 ,000,`)—— 这是 faster-whisper `word_timestamps` 切词的产物,即发现⑤在*文本*层面的同一个毛病。所以 `golden/seg/` 里存在 Android 永远不会产生的 token 形状;不影响 `SegmentationParityTest`(它测 merge 函数而非分词器),但别误读成"Android 也会这样"。
- [x] **`:core-asr` 落地(2026-07-26)** —— sherpa-onnx Whisper + Silero VAD 的薄适配层(`WhisperTranscriber.kt` / `SpeechDetector.kt`),`assembleDebug` 通过。切窗与切句都在 `:core-scoring`,这里只剩 JNI 管线,**没有可在 JVM 上测的东西**(这是设计结果,不是缺口)。三个非显然的工程决定:
  - **依赖走"GitHub releases 当 ivy 仓库"**:k2-fsa **没有 Maven Central 制品**(`repo1` 上不存在 `com.k2-fsa` 组;搜到的 `sherpa-onnx` 都是第三方转包)。直接 `implementation(files("*.aar"))` 也不行 —— **AGP 拒绝为带本地 .aar 依赖的 library 模块产出 AAR**。settings 里声明一个 pattern 为 `v[revision]/[artifact]-[revision].[ext]` 的 ivy 仓库正好命中 release URL,于是它变成真正的模块依赖。字节由 `verifySherpaAar` 的 sha256 钉死(该 ivy 仓库没有签名),**并断言恰好解析到 1 个制品** —— 空解析下的校验循环比没有校验更糟。
  - **选 static-link 变体(37.6MB)而非默认 AAR(48.8MB)**:默认 AAR 自带 `libonnxruntime.so`,与 `onnxruntime-android`(`:core-embed`/`:core-align`/`:core-mdd`)带的那个**同名冲突**。两边今天都是 1.27.0,`pickFirst` 会"无害"解决 —— **这正是问题**:哪天任一侧升版本,胜出的那个 .so 会静默地同时服务两边,故障形态是线上崩溃而不是构建报错。静态链接把这个共享符号彻底消掉,代价是每 ABI 多约 19MB 的 ORT 副本。(顺带核过:`libsherpa-onnx-jni.so` 的 LOAD 段 `p_align = 0x4000`,**满足 Android 16KB 页要求** —— ffmpeg-kit 正是栽在这条上。)
  - ✅ **只发 arm64-v8a(2026-07-26 拍板,已落 PRD NFR-4①)**:首先是正确性而非体积 —— Gate D 的 ~3.5GB 峰值预算(espeak 单模型 302.9MB + ORT arena)**32 位进程根本寻址不下**,能跑这个应用的设备都是 arm64;顺带把上面那 19MB 的重复代价减半。
- [x] **R-9 / Gate E 桌面侧结论(2026-07-26)—— `:core-audio` 改走 MediaCodec,Phase 2 不再需要 NDK**(`docs/reviews/2026-07-26-android-gate-e-audio-decode.md`,脚本 `scripts/resampler_parity.py`)。
  - **原判据(样本误差 ≤1 LSB)自身失效**:它只有在已经选了 FFmpeg 时才可能通过,换重采样核就必然换样本值 —— 不是在检验路线,而是在假设路线。真正要问的是「参考音频用哪个重采样器,会不会改变学习者看到的分数」,判据必须落在分数域。
  - **发现②的前提在 Android 上不存在**:学习者路径是 `AudioRecord` 直采 16kHz PCM,**根本不产生编码音频** —— webm/opus 是浏览器 `MediaRecorder` 的产物,随 WebView 一起消失。只剩视频音轨要解。而 Opus 解码**自 API 21 起是平台强制项**(容器 Ogg/MP4/Matroska),minSdk 28 稳过;`.mp4/.m4v/.mov/.mkv/.webm` 全在平台强制表里,**唯一缺口是 `.avi`**(官方文档全文未列),那是 FR-M2 的导入面 → 建议 Android 导入白名单去掉 `.avi`(要落 PRD),需要时再接 Media3 实验性 `AviExtractor`。
  - **重采样核的选择在分数域上是零(决定性)**:相对 libswresample,多相 sinc / soxr_hq / int16-PCM 输入的样本 SNR 只有 **30.5–43.0dB**(maxΔ ≈ 数百 LSB),但 CMVN 后逐帧嵌入余弦 **0.9983–0.9998**(全 ≥0.995;掉到 0.99 以下的 1–6/1250 帧全部落在低能量帧,是 CMVN 放大静音噪声)。更贴近真实用法的一测 —— **固定学习者、只换参考的重采样器**(Android 上学习者永远不重采样)—— 在 cost 0.30–0.39 的真实档位上 **Δcost ≤0.0011、Δaccuracy 0.00**,Gate A 容差 ±0.02/±2.0,**余量 18×**。**MediaCodec 默认的 int16 PCM 输出是免费的**(与 float 输入在四位小数上一致)。
  - **顺带一个自洽性发现**:macOS 自己就用了两个重采样器 —— `audio_io.py` 走 soxr、`video.py` 走 swresample。「必须与 macOS 逐样本一致」这个诉求本来就无对象。
  - **代价写清楚**:失去「所有设备样本一致」的保证(系统解码器是各家 OEM 实现,不像 FFmpeg 处处同一份)—— **这是路线 B 唯一真实的风险,且只能在设备上测**,已进设备清单。先验上安全(换重采样核这么大的扰动才值 0.0011,合规解码器之间应远小于此),但那是推断不是测量。
  - **顺带消掉**:buildSrc 的 NDK FFmpeg 构建(本机也确实没装 NDK)、LGPL 重链接义务、16KB 页对齐约束(无自带 .so)、+2–4MB/ABI 包体。
  - **`video.py:88` 的 seek 语义必须照抄**:seek 到 `start` 之前最近的关键帧且**不丢弃 pre-start 样本**。这决定句子片段的起点 → 按 R-10 立下的规矩(决定音频在哪里被切的代码必须能在 JVM 上验),切片策略进 `:core-scoring`,`MediaExtractor` 只提供关键帧时间。
- [x] **`PolyphaseResampler` + `:core-audio` 落地(2026-07-26)—— Phase 2 模块齐了**。
  - `:core-scoring/.../resample/PolyphaseResampler.kt` 是 **`scipy.signal.resample_poly`(默认 Kaiser 5.0)的 1:1 移植**,逐样本 |Δ| < 1e-12 对 4 例 float64 金标准(`golden/resample/`)。**钉 scipy 而不是"写个够好的"**,是因为 R-9 那组分数域测量就是用它做的 —— 不钉住,测量转移不过来。`:core-scoring` **53/53 全绿**(新增 5 项)。
  - `:core-audio/.../MediaAudioDecoder.kt`:`MediaExtractor`+`MediaCodec` → 下混 → 重采样,`findDecoderForFormat` 前置探测,采样率取**输出格式**而非轨道格式。`assembleDebug` 通过 —— 与 `:core-asr` 同样,**框架调用一次都还没在设备上跑过**。
  - `DecodedAudio.startS` 返回首个解出样本的真实时间戳(seek 到前一同步样本、保留 pre-start 样本,与 `video.py` 同),FR-8 回放区间需要它。
- [x] **R-11(2026-07-26)Whisper 档位 —— 量了 tiny.en,不建议采用**(`docs/reviews/2026-07-26-android-r11-whisper-tier.md`,`scripts/asr_text_parity.py --tier`)。
  - **换档是未测量的动作**,R-10 的三条判据是在 base.en 上量的,所以换档要自己再过一遍。同语料同策略(`vadwin`/int8)实测:**tiny.en 102.8MB / WER 4.89% / 标点 1.88% / 单元 162**,三条判据都过 —— **但余量只剩 0.11pp 与 0.12pp**,而 R-10 的判据本是**事后定的**、语料只有一段(R-10 自己写明"不足以给出 WER 的置信区间")。一条事后定的线 + 一段语料 + 0.11pp,不构成"过了"。
  - **决定性的是分歧结构退化,而 R-10 判 PASS 恰恰依赖这一条**("全是局部替换,没有一处整段崩坏")。多词分歧摊开:base.en 6 处**无一产生非词**(`51 %`→`fifty one percent`、`stride and`→`strident` 之类);tiny.en 新增 `tariff ruling, in essence`→**`terror-frueling, and, as since`**、`decide? In factically,`→**`infatically`**,以及把主播名 `Tony DeCoupe` 揉成 `Tonya Colpola`。**MMS 强制对齐没有拒绝路径** —— 给它非词就必须把从未说出的字符铺到真实音频上,该 span 内 FR-2/FR-6/FR-8 直接失去对应关系(FR-11 有 canonical 自拟合门控兜底,**另三条没有**)。所以那 0.88pp 不是均匀变差,买来的是一类下游无防线的新错误。
  - **tiny.en 真正值钱的是快 1.67×**(636s 全片 38.2s→22.9s 墙钟,CPU 142s→82s)—— 这把 R-10 的"换档才是那根杠杆"量出来了。**保留为低端设备的运行期降级档,不作发布默认**;降档触发条件待设备数据(桌面上量不出"多慢算太慢")。
  - **顺带否掉「量化 embedding 表」**:该表(base.en 106.2MB,占 int8 decoder 130.7MB 的 **81%**)有 `Gather`/`Identity`/`Add` 三个消费者。`op_types_to_quantize=["MatMul","Gather"]` 只给 Gather 加一份 26.6MB uint8 副本,**fp32 原表因另两个消费者仍需保留**,文件反而变大(130.7→**157.2MB**;tiny 89.9→109.8MB)。要真省下来得改图让 tied 输出投影也吃 int8 表 —— 那是动 logits 路径,风险收益不对称,**不做**;若日后包体成硬约束,这是一条已定位清楚但需单独一道门的路。
- [x] **R-12(2026-07-26)设备侧首跑 —— 六个 core 模块首次在 arm64-v8a 上端到端跑通,22/22 绿**(`docs/reviews/2026-07-26-android-device-first-run.md`,harness:`app/src/androidTest` + `scripts/push_device_models.sh` + `scripts/run_device_gates.sh`)。方法是**判据一字不改地搬过来,看谁不过**。
  - **R-5 换了模型,没改判据。** int8-transformer 在 arm64 上不变性 0.18323(≤0.18)、最差金标准余弦 0.98297(≥0.985),**两条同时失手**;校准后 accuracy 仍 95.00 与 macOS fp32 逐位相同,坏的是**余量**(到第一个拐点只剩 0.0032,fp32 时代 0.0155)。按本文 §Phase 0 早已写明的 no-go 阶梯退 **fp16**:0.16917 / 0.990–0.997 / 余量 0.0172,**比 macOS fp32 自身的 0.1714 还好**。代价 **+43.9 MiB**(95.8→139.7)与吞吐 21.6–25.2×→12.2–12.8× 实时(两次运行的区间 —— **只有墙钟在抖**,不变性/余弦/成对代价全部逐位复现,所以吞吐给区间而判据给单值;比值稳定 1.8–2.0×,跨运行取数不可比;单句路径 12.7–13.1×,3s 句子 231–234 ms),用户拍板接受。**没有把线放宽到 0.185/0.982** —— 只因量化恰好落得好才成立的阈值不是阈值,而放宽会让此前所有 R-5 数字不再描述任何东西。两个数并排留在 `SslPrecisionProbeDeviceTest` 里,+43.9 MiB 因此是可复核的而非声明的。
  - **阶梯里那个 fp16 兜底本身是坏的,两层。** ①`onnxconverter_common.float16` 产出的图**根本载入不了**(Cast 输出 fp16 而声明 fp32),改用 ORT 自己维护的 `onnxruntime.transformers.float16`;②修好后桌面能载入、**Android 仍拒收**:ORT 的**载入期优化器**把图里 17 个 `Erf` 融成 `com.microsoft.Gelu`,桌面 ORT 有它的 fp16 kernel、**裁剪版移动构建没有**。把 `Erf` 留在 fp32 打断融合模式即可(代价是其余融合一并失去 —— 12.2–12.8× 里有一部分是**这份导出**的账,不是 fp16 的账,如实记)。**"能不能打开"此前和 parity 一起被推迟了,现在导出脚本直接断言它。**
  - **`:core-audio` 两个真实缺陷,只有设备能暴露。** ①`toMono` 取算术平均,而 libswresample 的 `layout=mono` 是能量守恒重矩阵 `(L+R)/√2` —— **每路视频参考音低 3.01 dB**;下游 `frameDb`(相对参考)、`stressPos`(只取位置)、CMVN(逐维归一)恰好全都尺度不变所以分数上几乎不可见(Δcost 0.003),**但尺度不变是当下消费者的性质、不是保证**(Silero VAD 有绝对灵敏度),故电平现在**单独 gate**;②mp4/AAC seek 到 1.000s,首个输出时间戳 1.0217s **在请求点之后**,FR-8 按词回放的起音被削掉 → `PRE_ROLL_S = 0.1`。
  - **三处测量方法返工。** ①整数对齐不够,AAC 的 2112 样本 priming 在 16kHz 上是 **766.2** 个样本,分数残差在 3kHz 上就值 −12 dB —— 第一版把纯时基偏移读成了 10.7 dB 的"解码器失真",加窗 sinc 分数移位后是 47.7–50.3 dB;②Gate E 判据 ① 的 0.995 是**桌面 fp32 编码器**量出来的,搬到量化编码器上等于要求跨解码结果的吻合度高于编码器对自己跨精度的吻合度,改为对**实测噪声底** `controlCos` 判定 —— 不过 fp16 换装把这条结论的适用范围改窄了:换装后判据 ① **直接达标**(0.999803–0.999956 ≫ 0.995),噪声底退为**休眠兜底**,它只在 int8 那次运行里是唯一的通过路径(0.9888–0.9928);③模型校验测试**报了它没测的数**(`Infinity MiB/s` —— marker 跨运行存活,`verifyAll` 直接返回),现在先删 marker 再计时并**结构性断言**,而不是拿时间当代理(第一版 `ms > 1000` 被模拟器的宿主 page cache 当场证伪:424 ms / 2205 MiB/s,**真机冷存储 I/O 仍未知**)。
  - **一个非算法的坑**:六个 core 模块原挂 `androidTestImplementation`(理由是 `:app` 还是空壳),11 个测试在 class-init 全灭于 `dlopen` 找不到 `libonnxruntime4j_jni.so` —— 三个 `.so` 都在,在**错误的 APK** 里:instrumentation 合并 test APK 的 **dex**,**不**以同样方式合并它的 `lib/`。而 R-8 要测的"一个进程同时持有所有 session 的峰值"本就是**应用进程**的性质。已改 `implementation`。
  - **R-8 转 PASS 但范围是部分的**:峰值 PSS 892 MiB(预算 3500)、20 轮增长 67.5 MiB、单轮 624–673 ms(两次运行,中位 640/646);**没测到** espeak 推理、whisper 与 SSL 真正并发、30s 片段 → NFR-4③ 要到 Phase 3 才能真正关门。R-6 设备侧完美(9 个边界逐个相同,最差漂移 0.0248 帧);R-10 四段转写与桌面**逐字相同**、18.1–20.7× 实时。**跑了两次的收获不只是区间**:所有数值(不变性、四个金标准余弦、Gate E 三个余弦与其噪声底、9 个词边界、四段转写文本)**逐位复现**,变化只在墙钟 —— 端侧这条链是确定性的,这一点比任何单次的数字都更值得记。
- [ ] **真机(非模拟器)复测** —— 一台模拟器是一个解码器实现、一份宿主 page cache。留三项:多 OEM 解码一致性(R-9 原遗留)、**冷存储全量校验耗时**(决定 warmup 是否每次启动都校验)、CPU 热降频下的 NFR-3。另:`golden/device/manifest.json` 的 `emb_min_cosine: 0.995` 已补 `emb_cosine_note` 说明析取与噪声底;若日后换回量化编码器,该析取重新变为现役判据,届时应把 `controlCos` 实测值也落进 manifest。
- [ ] R-7 设备侧复测 —— 随 Phase 3 `:core-mdd` 一起做(espeak 至今没在设备上推理过,它同时是 R-8 关门的前提)。
- [ ] **Phase 4 `:app` 外壳(2026-07-27 启动)** —— 原生应用壳。实施计划 `.claude/plans/scalable-brewing-wall.md`。里程碑:
  - **M0**:`:core-scoring` 补**暂停特征提取**。`scoreTrackB` 一直需要 `pausePerS`/`pauseRatio`,但 Kotlin 侧**从未实现过计算** —— JVM parity 测试是从 `golden/pair/*_fluency.json` 读的现成值。补 `audio/PauseFeatures.kt`(RMS→dB,沿用已 bit-exact 移植的 `AudioPreproc` dB 链;Praat `-25dB` 阈值、`0.15s` 最小停顿),落纯 JVM 层 + parity 测试。**只 `pause_ratio` 进流畅度 GAM**(`pause_per_s` 是 API 稳定性预留,`score_b.py:78` 注释)。诚实边界:macOS 用 Praat `to_intensity()`,Android 无 Praat 等价物 → 暂停检测在**真实带停顿音频**上与 macOS 有界分歧,归设备侧流畅度对齐项(同 TarsosDSP 音高缺口);**JVM 金标准集不受影响**(4 条 `say` 合成语料 Praat 实测均 0 停顿,RMS 检测同样为 0,逐位一致)。
  - **M1**:端到端垂直切片 —— 内置 `7.1.mp4`(随包发)→ 选句(直读随包 `sentences.json`,**不跑 Whisper**)→ AudioRecord `UNPROCESSED` 跟读 → `AnalyzePipeline`(SSL+MMS+评分+detail+word_diff,**内置路径无需 Whisper/VAD**)→ Compose 出分屏(逐词 good/weak/bad/missed 着色 + 中文提示 + A/B 回放)。DI 手工 `AppContainer`;模型走 `DirectoryModelSource(filesDir/models)` + adb push(同 R-12 harness)。
  - **M3(先于 M2)**:**Play install-time Asset Pack 投递**(`asset-pack-models/` 模块 + `AssetPackModelSource`)—— **打包链路已验证**:`asset-pack-models` 模块(`com.android.asset-pack`,install-time)把 935 MiB 模型同步进 `src/main/assets`(构建期 syncModels,gitignored),`bundleDebug` 产出 756 MiB AAB,`bundletool build-apks` + `install-apks` 装到模拟器后 **`split_nlg_models.apk` 正确加载、`AssetPackManager.getPackLocation` 找到包、不崩**。**运行期 `assetsPath()` 仍待 Play 轨道验证**:bundletool 本地安装(含 `--local-testing`)下 `getPackLocation` 返回非空但 `assetsPath() == null` —— 模拟器的 Play 服务**不把 install-time 包解包成真实目录**(只有 Play Store 安装才解),所以模型在本地无法以文件路径打开、analyze 跑不通。这正是 `core-models/.../ModelSource.kt:36` 早已标注的"需要 Play Console 才能端到端测"。`AssetPackModelSource` 已对本地安装**优雅降级**(`assetsPath` null → 返回 null → 回退到 `DirectoryModelSource`),故 gate harness / 冒烟测试(adb 推模型)不受影响。**剩余验证**:上 Play internal-test 轨道,确认 `assetsPath()` 非空、warmup 校验 935 MiB、analyze 出分,全程无 adb push。bundletool 在 `NativeLingoAndroid/.tools/`(gitignored)。
  - **M2**:用户导入(FR-M2)—— SAF content URI → 复制 → `TranscriptionService`(Silero VAD + Whisper + MMS 对齐 + SentenceSegmenter,WorkManager 后台)→ 缓存 `*.sentences.json` → 走与内置相同的 analyze。
  - **本轮不做**:FR-11 `:core-mdd`(v1.0 后,P2/自门控)、FR-12 Room(暂缓,P2/无模型依赖)。
- **模型包体(NFR-4②,第四次修正,全部为实测)**:whisper base.en **159.8MB**(int8;R-10 实测,前两版记的 ~70MB 错了 2.3 倍)+ wav2vec2 **139.7MB**(**fp16** —— R-12 把它从 95.8 的 int8-transformer 换掉了,理由见上)+ espeak 302.9MB(int8 全量)+ MMS 338.6MB(int8 transformer-only)+ VAD/tokens = **935 MiB**。whisper 的 160MB 越过 Play base APK 的 150MB 压缩上限,**四个模型统一走安装时 asset pack**(上限 1.5GB,计入安装体积,现余 590 MiB)—— 这样选是因为另外三项 **无论如何都要下载机制**,whisper 搭这趟车的增量成本≈0(这一点上一版低估了,如实修正)。**+43.9 MiB 没有改变分发机制**,这正是那个决定除吞吐外的全部代价。若日后要压:MMS(338.6MB)最大,其次 espeak(302.9MB,惰性加载减 RAM 但不减下载);**whisper 换 `tiny.en` 已由 R-11 量过,省 57MB 但换来 MMS 必须对齐的非词,不作为压缩手段**,只作低端设备的速度降级档(触发条件现有设备数据可定:base.en 18.1–20.7× 实时)。
