# Survival 生存游戏模块 —— 设计文档

> 状态:设计稿(2026-08-08)。对应需求 FR-19..FR-26 与 NFR-6,见 `docs/PRD.md`。
> 可行性与符合性门控见 `docs/reviews/2026-08-08-survival-game-fit.md`(R-14)。
> **本文档为设计基线,不含实现。**R-14 未通过前不得进入实现。

## 1. 为什么要做这个模块

Speaking 模块评的是「读得像不像」—— 给定参考音,测学习者的发音与韵律偏差。它解决的是
**准确度**问题。但它结构性地解决不了另一个问题:

> 成人学习者的核心心理障碍不是发音不准,而是**怕用错词**。二语在他们那里是交际工具,
> 而不是「让对方听懂」这个纯粹目的本身。

儿童没有这个障碍,因为他们的习得环境有四个特征,而成人的学习环境把这四条全丢了:

| 儿童自然习得环境 | 成人学习环境 |
|---|---|
| 句式简单、语速慢,理解负担低 | 素材语速快、句子长(本 App 的新闻语料正是如此) |
| 语气亲切、材料有趣,情绪负担低 | 任务化、考试化,情绪负担高 |
| 会话式语言,双方目的是**沟通成功** | 表演式语言,目的是**不出错** |
| 表达正确后获得**奖励正反馈** | 表达错误后获得**纠错反馈** |

再叠加成人特有的三个环境缺陷:缺乏真实语境、学习时间碎片化、他人包容性不足打压自信。

本模块用一个叙事设定把这四条一次性还原。

## 2. 叙事设定

> 你是一个地球人,混入一个讲人类语言的外星族群,伪装外形与语言。仅存的人类派你作为
> 卧底,把你的意识注入了一只被遗弃的外星婴儿的身体,然后送回族群附近。别人对你的
> 包容性很强,但**没有责任抚养你** —— 你需要通过交流让对方听懂,从而满足自己的
> 基本生存需求。

这个设定不是包装,它的每一个成分都在承担一项心理功能:

| 设定成分 | 承担的心理功能 |
|---|---|
| **被遗弃的婴儿身体** | 语言能力低是**设定内的合理状态**,不是失败。说得差不构成羞耻 |
| **包容性很强** | NPC 不评判、不嘲笑、不打压自信 —— 直接对应成人环境里缺的那一条 |
| **没有责任抚养你** | 保留真实的交际压力。包容 ≠ 白给,你必须真的让对方听懂 |
| **卧底身份** | 给「观察与模仿他人」一个叙事动机 —— 这本是儿童习得的主要途径 |
| **生存需求驱动** | 语言是**手段**,成功判准是「对方给了物资」,而不是「分数高」 |

## 3. 机制映射表

每条机制都必须回溯到上面的某条习得特征。没有对应特征的机制不进这个模块。

### 3.1 儿童习得特征 → 机制

| 习得特征 | 机制 |
|---|---|
| 句式简单、语速慢 | NPC 台词受场景 tier 约束,用词不超出用户当前词汇库 + N 个新词(N 为该场景 `new_words` 的规模) |
| 语气亲切、材料有趣 | 未命中时的反馈是「没听懂,再说一次?」,不是扣分或纠错 |
| 会话式语言,目的是沟通 | 主线是生存需求;判定成功的信号是**拿到物资**,分数不作为主界面焦点 |
| 母亲式语言:高音高、夸张元音、慢速 | NPC 语音回应用 Piper 合成(`piper_tts.synth_wav`),放慢、清晰 —— 同时是 FR-24 扩词的听力输入 |
| 与生活中特定物体、事件建立联系 | 复用 Memorizing:用户上传**自己家**的照片,YOLOE 检测出的物品直接进词汇库 |
| 表达正确后获得奖励 | 物资奖励 + 需求层级解锁(FR-25) |
| 直接通过模仿外界获得能力 | 「观察他人」是**核心玩法**,不是辅助功能(FR-24) |

### 3.2 成人障碍 → 机制

| 成人障碍 | 机制 |
|---|---|
| 缺乏真实语境 | 场景全部取自日常真实有需求的情境(FR-21);照片扩词接入用户真实环境 |
| 学习时间不足、连续性被打断 | 单场景一次交流即可完成;进度持久化(FR-26),随时中断与恢复 |
| 他人包容性不足、打压自信 | 婴儿身份 + 包容 NPC;NPC 只表达「听懂 / 没听懂」,不评判表达质量 |
| **怕用错词** | R-14 的 **G7 单调性判据**:意思传达到就有回报,**语法不完美不判失败** |
| 认知已由母语构建,二语被任务化 | 需求驱动而非课程驱动;没有单元、没有进度条式课程表 |

