# NativeLingo 产品需求文档(PRD)

> 版本:v0.1(2026-07-25)
> 状态:已生效。此后所有技术迭代必须能追溯到本文档的需求条目(见 §6 追踪矩阵);新需求先落本文档,再排技术方案。
>
> **v0.1 变更(2026-07-25)**:平台扩为 macOS + Android(NFR-2 重写);新增 NFR-4(Android 移动端约束);FR-12 学习记录转 in-scope 并写验收。Android 迁移方案见 `docs/android-migration.md`,Phase-0 符合性评审计划 R-5..R-9 见 §7。

## 1. 背景与愿景

英语口语学习者缺少"知道自己哪里读得不对、怎么改"的反馈手段。NativeLingo 是一个 macOS 桌面应用:学习者跟读一段**真实英语原声素材**,软件对比原声与学习者录音,给出**发音准确度**与**流畅度**评分,定位到句/词,并给出可执行的朗读改进方向。

技术差异化:复用语音克隆赖以成立的解耦潜空间(SSL 语音表示),逆向做评估——剔除音色因子,只测内容与韵律偏差。LLM 不打分,只生成反馈。

## 2. 目标用户与核心场景

- **用户**:中高级英语学习者(备考雅思/托福、职场英语、口音改善),自学场景。
- **核心场景**:用户想练"地道的新闻英语"→ 打开素材库选一段 BBC 类新闻播报 → 听原声、看字幕 → 按句/段跟读录音 → 立即看到分数、问题词、每个问题词的改法 → A/B 对比回放原声与自己的读法 → 重练。

## 3. 素材需求(本版新增确认)

**FR-M1(P0)跟读素材来源:网络真实视频,以新闻播报(BBC 类)为标杆品类。**
- 参考音频一律来自真实说话人的网络视频(新闻播报、访谈、演讲等),**不使用合成音作为产品参考音**。
- 验收:应用内可选的每条素材都是真实人声视频;音频由应用自行从视频中提取(ffmpeg)。
- 含义:评分、对齐、校准等所有技术环节面对的"参考音"分布 = 真实广播人声(演播室音质、播报语速、正式新闻腔、偶有背景音乐/现场声),任何技术假设都必须对该分布成立。

**FR-M2(P1)素材获取方式。**
- 当前(v0.x):用户自备视频文件放入 `videos/` 目录。
- 目标:应用内素材库(预置精选新闻片段 + 用户导入),含来源/时长/难度等元信息。
- 约束:版权——新闻视频有版权,分发形态只能是"用户自行获取素材"或链接指引,应用不得内置受版权保护的成片(见 §5 风险)。

**FR-M3(P1)素材难度适配。**
- 新闻播报语速快、句子长、连读多。需要:句子级切分粒度适合跟读(已实现,标点合并);语速信息展示;长句可再细分(**已实现 v4**:>8s 或 >20 词的句子在从句边界自动二级切分,CBS 素材残余超长句仅 3/164)。

## 4. 功能性需求

| 编号 | 优先级 | 需求 | 验收标准 | 状态 @v0.2 |
|---|---|---|---|---|
| FR-1 | P0 | 视频素材选择与浏览 | 列出 `videos/` 内视频,可选中、可流式播放定位到句 | ✅ 已实现 |
| FR-2 | P0 | 视频自动转写与句子/词切分 | faster-whisper 转写 + MMS 强制对齐词边界;缓存可复用 | ✅ 已实现 |
| FR-3 | P0 | 跟读录音 | 选定句范围(可单句),播放无声视频+字幕供跟读,麦克风录音 | ✅ 已实现 |
| FR-4 | P0 | 发音准确度评分(0–100) | 对真人原声参考稳定;不同嗓音读同一正确文本仍得高分(说话人不变性 ≥70,试金石测试) | ✅ 已实现,校准后(见 NFR-Q1) |
| FR-5 | P0 | 流畅度评分(0–100) | 与人工流畅度判断相关;停顿多/偏速不得加分 | ✅ 已实现(单调 GAM 校准) |
| FR-6 | P0 | 句级/词级问题定位 | 每句 accuracy/fluency;每词 good/weak/bad/missed 状态 | ✅ 已实现 |
| FR-7 | P0 | **单词级朗读改进方向** | 每个问题词给出具体改法(重音位置/时长/音高走向/连读),中文、可执行 | ✅ 已实现(规则引擎) |
| FR-8 | P0 | 原声/学习者 A/B 回放 | 任意词、任意句可分别回放原声与自己的录音,**双方均为采样级精确** | ✅ 已实现(v0.3:学习者回放改走后端切 WAV,与原声同机制) |
| FR-9 | P1 | 教学反馈总结 | 整体档位 + 针对性练习建议;LLM 仅措辞不打分 | ✅ 规则版已实现;LLM hook 预留 |
| FR-10 | P1 | 反复练习闭环 | 同一素材可重复跟读、重看结果 | ✅ 已实现 |
| FR-11 | P2 | 音素级诊断 | 能指出"/θ/ 发成了 /s/"级别的替换诊断;宁缺毋滥(不确定时静默) | ✅ 已实现(假设打分式 MDD + 自验证门控,见 CHANGELOG v0.4) |
| FR-12 | P2 | 学习记录/进度 | 本地存储历史成绩(按素材/句),可看进步曲线;纯端侧,无云 | 🚧 待实现(Android 版起 in-scope,见 `docs/android-migration.md`) |

