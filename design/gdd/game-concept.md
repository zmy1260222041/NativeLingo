# Game Concept: 异乡人 / Stranger

*Created: 2026-08-10*
*Status: Approved for vertical-slice pre-production*

---

## Elevator Pitch

> 《异乡人》是一款单人 3D 第三人称社交生存 RPG。玩家以寄居外星聚落的弃儿身份，
> 通过敏捷探索、解决日常生存问题，并在交易、求助和谈判时真正开口说英语，从无人照料的
> 异乡人成长为聚落不可缺少的一员。

## Core Identity

| Aspect | Detail |
| --- | --- |
| **Genre** | 3D 第三人称社交生存 RPG / 剧情冒险 |
| **Platform** | PC 桌面端；macOS 优先，架构保留 Windows 导出路径 |
| **Target Audience** | 13 岁以上、已有基础英语但害怕开口的中文母语玩家 |
| **Player Count** | 单人 |
| **Session Length** | 30–60 分钟；纵切完整时长约 90–150 分钟 |
| **Monetization** | 买断制，无订阅、广告或付费体力 |
| **Estimated Scope** | Large（完整愿景个人开发约 24–36 个月；六个月纵切先行） |
| **Comparable Titles** | Noun Town、My Time at Sandrock、Terra Alia |

## Core Fantasy

玩家不是在做语言练习，而是在一个陌生文明中真正靠观察、行动和表达活下来。起初没有人
有义务照顾玩家；每一份食物、每一个落脚点和每一次被信任，都来自玩家对世界的理解与
对人物的长期投入。最终的力量幻想不是战胜所有敌人，而是从无法被理解的异乡人成长为
能理解别人、也被整个聚落理解的人。

## Unique Hook

没有传统对话轮盘。玩家在高价值社交节点真正开口，NPC 根据意思是否传达到做出物资、
承诺和关系反馈；表达不完整或识别失败不会扣好感，NPC 会以指物、点头、摇头和免费重说
把交流继续留在游戏世界里。

## Visual Identity Anchor

**Direction: 千禧年代外星动画冒险**

**One-line rule:** 每个角色和场景必须在剪影上活泼、在颜色上亲切、在细节上陌生。

1. **弹性剪影**：角色采用夸张比例、清晰肢体动作和强表情；远距离也能凭轮廓识别。
   *Design test:* 如果动画只能靠字幕解释情绪，表演与轮廓需要重做。
2. **熟悉生活的异星变体**：市场、火炉、住所等功能一眼可懂，但形体、材料和生态细节
   不照搬地球。
   *Design test:* 先保证玩家能理解用途，再加入陌生感。
3. **昼夜情绪变色**：白天以珊瑚橙、青绿和暖黄表达接纳；夜晚以靛蓝、紫色和生物荧光
   表达生存压力。
   *Design test:* 不看 HUD 也应能判断一天的情绪与危险程度。

参考《星际宝贝》和《Ben 10》的动画活力与外星童话感，但不复制其角色、标志性生物、
服装、道具或具体造型。3D 采用卡通渲染、适度轮廓线和手绘感渐变材质。

## Player Experience Analysis (MDA Framework)

### Target Aesthetics

| Aesthetic | Priority | How We Deliver It |
| --- | ---: | --- |
| **Challenge** | 1 | 时间、路线、需求和承诺管理；语言尝试本身不受罚 |
| **Narrative** | 2 | 跨年龄成长、身份谜团、NPC 长期记忆 |
| **Fantasy** | 3 | 在陌生文明中凭行动与表达获得归属 |
| **Discovery** | 4 | 聚落日程、人物习惯、环境词汇与隐藏路线 |
| **Fellowship** | 5 | 与五名关键 NPC 建立可靠关系网络 |
| **Sensation** | 6 | 敏捷移动、强动画轮廓、昼夜色彩和环境声 |
| **Expression** | 7 | 用玩家自己的粗糙英语表达同一意图 |
| **Submission** | 8 | 日终回家、整理背包和关系结算提供恢复节奏 |

### Key Dynamics

- 玩家会根据 NPC 日程规划路线，而不是追逐地图问号。
- 玩家会观察物品、动作与上下文，再决定向谁开口以及怎样表达。
- 玩家会为了保住承诺主动调整资源计划，逐渐把人物关系视为生存基础设施。
- 玩家会用更短、更可靠的表达开始交流，并随着能力增长主动尝试更丰富的说法。

### Core Mechanics

1. 第三人称移动、镜头、跳跃、观察和环境交互。
2. 时间推进、食物/保暖/住所需求与昏倒恢复。
3. NPC 日程、个人信任、承诺和持久记忆。
4. 情境化语音表达、确定性语义槽位判定与手势澄清。
5. 三日任务弧、背包、物资奖励与版本化存档。

## Player Motivation Profile

### Primary Psychological Needs Served

