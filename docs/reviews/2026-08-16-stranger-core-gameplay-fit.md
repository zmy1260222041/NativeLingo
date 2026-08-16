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

Phase 2 已完成代码级实现(未提交):FR-30 新手引导、FR-31 目标收拢与 NPC 主动招呼、
FR-37 需求 UI 的第一批改动。G1/G2 代码级 PASS,G8 部分 PASS(一次性紧急音效待音频
资源后补),G9 回归绿(仅 `test_game_state` 的 3 个存档断言受本机 macOS TCC 权限
失败,与本次改动无关)。后续按计划 Phase 3–6 实现并逐门回填。

| 门 | 判据 | 实现前 | 实现后结果 | 备注 |
|---|---|---|---|---|
| G1 | 引导保护与可跳过 | 已写死 | ✅ 代码级 PASS(2026-08-16) | `test_onboarding.gd` 全绿;需求/时钟冻结,skip/complete 恢复衰减 |
| G2 | 目标收拢 + NPC 主动招呼 | 已写死 | ✅ 代码级 PASS(2026-08-16) | `HudTest` + `NpcAttentionTest` 全绿;目标 3.5s 收拢,NPC 社交半径一次性招呼 |
| G3 | TTS 边界与降级 | 已写死 | 待实现 | |
| G4 | 社会对话覆盖度 | 已写死 | 待实现 | |
| G5 | 词汇库完整性与迁移 | 已写死 | 待实现 | |
| G6 | 三态单调与零惩罚 | 已写死 | 待实现 | |
| G7 | 词级评分协议一致性 | 已写死 | 待实现 | |
| G8 | 需求 UI | 已写死 | 🟡 部分 PASS(2026-08-16) | 阈值行动词、SiltInkPanel 折角面板、150% 布局通过;一次性紧急音效待音频资源后补 |
| G9 | 回归与主线完整可玩 | 已写死 | ✅ 回归绿(2026-08-16) | 既有 10 套 Godot headless 中除本机 TCC 存档用例外全绿;`test_game_state` 仅 3 个 `user://` 写入断言受 macOS 权限环境失败 |