## 4. 核心循环

```
需求出现(饿 / 渴 / 冷)
   → 选择场景与 NPC
   → 语音表达(录音)
   → 评估(§6)
   → NPC 以母亲式语言回应 + 按表达效果施舍物资
   → 需求缓解;满足后按需求层次解锁下一层场景
        ↑                                    ↓
        └──── 「观察他人」扩词 ←──────────────┘
              (NPC 台词新词 / 上传生活照片)
```

关键设计约束:**循环里没有「失败」出口**。未命中槽位的结果是 NPC 没听懂、物资更少、
可以再说一次 —— 而不是任务失败、扣血、重来。这是 §2 「包容性」设定的机制化。

## 5. 场景库

位置:`desktop/backend/core/game_scenarios/*.json`(每个场景一个文件,便于评审逐条核)。

场景库的质量直接决定本模块对语言学习的帮助上限 —— 因此 R-14 的 **G3** 把「日常常见度」
与「需求贴合度」设为量化门,而不是留给实现时的直觉。

**G3 已通过(2026-08-09)**:45 个场景,**由用户本人评分**(判据明写「agent 自评不算」——
场景由 agent 写,自评只是重复写作时的判断),常见度 **4.49** / 贴合度 **4.84**,均 ≥4.0,
逐 tier 无一档低于 4.0。评分表结构性地不向评分者展示 `provenance.rationale`:那是作者
「为何常见」的论证,先读它就变成在给论证打分,并恰好在作者最有说服力处抬高常见度。
工具 `scripts/game_scenario_rating_gate.py`,provenance 逐条核走独立的 `--review` 一趟。

### 5.1 Schema

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 稳定标识,如 `food-ask-bread` |
| `version` | int | 场景 schema 版本,便于惰性迁移 |
| `tier` | enum | `infant` / `toddler` / `youth` / `professional` |
| `need` | enum | `food` / `water` / `warmth` / `shelter` / `safety` / `belonging` / `esteem` |
| `maslow_level` | int | 1..4,对应 FR-25 的需求层级解锁 |
| `situation` | object | `{ zh, en }` —— 呈现给用户的情境描述 |
| `npc` | object | 见 §5.2 |
| `slots` | array | 语义槽位,见 §5.3 |
| `reward` | array | 分数区间 → 物资映射,见 §5.4 |
| `new_words` | array | 本场景可被「观察」收入词汇库的新词,每项 `{ en, zh, source }` |
| `reference_answer` | string | 一条标准答法。**仅**用于可选发音轨的 Piper 参考音合成(§6.4),不参与 delivery 判定 |
| `provenance` | object | `{ rationale, frequency_basis }` —— 该情境为何常见、依据是什么。为 G3 留审计痕迹 |

### 5.2 `npc` 字段

```
npc: {
  persona: string,          // 简短角色设定,约束 NPC 语气
  greeting: string,         // 场景开场台词(英文,受 tier 词汇约束)
  responses: {
    hit:     string[],      // 槽位全部命中
    partial: string[],      // 必需槽位部分命中
    miss:    string[]       // 必需槽位未命中 —— 措辞必须是「没听懂」而非「你说错了」
  }
}
```

`responses.miss` 的措辞规则单独写在这里,因为它承载 §2 的包容性设定:允许
"Sorry? Say it again?" / "Hmm? What do you need?",**禁止**任何指出错误、纠正语法或
评价能力的措辞。

### 5.3 `slots` —— 语义槽位

每个槽位描述「这句话必须传达到的一个意思单元」,而不是「必须说出的某个词」:

```
slots: [
  {
    key: "need_object",           // 槽位语义角色
    required: true,
    accept: ["bread", "food", "something to eat", "eat"],
    zh_hint: "你要的东西"
  },
  {
    key: "request_act",
    required: true,
    accept: ["want", "need", "give me", "can I have", "please"],
    zh_hint: "表达这是一个请求"
  },
  {
    key: "politeness",
    required: false,           // 非必需 —— 影响物资品质,不影响是否传达到
    accept: ["please", "thank you", "thanks"],
    zh_hint: "礼貌标记"
  }
]
```

设计要点:

- `accept` 是**同义/变体表达集合**,允许多词短语,匹配时不要求语法完整。
- `required: false` 的槽位(如礼貌标记、专业度)只影响物资**品质**,不影响
  「意思有没有传达到」。这是 G7 单调性判据在数据层的落点。
