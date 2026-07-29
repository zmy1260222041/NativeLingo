# NativeLingo 产品需求文档(PRD)

> 版本:v0.6(2026-07-29)
> 状态:已生效。此后所有技术迭代必须能追溯到本文档的需求条目(见 §6 追踪矩阵);新需求先落本文档,再排技术方案。
>
> **v0.6 变更(2026-07-29)**:新增 **Memorizing 模块** —— 看图识物(FR-13 整件识别+定位 / FR-14 部件级微观)+ 情景例句记忆强化(FR-15,纯文字、与 Speaking 评分分离、**不触 FR-M1**)+ 双模块信息架构 Speaking/Memorizing(FR-16)。智能层全端侧、无云无密钥(NFR-5,延续 NFR-1/FR-12);模型选型「最小可行」:YOLOv8n-onnx 做宏观整件检测(带 box 热点)+ Qwen2.5-VL-3B 做部件微观命名 + Qwen2.5-Instruct(≤1.5B)做情景例句。同步全 App 视觉升级为 Duolingo 风高级感(NFR-UX)。识物质量为最大不确定性,以 R-13 数字门控。新增评审记录 R-13。
>
> **v0.1 变更(2026-07-25)**:平台扩为 macOS + Android(NFR-2 重写);新增 NFR-4(Android 移动端约束);FR-12 学习记录转 in-scope 并写验收。Android 迁移方案见 `docs/android-migration.md`,Phase-0 符合性评审计划 R-5..R-9 见 §7。
>
> **v0.2 变更(2026-07-26)**:落地四项 Android 决策 —— FR-M2 Android 导入面去掉 `.avi`(R-9,平台对 AVI 无保证);FR-2 预置素材的切分随包提供、导入素材仍走端侧转写;NFR-4① 明确**仅发 arm64-v8a**(32 位地址空间装不下 NFR-4③ 的内存预算);NFR-4② 包体按实测改为 **~897MB**、四模型统一走安装时 asset pack,`tiny.en` 降为低端设备降级档(R-11)。新增评审记录 R-9 / R-10 / R-11。
>
> **v0.3 变更(2026-07-26)**:设备侧首跑(R-12)—— 前六道门首次在 arm64-v8a 上以**原判据**复测,22/22 通过,但 **R-5 是靠换模型才过的**:int8-transformer 编码器在 arm64 上说话人不变性 0.18323(判据 ≤0.18)、最差金标准余弦 0.98297(判据 ≥0.985),两条同时失手;按 R-5 既有 no-go 阶梯退 **fp16**(实测 0.16917 / 0.990–0.997,优于 macOS fp32 自身),**判据一字未改**。连带 NFR-4② 包体 ~897MB → **935 MiB**(wav2vec2-base 95.8 → **139.7**)。此外 `:core-audio` 修掉两个只有设备能暴露的真实缺陷(立体声下混少了 √2 能量守恒因子、seek 后首帧被吃)。R-8 转为**部分范围 PASS**(espeak/whisper 并存与 30s 片段待 Phase 3)。详见 `docs/reviews/2026-07-26-android-device-first-run.md`。
>
> **v0.4 变更(2026-07-27)**:Phase 4 `:app` 外壳启动,三项范围决策落定 —— ① **FR-M2 内置素材的视频本身随包发**(精选语料为用户自有、无版权,故不只发 `.sentences.json`,视频文件一并随包);用户导入路径(FR-M2)与内置并存。② **FR-11 音素诊断(`:core-mdd`)标为 v1.0 后待完成** —— P2 且自门控(不确定时静默),不影响其它流程的发布。③ **FR-12 学习记录(Room)本轮暂缓** —— P2、无模型依赖,事后补。本轮 DI 用手工 `AppContainer`(无 Hilt)。详见 `docs/android-migration.md` §12 Phase 4。
>
> **v0.5 变更(2026-07-27)**:模型投递从 Play install-time asset pack 切换为 **APK 内 assets 首次启动自动解压** —— GitHub APK 发布不依赖 Play Store 资产分发链路;935 MiB 模型在 `assets/models/` 内随 APK 压缩存储(zip,830MB),`AssetsModelSource` 首次启动时解压至 `filesDir/models/` 并显示进度条,后续启动跳过。Warmup 增加 `Copying` 态区分"解压中"与"校验中"。`DirectoryModelSource`(adb push)保留为降级兜底,`AssetPackModelSource` 保留源码供日后 Play 发布切换(见 `app/build.gradle.kts` 注释说明)。详见 `docs/android-migration.md` §12。

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
- 约束:版权——新闻视频有版权,分发形态只能是"用户自行获取素材"或链接指引,应用不得内置受版权保护的成片(见 §5 风险)。**例外(v0.4)**:应用随包分发的**精选预置语料为用户自有、无版权**素材(如 `7.1.mp4`),故其**视频文件本身随包发**(与 `.sentences.json` 一并),不触本约束;用户导入路径与预置并存。
- **导入格式(v0.1 分平台)**:macOS `{.mp4, .mov, .mkv, .m4v, .webm, .avi}`;**Android 为 `{.mp4, .mov, .mkv, .m4v, .webm}` —— 不含 `.avi`**。Android 走系统 `MediaExtractor`(R-9 决定放弃 FFmpeg NDK 路线),而 Android 官方 *Supported media formats* 对前五种容器是**平台强制项**,对 AVI **无任何保证**。后果限于"该文件导不进来"(有明确报错,不是静默算错分);需要时再接 Media3 的实验性 `AviExtractor`。Android 侧不支持的格式须在导入处给出可读的失败原因(区分"这台机器没有解码器"与"文件损坏",由 `findDecoderForFormat` 前置探测提供)。