## 5. 非功能性需求与约束

- **NFR-1 全本地/离线/隐私**:所有模型本地运行,录音不出设备;sidecar 绑定 127.0.0.1 + 随机 token。
- **NFR-2 平台**:双平台 —— macOS 桌面(Tauri v2,Python sidecar 冻结为二进制)+ **Android 移动端(原生 Kotlin + Jetpack Compose,全端侧推理)**。Android 不复用 Python 后端(PyInstaller/torch 栈在 Android 不可行),改为 4 个模型用 ONNX Runtime Mobile / sherpa-onnx int8 重写实现;迁移方案见 `docs/android-migration.md`。两端共享评分契约与 `calibration.json`/音素表,**macOS 版作为 Android 数值对齐的金标准源**。
- **NFR-4(Android 移动端约束)**:① 最低 Android 9(API 28+),arm64-v8a;② 全端侧推理,模型 int8 量化后总量 ~460MB(whisper base.en 打包进 APK,余 wav2vec2-base / MMS / espeak-cv-ft 首启后台下载,流程同 macOS `/warmup`);③ 设备 RAM:6GB 设备须能无 OOM 跑完整 `analyze`(espeak-cv-ft 惰性加载、句间释放 session);④ 麦克风权限 `RECORD_AUDIO`,采集用 `AudioSource.UNPROCESSED`(免 AGC/降噪染色,保评分保真);⑤ 数值对齐:Android 端评分须与 macOS 同语料在容差内一致(accuracy ±2.0 / fluency ±3.0 / DTW cost ±0.02),由 R-5 把关。
- **NFR-3 性能**:单句分析秒级出结果;视频首次转写可后台进行并缓存。
- **NFR-Q1 评分质量指标**:校准映射留出验证 PCC — accuracy ≥ 0.55(当前 0.60),fluency ≥ 0.40(当前 0.43);说话人不变性测试必须通过。**且校准必须对 FR-M1 的真实人声参考成立**(R-1 已实测验证:真人参考下分数不降反略升;新参考音品类须用 `scripts/ref_swap_experiment.py` 复验)。
- **已知限制**:MMS 模型体积 1.18GB;首次转写慢(有缓存);超长连续选段(>5 分钟)wav2vec2 编码在 MPS 上有内存风险(P2,待分块编码)。
- **风险**:素材版权(BBC 等)——产品形态必须停留在"用户自备素材",不得分发成片;技术调研不得引入需联网调用的评分服务(违反 NFR-1)。

## 6. 需求-技术追踪矩阵

| 需求 | 技术实现 | 符合性 |
|---|---|---|
| FR-M1 真实视频素材 | `video.py`(ffmpeg 提取)+ `transcribe.py` + `forced_align.py` | ✅ |
| FR-4/5 评分 | Track B:SSL(6–9 层)+ CMVN + DTW + isotonic 校准 | ✅ 实测迁移性通过(§7 R-1:真人参考下分数不降反略升) |
| FR-6 定位 | DTW 路径投影到 MMS 词网格(`detail.py`) | ✅ |
| FR-7 词级改进方向 | `word_diff.py`(能量/音高/间隙声学对比 + 规则措辞) | ✅ |
| FR-11 音素诊断 | `phoneme.py`:参考解码定 canonical → 学习者 emission 强制对齐打分 → 替换/删除假设竞争 | ✅(v0.4) |
| FR-8 A/B 回放 | `/clip` 原声采样级;学习者回放走 `/recordings/{id}/clip` 后端切 WAV(v0.3) | ✅ |
| FR-9 反馈 | `feedback.py` 规则引擎 + `llm_hook` 预留 | ✅ |
| 单参考依赖 | 当前每条素材仅其视频原声一条参考 | ⚠️ Richter 式相对 DTW 与 FR-M1 冲突 → 见 §7 R-2 |

