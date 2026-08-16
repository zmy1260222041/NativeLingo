# R-17 · Stranger 竖切片语音门控物资符合性评审(2026-08-15)

> 需求来源:用户指示「改进当前任务主线,进行语音交流才能获取资源。NPC 根据语音表达
> 效果,判断发音是否准,传达出来的意思是否明确。表达效果越差,给出的资源越少」。
> 落库为 **FR-28**(`docs/PRD.md` §4 / §6 / §7)。
> 本评审覆盖 `game/`(Godot 4.6.3 `Stranger` 竖切片)与 `game/speech_service/`。
> 判据在实现开始之前写死;实现完成后回填 §6。

## 1. 范围

- **改**:三日主线资源获取路径(食物/零件/水)、NPC 语音判定协议、语音服务评分、
  `GameState` 分档奖励与存档版本、HUD 文案与本地化。
- **不改**:桌面 Survival 模块(FR-19..FR-27)的槽位判定、`game_eval.py`、45 个
  场景 JSON、Android 分支;Web/Desktop Beta 无语音构建的**完整可玩**承诺;
  Godot 移动/镜头/跳跃等既有系统。

## 2. 与既有约束的冲突与解决

| 既有约束 | 本次变化 | 解决方式 |
|---|---|---|
| FR-25:表达效果决定物资,分档给、低档不给但不消耗机会 | 竖切片此前从拾取物直接拿资源,不经过表达判定 | 拾取物改为引导物;资源只经 NPC 语音请求获得,分档沿用 FR-25 体例 |
| 仓库约定:「语音服务不可用时手势兜底完整可玩」 | 若手势完全不产出资源,无语音构建无法通关 | `gesture_fallback` 通道在**无语音能力**时给最低生存档;有语音能力时普通手势只表达善意、不产出资源 |
| Survival 设计:「循环里没有失败出口、错误不惩罚」 | 「表达越差资源越少」有惩罚化风险 | 低于最低档只是**这次没有收获**:不扣需求、不伤关系、不消耗次数,可立即免费重说 |
| FR-22 发音评分口径:主判据是确定性 delivery,发音轨是可选项 | 用户明确要求 NPC 判断「发音是否准」 | 发音分独立成维,权重 50%;参考评分器可用时用 SSL+DTW,不可用时用 Whisper 声学置信度兜底并在结果中显式标注来源 |

## 3. 门控判据(实现前写死)

- **G1 语音门控**。在 `SpeechAdapter.is_available() == true` 的运行态:
  `interact("berry"|"scrap"|"water", …)` 不得改变 `food/berries/scrap/water/warmth/energy`
  任一资源或需求值;只有 `interact("npc", <供给者>, "voice", <有效表达>)` 可以加资源。
  判据形态:headless 测试逐交互断言状态向量不变。
- **G2 表达分双维**。服务返回 `pronunciation` 与 `delivery` 两个 0–100 分,
  `score = 0.5×pronunciation + 0.5×delivery`;`pronunciation_source` 必须是
  `"reference_dtw"` 或 `"whisper_confidence"` 之一,不得把兜底标成参考评分。
  `delivery` 用词边界槽位匹配(大小写不敏感、多词 accept 按短语整体匹配),
  **不做语法检查**;语法不完美但关键槽位命中不得扣分。
- **G3 单调分档**。奖励随 `score` 单调不减:≥70 → 2 份,40–69 → 1 份,
  <40 → 0 份。0 份时需求/关系/已完成步骤全部不变(重说无代价)。
- **G4 兜底完整可玩**。`web_beta_no_voice` / `desktop_beta_no_voice` 构建、
  或运行时麦克风/服务不可用,`gesture_fallback` 给最低生存档(1 份/次),
  三日主线可完整通关;通关路径不得要求语音。
- **G5 持久化**。`SAVE_VERSION` 1→2,旧存档读入后按旧字段迁移
  (`berries/scrap/water` 保留),不丢已获资源与关系。
- **G6 回归**。`test_game_state.gd`、`test_web_beta_no_voice.gd`、
  `test_desktop_beta_no_voice.gd`、`test_hud.gd`、`VoiceTargetCancelTest` 等现有
  headless 套件全绿;新增 `test_voice_gated_rewards.gd` 覆盖 G1–G5 的纯状态断言;
  `server.py` 有 `python3 -m py_compile` 级与判定函数单元断言。

## 4. 设计基线

### 4.1 供给者与三日主线

| 天数 | 步骤 | 资源供给 |
|---|---|---|
| 1 | 向米拉问好(语音或手势)→ 向塔维语音请求食物 ×2 份 → 庇护所睡觉 | `berries +2/+1/0`,food 随档回填 |
| 2 | 向维什语音请求零件 ×2 份 → 修加热器 → 睡觉 | `scrap +2/+1/0` |
| 3 | 向奥里语音请求水 → 把水带给罗文并表达帮助(语音或手势)→ 通关 | `water = 1`,energy 随档回填 |

### 4.2 意图槽位(服务端确定性判定)

每个供给者一个意图档案:`required` 槽(请求行为 + 目标物)与 `optional` 槽(礼貌标记)。
`delivery = 85 × 必需槽命中率 + 15 × 可选槽命中率`,与桌面 `game_scenario.py` 同构。
罗文送水意图仍以「帮助 + 水」为必需槽。

### 4.3 发音分两级来源

- `reference_dtw`:服务进程可导入 `desktop/backend/core/{pipeline,piper_tts,audio_io}`
  且参考音合成成功时,Piper 确定性合成意图参考句,`pipeline.analyze_arrays` 出
  accuracy(0–100)作为 `pronunciation`。首次加载 SSL 编码器较慢,由服务端缓存,
  不阻塞游戏主线程(HTTP 请求本来就异步)。
