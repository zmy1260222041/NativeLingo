# 《异乡人 / Stranger》主架构

## 文档状态

- 版本：0.3（语音门控物资 + 云评分）
- 更新：2026-08-16
- 引擎：Godot 4.6.3-stable / GDScript
- 覆盖：`game-concept.md`、`systems-index.md`、FR-28 语音门控物资、FR-29 云评分
- 评审：Solo；TD 自检通过，LP-FEASIBILITY 按模式跳过；R-17 / R-18 已放行(代码侧)

## 技术需求基线

| ID | 来源 | 需求 | 领域 |
|---|---|---|---|
| TR-concept-001 | Core Mechanics | 第三人称快速移动、镜头、跳跃和交互 | Core/Physics |
| TR-concept-002 | Core Mechanics | 三类需求、时间与非破坏性昏倒 | Simulation |
| TR-concept-003 | Core Mechanics | NPC 信任、承诺和持久记忆 | Feature/Save |
| TR-concept-004 | Unique Hook | 语音意图与手势澄清共享任务结果 | Speech/API |
| TR-concept-005 | Core Loop | 一个聚落的三日时间盒；主线按生理需求去对应的店，无指定任务顺序（FR-42） | Quest/Data |
| TR-concept-006 | Platform | macOS 优先并保留 Windows 路径 | Platform |
| TR-concept-007 | Pillar 2 | 语言错误不得损伤生存或关系状态 | Invariant |
| TR-concept-008 | Long-term | 状态格式支持未来年龄阶段字段 | Save/Schema |
| TR-systems-001 | Systems Index | 五名可识别 NPC，至少两名有关系记忆 | Feature |
| TR-systems-002 | Systems Index | 键鼠和手柄均可完成核心路径 | Input/UX |
| TR-systems-003 | Systems Index | 核心状态可无渲染测试 | QA |

## 引擎风险摘要

Godot 4.6 晚于模型基础知识，所有引擎 API 以版本化 4.6 文档和本地
4.6.3 编辑器运行结果为准。当前高风险面是 Jolt 碰撞差异、输入事件序列化、导出模板和
未来跨平台 sidecar 生命周期。已验证 `CharacterBody3D`、`move_and_slide()`、InputMap、
autoload、`FileAccess` 和 JSON 保存路径能由 4.6.3 解析运行。

## 系统分层

```text
Presentation  HUD / subtitles / interaction prompts / audio feedback
      ↓ signals and read-only projections
Feature       three-day quest / NPC memory / settlement / language intent
      ↓ commands and domain events
Core          player controller / survival needs / resources / interaction
      ↓ narrow engine-facing adapters
Foundation    GameState / save repository / speech adapter / scene bootstrap
      ↓
Platform      Godot 4.6.3 / Jolt / InputMap / localhost process boundary
```

依赖只能向下。Presentation 不直接改变任务；它发送命令。语音适配器不拥有关系或任务
状态，只返回语言意图结果。手势适配器与语音适配器处于同一边界。

## 模块所有权

| 模块 | 独占拥有 | 暴露 | 消费 | Godot API |
|---|---|---|---|---|
| `GameState` | 天数、需求、关系、记忆、目标；组合物品命令与需求效果 | `interact`、`item_command`、`save_game`、signals | 表达渠道结果、物品效果 | Node、Signal、FileAccess、JSON |
| `ItemState` | 实例、交易/供应账本、携带容量、住所物品与设施进度 | `deliver/pack/consume/place/use_home/reclaim`、纯数据快照 | 具名成交结果、需求快照 | RefCounted（不依赖场景） |
| `ItemWorld` / `ItemPanel` | 世界投影 / 临时物品选择 UI | 只读展示、向 GameState 发意图 | items_changed、持久实例 | Node3D / Control |
| `PlayerController` | 移动速度、相机输入、最近交互对象 | `interaction_prompt` | InputMap、世界交互接口 | CharacterBody3D、SpringArm3D |
| `WorldInteractable` | 世界对象身份和提示 | `interact`、`get_interaction_prompt` | GameState command | Node3D、groups |
| `Main` | 当前关卡的场景构成 | 场景启动 | GameState load | MeshInstance3D、StaticBody3D |
| `HUD` | UI 节点和短时消息展示，云端激活浮层 | 无状态视图 + 激活码输入 | GameState signals / player prompt / SpeechAdapter auth | CanvasLayer、Control |
| `SpeechAdapter` | 麦克风会话、本地服务或云端评分连接、设备激活与 token 存储 | `activate_cloud`、`recognition_finished(target, accepted, transcript, reason, expression)`、`cloud_auth_finished` | 本地 `127.0.0.1:17831` 或云 `/game/evaluate` | AudioEffectRecord、HTTPRequest、TLSOptions、ConfigFile |