**FR-M3(P1)素材难度适配。**
- 新闻播报语速快、句子长、连读多。需要:句子级切分粒度适合跟读(已实现,标点合并);语速信息展示;长句可再细分(**已实现 v4**:>8s 或 >20 词的句子在从句边界自动二级切分,CBS 素材残余超长句仅 3/164)。

## 4. 功能性需求

| 编号 | 优先级 | 需求 | 验收标准 | 状态 @v0.2 |
|---|---|---|---|---|
| FR-1 | P0 | 视频素材选择与浏览 | 列出 `videos/` 内视频,可选中、可流式播放定位到句 | ✅ 已实现 |
| FR-2 | P0 | 视频自动转写与句子/词切分 | faster-whisper 转写 + MMS 强制对齐词边界;缓存可复用。**Android:预置素材的切分随包提供,用户导入素材走端侧转写**(见表后说明) | ✅ 已实现 |
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
| FR-13 | P0 | 看图识物·整件识别与定位(Memorizing) | 用户上传日常照片,端侧识别图中整件物品并标注**目标语言(英语)+ 中文释义**;返回每个物品的可点击定位(box),点击可进入该物品详情。验收:常见物品(家具/餐具/电子/交通工具等)整件识别 precision ≥0.80、recall ≥0.60(R-13 实测);标签含目标语言 + 母语释义;全程无网络调用(NFR-5) | 🚧 待实现 |
| FR-14 | P1 | 部件级识别·微观(Memorizing) | 点击某整件物品 → 放大进入该物品详情页 → 展示其各组成部分的名称(目标语言 + 中文释义)。验收:对裁剪后的物品,部件命名人工相关性 ≥0.75、幻觉率(列出不可见部件)≤0.15(R-13) | 🚧 待实现 |
| FR-15 | P1 | 情景例句·记忆强化(Memorizing) | 为某物品/部件生成 1–3 句把它融入真实生活情景的目标语言例句(+中文翻译),用于加深记忆;**纯文字、不参与发音评分、不与 Speaking 模块的跟读参考混用**(故不触 FR-M1)。验收:例句流畅度(人工 1–5)≥4.0、情境贴切度 ≥3.5、中英匹配 ≥0.95(R-13) | 🚧 待实现 |
| FR-16 | P1 | 双模块信息架构 | App 顶层划分为 **Speaking**(口语跟读评估,含原视频跟读/上传音频)与 **Memorizing**(看图识物 + 情景例句)两大模块,各自独立流程、互不干扰。验收:模块切换清晰;Memorizing 模型的加载/释放不影响 Speaking 评分;视觉为 Duolingo 风高级感(NFR-UX) | 🚧 待实现 |

