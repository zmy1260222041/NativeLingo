# NativeLingo 产品需求文档(PRD)

> 版本:v0.7(2026-08-08)
> 状态:已生效。此后所有技术迭代必须能追溯到本文档的需求条目(见 §6 追踪矩阵);新需求先落本文档,再排技术方案。
>
> **v0.7 变更(2026-08-08)**:新增 **Survival 生存游戏模块**(FR-19..FR-26)—— 顶层信息架构由 Speaking/Memorizing **双模块扩为三模块**(FR-19)。本模块解决 Speaking 结构性解决不了的问题:成人学习者的核心心理障碍不是发音不准,而是**怕用错词** —— 二语在他们那里是交际工具,而非"让对方听懂"这个纯粹目的本身。游戏用「地球人卧底意识被注入外星弃婴、族人包容但无抚养责任、必须让对方听懂才能换取生存物资」的叙事设定,把儿童自然习得环境的四个特征(简单慢速、亲切有趣、会话式沟通目的、奖励正反馈)一次性还原。核心玩法是**观察他人扩充词汇**(FR-24),主线由生存需求驱动(FR-21),表达效果决定 NPC 施舍的物资(FR-25)。评估以**确定性语义槽位匹配 + reference-free 韵律**为主判据(FR-22,完全离线、可解释),**DeepSeek 云端表达审核为可选加成**(FR-23,默认关闭、静默降级)。为此新增 **NFR-6** —— 一条措辞极窄的 NFR-1 联网例外:**仅**授予游戏模块的表达审核、**仅**用户显式开启后生效、出站数据白名单只含文本、**Speaking 与 Memorizing 的离线保证表述一字不改**,§5 风险条对 FR-4/FR-5 发音与流畅度评分继续完全成立。"LLM 不打分,只生成措辞"这一原则的**既有适用范围不修改** —— 游戏主判据是确定性槽位分,云端审核是可选加成且不确定时静默,沿用 FR-11「宁缺毋滥 + 自门控」体例。游戏进度是桌面端第一个持久化功能(FR-26),采用版本化 JSON(不引入 SQLite,避免与 Android 侧 FR-12 的 Room 规划提前分叉)。词汇分级需引入外部 CEFR/NGSL 类词表随包分发 —— 仓库现有 `yoloe_labels.json`(218)与 `yoloe_everyday_labels.json`(11 类)是**检测器实体词表、几乎全是名词**,撑不起请求句式所需的动词与功能词。设计文档见 `docs/survival-game.md`,质量与符合性以 **R-14** 七道门(G1..G7)数字门控。**R-14 §5.2(2026-08-10)已放行内测采集版** —— G1/G2 重分类为实现期验收门(判据依赖产品运行才能测),解开「不实现 → 拿不到语料 → 两门永远不可判」的死锁;**一个阈值都没动**,内测范围封闭列举(见 `docs/reviews/2026-08-08-survival-game-fit.md` §5.2)。游戏为独立视觉域,见 `docs/FRONTEND_DESIGN.md` §17。
>
> **v0.6 变更(2026-07-29)**:新增 **Memorizing 模块** —— 看图识物(FR-13 整件识别+定位 / FR-14 部件级微观)+ 情景例句记忆强化(FR-15,纯文字、与 Speaking 评分分离、**不触 FR-M1**)+ 双模块信息架构 Speaking/Memorizing(FR-16)。智能层全端侧、无云无密钥(NFR-5,延续 NFR-1/FR-12);宏观整件检测直接使用 YOLOE-26S-PF 的 detection-only 动态 ONNX(带 box 热点、实体词表与逐标签阈值)，**不做 Florence 整图后台补充**;Microsoft Florence-2-base-ft(`florence-community/Florence-2-base-ft` 原生 Transformers 转换)仅用于点击后的部件视觉增强;`Qwen/Qwen2.5-0.5B-Instruct-GGUF` 的 Q4_K_M 文件通过 llama.cpp 实时生成情景例句。不使用 Apple 系统模型、不升 1.5B/3B。同步全 App 视觉升级为 Duolingo 风高级感(NFR-UX)。识物质量以 R-13 数字门控。
>
> **v0.6.x 变更(2026-07-31)**:FR-15 情景例句由「1–3 句第一人称陈述句」改为**多角色日常对话**(固定 2 位说话人 A/B、2–3 轮,每轮英文 + 中文,目标词自然出现在至少一轮)——让例句贴近生活口语而非陈述句;仍纯文字、本地实时生成(Qwen2.5-0.5B-Instruct Q4_K_M)、不读取预制例句、不参与发音评分、不与 Speaking 模块混用(故不触 FR-M1)。R-13 情景轨新增「对话自然度(1–5)≥3.5」指标。
>
> **v0.6.x 变更(2026-07-31,容器内容物)**:FR-14 在普通物品的部件分析之外，增加**容器感知的一层内容物增强**。YOLOE 仍是唯一整图检测器；用户点击 `cabinet` / `shelf` / `showcase` 等容器后，Florence 先从裁剪图生成详细描述，Qwen 只提取描述中明确可见的独立实体（Qwen 空结果时，仅从同一描述按实体词表确定性回退），再由 Florence phrase grounding 为全部候选联合定位。只有同时被描述和定位、且通过实体词表/几何/去重门控的候选才展示为 `contents`。内容物记录父容器关系但不得继续下钻，最大深度固定为 1；结构部件与内容物分区展示，防止把 `shelf` / `door` 当内容物或形成递归嵌套。
>
> **v0.6.x 变更(2026-08-01,容器扩展+标签对齐)**:FR-14 容器关系从 10 个扩展到 **48 个**——碗碟杯等餐具(bowl/plate/cup/mug/wine glass/coffee cup/soup bowl/salad bowl)、烹饪盛放(pot/pan/casserole/thermos/flask/jar/bottle/jug/pitcher/can/tin/box/tray/bag/basket)、储物(fridge/microwave/oven/washing machine/drawer/chest/locker/safe/luggage/backpack/handbag/briefcase/hamper/bin/waste container/cart/trolley)均为容器,点击后 Florence 识别其中独立可见内容物。**标签与模型词表直接对齐**(用户选定方案):`yoloe_labels.json` 死标签改名/删除、模型拼写标签按需新增(plane/jet/airliner、tub、smartphone、writing desk、file cabinet、toilet seat、ski、teddy),允许词表 157→**208 全部命中 YOLOE 4585 词表**(`vision.py` 不再有拼写别名映射);COCO 80 类保留保守覆盖,其拼写与模型不同的标签(airplane/cell phone/dining table/fire hydrant/refrigerator/skis/suitcase/teddy bear/toilet/tv)由模型词表等价标签(plane/smartphone/table/hydrant/fridge/ski/luggage/teddy/toilet seat/television)覆盖检出。
>
> **v0.6.x 变更(2026-08-01,餐桌食物词)**:FR-13 整图检测的实体 allowlist(`yoloe_labels.json`)从 157 扩到 **204 标签**,新增 **47 个常见餐桌食物词**(海鲜: squid/shrimp/crab/lobster/oyster/clam/scallop/octopus/abalone;蔬菜: tomato/onion/garlic/lettuce/mushroom/cucumber/corn/carrot/broccoli/potato/eggplant/cabbage/spinach/bell pepper/ginger/pumpkin;主食: rice/noodle/dumpling/bread/pizza/hamburger/hot dog/French fries/soup/salad/egg/tofu/steak/sausage/bacon/ham;调味: cheese/butter/salt/sugar/mustard/vinegar),全部经校验在 YOLOE 模型 4585 词表内,min_score 按同类小物体阈值设 0.35–0.50。香菜(cilantro/coriander)不在模型词表,FR-13 整图识别不了;FR-14 内容物词表可后续扩展。
>
> **v0.6.x 变更(2026-07-31,单词发音)**:新增 **FR-17 单词发音**(Memorizing)—— 识别物品的英文标签旁提供 🔊 播放按钮，用开源 **Piper 神经 TTS**(`en_US-libritts_r-medium`, CC-BY 4.0, ONNX ~79MB,全离线)合成词典式标准发音;用户可选录音跟读，后端用现有 SSL+DTW Track B 管线把 TTS 参考音与学习录音对比出分(accuracy/fluency)。Piper 合成在词汇学习场景作为单词参考音，**不违反 FR-M1**(FR-M1 范围限定为 Speaking 模块句子级真实人声跟读，单词词汇学习场景独立；详见 §6 追踪矩阵 FR-17 行)。Piper 模型由 `memorize_warmup` 纳入第 4 阶段下载/加载，离开模块时释放。发音模型经听感对比选定 `libritts_r`：lessac 吞词首 `/s/`+塞音簇(statue→tatue)、amy 保留 /s/ 但模糊 /t/(→satue)、libritts_r 两者都清晰。
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
| FR-13 | P0 | 看图识物·整件识别与定位(Memorizing) | 用户上传日常照片,端侧识别图中整件物品并以**目标语言(英语)单语标注**;返回每个物品的可点击定位(box),点击可进入该物品详情。验收:常见物品(家具/餐具/电子/交通工具等)整件识别 precision ≥0.80、recall ≥0.60(R-13 实测);整图框、图片下方汇总、详情标题、悬停提示和无障碍词汇均不显示中文释义;全程无网络调用(NFR-5) | 🚧 功能已实现，正式手标质量门待完成 |
| FR-14 | P1 | 部件与容器内容物·微观(Memorizing) | 点击普通整件物品 → Florence 详细描述/密集区域描述 → 以**目标语言(英语)单语**展示可见结构部件；点击 `cabinet` / `shelf` / `showcase` 等容器 → 详细描述 + Qwen 独立实体提取 + Florence phrase grounding → 分区展示可见内容物。内容物须同时出现在描述候选和有效定位框中，记录 `parent_id` / `relation` / `depth=1`，不允许再次触发微观分析；结构部件与内容物不得互相混入。验收:所有框、按钮、悬停提示和无障碍词汇不显示中文释义；部件/内容物人工相关性 ≥0.75、不可见项幻觉率≤0.15；容器内容物去重后最多 8 项、最大层级深度固定为 1；不依赖 Apple Vision/Foundation Models | 🚧 待实现 |
| FR-15 | P1 | 情景例句·记忆强化(Memorizing) | 固定用 `Qwen2.5-0.5B-Instruct-GGUF` Q4_K_M 在本机实时生成**一段简短多角色日常对话**(固定 2 位说话人 A/B、2–3 轮,每轮英文 + 中文翻译),场景取自当前照片、整件物品/所选部件与同图物体,所点击的目标词自然出现在至少一轮,贴近生活口语而非陈述句,用于加深记忆;**不读取预制例句、纯文字、不参与发音评分(单词发音评分走独立 FR-17 端点)、不与 Speaking 模块的跟读参考混用**(故不触 FR-M1)。验收:对话流畅度(人工 1–5)≥4.0、图片/部件情境贴切度 ≥3.5、对话自然度(人工 1–5)≥3.5、中英匹配 ≥0.95、明显臆造图片事实率 ≤0.10(R-13) | 🚧 待实现 |
| FR-16 | P1 | 双模块信息架构 | App 顶层划分为 **Speaking**(口语跟读评估,含原视频跟读/上传音频)与 **Memorizing**(看图识物 + 情景例句)两大模块,各自独立流程、互不干扰。验收:模块切换清晰;Memorizing 模型的加载/释放不影响 Speaking 评分;视觉为 Duolingo 风高级感(NFR-UX) | 🚧 待实现 |
| FR-17 | P1 | 单词发音(Memorizing) | 识别出的物品英文标签旁有 🔊 按钮,点击播放内置词典式标准发音(Piper 开源神经 TTS,`en_US-libritts_r-medium` CC-BY 4.0,ONNX ~79MB,全离线;经听感对比选定,lessac 吞词首 `/s/`+塞音簇、amy 模糊 /t/、libritts_r 两者清晰);用户可选录音跟读,系统用现有 SSL+DTW 管线对比 TTS 参考音出分。Piper 合成音在本模块作为单词参考音**不违反 FR-M1**(FR-M1 范围限定为 Speaking 模块句子级真实人声跟读,单词词汇学习场景独立)。验收:播放延迟 <1s;评分与 Speaking 同容差(accuracy ±2.0);Piper 模型纳入 Memorizing warmup 第 4 阶段、离开模块时释放 | 🚧 待实现 |
| FR-19 | P0 | 三模块信息架构(Survival) | App 顶层由双模块扩为 **Speaking / Memorizing / Survival** 三模块,各自独立流程、互不干扰。Survival 模块**不持有 Florence 与 Qwen**,不与 `memorize_warmup` 的 generation-token 生命周期争用(该设计假设单一 owner,两模块各自 `start()`/`release()` 会互相拆台);游戏的模型与网络行为不影响另两模块的评分数值与离线性。验收:三模块切换清晰;进入/离开 Survival 不改变 Memorizing warmup 的 stage 与进程 RSS;Speaking 的 accuracy/fluency 逐位不变(R-14 G6) | 🚧 待实现 |
| FR-20 | P0 | 能力初始化与分级词汇库(Survival) | 首次进入按 **婴儿级 / 幼儿级 / 青年级 / 职业级** 四档初始化用户词汇库(默认建议幼儿级 —— 大部分学习者的实际初始水平);词汇库为**随包分发的外部分级词表**子集 —— 已选定 **CEFR-J Wordlist v1.6**(等级 A1–B2)+ **Octanove C1/C2 v1.0**(补 C1/C2)+ **NGSL 1.2 stats**(SFI 频次);用户可随时查看"我现在会哪些词"及每个词的来源(`initial`/`observed_npc`/`observed_photo`)。**四档准入只用 CEFR 等级,不用频次排名切分** —— R-14 实测(`scripts/game_provenance_check.py`,42 场景逐词查 NGSL)发现频次排名与本模块场景难度**方向相反**:请求构式 `can`#38 / `want`#76 / `need`#90 全在首百词,而场景要求说出的具体物名 `bread`#2262 / `cup`#1491 / `rice`#2695 排在很后,`toilet` / `soap` / `apple` / `fever` 等 25 个内容词**不在 NGSL 2,809 词内**(NGSL 为阅读覆盖率而建,不收基数词、星期月份与低频家居物件);按频次切分会让婴儿级"能说请求句式却没有东西可请求"。频次仅用于**同级内排序**与 NPC 用词的「+N」上限。**索引键必须为 `(headword, pos)`** —— 同形词按词性拆行(`can` = A1 modal + A2 noun),实测仅 Octanove 一份就有 121 条会在裸 `headword` 键下互相覆盖。**仓库现有 `yoloe_labels.json`(218)/`yoloe_everyday_labels.json`(11 类)是检测器实体词表、几乎全是名词,只能提供生活化名词锚点,不能充当分级骨架**。验收:词表许可允许随包再分发(R-14 G4 逐条核实 ✅);四档切分点已写回 `docs/survival-game.md` §7.1 ✅;体积与首启延迟不违反 NFR-3 ✅ —— 三份资产解压后合计 **1,206,216 bytes(1.15 MiB)**、冷启动构建完整索引 **76.4 ms** vs 参考预算 1,000 ms(余量 13×),`scripts/game_vocab_gate.py` 实测;§7.1 的四档准入表已在真实词表上验证为**可执行判据**而非文档主张 —— 109 个必需槽位逐一检查「该 tier 是否至少有一条说得出来的说法」,**109/109 可达、0 个不可达、0 个无法判定** | 🚧 待实现 |
| FR-21 | P0 | 生存场景库与需求驱动主线(Survival) | 主线任务由**生存需求**驱动(食物/水/保暖/住所),场景全部取自**日常真实有需求的情境**;每个场景以 JSON 声明所需**语义槽位**与每槽的可接受同义表达集合(`slots[].accept`)、NPC persona 与三档回应(命中/部分命中/未命中)、分数→物资映射、可被观察的新词,以及 `provenance`(该情境为何常见的依据,为覆盖度评审留审计痕迹)。**未命中不构成失败** —— NPC 回应措辞只能表达"没听懂",禁止指出错误、纠正语法或评价能力,且不消耗任何机会。**场景常见度与需求贴合度决定本模块对语言学习帮助的上限**,须以覆盖度指标验收。验收:场景 ≥40 个覆盖需求金字塔前三层;人工评"日常常见度"与"需求贴合度"(1–5)均 ≥4.0;空 `provenance` 的场景不计入(R-14 G3)—— **✅ 已通过(2026-08-09)**:实测 **45 个**场景,层级 `{1:18, 2:12, 3:12, 4:3}`、`provenance` 45/45、`id` 唯一;**由用户本人评分**(非 agent 自评,判据明写「agent 自评不算」)45/45 两项填齐,**常见度 4.49 / 贴合度 4.84**,逐 tier 无一档低于 4.0,0 个场景需改写。工具 `scripts/game_scenario_rating_gate.py` | 🚧 待实现 |
| FR-22 | P0 | 语音表达效果评估·确定性主判据(Survival) | 用户**语音**输入 → `_decode_upload` 解码 → `transcribe_waveform` **自由转写**(无参考文本、无提示条件化)→ 场景槽位**确定性词边界匹配**得出 **delivery(意思传达程度)**;`extract_prosody` 的 `ProsodyFeatures` **绝对量**(说话时间/停顿数/停顿总时长/语速/音高变化)得出 **fluency**。**不依赖任何参考录音**,主判据完全离线、可解释、可复现。**不做语法检查** —— 语序、冠词、时态错误不扣 delivery。可选发音轨:以 `piper_tts.synth_wav(reference_answer)` 合成参考 + `pipeline.analyze_arrays` 出分,**合成音在本模块作参考不违反 FR-M1**(沿用 FR-17 已确立的同一论证:FR-M1 范围限定为 Speaking 模块句子级真实人声跟读,词汇学习与游戏场景独立)。**注意:`compare_prosody` 与 `score_b.fluency_from_features` 均需参考录音/DTW 路径,本模块不可复用**(后者 GAM 权重联合拟合,不可拆单分量)。验收:手标 ≥200 条学习者应答(四档各 ≥50)precision ≥0.85 / recall ≥0.70(R-14 G1);`base.en` 在婴儿/幼儿级短句(2–6 词、L2 口音、语法可不全)关键词召回 ≥0.85(R-14 G2,**既有 4.01% WER 是新闻播报语料所测,分布不同不可外推**);单调性 + 包容性判据(R-14 G7) | 🚧 **内测实现中** —— 槽位匹配 + `delivery` + 独立转写入口 `game_transcribe.py`(不调 `transcribe_waveform`)已就位;**内测版只出 `delivery`,fluency 待 G7**(红线 3)。G1/G2 判据未动,等内测语料回填 |
| FR-23 | P1 | 云端表达审核·可选加成(Survival) | 可调用 **DeepSeek API** 审核表达的自然度与情境适切性,作为**加成项 naturalness** 叠加在 FR-22 的确定性分之上。**默认关闭,需用户显式开启**;关闭时游戏必须完整可玩。离线/超时/异常/低置信 → **静默降级为纯确定性分,不返回也不显示该维度**(沿用 FR-11「宁缺毋滥 + 自门控」体例,而非给 0 分),不得阻塞游戏。**出站数据白名单:转写文本 + 场景摘要 + 词汇等级;禁止发送音频、录音、照片、设备标识,以及任何 Speaking/Memorizing 模块的数据**(NFR-6)。本项是"LLM 不打分"原则的**范围限定例外而非推翻** —— 主判据仍是确定性槽位分。验收:代码级审计确认 payload 只含白名单字段;关闭开关时**零出站请求(抓包验证,非读码推断)**;离线/超时/异常三条路径均静默降级且游戏可完整完成(R-14 G5) | 🚧 待实现 |
| FR-24 | P1 | 观察他人扩词(Survival) | 提供"**观察他人**"选项扩充词汇库 —— 这是**核心玩法**而非辅助功能(对应儿童"直接通过模仿外界获得能力")。两条来源:(a) 场景 NPC 台词中的新词(`new_words`);(b) **复用 Memorizing 已在产链路**:上传生活照片 → `vision.detect` → 物品词入库,与 `/memorize/analyze` 同一预处理契约 `memorize-image-v1`,零新增模型。新词**立即可用于后续交流并真实影响 delivery**。NPC 语音回应用 Piper 合成、放慢清晰(对应"母亲式语言"),同时构成听力输入。验收:观察所得新词在下一次交流中被槽位匹配采纳;照片扩词不绕过 `canonicalize_upload` | 🚧 待实现 |
| FR-25 | P1 | 物资奖励与需求金字塔养成(Survival) | 表达效果决定 NPC 施舍的**物资数量与品质**(场景 `reward` 分数区间映射);非必需槽位(礼貌标记、专业度)只影响品质,**不影响"是否传达到"的判定**。生存需求满足后按**需求层次逐级解锁**(生理→安全→归属→尊重),对应场景难度与词汇要求提升。低于最低区间不给物资但**不消耗机会**,可立即重说。验收:奖励随 delivery 单调不减;需求层级解锁与场景 `maslow_level` 一致 | 🚧 **内测最小版** —— 物资随 `delivery` 分档产出(hit/partial/miss + reward band)、重说不消耗机会已实现;**完整需求层级推进(FR-26)在内测范围外** |
| FR-26 | P1 | 游戏进度持久化(Survival) | 词汇库(含每词来源)、已完成场景、物资清单、当前需求层级、初始化等级**本地落盘**,重启后恢复。位置 `NATIVELINGO_DATA_DIR` 下 `game/profile.json`;带 `version` 字段与惰性迁移,沿用 `transcribe.py` 的 `CACHE_VERSION` 体例(项目内唯一的落盘先例)。**不引入 SQLite** —— 新依赖 + 新约定,且 Android 侧 FR-12 已规划 Room,桌面端提前分叉会留对齐债。**纯端侧、无云同步:NFR-1 对进度数据完全成立,NFR-6 的联网例外不覆盖进度**。验收:重启后进度完整恢复;旧版本 profile 可惰性迁移不丢词汇 | 🚧 待实现 |