- 每个 `accept` 集合都要覆盖 tier 内学习者最可能说出的粗糙形式("me hungry"、
  "want eat"),否则 G1 的 recall 过不了。

### 5.4 `reward`

```
reward: [
  { min_delivery: 90, quality: "generous", items: [{ id: "bread", count: 2 }] },
  { min_delivery: 60, quality: "plain",    items: [{ id: "bread", count: 1 }] },
  { min_delivery: 30, quality: "scrap",    items: [{ id: "crumb", count: 1 }] }
]
```

低于最低区间不给物资,但**不消耗任何机会** —— 可立即重说。

### 5.5 示例场景(填好的两条)

> 注:以下示例展示的是**场景 schema 的形状**,不是逐字节拷贝。`food-ask-bread` 在
> G3 评分轮(用户按低分反馈改写场景文本)后已升到 `version: 2`,`situation` 改为
> 面包店柜台的措辞,`reward` / `new_words` / `provenance` 也随之更新。以
> `desktop/backend/core/game_scenarios/L1-food-ask-bread.json` 为准;本示例保留原始
> 简化措辞以说明字段语义。

**示例 A —— `food-ask-bread`(婴儿级 / 生理需求)**

```json
{
  "id": "food-ask-bread",
  "version": 1,
  "tier": "infant",
  "need": "food",
  "maslow_level": 1,
  "situation": {
    "zh": "你饿了。街边有人正在分发面包。",
    "en": "You are hungry. Someone by the street is handing out bread."
  },
  "npc": {
    "persona": "A calm elder handing out bread. Patient, never critical.",
    "greeting": "Oh, little one. Are you hungry?",
    "responses": {
      "hit": ["Bread? Here you are. Take two.", "Of course. Here, eat."],
      "partial": ["Food? Which one do you want?", "You want something. Show me?"],
      "miss": ["Sorry? Say it again?", "Hmm? What do you need?"]
    }
  },
  "slots": [
    {
      "key": "need_object",
      "required": true,
      "accept": ["bread", "food", "something to eat", "eat", "hungry"],
      "zh_hint": "你要的东西"
    },
    {
      "key": "request_act",
      "required": true,
      "accept": ["want", "need", "give me", "can i have", "may i have", "please"],
      "zh_hint": "表达这是一个请求"
    },
    {
      "key": "politeness",
      "required": false,
      "accept": ["please", "thank you", "thanks"],
      "zh_hint": "礼貌标记"
    }
  ],
  "reward": [
    { "min_delivery": 90, "quality": "generous", "items": [{ "id": "bread", "count": 2 }] },
    { "min_delivery": 60, "quality": "plain", "items": [{ "id": "bread", "count": 1 }] },
    { "min_delivery": 30, "quality": "scrap", "items": [{ "id": "crumb", "count": 1 }] }
  ],
  "new_words": [
    { "en": "bread", "zh": "面包", "source": "npc" },
    { "en": "hungry", "zh": "饿的", "source": "npc" }
  ],
  "reference_answer": "I want bread, please.",
  "provenance": {
    "rationale": "获取食物是生理需求中最高频的一项,且请求食物是所有语言中最早习得的言语行为之一。",
    "frequency_basis": "需求金字塔第 1 层;所需词汇全部落在分级词表最低频段。"
  }
}
```

**示例 B —— `warmth-ask-blanket`(幼儿级 / 生理需求)**