## 5. 非功能性需求与约束

- **NFR-1 全本地/离线/隐私**:所有模型本地运行,录音不出设备;sidecar 绑定 127.0.0.1 + 随机 token。
- **NFR-2 平台**:双平台 —— macOS 桌面(Tauri v2,Python sidecar 冻结为二进制)+ **Android 移动端(原生 Kotlin + Jetpack Compose,全端侧推理)**。Android 不复用 Python 后端(PyInstaller/torch 栈在 Android 不可行),改为 4 个模型用 ONNX Runtime Mobile / sherpa-onnx int8 重写实现;迁移方案见 `docs/android-migration.md`。两端共享评分契约与 `calibration.json`/音素表,**macOS 版作为 Android 数值对齐的金标准源**。
- **NFR-4(Android 移动端约束)**:
  - **① 设备支持面:最低 Android 9(API 28+),仅 `arm64-v8a`。** 不发 `armeabi-v7a`。这不是为省体积 —— NFR-4③ 的 ~3.5GB 峰值内存预算在 32 位进程的地址空间里**结构性不可达**,32 位设备装上也跑不完一次 `analyze`。附带收益:`:core-asr` 的 sherpa-onnx AAR 静态链接 ORT,每个 ABI 约 19MB,单 ABI 省掉这份重复。
  - **② 模型总量与分发:量化后 935 MiB**(wav2vec2-base **139.7** + MMS 338.6 + espeak-cv-ft 302.9 + whisper 159.8 + VAD/tokens;前三项为 R-5/R-6/R-7 实测并经 R-12 设备侧修正,whisper 为 R-10 实测。早先 ~460MB / ~807MB / ~897MB 的数字均已作废)。wav2vec2-base 从 95.8 涨到 139.7 是 R-12 的结论:**int8 编码器在 arm64 上过不了 R-5 判据,换 fp16**(见 §7 R-12),+43.9 MiB 是这个决定的全部体积代价。**whisper base.en int8 = 159.8MB 越过 Play 基础 APK 的 150MB 压缩上限**,故四个模型统一走**安装时 asset pack**(上限 1.5GB,计入安装体积,现余 590 MiB 余量);流程对应 macOS 的 `/warmup`。**降档档位**:`tiny.en`(102.8MB,转写快 1.67×,WER 4.89% vs base.en 4.01%)保留为**低端设备的运行期降级选项**,不作为发布默认 —— 判据见 R-11;降档触发条件现已有设备侧延迟数据(base.en 18.1–20.7× 实时,R-12),待定。
  - **③ 设备 RAM**:6GB 设备须能无 OOM 跑完整 `analyze`(espeak-cv-ft 惰性加载、句间释放 session),峰值 RSS <3.5GB,20 连续无 OOM。
  - **④ 麦克风权限** `RECORD_AUDIO`,采集用 `AudioSource.UNPROCESSED`(免 AGC/降噪染色,保评分保真)。
  - **⑤ 数值对齐**:Android 端评分须与 macOS 同语料在容差内一致(accuracy ±2.0 / fluency ±3.0 / DTW cost ±0.02),由 R-5 把关。**转写文本不在对等目标内**(R-10 决定 2):两个 int8 base.en 解码器在难音频上以 ~4% 的比例各自出错且不可消除,参考切分不同只是给出另一个同样有效的练习单元。