| FR-27 | **P0** | 转写纠正入口与发音分诊(Survival) | 出分后展示**转写文本**,学习者可对任一词标「我说的不是这个」并给出本意词(来源限定为本场景 `slots[].accept` 与已掌握词汇库,避免自由输入引入噪声)。纠正后**立即按纠正结果重判本次应答**(不消耗机会,沿用 FR-25「低于区间不消耗机会」体例)。<br>**三重价值,缺一不可**:①**用户当下的出路** —— 仪器听错时不让学习者卡在循环里(§4「循环里没有失败出口」);②**语料生产** —— 每条纠正即一条带标注的真实 L2 录音,这是 G1/G2 目标语料的**唯一可行来源**(内测期收集);③**发音分诊** —— 若学习者主张说对了、但发音评分显示该词确实不合格,则该词进入**导流到 Speaking 模块**的建议列表(Survival 管「敢说」,Speaking 管「说准」,FR-4/5/11 正为此存在)。<br>**必须记录的偏倚**:纠正入口是**自选择**的 —— 只有自认说对了的人才会点,故它**系统性低估**真实错误率,尤其在最需要帮助的初学者身上。因此**不得**用纠正率反推 G2 的召回,只可用作语料来源与单条分诊。<br>**隐私**:录音与纠正记录**纯端侧落盘**(沿用 FR-26 的 `game/profile.json` 体例,录音单独存放);上传需**用户逐次显式同意**,NFR-6 白名单**不覆盖音频** —— 内测语料回收是**独立的显式授权流程**,不复用审核通道。<br>验收:纠正后重判生效且不消耗机会;纠正记录含原转写/纠正词/场景/时间戳并可导出;关闭上传时零出站(抓包);自选择偏倚在 R-14 中如实记录 | 🚧 **内测实现中(P0)** —— `/game/attempt/{aid}/correct` 已实现(不消耗机会、词级纠正、`triage_hint` 分诊 asr_miss/pronunciation);录音与纠正落 `NATIVELINGO_DATA_DIR/game/`,`/game/export` 可导出喂 G1/G2 量具。R-14 §5.2 已放行内测采集版以解开语料死锁 |