| Need | How This Game Satisfies It | Strength |
| --- | --- | --- |
| **Autonomy** | 同一需求可通过不同人物、路线和粗糙表达解决 | Core |
| **Competence** | 移动、资源规划与交流都从依赖提示逐步转为自主 | Core |
| **Relatedness** | NPC 记得帮助、承诺和误会，关系会跨日改变生存条件 | Core |

### Player Type Appeal

- [x] **Achievers**：完成日目标、稳定需求、解锁住所与成长阶段。
- [x] **Explorers**：理解聚落结构、NPC 日程和隐藏环境线索。
- [x] **Socializers / Storytellers**：经营人物关系并见证跨年龄故事。
- [ ] **Killers / Competitors**：无 PvP、排行榜或支配型玩法。

### Flow State Design

- **Onboarding curve**：前十分钟只教移动、观察、拾取和一次无代价的求食交流。
- **Difficulty scaling**：先增加路线与时间压力，再增加表达槽位；绝不靠提高识别苛刻度。
- **Feedback clarity**：NPC 动作、实物、关系行为和世界状态承担主要反馈，数字不成为焦点。
- **Recovery from failure**：语言可立即重说；生存失败回到安全点并推进时间，不回滚关系剧情。

## Core Loop

### Moment-to-Moment (30 seconds)

奔跑、调整镜头、跳过矮障碍、观察角色和物品、拾取资源、避开环境危险。移动必须在没有
任务或语言输入时也具有响应快、路线可读和镜头稳定的基本乐趣。

### Short-Term (5–15 minutes)

发现需求或承诺，寻找合适 NPC，观察其行为和附近物品获得语境，开口求助或交易，处理
NPC 的实物/手势澄清，得到物资与关系结果，再决定下一条路线。

### Session-Level (30–60 minutes)

经历聚落的一天：08:00 出门，完成一条主要人物任务和若干资源选择，22:00 前满足关键
需求并返回住所。日终结算关系、承诺和身份线索，形成自然停止点。

### Long-Term Progression

完整作品跨幼年、儿童后期、青年和成年四阶段。成长改变移动能力、可进入区域、社会身份、
任务责任和英语表达复杂度；纵切只实现第一个幼年阶段，但数据结构从第一天支持阶段字段。

### Retention Hooks

- **Curiosity**：玩家的人类意识来源、被遗弃原因和聚落历史。
- **Investment**：NPC 关系、住所改善、承诺和已建立的安全路线。
- **Social**：人物跨日记忆与关系事件，不依赖联网社交。
- **Mastery**：更高效的资源路线、更少提示的交流和更复杂的社会任务。

## Game Pillars

### Pillar 1: 先行动，后开口

玩家首先是在 3D 世界里探索与生存；语音只出现在值得开口的关键互动。

*Design test:* 教学内容能做成世界行为时，不用文本卡片呈现。

### Pillar 2: 生存有压力，表达无羞耻

饥饿、寒冷和时间会带来后果，但说得不完整、语法不完美或识别失败不会损失关系。

*Design test:* 惩罚可以来自路线和资源决策，不能来自一次英语尝试。

### Pillar 3: 关系就是生存资源

NPC 记得帮助、承诺和沟通结果；住所、工作与安全来自长期信任。

*Design test:* 重要奖励优先由人物关系解锁，而不是匿名商店或经验条。

### Pillar 4: 成长必须在世界中可见

语言能力、年龄、行动能力、社会身份和区域开放共同成长。

*Design test:* 升级必须改变玩家能做的事和别人如何对待玩家。

### Pillar 5: 小聚落，深模拟

首版用一个可反复游玩的聚落和五名人物制造深度，不追求无缝大世界。

*Design test:* 优先让现有地点产生新状态，不用空地图代替系统深度。

### Anti-Pillars

- **NOT 文本练习换皮**：它违背“先行动，后开口”。
- **NOT 战斗刷装 RPG**：它会稀释社交生存和语言情境。
- **NOT 因语言错误惩罚玩家**：它会重新制造开口焦虑。
- **NOT 首版无缝大世界**：它会牺牲 NPC 深度和六个月交付目标。

## Inspiration and References

| Reference | What We Take From It | What We Do Differently | Why It Matters |
| --- | --- | --- | --- |
| Noun Town | 世界化词汇、语音 NPC、关系成长 | 语言服务于生存承诺，不做词汇小游戏集合 | 验证玩家愿意在可探索世界中开口 |
| My Time at Sandrock | 第三人称聚落、日程、人物关系 | 不做大规模建造和战斗，关系直接影响生存 | 验证小聚落可承载长期人物投入 |
| Terra Alia | 语言学习与 RPG 叙事结合 | 避免单词匹配、频繁战斗和无意义跑图 | 提供明确反例边界 |

**Non-game inspirations:** 千禧年代电视动画的外星冒险活力、移民初到陌生社区的生活经验、
儿童通过观察与模仿获得语言和归属的过程。

## Target Player Profile

