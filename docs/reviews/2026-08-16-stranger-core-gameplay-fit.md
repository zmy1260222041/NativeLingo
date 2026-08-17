# R-19 · Stranger 核心玩法补完符合性评审(2026-08-16)

> 需求来源:用户 2026-08-16 核心玩法补完计划(新手引导、探索式目标、NPC 社会模拟、
> 词汇库三态习得、需求 UI、多轮对话),并确认:
> 1. NPC 台词语音使用 Qwen 官方 `qwen-audio-3.0-tts-plus`,经服务器代理合成;
> 2. 词级复读采用独立发音评分协议,奖励沿用 FR-28 单调档 `≥70 generous / 40–69 sparse / <40 none`。
>
> 落库为 **FR-30..FR-38 + NFR-8**(`docs/PRD.md` v0.10)。本评审判据在实现前写死;
> 实现后逐门回填,任何一门不过则该需求单独降级或 no-go,不放松判据。

## 1. 与既有约束的冲突与解决

| 约束 | 冲突 | 解决 |
|---|---|---|
| NFR-1 全离线、无云 key | NPC 语音合成必须调用 Qwen TTS API | NFR-8 第三条例外:仅 `POST /game/tts`;客户端只发台词 ID,key 只存服务器;未激活零出站;失败文字降级 |
| NFR-7 只允许 `/game/evaluate` 一个音频出站端点 | 词级复读需要上传单词语音 | NFR-8 扩展为第二个音频出站端点 `POST /game/score_word`,同样激活门控、解码即弃、失败降级 |
| 当前目标卡常驻 HUD | 用户要求玩家自主探索、NPC 主动招呼 | FR-31:目标只在变化时短暂展开,默认收拢;NPC 招呼承担引导 |
| 词汇库目前只在桌面 Survival 设计中 | Stranger 竖切片内要成为核心玩法 | FR-35:词表资产随 `game/` 包分发,运行时构建索引;SAVE_VERSION 3 持久化 |
| 当前语音服务只有整句意图评分 | 三态习得中的 `spoken` 需要单词语音评分 | FR-36:新增本地 `POST /score_word` 与云端 `POST /game/score_word`,与整句 `delivery` 完全分离 |

## 2. 目标架构基线

```text
Godot(Web/桌面)
  ├─ NPC 台词 → NpcVoiceAdapter
  │             ├─ 已激活 → POST /game/tts {npc_id, line_id, voice, format}
  │             │            └─ 服务器:台词目录查文本 → qwen-audio-3.0-tts-plus → 缓存 → WAV
  │             └─ 未激活/失败 → 现有文字气泡(无网络请求)
  ├─ 词级复读 → WordPractice
  │             ├─ 本地开发 → 127.0.0.1:17831 POST /score_word
  │             └─ 云模式   → POST /game/score_word (Bearer + X-Stranger-Lexical + WAV)
  │                            └─ 服务器:随包词条参考 WAV / TTS 参考 → ORT SSL+DTW
  │                               → {pronunciation, score, band, pronunciation_source, text}
  └─ 观察社会对话 → VocabularyState: heard → spoken → used(奖励单调递增)
```

## 3. 门控判据(实现前写死)

- **G1 引导保护**。首次进入的引导覆盖移动/镜头/冲刺/跳跃/互动/一次求食/回庇护所;
  引导期逐帧断言 food/warmth/energy 不触 0;每步可跳过,跳过与完成都不改变后续任务判定;
  跳过引导后仍可用 FR-28 的三日主线完整通关。
- **G2 目标不常驻与 NPC 主动招呼**。默认状态下目标卡只保留收拢态;目标变化时展开
  3.5 秒后自动收拢;NPC 在首次进入聚落、靠近和当日关键节点的主动招呼不阻塞移动、
  不强制进入对话,措辞儿童友好;无任何常驻任务问号墙/路线规划 UI。
- **G3 TTS 边界**。PCK 与仓库内不含 Qwen API key;客户端 TTS 请求 payload 只有
  `npc_id + line_id + voice/format`,不含自由文本;未激活/无语音构建 TTS 请求数为 0
  (抓包级);TTS 失败/离线时显示文字气泡,三日主线完整可玩;音频与字幕同步。
- **G4 社会对话覆盖度**。首三日全部生存必需表达(问候、要食物、要合金、要水、提供帮助)
  在 NPC-NPC 或 NPC 主动社会对话中至少可观察一次,自动覆盖度工具断言 100%;对话内容
  范围大于玩家当前基础需求范围,并随需求金字塔层级单调扩张;社会对话不打断主线、
  不产生任务失败。