```json
{
  "id": "warmth-ask-blanket",
  "version": 1,
  "tier": "toddler",
  "need": "warmth",
  "maslow_level": 1,
  "situation": {
    "zh": "夜里很冷,你在发抖。旁边的摊位上堆着一些毯子。",
    "en": "It is cold at night and you are shivering. There are blankets on a nearby stall."
  },
  "npc": {
    "persona": "A stall keeper closing up for the night. Kind but busy.",
    "greeting": "Cold night, isn't it?",
    "responses": {
      "hit": ["A blanket? Take this one. Stay warm.", "Here. It is warm."],
      "partial": ["You are cold? What do you need?", "Something for the night?"],
      "miss": ["Sorry, say that again?", "I did not catch that."]
    }
  },
  "slots": [
    {
      "key": "need_object",
      "required": true,
      "accept": ["blanket", "something warm", "cloth", "cover"],
      "zh_hint": "你要的东西"
    },
    {
      "key": "reason_state",
      "required": true,
      "accept": ["cold", "freezing", "i am cold", "shivering"],
      "zh_hint": "说明你的状态,让对方理解需求"
    },
    {
      "key": "request_act",
      "required": false,
      "accept": ["can i have", "may i", "could you", "please", "need", "want"],
      "zh_hint": "请求标记"
    }
  ],
  "reward": [
    { "min_delivery": 90, "quality": "generous", "items": [{ "id": "blanket", "count": 1 }, { "id": "hot_drink", "count": 1 }] },
    { "min_delivery": 60, "quality": "plain", "items": [{ "id": "blanket", "count": 1 }] },
    { "min_delivery": 30, "quality": "scrap", "items": [{ "id": "rag", "count": 1 }] }
  ],
  "new_words": [
    { "en": "blanket", "zh": "毯子", "source": "npc" },
    { "en": "warm", "zh": "暖和的", "source": "npc" },
    { "en": "cold", "zh": "冷的", "source": "npc" }
  ],
  "reference_answer": "I am cold. Can I have a blanket?",
  "provenance": {
    "rationale": "保暖是生理需求第二高频项;「说明状态 + 提出请求」是比单纯命名物品更进一步的言语行为,适合幼儿级。",
    "frequency_basis": "需求金字塔第 1 层;引入状态描述槽位,词汇仍在低频段。"
  }
}
```

## 6. 评估算法

用户明确的取舍:**确定性语义槽位匹配 + reference-free 韵律为主判据,DeepSeek 云端审核
作为可选加成。**主判据必须完全离线、可解释、可复现。

```
录音
 └→ _decode_upload (main.py:99)
     └→ transcribe_waveform (transcribe.py:258) ──→ 槽位匹配 ──→ delivery  [主判据]
     └→ extract_prosody     (prosody.py:47)     ──→          ──→ fluency   [离线]
                                                    [可选] DeepSeek 审核 ──→ naturalness [加成,可静默]
                                                    [可选] Piper + SSL/DTW ─→ pronunciation [加成,可静默]
                                                                              ↓
                                                                    NPC 施舍决策(§5.4)
```

### 6.1 delivery —— 意思传达程度(FR-22,主判据)

- 输入:`transcribe_waveform` 的转写文本。**解码配置与跟读模块不同,且必须不同**
  (2026-08-09 代理实测,见 R-14 G2):
  - `beam_size=5` —— 在产的 `beam_size=1`(`transcribe.py:262`)是为**新闻长句**调的;
    2–6 词应答几乎没有上下文供语言模型纠正声学歧义,贪心解码在代理语料上直接损失
    约 7pp 召回,而句子短使得 beam5 的额外开销可忽略(实测 400 ms/条,与 beam1 持平)。
  - **场景 `slots[].accept` 词表作 `hotwords` 解码偏置**(faster-whisper ≥1.2.1)。
    游戏**在用户开口前就知道是哪个场景**,这份词表是免费的先验:零体积、零延迟、零 UX 代价,
    代理实测 +5.6pp。**这不违反「无参考文本」** —— 偏置的是「本场景可能出现哪些词」这一
    集合,不是某一个正确答案;§11 张力 1 禁止的是对着**单条** `reference_answer` 打分,
    而 accept 集合恰恰包含几十种等价说法。
  - **不可**沿用跟读模块的 `transcribe_waveform` 原参数直接调用 —— 那条路径的分数已按
    现有解码配置校准(Track B),改它会动到 Speaking 的既有分数(G6 要求逐位不变)。
    游戏需要独立的转写入口。
  - **幻觉防线是必需件,不是可选优化**:实测到专家满分词的输入被转写成
    `I will see you in the next video`(训练数据里的 YouTube 结束语,与音频无关)。
    幻觉比丢词更危险 —— 丢词只是不给物资,幻觉会让槽位**命中学习者根本没说的词**。
    候选防线:`no_speech_prob` / `avg_logprob` 阈值拒绝、`condition_on_previous_text=False`。
- 判定:对每个 `slots[i].accept` 集合做词边界匹配。**沿用 `scenario.py:223` 已在产的
  正则写法** `(?<![A-Za-z])…(?![A-Za-z])`,避免 "bus" 命中 "business"。多词短语按
  空白归一后整体匹配。
- 计分:必需槽位命中率为主体;非必需槽位只加分,不参与「是否传达到」的判定。
- **不做语法检查。**语序错误、缺冠词、时态错误都不扣 delivery —— 这是 G7 的要求,
  也是整个模块的心理前提。