| Attribute | Detail |
| --- | --- |
| **Age range** | 13+；核心为青少年和成年英语学习者 |
| **Gaming experience** | Casual 至 Mid-core |
| **Time availability** | 工作日 30–60 分钟，周末可连续完成两天 |
| **Platform preference** | PC 桌面端，键鼠或手柄 |
| **Current games they play** | 社交 RPG、叙事冒险、轻量生存或生活模拟 |
| **What they're looking for** | 真正可玩的冒险，以及安全但有意义的开口环境 |
| **What would turn them away** | 作业感、频繁文本测验、ASR 误判惩罚、重复跑图与强制刷怪 |

## Technical Considerations

| Consideration | Assessment |
| --- | --- |
| **Recommended Engine** | Godot 4.6 / GDScript；适合个人开发的原生 3D 场景、物理、导航和导出 |
| **Key Technical Challenges** | Godot 与本地 Python ASR sidecar 的启动、鉴权、音频上传和打包 |
| **Art Style** | 原创风格化 3D 卡通外星童话 |
| **Art Pipeline Complexity** | Medium；现成授权资产 + 原创轮廓、材质、配色和动画改造 |
| **Audio Needs** | Moderate；环境、角色拟声、反馈、英语 NPC 语音与麦克风输入 |
| **Networking** | 无；只允许随机端口的 localhost sidecar |
| **Content Volume** | 纵切 1 聚落/5 NPC/3 天；完整愿景 4 阶段/8–12 小时 |
| **Procedural Systems** | 无程序化世界；只允许数据驱动的日程与事件条件组合 |

## Risks and Open Questions

### Design Risks

- ASR 偶发误识别可能破坏“NPC 真正在听”的关系幻想。
- 三类需求与五名 NPC 的组合可能在第二天后失去新鲜感。
- 生存压力过轻会失去挑战，过重又会压倒安全表达空间。

### Technical Risks

- 原生 Godot 进程与 PyInstaller sidecar 的跨平台生命周期尚未验证。
- 麦克风编码格式、15 秒转写预算与游戏主线程响应需要端到端原型。
- 当前后端入口加载了不属于游戏的模型，需要精简服务避免高内存和长启动。

### Market Risks

- 教育标签可能让 RPG 玩家预判为练习软件。
- 风格化青少年视觉与成人语言学习者之间需要试玩验证。

### Scope Risks

- 五名 NPC 的原创模型、动画、日程、任务和关系记忆容易形成内容组合爆炸。
- 四年龄阶段只属于完整愿景，若提前进入纵切会直接破坏六个月目标。

### Open Questions

- 玩家是否会在 30 分钟后仍觉得“探索 → 开口 → 关系回报”有趣？用三日纵切试玩回答。
- 手势澄清是否比字幕编辑更自然且不降低语料价值？用语音桥接原型回答。
- 现成资产能否统一成原创动画风格？用一个角色和一个市场角落的 art test 回答。

## MVP Definition

**Core hypothesis:** 玩家愿意连续玩完三天，因为“探索获得上下文 → 开口完成关键社交 →
关系帮助生存”的循环本身有趣，而不是因为外部学习奖励。

**Required for MVP:**

1. 稳定且有基本乐趣的第三人称移动、镜头、观察和拾取。
2. 一名 NPC、一种需求、一次真实语音请求与手势澄清。
3. 一次关系记忆回报：NPC 在稍后场景中根据前次互动改变行为。

**Explicitly NOT in MVP:**

- 四年龄阶段、完整身份谜团、复杂建造和战斗。
- 五名 NPC 的全部任务、最终美术、完整英语课程覆盖。

### Scope Tiers

| Tier | Content | Features | Timeline |
| --- | --- | --- | --- |
| **MVP** | 市场角落、1 NPC、1 需求、约 15 分钟 | 移动、交互、语音、一次关系回报 | 6–8 周 |
| **Vertical Slice** | 1 聚落、5 NPC、3 天、90–150 分钟 | 三类需求、日程、关系、任务、存档、统一美术 | 6 个月 |
| **Alpha** | 四阶段主线全部可通，资产可占位 | 所有核心系统和内容路径 | 18–24 个月 |
| **Full Vision** | 四阶段、8–12 小时、完整原创表现 | 打磨、可访问性、平台导出和完整 QA | 24–36 个月 |

## Next Steps

- [x] `/setup-engine` 固定 Godot 4.6、GDScript 与导出目标
- [ ] `/art-bible` 完成视觉身份规范
- [ ] `/design-review design/gdd/game-concept.md`
- [ ] 通过 `ccgs-agent-router` 执行 creative-director 复核
- [x] `/map-systems` 创建系统依赖图与 systems-index
- [ ] `/design-system` 按依赖顺序编写系统 GDD
- [x] `/create-architecture` 创建主架构（ADR 列表已建立，正式 ADR 待补）
- [ ] `/gate-check pre-production`
- [ ] `/prototype spoken-social-survival-loop`
- [ ] `/playtest-report`
- [ ] `/sprint-plan new`