> **Survival 模块为桌面端第一个需要持久化的功能。**此前全项目没有任何用户进度存储 —— 照片在 `tempfile.mkdtemp` 临时目录、检测结果在进程内 dict、前端 store 纯内存,唯一落盘的用户状态是 `localStorage` 里的 `nl-theme` 主题色。FR-26 因此是从零建立第一个存储层,而非扩展既有能力。
>
> **Survival 的评估是净新增能力。**现有全部评分(FR-4/FR-5/FR-6/FR-7/FR-11)都是 **reference-anchored** —— SSL 嵌入 + DTW 对比一条具体参考录音,回答"读得像不像"。"意思有没有传达到"在仓库里此前完全不存在。这也是本模块存在的理由:Speaking 结构性地回答不了成人学习者"说得通不通"的焦虑。

## 5. 非功能性需求与约束

- **NFR-1 全本地/离线/隐私**:所有模型本地运行,录音不出设备;sidecar 绑定 127.0.0.1 + 随机 token。**唯一例外见 NFR-6**(Survival 模块的可选表达审核,默认关闭、只出文本)—— 该例外**不改变本条对 Speaking 与 Memorizing 的表述**:这两个模块的离线保证一字不变,录音、照片与音频在任何情况下都不出设备。
- **NFR-2 平台**:双平台 —— macOS 桌面(Tauri v2,Python sidecar 冻结为二进制)+ **Android 移动端(原生 Kotlin + Jetpack Compose,全端侧推理)**。Android 不复用 Python 后端(PyInstaller/torch 栈在 Android 不可行),改为 4 个模型用 ONNX Runtime Mobile / sherpa-onnx int8 重写实现;迁移方案见 `docs/android-migration.md`。两端共享评分契约与 `calibration.json`/音素表,**macOS 版作为 Android 数值对齐的金标准源**。
- **NFR-4(Android 移动端约束)**:
  - **① 设备支持面:最低 Android 9(API 28+),仅 `arm64-v8a`。** 不发 `armeabi-v7a`。这不是为省体积 —— NFR-4③ 的 ~3.5GB 峰值内存预算在 32 位进程的地址空间里**结构性不可达**,32 位设备装上也跑不完一次 `analyze`。附带收益:`:core-asr` 的 sherpa-onnx AAR 静态链接 ORT,每个 ABI 约 19MB,单 ABI 省掉这份重复。
  - **② 模型总量与分发:量化后 935 MiB**(wav2vec2-base **139.7** + MMS 338.6 + espeak-cv-ft 302.9 + whisper 159.8 + VAD/tokens;前三项为 R-5/R-6/R-7 实测并经 R-12 设备侧修正,whisper 为 R-10 实测。早先 ~460MB / ~807MB / ~897MB 的数字均已作废)。wav2vec2-base 从 95.8 涨到 139.7 是 R-12 的结论:**int8 编码器在 arm64 上过不了 R-5 判据,换 fp16**(见 §7 R-12),+43.9 MiB 是这个决定的全部体积代价。**whisper base.en int8 = 159.8MB 越过 Play 基础 APK 的 150MB 压缩上限**,故四个模型统一走**安装时 asset pack**(上限 1.5GB,计入安装体积,现余 590 MiB 余量);流程对应 macOS 的 `/warmup`。**降档档位**:`tiny.en`(102.8MB,转写快 1.67×,WER 4.89% vs base.en 4.01%)保留为**低端设备的运行期降级选项**,不作为发布默认 —— 判据见 R-11;降档触发条件现已有设备侧延迟数据(base.en 18.1–20.7× 实时,R-12),待定。
  - **③ 设备 RAM**:6GB 设备须能无 OOM 跑完整 `analyze`(espeak-cv-ft 惰性加载、句间释放 session),峰值 RSS <3.5GB,20 连续无 OOM。
  - **④ 麦克风权限** `RECORD_AUDIO`,采集用 `AudioSource.UNPROCESSED`(免 AGC/降噪染色,保评分保真)。
  - **⑤ 数值对齐**:Android 端评分须与 macOS 同语料在容差内一致(accuracy ±2.0 / fluency ±3.0 / DTW cost ±0.02),由 R-5 把关。**转写文本不在对等目标内**(R-10 决定 2):两个 int8 base.en 解码器在难音频上以 ~4% 的比例各自出错且不可消除,参考切分不同只是给出另一个同样有效的练习单元。