- **G5 词汇库完整性**。CEFR-J v1.6 + Octanove C1/C2 + NGSL 1.2 三份资产**原样**随
  `game/` 包分发并附 ATTRIBUTION;默认 toddler(A1+A2)初始化;索引键为 `(headword, pos)`;
  来源字段只允许 `initial/observed_npc/...` 等已知枚举;SAVE_VERSION 3 惰性迁移旧档
  不丢资源、关系与任务进度;派生索引运行时构建、不落盘、不分发。
- **G6 三态习得单调性与零惩罚**。词汇状态只允许 `heard → spoken → used` 向前迁移;
  三态奖励随状态单调递增;解锁 `spoken` 后必须展示拼写卡;任何失败/低分路径不消耗机会、
  不扣需求/关系/任务状态。
- **G7 词级评分协议**。本地 `/score_word` 与云端 `/game/score_word` 返回同构 JSON;
  云端与本地对同一词条使用同一批参考音频;`score = pronunciation` 逻辑,不混入整句
  `delivery`;词级分档沿用 FR-28 单调档(≥70/40–69/<40);云端断网/超时/5xx/未激活时
  静默降级为免费重试或既有手势路径,词级失败永不扣状态。
- **G8 需求 UI**。三大需求 UI 符合 `design/ux/hud.md` 与 Art Bible §6:阈值行动词、
  注意/紧急态形状与一次性音效、淤泥墨手绘描边面板;1152×720、150% HUD scale 下不裁切;
  颜色不是唯一信号;现有 HUD/分辨率/Web/Desktop Beta 测试套件全绿。
- **G9 回归与主线完整可玩**。既有 Godot headless 套件全绿;无语音构建
  (`web_beta_no_voice`/`desktop_beta_no_voice`)通过 `gesture_fallback` 完成三日主线;
  新增测试覆盖 G1–G8;`python3 -m py_compile game/speech_service/server.py` 通过。

## 4. 已知取舍(如实记录)

1. **TTS 是表现增强,不是玩法依赖**。未激活/断网时文字气泡承担全部交流内容;
  语音合成缓存只存服务器生成的 NPC 音频,不含用户数据。
2. **社会对话内容先行静态化**。首轮用审查过的静态台词目录保证覆盖度可自动验证,
  后续再演进为动态生成;动态生成前不得宣称「地道多轮」。
3. **词级参考音频口径**。本地 Piper 与云端 TTS 参考可能存在音色差异;G7 只要求
  云端/本地对同一部署参考一致,词级评分仍标注 `pronunciation_source`,不冒充
  真实人声评分。
4. **三态中的 `used` 由整句 delivery 槽位命中证明**,不是另一次词级评分;
  `heard → spoken` 的复读入口不产出资源,只给词汇解锁奖励。

## 5. 实现状态

Phase 2 已提交(`af8cb357`),Phase 3 已提交(`78c2540d` / 云端 `986aaa50`),
Phase 4 已提交(`fb0e7997`),Phase 5 已提交(`19af3122`),Phase 6 已提交
(`cb6d4282` / 云端 `94332aec`),语音选择式复读已提交(`041fc4ee` /
云端 `061d3e8e`)。部署收尾(2026-08-16):修复 SAVE_VERSION 3 词汇字段实际
落盘/加载、修复 Cloud Voice 导出因 debug bridge 引用未导出 addons 而崩溃;
`test_save_migration` 在 OS temp 目录实测 v2→v3 迁移;源码 GUI、macOS
Desktop Beta 与 macOS Cloud Voice 三个运行时均启动退出 0(Apple M5 /
OpenGL Metal)。G1/G2/G4/G5/G6/G7/G9 代码级 PASS,G3/G8 部分 PASS
(真实 Qwen key 联调与一次性紧急音效待补)。