- **NFR-3 性能**:单句分析秒级出结果;视频首次转写可后台进行并缓存。
- **NFR-Q1 评分质量指标**:校准映射留出验证 PCC — accuracy ≥ 0.55(当前 0.60),fluency ≥ 0.40(当前 0.43);说话人不变性测试必须通过。**且校准必须对 FR-M1 的真实人声参考成立**(R-1 已实测验证:真人参考下分数不降反略升;新参考音品类须用 `scripts/ref_swap_experiment.py` 复验)。
- **NFR-5 端侧智能(Memorizing 模块)**:看图识物与情景例句的全部推理在设备本地完成(YOLO 检测 + 端侧 VLM + 端侧小 LLM),**无云调用、无 API key、无联网** —— 延续 NFR-1 与 FR-12 的离线/隐私立场;用户照片不出设备。LLM 选型遵循「最小可行」:优先 ≤1.5B 参数,质量不足再升档(R-13 定);VLM/LLM 多 GB 权重走首次惰性下载(同 wav2vec2/MMS),由 `memorize_warmup` 预取并分阶段显示进度。
- **NFR-UX 高级感视觉**:全 App 视觉升级为 Duolingo 风高级感(亮色主调、大圆角、3D 立体按键、友好),并承载 FR-16 的双模块顶层导航。设计令牌见 `desktop/src/styles.css`。
- **已知限制**:MMS 模型体积 1.18GB;首次转写慢(有缓存);超长连续选段(>5 分钟)wav2vec2 编码在 MPS 上有内存风险(P2,待分块编码);Memorizing 的 VLM/LLM 首次下载数 GB、首轮推理含加载延迟(分阶段进度 UI 缓冲)。
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
| FR-13 整件识别+定位 | `core/vision.py`(YOLOv8n-onnx,onnxruntime CPU)+ `/memorize/analyze` | 🚧(待 R-13) |
| FR-14 部件级微观 | `core/parts.py`(Qwen2.5-VL-3B,MPS)+ `/memorize/parts` | 🚧(待 R-13) |
| FR-15 情景例句 | `core/scenario.py`(Qwen2.5-Instruct,MPS)+ `/memorize/scenario` | 🚧(待 R-13) |
| FR-16 双模块 IA | `desktop/src/{index.html,main.js,styles.css}` | 🚧 |

