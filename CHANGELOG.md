# Changelog

NativeLingo 版本演进与技术特点。

## [v1.2] — 2026-07-19 — 中层编码 + 数据驱动打分校准

在 v1.1 基线上完成路线图最高优先级的两项:**编码器选层**与**打分校准**,并顺手修掉 fluency 重复计算。打分从"手设阈值"变为"在 speechocean762 真人评分上拟合的映射"。

### 变更 1:SSL 编码器末层 → 中层平均(6–9 层)

文献(Pasad et al. 2021 等)一致指出 wav2vec2 的语音学判别信息在中层达到峰值,末层偏向 CTC 目标。自建受控实验(`scripts/layer_comparison.py`,macOS `say` 多嗓音合成)在本任务上实测五种配置:

| 配置 | 跨声同文 cost↓ | 不变性 gap↓ | 错文区分度↑ |
|---|---|---|---|
| 末层(v1.1) | 0.182 | 0.182 | 0.472 |
| 第 5 层(文献 ABX 最优) | 0.313 | 0.313 | 0.539 |
| mean 4–8 / 3–10 | 0.202 / 0.186 | 0.202 / 0.186 | 0.625 / 0.619 |
| **mean 6–9(采用)** | **0.159** | **0.159** | **0.653** |

结论:单层 ABX 最优(第 5 层)在跨说话人场景反而残留最多音色;**6–9 层平均**同时拿到最优说话人不变性(比末层 +13%)与最优错文区分度(比末层 +38%)。`ssl_encoder.py` 新增 `layers` 参数(`None` 恢复末层旧行为)。

### 变更 2:打分映射校准(speechocean762 + isotonic)

v1.x 的 `_lin_map`(0.10→100 / 0.55→0)是手猜的,为 README 自评"最弱环节"。v1.2 用 **speechocean762**(Apache-2.0,5000 条真实 L2 朗读 + 人工 accuracy/fluency 分)拟合:

- 参考音频:数据集无原声,用 macOS `say`(Samantha)按文本合成并缓存(`scripts/build_calibration.py`,1500 条,特征落盘 `data/calibration_features.jsonl`);
- **accuracy**:DTW 平均 cost → 人工 accuracy(0–100)的 **isotonic 回归**;
- **fluency**:[路径偏离, |log 速率比|, 停顿占比] 三个**单调 isotonic 分量**按 PCC² 加权融合(isotonic GAM)。弃用 OLS:多重共线性下系数符号翻转,外推危险(犹豫朗读者反而加分);GAM 逐特征单调,停顿/偏速永不加分;
- 拟合参数随代码分发(`backend/core/calibration.json`,8KB);缺失时回退 v1.1 手工映射(但已去掉 rate 双罚)。

**留出验证集(300 条)对比**:

| 维度 | 旧手工映射 PCC | 新校准映射 PCC | Spearman |
|---|---|---|---|
| accuracy | 0.459 | **0.600** | 0.564 |
| fluency | 0.112 | **0.426** | 0.432 |

端到端实况:同声 95 / 跨声(Daniel)95 / 跨声(Karen)92 / 错词 74.5(与正确拉开 ~20 分)。注意校准分布内只含"按稿朗读",错词属分布外输入,逐词级状态(missed/weak/bad)仍是识别错词的主通道。

### 变更 3:fluency 去除重复计算

删掉 v1.1 的 `rate_penalty`(路径偏离的理想对角线已吸收全局语速,再罚一次属重复计算),语速与停顿改以特征形式进入 GAM 校准映射。

### 当前版本技术特点(完整栈)
- **轨道 B(核心打分)**:`ssl_encoder`(wav2vec2-base-960h,**6–9 层平均**,50Hz)→ `speaker_norm`(CMVN)→ `align`(带状 DTW + 余弦)→ `score_b`(**isotonic 校准** accuracy;**isotonic GAM** fluency:路径偏离/速率/停顿)。
- **校准数据**:speechocean762 真人评分 + `say` 合成参考;`scripts/` 三件套(层对比 / 特征构建 / 拟合)可复现、可重拟合。
- **轨道 A(韵律锚点)**:`prosody`(Parselmouth F0 / 能量 / 停顿 / 语速),停顿特征同时供 fluency 校准。
- **轨道 C(反馈)**:`feedback` 规则引擎 + `word_diff` 逐词韵律 diff;**LLM 不打分**,预留 `llm_hook`。
- **转录与边界**:`transcribe`(faster-whisper)→ `forced_align`(MMS 词边界)→ `detail`(DTW 路径投影,逐句/逐词分数同样走校准映射)。

### 已知限制与未解决问题
- ⚠️ **校准参考为 TTS 合成声**:校准分布 = 真人学习者 vs 合成参考;产品参考为真人原声,分布略有偏移(同族映射,单调性不受影响)。后续可用真实原声重拟合。
- ⚠️ **fluency 校准以语速特征为主导**(GAM 权重 0.65):数据集为单句短朗读,句内停顿信号弱;长句/多句场景停顿分量作用会增强。
- ⚠️ **学习者词回放仍非采样级精确**(前端 timeupdate ~250ms 粒度,见 v1.1)。
- ⚠️ **单参考**:未引入相对 DTW(双参考集)。
- ⚠️ **无音素级诊断**(MDD)。
- 📈 **下一步优先级**:相对 DTW(双参考集)→ 真实原声重校准 → 音素级 MDD。

### 测试
`pytest backend/tests/` —— 7/7 通过(含试金石 `test_speaker_invariance`,校准映射下跨声同文 95 分)。

---

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
