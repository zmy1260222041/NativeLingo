# Changelog

NativeLingo 版本演进与技术特点。

## [v1.5] — 2026-07-25 — 首个可分发版(macOS .dmg)

把后端从"开发态 venv"固化为**可分发 `.dmg`**:PyInstaller `--onedir` 冻结 Python 后端(torch/torchaudio/transformers/faster-whisper 全栈)→ 作为 Tauri 资源打包 → ad-hoc 签名 → ULFO 压缩 dmg(**383MB**)。收尾 NFR-2「后端冻结为 sidecar 二进制」工程债。

### 方案
- **`backend/freeze.spec`**:`--onedir`(torch dylib 需目录形态);`collect_all` 覆盖 torch/torchaudio/transformers/faster_whisper/ctranslate2/sklearn/numba/llvmlite;排除 datasets/pyarrow(脚本依赖);**onnxruntime 必留**(faster-whisper VAD 依赖,误排会让转写报 "Applying the VAD filter requires the onnxruntime package");`calibration.json` 显式入 `datas`。
- **`requirements-runtime.txt`**:运行时依赖子集(与含校准脚本的 `requirements.txt` 分离),配合干净 `.venv-freeze` 冻结。
- **`src-tauri/src/main.rs`**:`spawn_backend` 加 bundled 分支——启动 `Resources/resources/nativeLingoBackend/nativeLingoBackend`,注入 `PATH`(给随包 ffmpeg)、`NATIVELINGO_DATA_DIR`(用户数据目录)、stdout/stderr 重定向到日志文件。dev 分支不变。
- **`backend/core/video.py`**:改用 **PyAV(`av`)** 解码视频/音频(取代 ffmpeg CLI 子进程);`videos_dir` 支持 `NATIVELINGO_DATA_DIR` env(冻结后 `__file__` 失效;dev 向后兼容)。`av` 随 faster-whisper 已在冻结包内 → 干净 Mac 无需额外 ffmpeg 二进制(亦避开 GPL 许可)。
- **`scripts/build_dmg.sh`**:A 冻结 → B 暂存 + strip → C `tauri build --bundles app` → D ad-hoc(或 Developer ID)签名 → E hdiutil ULFO dmg → F 可选公证装订。

### spike 发现并修复的冻结缺口
1. librosa 依赖 sklearn(误排除 → 音频解码全挂)。
2. `calibration.json` 源码相对加载,PyInstaller 不收 `.json`(→ 静默回退手工映射);已加 `datas`。
3. videos/ 目录冻结后 `__file__` 失效(→ `/videos` 空);加 `NATIVELINGO_DATA_DIR` env。
4. Tauri 保留 glob 的 `resources/` 前缀 → 后端实际在 `Resources/resources/nativeLingoBackend/`(对齐 main.rs 路径)。

### 打包要点(固化进 build_dmg.sh)
- **体积**:干净 venv(砍 datasets/pyarrow 泄漏)+ ULFO(LZMA)压缩 + **仅 `.app` 的干净 staging 成像**(Tauri 残留的 `rw.*.dmg` 会让源目录虚胖 3x)→ **413MB**(onnxruntime 63M 必留:faster-whisper VAD 依赖)。
- **不用 strip**:曾用 `strip -x` 省 ~13M,但它破坏部分 `.dylib` 签名("Invalid Page"),干净 Mac(无系统副本可 dlopen 回退)启动即崩——已移除。
- **签名**:逐文件 ad-hoc 重签(`codesign --deep` 漏签 PyInstaller 深层 `.so`/`.dylib` → arm64 无日志崩溃)。
- **PyAV 取代 ffmpeg**:`video.py` 用已捆绑的 `av` 解码,无需额外 ffmpeg 二进制。

### 干净 Mac 验证(模拟)
以干净 Mac 默认 `PATH=/usr/bin:/bin:/usr/sbin:/sbin`(无 ffmpeg)启动打包后端:`/health` 200、`/videos` 列出视频、`/analyze_video` accuracy 86.5 / 6 词 6 学习者区间——**完整视频跟读流程在无 ffmpeg CLI、无系统库回退下跑通**。

### 验证
启动 `.app` → 壳拉起冻结后端 → `/health` ok、`/analyze` accuracy 95.0(试金石跨嗓音同文)。`pytest` 12/12 不变(纯打包,未改评分逻辑)。

### 已知限制
- **冷启动 ~1-3 分钟(每次启动)**:numba/torch/transformers 冻结态导入 + 模型加载;前端轮询 `/health` 并显示"后端启动中"(等待上限 240s)。后续可惰性加载优化。
- **arm64-only**:Intel Mac 需另冻结 + 通用二进制(未做)。
- **模型首运下载**(~1.7GB,之后离线);未预打包(NFR-1)。
- **未公证**:GitHub 发布足以(用户首次右键绕过 Gatekeeper);公证($99/yr Developer ID)为可选项。