> **Android 平台映射**:同一张表的需求在 Android 上由对应 Kotlin Gradle 模块满足 —— FR-4/5 → `:core-scoring`,FR-2 → `:core-asr` + `:core-align`,FR-11 → `:core-mdd`,FR-8 → `:app` RecordingsRepository + Media3,FR-12 → `:app` Room。完整需求→模块矩阵见 `docs/android-migration.md`。
>
> **Android 侧实现状态(2026-07-25)**:**FR-4 / FR-5 / FR-6 / FR-7 / FR-9 的评分层已在 `:core-scoring` 移植完毕**,以 macOS 抓取的金标准 fixture 在 JVM 断言(21/21 绿):分数走 NFR-4⑤ 容差(accuracy ±2.0 / fluency ±3.0 / cost ±0.02),而问题区间边界、词级标签与中文提示串**逐字精确断言** —— 学习者是照着提示念的,"差不多"在这里不构成验收。唯一保留的等价性缺口是 FR-7 的音高提示(Praat vs TarsosDSP YIN 无逐位等价),已隔离为可注入的 `PitchEstimator`,留待设备侧验证。FR-2 / FR-8 / FR-10 / FR-11 / FR-12 待 Phase 2–4。
>
> **补充(2026-07-25,Phase 2 首项)**:**FR-2 的词边界与 FR-8 的回放区间已在 `:core-align` 打通**(8/8 绿)—— MMS 强制对齐模型经 HF state-dict 载重导出为 int8 ONNX(338.6MB),对齐结果在金标准 emission 上逐字符精确、int8 端到端在 1 帧(20ms)内,达 R-6 判据。**NFR-4② 的包体数字需按此修正**:首启下载由 ~700MB 修正为 **~737MB**(MMS 实测比估值大),整包 ~807MB。FR-2 的转写侧(Whisper)、FR-8 的播放侧仍待 `:core-asr` / `:app`。
>
> **补充(2026-07-26,Phase 2 收口 + 设备侧首跑)**:`:core-asr` / `:core-audio` 已落地(R-10 / R-9),**六个 core 模块首次在真机 ABI 上端到端跑通**(`app/src/androidTest`,22/22 绿,详见 R-12)。至此 **FR-2 / FR-4 / FR-5 / FR-6 / FR-7 / FR-9 的算法侧在 arm64 上有实测背书**;FR-8 的**切片**侧一并验过(采样级精确 + seek 起音缺陷已修),**播放**侧仍待 `:app`。剩余:FR-11(`:core-mdd`,Phase 3,同时是 R-8 关门的前提)、FR-1 / FR-3 / FR-8播放 / FR-10 / FR-12(Phase 4)。工程侧一条值得记的坑:六个 core 模块原挂在 `androidTestImplementation`,导致 11 个测试在 class-init 阶段全灭于 `dlopen` 找不到 `libonnxruntime4j_jni.so` —— instrumentation 合并 test APK 的 **dex** 但**不**以同样方式合并其 `lib/`,而"一个进程同时持有所有 session 的峰值内存"本就是**应用进程**的性质,必须按应用将来加载它们的方式加载。已改为 `implementation`。
>
> **FR-2 的 Android 行为(2026-07-26 拍板)——预置素材的切分随包提供,不在设备上转写。**
> `videos/` 里的**预置精选素材**随包附带 macOS 侧预先生成的 `*.sentences.json`(转写文本 + 句/词边界),
> 应用直接读取;**用户自行导入的素材(FR-M2)仍走完整端侧转写**。三条理由:
> (i) 预置素材的练习单元与 macOS 版**逐字一致**,消掉 R-10/R-11 量到的 ~4% 转写分歧对内置内容的影响;
> (ii) 636s 素材首次转写在桌面上 38.2s,手机上是数分钟量级,这段等待落在用户第一次打开应用时(NFR-3);
> (iii) **不违反 NFR-1** —— 变的只是"内置内容的切分由谁预制",没有任何数据离开设备,也没有任何云调用。
> 验收:预置素材开箱即可进入跟读,无转写等待;导入素材的端侧转写路径不受影响、须单独验收。
>
> **Phase 4 `:app` 外壳(2026-07-27 启动)**:进入原生应用壳(此前 `:app` 仅有 `Placeholder.kt`,无 Activity)。范围:**内置 `7.1.mp4` → 选句 → 跟读录音 → 出分 + 逐词着色 + 提示 + A/B 回放**的端到端垂直切片为先,用户导入(FR-M2)为后。DI 用手工 `AppContainer`,UI 用 Compose + Navigation-Compose,播放用 Media3 ExoPlayer,录音用 AudioRecord `UNPROCESSED`。**本轮不做** FR-11(`:core-mdd`,v1.0 后)与 FR-12(Room,暂缓)。开工前先补一个真实洞:`:core-scoring` 此前没有暂停特征提取(`scoreTrackB` 的 `pausePerS`/`pauseRatio` 一直从 golden JSON 读、从未在 Kotlin 算),M0 移植 `prosody._pause_feats` 落进纯 JVM 层。模型投递先走 `DirectoryModelSource` + adb push 让外壳跑通,**Play install-time Asset Pack 的端到端投递验证提前做**(唯一没验过的发布链路)。实施计划见 `.claude/plans/scalable-brewing-wall.md`,进度回写 `docs/android-migration.md` §12。

## 7. 技术符合性评审记录