- `whisper_confidence`:上述任何一环不可用时,用 `avg_logprob` / `no_speech_prob`
  的固定线性映射得到 0–100 声学置信度,并显式标注 `pronunciation_source`。
  这是声学清晰度代理,不是参考发音评分 —— 协议与 HUD 都不得将其显示为
  「发音准」。

### 4.4 协议

`POST /transcribe` 200 响应新增字段(向后兼容保留 `accepted/text/reason`):

```json
{
  "accepted": true,
  "text": "can i have some food please",
  "reason": "VOICE_REASON_ACCEPTED",
  "pronunciation": 81,
  "delivery": 100,
  "score": 90,
  "pronunciation_source": "reference_dtw",
  "band": "generous",
  "slots": [{"key":"request_act","required":true,"hit":true}]
}
```

`accepted` 只表示服务产出有效判定(而非麦克风/服务故障);`band` 决定物资。

### 4.5 手势通道语义

`GameState.interact` 的 `communication` 取值扩为:
`"action"`(E 观察/互动)、`"voice"`(带 `expression` 字典)、
`"gesture"`(语音可用时的善意手势,不产出资源)、
`"gesture_fallback"`(无语音能力时的保底,给最低生存档)。
`PlayerController` 负责在按 G 时按 `SpeechAdapter.is_available()` 选择后两者,
`GameState` 保持对适配器的零依赖。

## 5. 已知取舍(如实记录)

1. **Whisper 置信度不是发音准确度**。兜底档在无参考评分器的环境(如无 torch 栈)
   只能给出「说得是否清楚/有把握」的代理分;这是可玩性兜底与 127.0.0.1 轻量服务
   约束下的取舍,协议字段显式标注来源,不冒充参考评分。
2. **参考音是 Piper 合成音**。FR-M1 禁止合成音作为 *Speaking* 产品参考;
   Survival 游戏场景沿用 FR-17/FR-22 已确立的论证(合成音仅作游戏内评分参考,
   与真人新闻跟读独立),FR-28 只改竖切片,不触及 FR-M1 范围。
3. **口语短句的 DTW 分档阈值未做独立校准**。70/40 分档沿用 FR-25 的 reward band
   思路,但这是竖切片档位而非对 desktop 场景 JSON 的重标定;R-14 的 G1/G2/G7
   语料门不因本变更而通过。
4. **「有语音能力时手势不产出资源」是产品收紧**。若内测反馈该收紧过强,
   可把普通手势改回 0.5 份而不触 G1(需另开评审改 FR-28,不改代码默认值)。

## 6. 实现后回填

- 代码:`game/speech_service/server.py`、`game/scripts/{speech_adapter,game_state,
  player_controller,interactable,main,hud}.gd`、`game/localization/stranger.csv`。
- 测试:新增 `game/tests/test_voice_gated_rewards.gd`;更新
  `test_game_state.gd`、`test_web_beta_no_voice.gd`、`test_desktop_beta_no_voice.gd`。
- 结论:六道门全部放行,见下表。

| 门 | 判据 | 实现后结果 | 备注 |
|---|---|---|---|
| G1 | 语音可用时拾取物/设施不改资源 | ✅ PASS | `test_voice_gated_rewards.gd` 断言 berry/scrap/reservoir 交互后资源向量逐项不变;`main.gd` 拾取物 `one_shot=false` 仅作引导物 |
| G2 | pronunciation + delivery 双维、来源显式 | ✅ PASS | 服务端 `judge()` 返回两维与 `pronunciation_source`(`reference_dtw`/`whisper_confidence`);实测同句 95/100 → score 97.5 generous,错误句 33.3/0 → score 16.6 none;HUD 显示「表达分/发音/意思」 |
| G3 | 奖励随 score 单调、低档无代价 | ✅ PASS | 40/70 档边界逐档断言:0/1/2 份单调不减;<40 时资源、需求、关系全不变且可立即重说 |
| G4 | 无语音构建手势兜底完整通关 | ✅ PASS | Web/Desktop Beta 套件用 `gesture_fallback` 完整走完三日;普通 `gesture` 在语音可用时只回「指指嘴巴」引导文案 |
| G5 | SAVE_VERSION 2 旧档迁移 | ✅ PASS | 测试写 version-1 JSON,`load_game()` 接受并保留 berries/scrap |
| G6 | 回归套件全绿 | ✅ PASS(1 项既有失败,非本次引入) | `test_voice_gated_rewards`/`test_game_state`/`HudTest`/`WebBetaNoVoice`/`DesktopBetaNoVoice`/`VoiceTargetCancel`/`MainEnvIntegration`/`test_walk_fix`/`test_directional_locomotion` 全部 EXIT 0;`test_character_asset` 的 facial-morphs 断言失败为本轮改动前既有状态(玩家源资产 v06 无 morphs),FR-28 未触及该资产 |

## 7. 实测服务边界

`server.py` 在仓库 `.venv` 下实测:`/health` protocol=2;对同一句
"Can I have some food please?" 返回 `reference_dtw` pronunciation 95.0、
delivery 100.0、score 97.5、band generous;对问候句请求食物返回
pronunciation 33.3、delivery 0、score 16.6、band none。服务启动时后台预热的
SSL 编码器强制 CPU(避免 ThreadingHTTPServer 工作线程在 MPS 上的进程崩溃),
首次请求后热态 DTW 约 0.08 s。