## 关键数据流

FR-44：具名且同轮语音结束的成交 → `ItemState` 原子交付到柜台 → 玩家领取或使用 → `GameState` 同步应用物品与需求变化。
物品事件不推进词汇状态，原观察/练习/后续真实交流的异步词汇流程保持独立。详见 [ADR-0009](adr-0009-item-lifecycle.md)。

### 每帧更新

```text
InputMap → PlayerController._physics_process → CharacterBody3D.move_and_slide
        → GameState need deltas → state_changed → HUD projection
```

### 世界互动

```text
Input action → nearest WorldInteractable → GameState.interact(kind, id, channel)
             → domain mutation → message_requested/state_changed → HUD/NPC feedback
```

### 语言互动

```text
V → SpeechAdapter ── 本地开发: 127.0.0.1:17831 /transcribe
                 └─ 云模式: POST /game/evaluate (Bearer token + X-Stranger-Target)
                        → graded expression {pronunciation, delivery, score, band}
G → gesture (善意,不产出资源) / gesture_fallback (无语音/未激活,给最低生存档) ─┐
service/error/low confidence ─────────────────────────────────────────────────┘
        → GameState.interact(kind, id, channel, expression)  (失败永不扣状态)
```

服务柜台(FR-41 / NFR-9)拆成实时平面与工作平面:

```text
松键 → /transcribe (fast Whisper)
     → POST /game/dialogue (Accept: text/event-stream)
          实时: Gemini streamGenerateContent 首句 → 首句 TTS 缓存 → event speaking → NpcVoice
          工作: player_turn JSON → event score → 播完后成交
```

T_speak≈1 秒内没有首句、或 429/503,则 stub 开口;已承诺台词不替换,地道分可后到。无 Gemini key 时才用 grok-4.3。开口目标 ≤ 3 秒。旧客户端不带 SSE 头时仍返回一次性 JSON。

### 远程评分模式(FR-29)

- 构建判定:`stranger_cloud/enabled=true` 或导出 feature `stranger_cloud_voice`。
- 激活:`POST /register`(激活码换每设备 token);token/设备 id 仅存 `user://`。
- 传输:桌面 `TLSOptions.client(res://certs/nl_ca.pem)` 固定私有 CA;Web 同源
  nginx `/game/` 反代,浏览器只信任 Let's Encrypt。
- 降级:未激活、断网、超时、401/5xx → `VOICE_REASON_*` 失败态 →
  `gesture_fallback`,三日主线保持完整可玩。
- 本地开发模式保留:`stranger_cloud/enabled=false` → 可选本地服务,
  参考音频 `game/speech_service/reference_audio/` 与云端同一批。

### 保存与启动

```text
day transition / key relationship → GameState plain Dictionary
                                   → JSON → user://stranger_save.json
scene bootstrap → version check → field defaults/migration → GameState
```

初始化顺序为：Godot autoload `GameState` → 主场景读取保存 → 构建世界 → 玩家/HUD 订阅信号。
录音/评分请求(本地服务或云端)必须异步,结果以 signal 回到主线程;HTTP 回调期间
`GameState.interaction_time_frozen` 保证等待评分不消耗生存时间。

## API 边界与不变量

