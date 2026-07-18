# Changelog

NativeLingo 版本演进与技术特点。

## [v1.1] — 2026-07-08 — MMS 强制对齐(词边界)

在 v1.0 基线上,把"词边界"从 faster-whisper 的注意力时间戳换成 torchaudio MMS 强制对齐,修好原声词 / 学习者词回放被截断的问题。

### 新增 / 变更
- **`backend/core/forced_align.py`(新)** — torchaudio `MMS_FA`(`ctc_alignment_mling_uroman`,~1.18GB,首次下载到 `~/.cache/torch/hub`)强制对齐封装。`align_words(words, wav) -> [(start,end)|None]`:`model(wav)` 出 emission → `aligner(emission[0], tokenizer(词列表))` → 每词一组 `TokenSpan(token,start,end,score)`,词边界 = 首 `.start` ~ 末 `.end` 帧,秒 = 帧 × ~0.02(~50Hz)。English 无需 uroman。CPU 单例;失败返回 `None` 供调用方回退。
- **参考路径**(`transcribe.py`,`CACHE_VERSION` 2→3):整段视频音频一次 `align_words` 覆盖 Whisper 词时间戳(只换时间戳,文本仍用 Whisper);`_merge_words_into_sentences` 按标点合并。验证(7.1.mp4,636s/105 句):0 个超长词,真实短词不再塌缩(如 "long" 20ms→201ms)。
- **学习者路径**(`pipeline.analyze_detailed`):**把参考文本对齐到学习者音频** → 每个参考词在学习者录音里 1:1 的 (start,end)。读错的词仍映射到"应该读的那个词"(对齐的是预期文本,不是转写说出的内容)。每个词都有回放区间(不再只限被标记词)。小 pad(头 −0.03 / 尾 +0.06,clamp)。旧 `transcribe_waveform`+difflib 降级为 fallback。

### 当前版本技术特点(完整栈)
- **轨道 B(核心打分)**:`ssl_encoder`(wav2vec2-base-960h,50Hz 帧)→ `speaker_norm`(CMVN 去音色)→ `align`(带状 DTW + 余弦)→ `score_b`(路径平均余弦距离→accuracy;路径偏离对角线+语速惩罚→fluency)。
- **轨道 A(韵律锚点)**:`prosody`(Parselmouth F0 / 能量 / 停顿 / 语速)。
- **轨道 C(反馈)**:`feedback` 规则引擎 + `word_diff` 逐词韵律 diff(重音 / 连读 / 时长 / 音高);**LLM 不打分**,预留 `llm_hook`。
- **转录与边界**:`transcribe`(faster-whisper base.en 出文本)→ `forced_align`(MMS 出词边界)→ `detail`(把 DTW 路径投影到边界网格,得逐句 / 逐词 accuracy+fluency 与问题区域)。
- **桌面壳**:Tauri v2 + FastAPI sidecar(绑定 `127.0.0.1` + 每次启动随机 token),全本地 / 离线。

### 已知限制与未解决问题
- 🔴 **打分未校准**:`score_b._lin_map` 的 0.10 / 0.55 阈值为手设,绝对分未必匹配人工判断 → 用 speechocean762 拟合 isotonic 回归替换。
- ⚠️ **学习者词回放仍非采样级精确**:边界已准,但前端 `playMyClip` 用 HTML `currentTime` seek + `timeupdate`(~250ms 粒度);彻底解决需让"我的"词回放走后端切精确 WAV(与原声 `/clip` 同路径)。
- ⚠️ **单参考**:未引入相对 DTW(双参考集),仍受单一原声口音 / 习惯主导。
- ⚠️ **编码器 / 层**:base-960h 默认末层,非发音最优;可选中层或加权多层。
- ⚠️ **fluency 重复计算**:`rate_penalty` 与路径偏离有重叠。
- ⚠️ **无音素级诊断**:有词边界,但无音素替换诊断(MDD)。
- 💾 **体积 / 速度代价**:MMS 模型 ~1.18GB;首次转写 7.1.mp4 ~235s(有缓存,每视频一次)。可上 MPS 提速。

### 测试
`pytest backend/tests/` —— 7/7 通过。

---

## [v1.0] — 2026-07-04 — 基线

初始版本。三轨道架构(SSL+DTW 核心 + 韵律 + 规则反馈)、Tauri v2 桌面壳、视频跟读 UX、faster-whisper 句 / 词分割(注意力时间戳)。`test_speaker_invariance`(两个不同嗓音读同一句正确文本必须仍得高分)作为逆向思路(音色被成功剔除)的试金石。