- **两类「没命中」必须在产品上分开处理**(2026-08-09 代理实测确立):

  | | 成因 | 实测召回 | 正确处置 |
  |---|---|---|---|
  | **(A)** | 学习者**确实没把这个词说出来** | 0.333 | **不给物资是正确行为。** 声音里没有那个音,任何模型都听不到 —— 这是真实语言环境的运作方式 |
  | **(B)** | 学习者说清楚了,**仪器没听见** | 0.876 / 0.917 | **是缺陷。** 由 FR-27 纠正入口兜底,并受 G2 判据约束 |

  判别依据:人类评分者的词级发音判定。代理语料上二者分离得很干净 —— 模型命中的词平均
  专家分 9.77,漏掉的词 7.62(其中 38% 被专家判为发音不合格,命中组仅 3%);
  **模型漏词的位置与人类判「说错了」的位置高度重合**。
  换更大模型只对 (B) 有效(`base.en`→`small.en`:0.876→0.917),对 (A) 几乎无效
  (0.300→0.333)——(A) 是物理上限,不是工程缺口。
- **(A) 类的出路是分诊,不是放宽判定**:学习者点 FR-27 的「我说的不是这个」后,若发音评分
  显示该词确实不合格,则导流到 Speaking 模块。**Survival 管「敢说」,Speaking 管「说准」**,
  纠正入口是二者之间的分诊器。绝不因为学习者说得差就悄悄放宽 accept —— 那等于对最需要
  帮助的人降低标准,且违反 R-14 §0。

### 6.2 fluency —— 说话时间 / 停顿 / 语速(FR-22,离线)

用 `extract_prosody` 返回的 `ProsodyFeatures` **绝对量**:`duration_s`、`num_pauses`、
`total_pause_s`、`articulation_rate`、`f0_std`。

**重要约束:不能用 `prosody.compare_prosody`**(`prosody.py:117`)—— 它的
`intonation_match` / `pause_match` 是与参考录音的相似度,本模块没有参考录音。同理
`score_b.fluency_from_features` 的 `path_dev` 与 `lograte` 两个分量都依赖 DTW 路径,
其 GAM 权重是联合拟合的,**不可只取其中的 `pause_ratio` 分量复用** —— 校准不成立。
本模块的 fluency 需要自己的绝对阈值,阈值来源在 R-14 的 G7 里定。

### 6.3 naturalness —— 云端表达审核(FR-23,可选加成)

- **默认关闭。**关闭时游戏必须完整可玩(NFR-6)。
- 出站数据白名单:**转写文本 + 场景摘要 + 词汇等级**。禁止发送音频、录音、照片、
  设备标识,以及任何 Speaking / Memorizing 模块的数据。
- 门控写法**沿用 FR-11 已确立的「宁缺毋滥 + 自门控」体例**:离线 / 超时 / 异常 /
  低置信 → **不返回该维度,UI 也不显示该维度**,而不是给 0 分。静默降级为纯确定性分。
- 与项目「LLM 不打分」原则的关系:该原则对 Speaking 模块(`feedback.py:5-8`)**一字不改
  继续成立**。本模块的主判据是确定性槽位分;云端审核是可选加成项且不确定时静默,
  因此不构成对该原则既有适用范围的推翻。

### 6.4 pronunciation —— 可选发音轨

`piper_tts.synth_wav(reference_answer)` 合成标准答法作参考 →
`pipeline.analyze_arrays(ref_wav, learner_wav)`(`pipeline.py:58`)。

**FR-M1 边界:**合成音在本模块作为参考音**不违反 FR-M1** —— 沿用 FR-17 已在 PRD 中
确立的同一论证:FR-M1 的范围限定为 Speaking 模块**句子级真实人声跟读**,词汇学习与
游戏场景独立。此论证须在 PRD 的 FR-22 行显式写明,不留隐含冲突。

此轨同样是加成项,失败时静默。

## 7. 词汇分级与扩词

### 7.1 四级初始化(FR-20)

词表已选定并随包:**CEFR-J Wordlist v1.6**(等级 A1–B2)+ **Octanove C1/C2 v1.0**
(补 C1/C2)+ **NGSL 1.2 stats**(SFI 频次排名)。授权逐条核对见
`docs/reviews/2026-08-08-survival-g4-wordlist.md`,署名见
`desktop/backend/assets/wordlists/ATTRIBUTION.md`。

**等级定准入,频次定排序 —— 两种量各司其职,不是二选一:**

| tier | 准入(CEFR 等级) | 说明 |
|---|---|---|
| `infant` | A1 | 入口层,最低准入 |
| `toddler`(默认) | A1 + A2 | 按用户观察,大部分学习者的实际初始水平 |
| `youth` | + B1 | |
| `professional` | + B2(C1/C2 由 Octanove 备用) | |