- **NFR-3 性能**:单句分析秒级出结果;视频首次转写可后台进行并缓存。
- **NFR-Q1 评分质量指标**:校准映射留出验证 PCC — accuracy ≥ 0.55(当前 0.60),fluency ≥ 0.40(当前 0.43);说话人不变性测试必须通过。**且校准必须对 FR-M1 的真实人声参考成立**(R-1 已实测验证:真人参考下分数不降反略升;新参考音品类须用 `scripts/ref_swap_experiment.py` 复验)。
- **NFR-5 端侧智能(Memorizing 模块)**:看图识物、情景例句与单词发音的全部推理在设备本地完成(YOLOE-26S-PF 检测 + Florence-2-base-ft 部件分析 + Qwen2.5-0.5B-Instruct Q4_K_M + Piper VITS 语音合成),**无云调用、无 API key;联网仅用于首次下载固定 revision 的模型,缓存后可离线**,用户照片与提示不出设备。YOLOE 为 45,190,231 bytes 的 detection-only 动态 ONNX，导出图在 Top-K 前固化 177 个实体类别过滤，运行时再做逐标签阈值与同框去重；Florence 不参与整图检测，只在用户点击物品后分析裁剪图。Florence 权重 463,178,864 bytes;GGUF 文件 `qwen2.5-0.5b-instruct-q4_k_m.gguf` 为 491,400,032 bytes,由 llama.cpp/Metal 运行;Piper 语音模型 `en_US-libritts_r-medium.onnx` 为 78,580,914 bytes(CC-BY 4.0,可再分发;经听感对比选定——lessac 吞词首 `/s/`+塞音簇、amy 模糊 /t/、libritts_r 两者清晰)。模型由 `memorize_warmup` 分阶段准备(yolo → llm → florence → piper),离开模块时释放内存。**不采用 Apple Vision/Foundation Models,不保留 1.5B/3B 升档路线。**
- **NFR-6 Survival 模块的联网例外(NFR-1 的唯一例外,范围极窄)**:下列每一条都是**约束**而非许可。
  - **范围三重限定**:例外**仅**授予 FR-23 的表达审核这一项能力,**仅**在 Survival 模块内,**仅**在用户显式开启后生效。任何其它功能、任何其它模块一律不得联网。
  - **默认关闭**。关闭状态下 Survival 必须**完整可玩** —— 确定性槽位分(FR-22)是主判据,云端只是加成项。关闭时须**零出站请求**(以抓包验证,不接受"读代码确认不发送"作为证据)。
  - **出站数据白名单**:转写文本 + 场景摘要 + 词汇等级。**禁止**发送音频、录音、照片、设备标识,以及任何 Speaking / Memorizing 模块的数据。白名单以外字段一律不得出站,须有代码级审计。
  - **不覆盖发音评分**:§5 风险条"技术调研不得引入需联网调用的评分服务"对 **FR-4 / FR-5 的发音与流畅度评分继续完全成立**。本例外与发音评分无关。
  - **不覆盖进度数据**:FR-26 的游戏进度纯端侧、无云同步。
  - **UI 义务**:开启处必须明确告知会有文本出站;游戏内须以**持续可见**的状态指示当前是否联网。
  - **不污染另两模块**:Speaking 与 Memorizing 的离线保证不受任何影响(NFR-1)。
  - 边界的可验证性以 R-14 的 **G5** 门控;G5 不过则 FR-23 单独不实现,FR-22 的纯离线玩法不受影响。
  - **分级词表随包分发,不联网获取**:FR-20 的词汇分级不依赖任何在线查询。三份资产**原样随包**(合计 <1 MB,相对 NFR-4② 的 935 MiB 模型总量可忽略,PRD 体积记录无需修正):**CEFR-J Wordlist v1.6**(版权方东京外国語大学投野研究室自授权,商用明文许可"can be used for both research and commercial purposes with a proper acknowledgement of the source",**唯一义务是署名**,无 ShareAlike / NonCommercial / NoDerivatives)、**Octanove Vocabulary Profile C1/C2 v1.0**(**CC BY-SA 4.0**,46,462 bytes)、**NGSL 1.2 stats**(**CC BY-SA 4.0**,62,566 bytes,Browne / Culligan / Phillips,明文 "even commercially")。**两套许可不可混为一套处理**,署名分别落实于 `desktop/backend/assets/wordlists/ATTRIBUTION.md`;逐条核对见 R-14 / G4 专项评审。**BY-SA 边界的实现约定**:词表以原样资产文件随包(与专有代码并置属聚合,不传染源码),**派生索引运行时构建、不落盘、不分发** —— 构建期转成自有格式即为分发 Adapted Material;且依 CC 4.0 "No downstream restrictions",词表资产**不得加密或混淆**。引用一律使用 `newgeneralservicelist.com`:`.org` 域名已过期并被重新注册为赌博联盟垃圾站,任何文档或 UI 不得把用户导向该域名。
