# Android 端完整迁移方案

> 版本:v0.1(2026-07-25)
> 关联 PRD:`docs/PRD.md` v0.1(NFR-2 双平台、NFR-4 移动端约束、FR-12 in-scope、§7 R-5..R-9)
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
| 视频解码(PyAV) | ffmpeg lib | **FFmpeg NDK 源码构建** |
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
| FR-M1 真实视频素材 | FFmpeg 解码,不用合成参考音 | core-audio |
| FR-M2 素材获取 | videos 目录 + 用户导入(Android 走 SAF/content URI) | `:app` |
| FR-M3 难度适配 | whisper 句切分 + >8s / >20 词从句边界二级切分 | core-asr |
| **NFR-1 本地/离线/隐私** | 全端侧推理,录音不出设备,RECORD_AUDIO;无任何云调用 | Gate A/R-5 保证 |
| **NFR-2 平台** | macOS + Android(原生 Kotlin) | — |
| NFR-3 性能 | 单句分析秒级(设备实测);转写后台+缓存 | 设备验证 |
| NFR-4 移动端约束 | API 28+ / arm64 / RAM / 包体 / UNPROCESSED / 数值对齐 | Gate D/R-8 等 |
| NFR-Q1 评分质量 | `calibration.json` 原样;PCC 0.60/0.43 保持;说话人不变性 | Layer2 验证 |

## 4. 已验证的运行时选型(每项一个,含 5 个重塑假设的发现)