```gdscript
# Domain command. Callers never mutate quest completion directly.
# channel: "action" | "voice" | "gesture" | "gesture_fallback"
# expression (voice only): {pronunciation, delivery, score, band, pronunciation_source, text}
GameState.interact(kind: String, target_id: String, channel: String, expression: Dictionary) -> void

# Optional adapter. Failure is a result, never a gameplay penalty.
SpeechAdapter.start_recording(target_id: String) -> bool
SpeechAdapter.activate_cloud(code: String) -> bool
signal recognition_finished(target_id, accepted, transcript, reason, expression)
signal cloud_auth_finished(success, message)

# Versioned persistence of plain values only.
GameState.save_game() -> bool
GameState.load_game() -> bool
```

必须保持的不变量：

1. `channel == "voice"` 的失败(低分/服务失败/未激活)不得减少需求、物品、关系或任务进度。
2. 资源只能由 NPC 语音交互增加(FR-28 G1);`gesture` 在有语音能力时不产出资源。
3. 语音不可用(无语音构建、未激活、麦克风/网络/服务失败)时 `gesture_fallback`
   给最低生存档,每个关键语言意图都有该完成路径,且允许再次尝试语音。
4. HUD 只读状态并发出用户意图,不直接写领域字段。
5. 存档只包含 JSON 安全值,不包含 Node、Resource 或场景路径引用;
   云 token/设备 id 存独立的 `user://stranger_cloud.cfg` / `stranger_device.cfg`。
6. 所有控制由 InputMap action 表达,不在脚本中轮询物理键码。

## ADR 审计与待建 ADR

当前没有正式 ADR。以下决定需要补文档，但已由已批准的实施方案临时约束：

### 编码前必须有（当前作为原型债务跟踪）

- ADR-0001：Godot 4.6.3 与 Compatibility renderer 的版本固定策略
- ADR-0002：领域状态 autoload 与信号驱动 UI 边界
- ADR-0003：JSON 存档版本化与迁移策略

### 在对应系统扩展前必须有

- ADR-0004：Godot 与本地 ASR sidecar 的生命周期、鉴权和端口发现
- ADR-0005：确定性语言意图槽位与置信度/澄清协议
- ADR-0006：NPC 日程和关系记忆的数据模型

### 可延后

- ADR-0007：最终卡通渲染器与轮廓线方案
- ADR-0008：Windows 打包与模型共享策略

## 架构原则

1. **世界先于语言**：移动、生存和实物互动在语音服务离线时仍完整可玩。
2. **表达渠道不拥有结果**：语音和手势只传递意图，领域层决定关系和任务变化。
3. **单一可测状态源**：纵切规则集中在可无渲染执行的领域状态中。
4. **小场景深状态**：复用聚落地点并改变其人物、资源与反馈，不以地图面积制造内容。
5. **版本边界明确**：引擎、存档和 sidecar 协议都显式版本化。

## 开放问题

- 最终卡通渲染是否需要 Forward+，由角色与市场角落 art test 决定。
- 本地 ASR 是复用精简版 faster-whisper，还是使用平台原生识别；以离线、延迟和包体测试决定。
- NPC 日程使用 Resource 资产还是 JSON 内容表；在第二名复杂 NPC 实现前决定。


## FR-46：2D 分支的默认呈现层（2026-09-11）

`Novel.tscn → novel_screen.gd → novel_controller.gd → GameState / ItemState / Dialogue / Vocabulary / SpeechAdapter / NpcDialogueService`。

`novel_content.gd` 提供六个地点和五段社会对白的轻量数据。屏幕只生成 Control / TextureRect / RichTextLabel / Container；地点身份替代世界距离。`GameState` 接入 `novel_world.validate_item_context` 复核物品命令；静态 NPC 台词通过只读信号同步呈现。原服务角色卡、具体库存、成交和习得判据继续由原领域模块拥有。

控制器在挂载期间关闭 GameState 的实时时钟，仅行动命令调用既有需求推进。睡眠、关系、交易、消耗仍由领域处理。存档使用独立文件，附加 `presentation_state` 保存地点、历史和 2D 引导完成标记。NpcVoice 根据 `stranger_novel/enabled` 选择非空间音频；原 3D 分支模式仍能选择空间音频。

本分支默认入口与专用导出不再包含玩家控制器、碰撞、环境模型、3D 灯光或 AnimationDebugBridge。完整迁移矩阵见 R-34。