- **R-1(2026-07-22)v0.2 校准使用合成声参考 vs FR-M1** → `docs/reviews/2026-07-22-calibration-ref-fit.md`。结论:**符合,无需校正**——三组实测(LibriSpeech 350 对 / CBS 新闻 62 对 / CMU ARCTIC 母语+L2 置换)表明真人参考下校准分数不降反略升(+0.8~1.9),低分尾更窄;fluency 特征为参考相对量,天然免疫。新参考音品类引入时用 `scripts/ref_swap_experiment.py` 抽查。
- **R-2(2026-07-22)相对 DTW 参考集 vs FR-M1** → 同上文档。结论:经典相对 DTW 与"任意网络视频"需求冲突,降级;以"多 TTS 声平均"作为符合需求的替代方向。
- **R-3(2026-07-23)新闻域技术链验证** → `docs/reviews/2026-07-23-news-domain-verification.md`。结论:**4 项全过,FR-M2 解锁**:whisper base.en 够用(跨模型一致 98.3%)、MMS 对齐鲁棒(边界一致 ~10ms)、长句二级切分已落地(FR-M3)、端到端评分行为正常(89/88,零误报)。新发现:长选段 MPS OOM 风险(P2,待修)。
- **R-4(2026-07-23)音素级 MDD 假设打分式方案 vs FR-11「宁缺毋滥」** → `docs/reviews/2026-07-23-mdd-phoneme-fit.md`。结论:**符合 FR-11**——三重门控(仅 weak/bad 词 + canonical 自验证 gate≤0.05 + 替换增益 margin=0.15)结构性保证精度优先:负样本增益 ≤+0.036、坏 canonical 被门控静默、good 词永不触发;think→sink 增益 +0.332 精准定位 /θ/。召回受参考解码质量上限约束(已知取舍:近亲音对、归因 delete/substitute 偶偏),不违反精度优先验收。
- **R-5..R-9(计划中,Android Phase-0 spike)**:Android 端侧迁移的 5 个 go/no-go 符合性评审,门控判据与降级方案见 `docs/android-migration.md` §Phase 0:
  - **R-5**(Gate A)端侧 int8 评分 vs NFR-1(离线)+ NFR-Q1(质量)+ FR-4/5 —— **项目存在性证明**。✅ **PASS(设备侧,2026-07-26,但结论模型已换)**:桌面侧 int8-transformer(CNN 留 fp32,95.8MB)cost 0.1773 ≤ 0.18;**同一份导出在 arm64 上是 0.18323,同时最差金标准余弦 0.98297 < 0.985 —— 两条断言同时失手**。校准后 accuracy 仍是 95.00(与 macOS fp32 逐位相同),坏的不是不变性而是**余量**:到第一个 accuracy 拐点只剩 0.0032(fp32 时代 0.0155)。按既有 no-go 阶梯退 **fp16**:0.16917 / 余弦 0.990–0.997 / 余量 0.0172,**优于 macOS fp32 自身的 0.1714**;代价 +43.9 MiB、编码吞吐 21.6–25.2× → 12.2–12.8× 实时(两次运行的区间;只有墙钟在抖,所有数值逐位复现,比值稳定 1.8–2.0×,跨运行比较无意义;单句路径 12.7–13.1× 实时,3s 句子 231–234 ms,NFR-3「秒级」仍宽松)。**判据一字未改** —— 只因量化恰好落得好才成立的阈值不是阈值,放宽会作废此前所有 R-5 数字。附带发现:阶梯里写的 fp16 兜底**此前根本载入不了**(转换器产出类型不自洽;修好后 Android 又因裁剪版 ORT 缺 `com.microsoft.Gelu` 的 fp16 kernel 而拒收 —— 该融合发生在**载入期优化器**,桌面原理上抓不到)。详见 `docs/reviews/2026-07-25-android-gate-a-onnx-int8.md` 与 `docs/reviews/2026-07-26-android-device-first-run.md` §1。
  - **R-6**(Gate B)手写 CTC Viterbi 对齐精度 vs FR-2 / FR-8(每词边界 ≤1 帧/20ms)。✅ **PASS(2026-07-25,JVM 侧完整)**:`CtcViterbi.kt` 复现 torchaudio 每字符边界 ±1 帧;emission 导出经 HF state-dict 载重解掉(423 张量全映射,fp32 1203MB → int8 338.6MB,fp32 余弦 1.00000/误差 0 帧,int8 余弦 0.99896/误差 1 帧),`:core-align` 端到端 8/8 绿。详见 `docs/reviews/2026-07-25-android-gate-b-mms-rehost.md`。**设备侧复测已过(2026-07-26,R-12)**:emission 余弦 0.999215,9 个词边界与 macOS **逐个相同**,最差漂移 0.0248 帧 —— 与 R-5 形成对照,同为 int8 导出而对齐这一侧毫无余量问题(边界是 argmax 的位置,不是连续量)。
  - **R-7**(Gate C)音素 MDD int8 门控 vs FR-11「宁缺毋滥」(自拟合增益阈值 int8 下复验)。✅ **模型保真已过(2026-07-25)**:espeak int8(303MB)CTC 贪解串精确、余弦 0.9946;完整 think→sink 诊断待真实误读语料(Phase 3)。详见 `docs/reviews/2026-07-25-android-gate-bc-onnx.md`。
  - **R-8**(Gate D)6GB 设备 RAM 预算 vs NFR-4③(峰值 RSS <3.5GB,20 连续无 OOM)。✅ **PASS,但范围是部分的(2026-07-26,R-12)**:SSL + MMS + whisper + VAD 同进程常驻,峰值 PSS **892 MiB**(预算 3500),warmup 后 824,20 轮连续增长 67.5 MiB、关闭后回落到 92,单轮 624–673 ms(两次运行,中位 640/646)。**明确没测到的**:espeak 推理(`:core-mdd` 属 Phase 3)、whisper 与 SSL 真正并发持有、30s 长片段 —— 所以 NFR-4③ 要到 Phase 3 才能真正关门,现在不能写成"通过"。fp16 换装使峰值从 713 涨到 892 MiB,仍有 2.6GB 余量。
  - **R-9**(Gate E)音频解码与重采样 vs FR-M1/FR-M2 + NFR-Q1。✅ **PASS(桌面侧,2026-07-26)**,且**原判据先失效** —— 原写「经 FFmpeg-NDK 解码样本误差 ≤1 LSB」,而换任何重采样核都必然换一批样本值,该判据只有先选定 FFmpeg 才可能通过,是在假设路线而非检验路线。改为分数域判据(嵌入余弦 ≥0.995 / DTW cost 差 ≤0.005 / accuracy 差 ≤0.5)后实测:换核在样本域差 30–43dB SNR,在分数域 **Δcost ≤0.0011、Δaccuracy 0.00**。据此**放弃 FFmpeg NDK 路线**,改用系统 `MediaExtractor`/`MediaCodec` + `:core-scoring` 内的纯 Kotlin 多相重采样器(`scipy.signal.resample_poly` 1:1 移植,逐样本 |Δ|<1e-12)。连带:**项目不再需要 NDK**、无 LGPL 重链接义务、Android 导入面去掉 `.avi`(见 FR-M2)。详见 `docs/reviews/2026-07-26-android-gate-e-audio-decode.md`。**设备侧 4/4 已过(2026-07-26,R-12),且是修掉两个真实缺陷之后**:①`toMono` 按声道数取算术平均,而 libswresample 的 `layout=mono` 做能量守恒重矩阵 `(L+R)/√2` —— **每一路视频参考音低 3.01 dB**,下游三个消费者恰好都尺度不变所以没报警(Δcost 0.003 / Δaccuracy 0.00),但 Silero VAD 有绝对灵敏度、学习者录音路径又不下混,于是只有参考音悄悄偏;②mp4/AAC seek 到 1.000s 首个输出时间戳是 1.0217s,**在请求点之后**,FR-8 的按词回放区间因此被削掉起音,加 `PRE_ROLL_S=0.1` 回退。另有一处判据返工:Gate E 判据 ① 的余弦 0.995 是**桌面 fp32 编码器**量出来的,搬到量化编码器上等于要求"两个不同解码结果穿过量化后的吻合度高于编码器对自己跨精度的吻合度",改为对**实测噪声底**(`controlCos`)判定。**但换 fp16 后判据 ① 恢复为直接达标**(AAC 0.999895 / Opus 0.999956 / seek 0.999803,全部 ≫0.995),噪声底那一支退为**休眠兜底**——它在 int8 那次运行里确实是唯一的通过路径(0.9888–0.9928),保留下来是为了记住"这条线为什么可能不适用"。多机/多 OEM 解码一致性仍待真机。