> **Android 平台映射**:同一张表的需求在 Android 上由对应 Kotlin Gradle 模块满足 —— FR-4/5 → `:core-scoring`,FR-2 → `:core-asr` + `:core-align`,FR-11 → `:core-mdd`,FR-8 → `:app` RecordingsRepository + Media3,FR-12 → `:app` Room。完整需求→模块矩阵见 `docs/android-migration.md`。
>
> **Android 侧实现状态(2026-07-25)**:**FR-4 / FR-5 / FR-6 / FR-7 / FR-9 的评分层已在 `:core-scoring` 移植完毕**,以 macOS 抓取的金标准 fixture 在 JVM 断言(21/21 绿):分数走 NFR-4⑤ 容差(accuracy ±2.0 / fluency ±3.0 / cost ±0.02),而问题区间边界、词级标签与中文提示串**逐字精确断言** —— 学习者是照着提示念的,"差不多"在这里不构成验收。唯一保留的等价性缺口是 FR-7 的音高提示(Praat vs TarsosDSP YIN 无逐位等价),已隔离为可注入的 `PitchEstimator`,留待设备侧验证。FR-2 / FR-8 / FR-10 / FR-11 / FR-12 待 Phase 2–4。

## 7. 技术符合性评审记录

- **R-1(2026-07-22)v0.2 校准使用合成声参考 vs FR-M1** → `docs/reviews/2026-07-22-calibration-ref-fit.md`。结论:**符合,无需校正**——三组实测(LibriSpeech 350 对 / CBS 新闻 62 对 / CMU ARCTIC 母语+L2 置换)表明真人参考下校准分数不降反略升(+0.8~1.9),低分尾更窄;fluency 特征为参考相对量,天然免疫。新参考音品类引入时用 `scripts/ref_swap_experiment.py` 抽查。
- **R-2(2026-07-22)相对 DTW 参考集 vs FR-M1** → 同上文档。结论:经典相对 DTW 与"任意网络视频"需求冲突,降级;以"多 TTS 声平均"作为符合需求的替代方向。
- **R-3(2026-07-23)新闻域技术链验证** → `docs/reviews/2026-07-23-news-domain-verification.md`。结论:**4 项全过,FR-M2 解锁**:whisper base.en 够用(跨模型一致 98.3%)、MMS 对齐鲁棒(边界一致 ~10ms)、长句二级切分已落地(FR-M3)、端到端评分行为正常(89/88,零误报)。新发现:长选段 MPS OOM 风险(P2,待修)。
- **R-4(2026-07-23)音素级 MDD 假设打分式方案 vs FR-11「宁缺毋滥」** → `docs/reviews/2026-07-23-mdd-phoneme-fit.md`。结论:**符合 FR-11**——三重门控(仅 weak/bad 词 + canonical 自验证 gate≤0.05 + 替换增益 margin=0.15)结构性保证精度优先:负样本增益 ≤+0.036、坏 canonical 被门控静默、good 词永不触发;think→sink 增益 +0.332 精准定位 /θ/。召回受参考解码质量上限约束(已知取舍:近亲音对、归因 delete/substitute 偶偏),不违反精度优先验收。
- **R-5..R-9(计划中,Android Phase-0 spike)**:Android 端侧迁移的 5 个 go/no-go 符合性评审,门控判据与降级方案见 `docs/android-migration.md` §Phase 0:
  - **R-5**(Gate A)端侧 int8 评分 vs NFR-1(离线)+ NFR-Q1(质量)+ FR-4/5 —— **项目存在性证明**。✅ **Python 侧已过(2026-07-25)**:int8 仅 transformer(CNN 留 fp32,95MB)守住说话人不变性(cost 0.1773 ≤ 0.18,acc 95.0);全量 int8 失效。SSL 编码器据此策略,fp16 兜底。详见 `docs/reviews/2026-07-25-android-gate-a-onnx-int8.md`;设备侧复测待 Tier 2/3。
  - **R-6**(Gate B)手写 CTC Viterbi 对齐精度 vs FR-2 / FR-8(每词边界 ≤1 帧/20ms)。✅ **算法侧已过(2026-07-25,JVM)**:`CtcViterbi.kt` 复现 torchaudio 每字符边界 ±1 帧。emission int8 导出受阻于 torchaudio 图怪癖,Phase 2 用 HF 侧载重解(CTC 鲁棒,espeak 已证 int8 可过)。
  - **R-7**(Gate C)音素 MDD int8 门控 vs FR-11「宁缺毋滥」(自拟合增益阈值 int8 下复验)。✅ **模型保真已过(2026-07-25)**:espeak int8(303MB)CTC 贪解串精确、余弦 0.9946;完整 think→sink 诊断待真实误读语料(Phase 3)。详见 `docs/reviews/2026-07-25-android-gate-bc-onnx.md`。
  - **R-8**(Gate D)6GB 设备 RAM 预算 vs NFR-4③(峰值 RSS <3.5GB,20 连续无 OOM)。
  - **R-9**(Gate E)WebM/Opus 解码保真 vs FR-3(经 FFmpeg-NDK 解码样本误差 ≤1 LSB)。