---

## [v1.4] — 2026-07-23 — 音素级替换诊断(FR-11,MDD 轨)

反馈从"这个词的重音/时长不对"下探到"这个**音**读错了":对 weak/bad 词给出"/θ/ 读成了 /s/"式替换诊断。

### 方案:假设打分式 MDD(`backend/core/phoneme.py`)
- **模型**:`facebook/wav2vec2-lv-60-espeak-cv-ft`(IPA 音素 CTC)。手读 `vocab.json` 做 id↔IPA 映射 + 手写 CTC 折叠,**避开 phonemizer/espeak-ng 系统依赖**(分发友好)。
- **不用学习者解码**:CTC 对 ~0.3s 孤立词解码噪声极大(实测 θ/s/ʃ 起音频繁丢失,补零上下文无效——纯零是分布外)。改为:**解码参考音**定 canonical(原声清晰、且天然携带主播本人的读音,贴合跟读场景)→ 对学习者 emission 做 **Viterbi 强制对齐打分** → 枚举单音素替换/删除变体,增益超阈(margin=0.15/帧)才采信。
- **自验证门控(宁缺毋滥)**:同一扫描先在参考音自身 emission 上跑——若 canonical 连参考音都拟合不过,说明解码本身坏了,该词**静默跳过**,不出错误诊断。实测:canonical 正确时诊断准确(think→sink 精确锁定 /θ/,增益 +0.33),负样本(同一音频)增益全部 ≤ +0.04,门控干净分离。
- **集成**:`pipeline.analyze_detailed` 对 weak/bad 词调用,诊断**前置**到现有 prosody tip;常见混淆对(θ/s、ð/z、ɪ/i、æ/e、v/w、l/r…)附发音部位指导。
- **上下文**:词切片带 ±0.25s 真实音频上下文(CTC 需要连续语音语境;生产环境天然满足)。

### 测试
`test_phoneme.py`:think→sink 必须点名 /θ/;同音频负样本必须静默;坏 canonical(fan)不得出伪诊断。**12/12 全量通过**。

### 已知限制
- 参考解码质量是上限:对 `say` 合成的个别词(thin/fan)解码失败 → 门控静默(漏诊);对真人原声预期更好。
- 近亲音对(ɪ/iː、æ/ɛ)区分力弱(gain < margin,漏诊)——精度优先于召回的设计取舍。
- 音素模型 ~315MB,首次按需下载;仅对 weak/bad 词运行,分析耗时可忽略。

---

## [v1.3] — 2026-07-23 — 新闻域验证 + 长句二级切分 + 采样级"我的"回放

按 `docs/PRD.md` 推进的三件事:新闻域技术链全面验证(FR-M2 解锁)、长句二级切分(FR-M3)、学习者回放采样级精确(FR-8 收尾)。

### 1. 新闻域验证(详见 `docs/reviews/2026-07-23-news-domain-verification.md`)
在真实播报素材(7.1.mp4,CBS News)上验证四项:**whisper base.en 够用**(与 small.en 文本一致 98.3%,零低置信段);**MMS 对齐鲁棒**(1944 词,重对齐边界差中位 10ms,塌缩词均为真实短功能词);**长句占比 43%** → 触发二级切分;**端到端评分正常**(异嗓音学习者 89.1/88.1,零误报)。

### 2. 长句二级切分(FR-M3,`transcribe.py` CACHE_VERSION 3→4)
新闻长句(>8s 或 >20 词)在从句边界递归二分:优先逗号/分号/冒号,其次连词(and/but/because/which...),取离中点最近且两侧 ≥4 词的切点。CBS 素材 105 → 164 句,中位 4.12s→3.50s,最长 22s→7.66s,残余超长仅 3 句。切点经人工抽查落在自然从句边界。

### 3. 学习者回放采样级精确(FR-8)
- 后端新增 `POST /recordings`(录音解码为 16kHz WAV 存临时目录,返回 id)与 `GET /recordings/{id}/clip?start&end`(精确切 WAV,与原声 `/videos/{n}/clip` 同机制;id 限 uuid-hex 防遍历)。
- 前端录音停止后自动上传;`playMyClip` 改为播放后端精确 WAV(未就绪时回退原 blob seek)。消除 HTML `timeupdate` ~250ms 粒度导致的词尾截断。
- 测试:`test_recordings_api.py` 验证 1s 切片恰好 16000 采样、内容逐采样一致;**9/9 通过**。

### 已知限制与未解决问题
- ⚠️ **超长选段 MPS OOM**:wav2vec2 编码 ~7 分钟连续选段注意力分配 8.65GiB 触发上限(正常使用≤数句不受影响)→ 分块滑窗编码(P2)。
- ⚠️ **无音素级诊断**(MDD,FR-11,进行中)。
- 💾 MMS 模型 ~1.18GB;首次转写每视频一次(有缓存)。

---

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