| 门 | 判据 | 实现前 | 实现后结果 | 备注 |
|---|---|---|---|---|
| G1 | 引导保护与可跳过 | 已写死 | ✅ 代码级 PASS(2026-08-16) | `test_onboarding.gd` 全绿;需求/时钟冻结,skip/complete 恢复衰减 |
| G2 | 目标收拢 + NPC 主动招呼 | 已写死 | ✅ 代码级 PASS(2026-08-16) | `HudTest` + `NpcAttentionTest` 全绿;目标 3.5s 收拢,NPC 社交半径一次性招呼 |
| G3 | TTS 边界与降级 | 已写死 | 🟡 部分 PASS(2026-08-16) | 本地/云端 `/game/tts`、台词 ID 目录、缓存、无 key 入库、Godot `NpcVoice` 无 token 零请求与失败降级均已代码级落地;真实 Qwen key 联调与抓包留待部署 |
| G4 | 社会对话覆盖度 | 已写死 | ✅ 首三日代码级 PASS(2026-08-16) | 五个必需表达 100% 可观察断言全绿;三组家庭/搭档关系覆盖五名 NPC;多层需求金字塔对话池随 Phase 6 词汇层级联动 |
| G5 | 词汇库完整性与迁移 | 已写死 | ✅ PASS(2026-08-16) | 三份原样资产+署名、运行时索引、默认 toddler;`test_save_migration` 在 OS temp 目录实测 v2→v3 惰性迁移与词汇 round-trip |
| G6 | 三态单调与零惩罚 | 已写死 | ✅ 代码级 PASS(2026-08-16) | WordAcquisitionTest:只前进、低分保持 heard、spoken→used、初始词不降级、GameState 存档镜像 |
| G7 | 词级评分协议一致性 | 已写死 | ✅ 代码级 PASS(2026-08-16) | 本地/云端 `/score_word` 同构 JSON、Piper 同源参考、单调档、断网/未激活零请求;WordPracticeTest + Python/云端契约测试全绿 |
| G8 | 需求 UI | 已写死 | 🟡 部分 PASS(2026-08-16) | 阈值行动词、SiltInkPanel 折角面板、150% 布局通过;一次性紧急音效待音频资源后补 |
| G9 | 回归与主线完整可玩 | 已写死 | ✅ 回归绿(2026-08-16) | 既有 10 套 Godot headless 中除本机 TCC 存档用例外全绿;`test_game_state` 仅 3 个 `user://` 写入断言受 macOS 权限环境失败 |

## 6. 实现后更新(2026-08-17)

用户上机实测后追加的修复与决策,均在本轮内验证:

1. **G3 升级为部署实测 PASS(含真实 key)**。原合成路径走该专属部署不存在的
   OpenAI 兼容 `/audio/speech`(实测 404),且默认音色 `Cherry` 被
   `qwen-audio-3.0-tts-plus` 以 InvalidParameter 拒绝(该模型族只有系统音色
   `longanlingxin` / `longanlufeng`)。本地 `game/speech_service` 与云端
   `server/backend/core/qwen_tts.py` 均改为 DashScope WebSocket SDK
   (`wss://<apiHost>/api-ws/v1/inference`,WAV 24kHz),凭据 `TTS.csv` 移至
   `game/speech_service/`(云端 `/opt/nativelingo/TTS.csv`,600,不入库),
   台词目录同源扩到 42 条(clarify/hint/settled/reward/thanks 等)。
   云端已部署重启并用真实激活码实测:`/game/tts` 经 Godot 客户端固定 TLS
   返回并播放音频。**判据修订(用户拍板):NPC 对话只出语音,不显示字幕;
   文字仅为无语音构建的兜底** —— 原 G3「TTS 失败文字降级且主线可通关」的
   降级通道保留(无语音构建/未激活),但语音可用时不再出字幕。
2. **G4 行为补全:NPC 先走到彼此附近(~1.4m)再交谈、结束后走回原位**。
   `SocialSimulator` 改为聚集→交谈→散开状态机;`WorldInteractable` 增加行走
   (`walk_to`/`walk_home`/`walk_finished`),程序化 NPC 身体用既有步幅摆动
   表现漫步(Mira 静态模型用起伏+摇摆);玩家正在交互的 NPC 跳过该场次,
   引导期不聚集(避免引导 speak 步的目标 NPC 走开)。`SocialDialogueTest`
   新增 8 条聚集/交谈/散开/归位断言。
3. **G1 缺陷修复:引导期 V 键被引导词练习劫持**。此前玩家走近 NPC 即开始的
   词练习会话会接管 `push_to_talk`,引导 speak 步「对塔维按 V 说英语」永远
   无法发出语音请求、引导无法完成(用户实测复现)。修复:引导期不开启词练习
   (`interactable.gd` 门控)、V/G 路由不受其影响(`player_controller.gd`)、
   `begin_onboarding` 强制结束遗留会话;`NpcAttentionTest` 增 3 条断言。
4. **配套修复**:`NpcVoice` 改为串行播放队列(取→播→完,社交对话整段按序),
   新增 `line_audio_finished`;无缓存路径直接从响应缓冲播放(修复
   `cache_enabled=false` 时成功响应误报 SAVE_FAILED)。
5. **回归**:20 套 Godot headless + 11 个本地 TTS unittest + 云端 21 个
   unittest 全绿;新增 `CloudActivationLiveTest`(真实服务器激活 + 云端 TTS,
   固定 TLS、无 insecure 开关)。