这张表**已在真实词表上验证过,不是仅有主张**:词表落盘(2026-08-09)后,
`scripts/game_vocab_gate.py` 对全部 **109 个必需槽位**逐一检查「该 tier 的学习者是否
至少有一条说得出来的说法」,结果 **109/109 成立,0 个不可达、0 个无法判定**。

判据是「**存在可达路径**」而不是「每条 `accept` 说法都在纲内」——`accept` 是多选一,
单个超纲同义说法(如 youth 档的 `throat`#B2)不构成缺陷,只要同槽另有 A1/A2 说法。
真正的缺陷形态是**某个必需槽位的全部说法都超出该 tier 上限**:那样的槽位按定义说不出来,
且**调匹配器参数无解**,只能改 `accept` 集合或改该场景的 tier。实测这类为 0。
详见 `docs/reviews/2026-08-08-survival-g4-wordlist.md` §8.3.3(含该检查自身的负向对照)。

**准入只用等级,不用频次排名做切分点。** 这一条是被实测推翻后改的,不是设计偏好:
`scripts/game_provenance_check.py` 在 45 个场景上逐词查 NGSL 排名,结果是频次排名与
本模块的场景难度**方向相反**。

请求构式全部在 NGSL 首百词 —— `can`#38、`want`#76、`give`#77、`need`#90、`may`#97;
而场景真正要求说出的**具体物名却排在很后甚至不在表内**:`bread`#2262、`cup`#1491、
`coat`#1863、`rice`#2695,`toilet` / `soap` / `towel` / `blanket` / `apple` / `fever`
**均不在 NGSL 2,809 词内**。NGSL 是为**阅读覆盖率**而建的 general service list,
它不收的三类恰好是生存场景的高频需求:

1. **基数词**(`two` / `three` / `ten` 全不在表内,而 `one`#35 在)
2. **星期与月份**(整类不收)
3. **低频具体家居物件**(上面那批)

因此**若用频次排名做准入切分,`infant` 档会拿到 `can` / `want` 却拿不到 `bread`** ——
一个能说出请求句式却没有任何东西可请求的词汇库。等级表不存在这个问题:CEFR-J 按教学
习得顺序定级,具体物名在 A1 就有。

频次的用途因此收窄为**排序**,不参与准入:

- 同一等级内先教哪个词(A1 内部按 SFI 排名升序)
- §6 要求「NPC 用词不超出用户词汇库 +N」——那个 N 只有频次能表达,等级是离散桶、
  桶内无序,表达不了「略高一点」
- 词表未收录的词(上述 25 个内容词)**按等级侧定级,频次侧记为无排名**,不得当作
  「最低频」或「最高频」处理

**索引键为 `(headword, pos)`,不是 `headword`。** CEFR-J 同形词按词性拆行
(`can` 既是 A1 modal 又是 A2 noun;`please` 既是 A1 adverb 又是 B1 verb)。
实测:仅 Octanove 一份就有 **121** 条会在裸 `headword` 键下互相覆盖,
而覆盖方向取决于文件读取顺序。NGSL 侧是 lemma,**lemma → `(headword, pos)` 是一对多**,
对齐层须显式处理(同一 lemma 的频次排名附着到共享该 lemma 的每个词性义项)。

### 7.2 为什么必须引入外部词表

仓库内**没有** CEFR 或词频数据。现有两份词表是**检测器实体词表**:

- `desktop/backend/core/yoloe_labels.json` —— 218 个标签,`{labels: {label: {min_score, zh}}}`
- `desktop/backend/core/yoloe_everyday_labels.json` —— 11 个类别的日常物 allowlist

两者**几乎全是名词实体**,撑不起请求句式所需的动词(want / need / give)与功能词
(can / may / please)。因此:**分级骨架必须来自外部词表**,现有词表只提供
**生活化名词锚点**。

### 7.3 词汇库存储

存「已掌握词集 + 来源」,来源三分:

| `source` | 含义 |
|---|---|
| `initial` | 初始化等级带来的词 |
| `observed_npc` | 从 NPC 台词中「观察」到的词(场景 `new_words`) |
| `observed_photo` | 用户上传生活照片、YOLOE 检测出的物品词 |

### 7.4 观察他人扩词(FR-24)

两条来源,第二条**整条链路已在产**,零新增模型:

1. **NPC 台词**:场景 `new_words` 在该场景完成后可被收入。
2. **生活照片**:上传照片 → `vision.detect`(`vision.py:411`) → 物品标签入库。
   与 `POST /memorize/analyze` 同一条链路,同一份预处理契约
   (`memorize_image.canonicalize_upload`,`memorize-image-v1`)。

新词收入后**立即可用于后续交流**,并真实影响 delivery —— 这是「观察→模仿→能力提升」
闭环成立的前提,不是装饰。

## 8. 进度持久化(FR-26)

沿用项目内**唯一**的落盘先例 —— `transcribe.py:167` `_cache_path` 的版本化 JSON
sidecar 体例(`CACHE_VERSION = 5`,`transcribe.py:164`,旧缓存惰性补算)。

- 位置:`NATIVELINGO_DATA_DIR` 下 `game/profile.json`。该环境变量由 Tauri 壳设为
  `~/Library/Application Support/com.nativelingo.app`,dev 下回落到仓库根
  (`video.py:32-47`)。
- 内容:词汇库(含来源)、已完成场景、物资清单、当前需求层级、初始化等级。
- 带 `version` 字段与惰性迁移。
- **纯端侧,无云同步** —— NFR-1 对进度数据完全成立,NFR-6 的联网例外**不覆盖**进度。

**为什么不用 SQLite:**新依赖 + 新约定,而 Android 侧 FR-12 已规划 Room;桌面端先分叉
存储方案会给两端对齐留债。版本化 JSON 是当前仓库已有的、经过实战的模式。

## 9. 端点与前端形态(草案)

### 9.1 端点

| 路由 | 方法 | 用途 |
|---|---|---|
| `/game/state` | GET | 读取进度(词汇库 / 物资 / 需求层级) |
| `/game/scenario` | GET | 按当前需求与等级取场景 |
| `/game/attempt` | POST | 上传录音 → 转写 + 槽位匹配 + 韵律 → delivery / fluency / 物资 |
| `/game/observe` | POST | 扩词(NPC 台词词 或 照片检测词) |
| `/game/review` | POST | 可选云端审核(默认关闭,NFR-6) |

全部沿用既有约定:bearer token 鉴权(`require_token`)、
`_within_memorize_deadline`(`main.py:477`)的 15s deadline → 504 + 可读中文,
模型不可用 → 503。

#### 9.1.1 内测采集版已实现的端点(2026-08-10)

§5.2 放行的内测采集版只实现了上面草案的一个子集。**已实现**:

| 路由 | 方法 | 用途 | 与草案的差异 |
|---|---|---|---|
| `/game/scenario` | GET | 取一条场景(`?tier=&session=`,随机不重复,不做需求层级推进) | 只出中文 `situation_zh` + `npc_greeting` + 槽位中文提示;**扣住**英文 `situation.en` / `reference_answer` / `accept` 集(采集要听真话,不能泄露答案) |
| `/game/attempt` | POST | 录音 → 游戏独立转写(`game_transcribe.py`)→ 槽位匹配 → `delivery` → NPC 三档回应 + 最小物资 → 落盘 → 返回 `attempt_id` | **只出 `delivery`**(G1 判据本身),**不出** fluency / 地道度(红线 3,G7 未测) |
| `/game/attempt/{aid}/correct` | POST | FR-27 词级纠正 → 按纠正文本重判 → 不消耗机会 | 草案里没有,FR-27 新增;`triage_hint` 标 `asr_miss`(delivery 升 ⇒ (B) 类)或 `pronunciation`(⇒ (A) 类,导流 Speaking) |
| `/game/export` | GET | 导出 `delivery_rows` + `asr_manifest`,格式直接喂两个量具 | 草案里没有;`origin` 列留空(人工 attestation),采集路由记在 `collection` 列 |

**未实现**(超出内测范围,受原门约束):
`/game/state`(进度经济,FR-26)、`/game/observe`(照片扩词,FR-24)、
`/game/review`(云端审核,FR-23 / G5 —— 内测期零出站)。

### 9.2 前端

- 新增 `desktop/src/modules/survival.js`,与 `speaking.js` / `memorizing.js`
  **完全同构**:冻结 stage 列表 + `setSurvivalStage(stage, context)` 校验后写
  `document.documentElement.dataset.survivalStage` 供 CSS 使用。
- `desktop/src/modules/shell.js:19` 的
  `moduleIcons = { speaking: "speaking", memorize: "camera" }` 需要第三个键。
- `desktop/src/index.html` 第 31 / 34 行的 `data-module` 按钮增加第三个入口,
  并新增对应 `.module-pane`。
- 沿用 `main.js` 已在用的**单调 cancel-token** 模式(进入时自增、每次 await 后比对)
  丢弃过期异步结果。
- HTTP 一律走 `modules/runtime.js`(`apiFetch` / `deadlineFetch` / `ApiError`),
  按 FRONTEND_DESIGN.md §13 不得在 `main.js` 复制鉴权或超时逻辑。

### 9.3 模块隔离(FR-19)

游戏的本地依赖是 whisper `base.en`(已在产)+ Parselmouth 韵律 + 可选 Piper / SSL 编码器。
**不持有 Florence 与 Qwen。**

这一条不是巧合而是硬约束:`memorize_warmup` 的 generation-token 设计
(`memorize_warmup.py:37`)假设**单一 owner**,两个模块各自 `start()` / `release()`
会互相拆台(Florence + Qwen 合计约 950MB,`release()` 存在的理由就是它们放不下)。
游戏与 Memorizing **没有共用模型**,因此不引入 warmup 竞争。R-14 的 **G6** 把这条设为
可测门。

## 10. 视觉

游戏是 `docs/FRONTEND_DESIGN.md` §17 定义的**独立视觉域**。§1「不是游戏化打卡产品」与
§3 的禁令继续对跟读 / 识物完整成立;游戏域获得**逐项封闭列举**的例外,且不得外溢。
可访问性(§12)、设计令牌(§4)、工程边界(§13)、后端契约(§14)对游戏域完整适用。

## 11. 已知设计张力

如实记录,不掩盖:

1. **确定性槽位匹配奖励「命中预设表达」,结构性地奖励不了创造性表达。**云端审核
   (§6.3)正是为补这个缺口而存在 —— 但它默认关闭,所以**离线玩法的可玩性上限由
   场景库覆盖度(G3)与槽位判准质量(G1)决定**,而不是由审核质量决定。
2. **离线时没有语义兜底。**本地 Qwen2.5-0.5B 判断力不足,不承担审核裁判角色;离线路径
   只有槽位匹配。这是有意的取舍,不是遗漏。
3. **场景库是人工内容,规模是长期成本。**G3 要求 ≥40 个场景覆盖需求金字塔前三层,
   这是持续投入而非一次性交付。
4. **转写层不是完美输入,而且它的错误对最需要帮助的人最不利。**(2026-08-09 代理实测)
   `base.en` 在真人 L2 短句上的关键词召回,现行解码配置下只有 **0.707**;修好解码配置
   (beam5 + accept 作 hotwords)并按发音合格词口径计,升到 **0.876**(`small.en` 0.917)。
   但**仪器缺陷在发音较差的人身上更集中**,这一层不因调优而消失。
   直接后果:**FR-27 纠正入口是判准链路的必需件,不是上线后的监控手段**。
5. **G1/G2 的目标语料只能从真实用户那里来,这是个鸡生蛋问题,已接受。**
   合成音被禁(无 L2 口音、无不流畅、无环境噪声),公开代理语料只能证伪不能证实
   (词汇更常见、照稿朗读、L1 单一,三个维度都更容易)。因此 G1/G2 的**通过**只能等内测
   录音。**已定的取法**:先按代理口径把已知缺陷修掉,内测期用 FR-27 收集语料,回来重测。
   代理数字**永不回填为通过**(`game_asr_gate.py --proxy-corpus` 在代码层面就不输出 PASS)。
6. **FR-27 的纠正记录是自选择样本,不能当作错误率的无偏估计。**
   只有自认说对了的学习者才会点纠正,故它**系统性低估**真实错误率,且恰恰在最需要帮助的
   初学者身上低估最多。它只能用作**语料来源**与**单条分诊**,不得用来反推 G2 的召回。
7. **whisper 幻觉是已实测的失效模式,且比丢词更危险。**
   实测输入 `WHAT WOULD IT BE LIKE THEN`(专家满分)被转写成
   `I will see you in the next video`。丢词只是不给物资;幻觉会让槽位匹配**命中学习者
   根本没说的词** —— 即 G1 的假阳性从转写层被注入,而 G1 明确 precision 优先。
   实现期必须有防线,并在 G1 harness 里单独统计幻觉致伪命中。

## 12. 不在设计范围

- 分级词表的实际选定与打包(需先过 G4 授权核实)
- DeepSeek API key 的存储方案(需 R-14 通过后单独设计)
- 场景库的实际内容编写(本文档只给 schema 与 2 条示例)
- Android 侧实现(按 CLAUDE.md §2,macOS 线新功能不混入 `android` 分支)