| 决策 | 选型 | 关键依据 / 发现 |
|---|---|---|
| Whisper 转写+VAD | **sherpa-onnx Android AAR**(`OfflineRecognizer` + Silero VAD) | 预编译 AAR、JNI 已通、arm64-v8a/armeabi-v7a 二进制俱全。**发现⑤**:Whisper 词时间戳不可靠(`forced_align.py` 注释明示会切尾/塌缩短词)→ Whisper 仅出**转写文本 + VAD**,词边界一律走 MMS 对齐,与 macOS 同构 |
| 强制对齐(MMS CTC) | **ONNX Mobile + 手写 Kotlin CTC Viterbi** | **发现①**:sherpa-onnx **不提供**强制对齐(Issue #3536 仍 open,无 PR)。torchaudio 的 `get_aligner()` 是教科书级 CTC Viterbi(~100 行),算法已逐行捕获(见 §5) |
| SSL 编码器(wav2vec2-base-960h, 6–9 层) | **ONNX Mobile,自定义导出 4 个 hidden-state 输出节点** | **发现④**:`output_hidden_states=True` 不会让 Optimum 默认导出中间层 → 必须 Optimum 导出后用 `onnx` 库把第 6–9 个 transformer block 的残差 `Add` 输出节点标为 graph output 再导出 |
| 音素 MDD(espeak-cv-ft) | **ONNX Mobile,动态 int8(318MB),惰性加载** | **发现③**:PyTorch ckpt ~2.4GB,但 `onnx-community/wav2vec2-lv-60-espeak-cv-ft-ONNX` 动态 int8 = **318MB**(fp32 1.26GB)。可载入 6GB 手机但 RAM 紧张 → 按词批惰性加载、句间释放 session |
| 视频/WebM/Opus 解码 | **FFmpeg NDK 源码构建 + 薄 JNI**;视频帧仍走 MediaCodec 硬解 | **发现②**:**ffmpeg-kit 已退役**(2025-01-06,二进制下架,不兼容 Android 16KB 页大小)。MediaCodec 对 WebM/Opus 覆盖不全 |
| F0/音高/能量 | **TarsosDSP(st-h fork 2.4.1)** 纯 Java YIN | 仅用于 word_diff 音高斜率提示(低风险);强度/停顿用自写 RMS |
| 重采样 | **AudioRecord 原生 16kHz 采集(免重采样)**;视频音轨走 FFmpeg `aresample` | 录音路径直接 16kHz,无需 librosa/soxr |
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
| `audio_io.py` | `:core-audio/.../{WavIo,Trim}.kt` | Kotlin + FFmpeg JNI | 中 |
| `transcribe.py` | `:core-asr/.../WhisperTranscriber.kt` | sherpa-onnx | 中(输出格式对齐) |
| `ssl_encoder.py` | `:core-embed/.../Wav2Vec2Encoder.kt` | ONNX Mobile(4 输出图) | 中–高(发现④ 图编辑) |
| **`forced_align.py`** | `:core-align/.../ForcedAligner.kt` + `CtcViterbi.kt` | ONNX Mobile + 手写 Viterbi | **高**(最难单点) |
| **`phoneme.py`** | `:core-mdd/.../PhonemeMdd.kt`(复用 `CtcViterbi`) | ONNX Mobile(int8 318MB,惰性) | **高**(最重模型) |
| `pipeline.py` | `:app/.../AnalyzePipeline.kt` | Kotlin 协程编排 | 低 |
| `video.py`/`warmup.py`/`main.py` | `:app/.../repo/{Video,Recordings}Repository.kt`,`Warmup.kt`,无 server | Kotlin + Media3 + FFmpeg | 中 |

## 7. Phase 0 — 风险 spike 门(go/no-go,先过完才动其他)

仿 macOS freeze-spike 门模式。5 个 make-or-break 风险,按序验证(每门即一份 fit-review,落 `docs/reviews/`,延续 R-1..R-4 编号):

- **R-5 / Gate A —— int8 下数值评分对齐(最高风险,项目存在性证明):** 导出 wav2vec2-base(6–9 层)+ int8 → Android ONNX,同一对 ref/learner 走 macOS PyTorch 与 Android,**accuracy ±2.0 / fluency ±3.0 / DTW cost ±0.02**,跨嗓音 `test_speaker_invariance` cost ≤0.18。**No-go 兜底:** int8 若破坏说话人不变性 → 退 **fp16**(~190MB);再不行 → 端侧全功能前提失败,须战略回桌。
- **R-6 / Gate B —— Viterbi 正确性:** 手写 `CtcViterbi.kt`,同一 MMS emission 走 torchaudio 与 Kotlin,每词 `[start,end]` 误差 ≤1 帧(20ms)。
- **R-7 / Gate C —— 音素 MDD 自拟合门控 int8 下仍成立:** espeak int8(318MB)重跑 think/sink 套件,canonical 自拟合 ≤0.04、垃圾 ≥0.09;若 int8 压缩增益域致误过门 → 设备上重调 `0.05`/`0.15`(数据在 `backend/tests/`)或退 fp16(635MB)。
- **R-8 / Gate D —— 6GB 设备 RAM 预算:** Pixel 4a 级设备全流程 `analyze` 30s 片段,峰值 RSS <3.5GB、20 连续无 OOM。兜底:espeak 按词批惰性 `OrtSession.close()`;仍紧 → MDD 按 `ActivityManager.MemoryInfo` 在低内存设备降级。
- **R-9 / Gate E —— Opus 解码对齐:** WebM/Opus blob 经 FFmpeg-NDK 解码 vs macOS `ffmpeg -ar 16000 -ac 1 -f f32le`,样本误差 ≤1 LSB。

**Gate A+B 是生死对。A 连 fp16 都失败 → "端侧全功能"不可达,须在投入更多前降级到"准确度/流畅度/word-diff、不含音素 MDD"。**

## 8. 工程 / 模块结构(Gradle 多模块)

硬规则:**一切影响校准分数的代码在 `:core-scoring`,零 Android 依赖**,可在 JVM 用 macOS 金标准文件单测。

```
NativeLingoAndroid/
├── app/                    :app — Compose UI / ViewModel / DI / AudioRecord / Media3 / Warmup / Repo
├── core-scoring/           :core-scoring — 纯 JVM(DTW/CMVN/Score/Detail/WordDiff/Feedback/CtcViterbi)+ 金标准测试
├── core-embed/             :core-embed — ONNX wav2vec2-base(4 输出图)
├── core-align/             :core-align — ONNX MMS CTC + ForcedAligner(用 core-scoring 的 CtcViterbi)
├── core-mdd/               :core-mdd — ONNX espeak-cv-ft int8 + PhonemeMdd
├── core-asr/               :core-asr — sherpa-onnx Whisper + Silero VAD
├── core-audio/             :core-audio — WavIo / Trim / FFmpeg JNI bridge
├── core-models/            :core-models — ModelRegistry(whisper 打包进 APK;余下首启下载)
└── buildSrc/               NDK FFmpeg 构建 + 约定插件
```

模块不变量:`:core-scoring` 只依赖 Kotlin stdlib;`:core-embed/align/mdd/asr` 依赖 `:core-scoring`(共用 `CtcViterbi`)+ `onnxruntime-android`;`:app` 依赖全部。

## 9. 分阶段交付(全功能目标,按风险排序;单人工程师估)

| 阶段 | 内容 | 估时 |
|---|---|---|
| **0** | spike 门 A–E(R-5..R-9),逐项 go/no-go | 3–4 周(**未过不进下阶段**) |
| **1** | `:core-scoring` + 金标准测试框架(JVM,过 Layer1+2) | 3–4 周 |
| **2** | `:core-embed/asr/audio/align` 接 ONNX/sherpa/FFmpeg,设备端跑通 | 4–5 周 |
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

**机械的(大部分 LOC):** `align/speaker_norm/score/detail/feedback` 直移(~30% 工);`audio_io/pipeline/UI/HTTP→进程内`(~30%,中风险在 FFmpeg JNI 与 AudioRecord OEM 怪癖)。

**真难的:** ① CTC Viterbi(~100 行,forced_align 与 MDD 共用,一个 off-by-one 全毁,Gate B/R-6 捕);② wav2vec2 hidden-state 自定义图导出(R-5/Gate A,1–3 天 Python+验证);③ **int8 评分保真(项目存在性证明,R-5/Gate A,1–2 周)**;④ 318MB espeak 在 6GB 手机(R-8/Gate D,~1 周);⑤ AudioRecord OEM 一致性(用 `UNPROCESSED`,API≥25,3–5 设备调音,~3 天)。

**降级候选(仅当对应 Gate 失败时触发,不违背"全功能"初衷):**
1. **音素 MDD(FR-11)** —— R-7/R-8 失败时,仅 `ActivityManager.lowMemory==true` 设备降级(其余仍全功能)。MDD 本就门控在 weak/bad 词后、`return ""` 静默降级,切口干净。
2. **espeak 退 fp16(635MB)** —— R-7 失败时,首 MDD 延迟 +~6s,可接受。
3. **学习记录(FR-12)** —— Room 本地存储,无模型依赖,永不降级。
4. **Whisper 档位** —— base 太慢则 APK 内置 `tiny.en`,base.en 作下载项。

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
- [ ] Phase 1 余项:校准映射(cost→accuracy/fluency,对齐 95.0/74.5)、detail 投影、word_diff、feedback。
- [ ] **R-5 / Gate A on-device spike**(需 Android SDK + Optimum 导出 wav2vec2-base 6–9 层 int8 → 设备跑说话人不变性;JVM 已证算法可移植,此步验 int8 保真)。