- **R-10(2026-07-26)Gate F —— Whisper 转写文本 vs faster-whisper 金标准** → `docs/reviews/2026-07-26-android-gate-f-asr-text.md`。**计划里原本没有这道门**,写 `:core-asr` 前才发现 ASR 需要自己的门:Whisper 在本流水线只贡献文本,而**标点决定练习单元切分**,标准 ASR 评测剥掉标点给不出这个数。✅ **PASS(桌面侧)**,判据是**事后定的**(如实记录):归一化 WER 4.01% ≤5%、终止标点分歧 1.65% ≤2%、练习单元 158 vs 金标准 159。最大发现:**分歧主因是切块策略而非模型/量化** —— Silero VAD 分段(§4 原选型)5.56%,而 AAR 不暴露 segment 时间戳使最优的长音频循环不可实现,最终采用 **VAD 段合并成 29s 窗**;切块逻辑因此归入 `:core-scoring`(`AsrWindowPlanner`)。次要发现:int8 对转写只损 0.11pp **且一点也不更快**(自回归解码器受内存带宽限,瓶颈在 embedding 表)。
- **R-11(2026-07-26)Whisper 档位 —— tiny.en 能否替掉 base.en** → `docs/reviews/2026-07-26-android-r11-whisper-tier.md`。起因是 R-10 实测 whisper 159.8MB 越过 Play 150MB 上限。结论:**tiny.en 三条判据都过但不建议采用**。判据余量只剩 0.11pp/0.12pp,而 R-10 的判据本是事后定的、语料只有一段;更关键的是**分歧结构退化**——base.en 的 6 处多词分歧无一产生非词,tiny.en 新增 `terror-frueling`/`infatically` 这类非词,而 MMS 强制对齐**没有拒绝路径**,必须把从未说出的字符铺到真实音频上 → FR-2/FR-6/FR-8 在该 span 内失去对应关系(FR-11 有自拟合门控兜底,另三条没有)。tiny.en 的真实价值是**快 1.67×**(636s:38.2s→22.9s),保留为低端设备降级档。顺带否掉「量化 embedding 表」这条杠杆:该表有 Gather/Identity/Add 三个消费者,量化只加副本、fp32 原表仍需保留,文件反而变大(130.7→157.2MB)。
- **R-12(2026-07-26)设备侧首跑 —— R-5/R-6/R-8/R-9/R-10 在 arm64-v8a 上以原判据复测** → `docs/reviews/2026-07-26-android-device-first-run.md`。方法就是**判据不动,看谁不过**。结果 22/22 绿,代价是**一门换了模型、两处是真实缺陷、三处是测量方法返工**(逐条见上面各门与 §5 NFR-4②)。三条跨门的教训值得单列:
  - **① 桌面能过不等于设备能过,而且失因未必在我们导出什么。** fp16 兜底在 Android 被拒是因为 ORT 的**载入期优化器**把图里 17 个 `Erf` 融成 `com.microsoft.Gelu`,而裁剪版移动构建没有它的 fp16 kernel —— 桌面有。这类"运行时从模型里推导出什么"的失败,桌面侧的载入测试原理上抓不到。
  - **② 尺度不变是当下消费者的性质,不是保证。** √2 下混缺陷之所以在分数上几乎不可见,是因为 `frameDb` 用相对参考、`stressPos` 只取位置、CMVN 逐维归一 —— 三个都恰好尺度不变。据此把它当"无害"就错了:VAD 有绝对灵敏度。所以电平现在**单独 gate**(`|gain−1|<0.01`),不靠下游分数间接兜。
  - **③ 一条绿着的测量可能在报它没测的数。** 模型校验测试打印过 `SHA-256 over 935.1 MiB took 0 ms (Infinity MiB/s)` —— marker 跨运行存活,`verifyAll` 直接返回,而这行正是它本该产出的 NFR-3 warmup 数据点。现在先删 marker 再计时,并**结构性断言**而非用时间做代理(第一版改法拿 `ms > 1000` 当下限,被模拟器的宿主 page cache 当场证伪:424 ms / 2205 MiB/s)。**真机冷存储 I/O 因此仍是未知数**,"每次启动是否全量校验"这个 warmup 设计问题待真机数据。
- **R-13(2026-07-29,计划中)端侧识物 + 情景质量门 vs FR-13/FR-14/FR-15 + NFR-5** → `docs/reviews/2026-07-29-photo-recognition-fit.md`。在手标照片小集上实测三模型,数字门控:宏观 YOLO precision ≥0.80 / recall ≥0.60、微观 VLM 相关性 ≥0.75 / 幻觉率 ≤0.15、情景 LLM 流畅度 ≥4.0 / 情境贴切 ≥3.5 / 中英匹配 ≥0.95、同驻峰值 RSS ≤12GB。决定两个开放架构问题:① 宏观走 YOLO(带 box 可点热点)还是整图 VLM caption(无热点降级);② 小 LLM 选型(0.5B→1.5B→3B 逐级,直至流畅度达标)。**结果待 Phase E 回填**。