- **NFR-UX 高级感视觉**:全 App 视觉升级为 Duolingo 风高级感(亮色主调、大圆角、3D 立体按键、友好),并承载 FR-16 的双模块顶层导航。Memorizing 的整件识别、部件识别与情景生成请求均有 **15 秒** 前端 AbortController 与后端 504 deadline:超时立刻清除加载态、显示可读错误并允许重试,不得无限“识别中”;每个 App 实例使用随机本地端口,不得连接到另一实例的旧后端。设计令牌见 `desktop/src/styles.css`。
- **已知限制**:MMS 模型体积 1.18GB;首次转写慢(有缓存);超长连续选段(>5 分钟)wav2vec2 编码在 MPS 上有内存风险(P2,待分块编码);Memorizing 的 Florence + GGUF 首次下载合计约 0.95GB、首轮推理含加载延迟(分阶段进度 UI 缓冲)。
- **风险**:素材版权(BBC 等)——产品形态必须停留在"用户自备素材",不得分发成片;技术调研不得引入需联网调用的评分服务(违反 NFR-1)。**该约束对 FR-4 / FR-5 的发音与流畅度评分继续完全成立** —— NFR-6 的联网例外只授予 Survival 模块 FR-23 的可选表达审核,**不覆盖任何发音评分路径**。

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
| FR-13 整件识别+定位 | `core/vision.py`(YOLOE-26S-PF detection-only ONNX,onnxruntime CPU,实体词表/逐标签阈值)+ `/memorize/analyze` | 🚧 功能完成，待正式 R-13 手标质量门 |
| FR-14 部件与容器内容物微观 | `core/parts.py`(Florence 详细描述/密集区域/phrase grounding + Qwen/显式描述词表实体过滤,最大深度 1)+ `/memorize/parts` | 🚧(待 R-13) |
| FR-15 情景例句 | `core/scenario.py`(Qwen2.5-0.5B-Instruct Q4_K_M,llama.cpp Metal/CPU)+ `/memorize/scenario` | 🚧(待 R-13) |
| FR-16 双模块 IA | `desktop/src/{index.html,main.js,styles.css}` | 🚧 |
| FR-17 单词发音 | `core/piper_tts.py`(Piper VITS ONNX,确定性合成)+ `/memorize/tts`(播放)+ `/memorize/pronounce`(复用 `pipeline.analyze_arrays` SSL+DTW)+ 前端 🔊/录音评分 | 🚧 |
| FR-19 三模块 IA | `src/index.html` / `src/main.js` / `src/modules/survival.js`(新,与 `speaking.js`/`memorizing.js` 同构)+ `modules/shell.js` `moduleIcons` 第三键 | 🚧 待 R-14 |
| FR-20 分级词汇库 | 随包词表 CEFR-J v1.6 + Octanove C1/C2 + NGSL 1.2(`assets/wordlists/`,原样)+ `core/game_vocab.py`(新,索引键 `(headword, pos)`);名词锚点复用 `core/yoloe_labels.json` | 🟡 G4 授权通过、切分点已定;体积/延迟待 CEFR-J 人工下载 |
| FR-21 场景库 | `core/game_scenarios/*.json`(新,每场景一文件便于逐条评审) | 🚧 待 R-14 G3 |
| FR-22 表达评估 | `core/transcribe.py::transcribe_waveform` + `core/prosody.py::extract_prosody` + `core/game_eval.py`(新,槽位匹配沿用 `scenario.py` 词边界正则) | 🚧 待 R-14 G1/G2/G7 |
| FR-23 云端审核 | `core/game_review.py`(新;可选、自门控、静默降级) | 🚧 待 R-14 G5 |
| FR-24 观察扩词 | 复用 `core/vision.py::detect` + `memorize_image.canonicalize_upload`;NPC 语音复用 `core/piper_tts.py` | 🚧 待 R-14 |
| FR-25 物资养成 | `core/game_state.py`(新) | 🚧 待 R-14 |
| FR-26 进度持久化 | `NATIVELINGO_DATA_DIR/game/profile.json`,版本化 JSON,沿用 `transcribe.py` `CACHE_VERSION` 惰性迁移体例 | 🚧 待 R-14 |
| FR-27 转写纠正与发音分诊 | 前端 `modules/survival.js` 转写词级可点选 + `core/game_eval.py` 重判入口 + `NATIVELINGO_DATA_DIR/game/corrections/`(录音与标注分开存放);分诊复用 `pipeline.analyze_arrays`(§6.4 口径) | 🚧 待 R-14;**G2 判据修订后升为 P0** |

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
- **R-13(2026-07-29,进行中)端侧识物 + 情景质量门 vs FR-13/FR-14/FR-15 + NFR-5** → `docs/reviews/2026-07-29-photo-recognition-fit.md`。探索集已完成 10 室内 + 10 室外逐图复核，并据此把宏观模型直接切为 YOLOE-26S-PF：Top-K 前屏蔽非实体词，运行时按标签校准阈值和去重，不再后台调用 Florence。热态中位 57.7ms、P95 63.8ms；该探索集没有手标框，不能替代正式 precision ≥0.80 / recall ≥0.60 门。Florence 微观相关性、Qwen 情景质量和同驻 RSS 仍待正式手标/人工评分回填。
- **R-14(2026-08-08,内测采集版已放行 2026-08-10)Survival 生存游戏可行性与符合性 vs FR-19..FR-26 + NFR-6** → `docs/reviews/2026-08-08-survival-game-fit.md`。**判据在任何实现开始之前全部写死**,这是 R-10/R-11 的直接教训:事后定判据会让余量失去意义(R-11 评估 tiny.en 时只剩 0.11pp 余量,却无法判断该余量是否可接受,因为判据本身是照着已有结果凑的)。七道门:**G1** 意思传达判准(手标 ≥200 条、四档各 ≥50,precision ≥0.85 / recall ≥0.70;precision 优先 —— 误判"传达到"让用户学到错表达,误判"没传达到"只是再说一次而设定里再说一次无代价);**G2** ASR 对 L2 短语可用性(婴儿/幼儿级 2–6 词短句关键词召回 ≥0.85;**既有 4.01% WER 是新闻播报语料所测,不可外推到 L2 口音短句**);**G3** 场景库覆盖度(≥40 个覆盖需求金字塔前三层、常见度与贴合度均 ≥4.0,空 `provenance` 不计入);**G4** 词表授权与体积(许可须明确允许随包再分发,逐条核对 —— 沿用 Piper 选 `libritts_r` 时核 CC-BY 的先例;授权未核实前四档切分点无法确定);**G5** 云端审核隐私边界(payload 白名单代码级审计 + 关闭时零出站**抓包**验证 + 三条降级路径均静默且游戏可完成;R-12 教训③"一条绿着的测量可能在报它没测的数",读码确认不算);**G6** 模块隔离(不改变 Memorizing warmup stage 与 RSS、Speaking 分数逐位不变 —— `memorize_warmup` generation-token 假设单一 owner);**G7** 教学有效性(单调性 + **语法不完美但意思传达到不得判失败**,这是产品心理意图的数值化;fluency 绝对阈值在本门样本上定,因 `score_b.fluency_from_features` 的 GAM 权重与 DTW 路径联合拟合、不可拆单分量复用)。**§5.2(2026-08-10)放行内测采集版**:G3 已通过(用户本人评分 4.49/4.84)、G4 已通过;G1/G2 重分类为**实现期验收门**(判据依赖产品运行才能测 —— G1 要真实录音经生产路径转写、G2 要 ≥8 位说话人 L2 口音,两者在「有东西可以录入之前」不可能存在),与 G5/G6/G7 同类;**一个阈值都没动**,内测范围封闭列举(取场景/录音/转写/槽位匹配/NPC 三档/最小物资/FR-27 纠正入口/端侧落盘/导出喂量具;不做云端审核、不做照片扩词、不做完整经济、不出未校准分数)。采集完成 ≠ 判据通过 —— 采完须重跑量具真实模式才是裁决。已如实记录四处设计张力,其中两处结构性:确定性槽位匹配**奖励不了创造性表达**(云端审核为补此缺口而生,但默认关闭,故**离线可玩性上限由 G3/G1 而非审核质量决定**);**离线时没有语义兜底**(本地 0.5B 判断力不足,不承担审核裁判,此为有意取舍非遗漏)。
- **R-15(2026-08-15)Godot Web Beta 无语音内测发布符合性 vs 用户《Godot 网页内测发布方案》** → `docs/reviews/2026-08-15-web-beta-no-voice-fit.md`。结论:**代码侧放行** —— Web Beta 导出预设(Compatibility / 无 Threads / 无 PWA / `web_beta_no_voice`)、无语音短路与 UI/重映射隐藏、Web 下 AnimationDebugBridge 全禁用、问卷入口与构建标签、可重复构建脚本、Nginx/Basic Auth/TLS/预压缩/回滚配置均已就位;构建脚本内 7 个测试套件全绿(`game_state`/`HUD`/`WebBetaNoVoice`/`VoiceTargetCancel`/`MainEnvIntegration`/`walk_fix`/`directional_locomotion`),导出的 PCK 不含 `res://tests|tools|addons|speech_service`,gzip 首包 35.0 MiB(门槛 70 MiB);Playwright/Chromium 真实 Web Release 冒烟 headless 与 headed 均通过(headed 验证首次点击指针锁定成功),mic API 调用 0、localhost/语音请求 0、控制台与页面错误 0。真实双平台/双浏览器手动通关与域名/备案/服务器/问卷属于外部操作,按 `production/web-beta/README.md` §6 门槛闭环。
- **R-16(2026-08-15)Stranger Desktop Beta 无语音分发符合性 vs D1–D4 已冻结决策** → `docs/reviews/2026-08-15-desktop-beta-fit.md`。结论:**代码侧放行,待真机与证书闭环** —— Windows x64/macOS arm64 双预设、`desktop_beta_no_voice` 门控、桌面专用文案/构建标签、调试桥禁用、8 套测试全绿、Windows ZIP 60.5 MiB / macOS DMG 58.2 MiB(门槛 300 MiB)、macOS PCK 不含开发目录、导出后 macOS 二进制 headless 启动退出码 0。残留:Windows/macOS GUI 真机矩阵(B/C 组)、Developer ID 公证、问卷 URL、应用图标与 GitHub draft release 实际发布。
