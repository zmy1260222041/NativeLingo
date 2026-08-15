# 《异乡人 / Stranger》主架构

## 文档状态

- 版本：0.1（纵向切片）
- 更新：2026-08-10
- 引擎：Godot 4.6.3-stable / GDScript
- 覆盖：`game-concept.md`、`systems-index.md`
- 评审：Solo；TD 自检通过，LP-FEASIBILITY 按模式跳过

## 技术需求基线

| ID | 来源 | 需求 | 领域 |
|---|---|---|---|
| TR-concept-001 | Core Mechanics | 第三人称快速移动、镜头、跳跃和交互 | Core/Physics |
| TR-concept-002 | Core Mechanics | 三类需求、时间与非破坏性昏倒 | Simulation |
| TR-concept-003 | Core Mechanics | NPC 信任、承诺和持久记忆 | Feature/Save |
| TR-concept-004 | Unique Hook | 语音意图与手势澄清共享任务结果 | Speech/API |
| TR-concept-005 | Core Loop | 一个聚落的三日任务弧 | Quest/Data |
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
| `GameState` | 天数、需求、资源、关系、记忆、目标 | `interact`、`save_game`、signals | 表达渠道结果 | Node、Signal、FileAccess、JSON |
| `PlayerController` | 移动速度、相机输入、最近交互对象 | `interaction_prompt` | InputMap、世界交互接口 | CharacterBody3D、SpringArm3D |
| `WorldInteractable` | 世界对象身份和提示 | `interact`、`get_interaction_prompt` | GameState command | Node3D、groups |
| `Main` | 当前关卡的场景构成 | 场景启动 | GameState load | MeshInstance3D、StaticBody3D |
| `HUD` | UI 节点和短时消息展示 | 无状态视图 | GameState signals / player prompt | CanvasLayer、Control |
| `SpeechAdapter` | 麦克风会话和 sidecar 连接 | `recognize(intent_context)` | localhost service | AudioEffectCapture、HTTPRequest（待实现） |

## 关键数据流

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
V → SpeechAdapter → recognized intent ─┐
G → GestureAdapter → same intent ─────┼→ GameState.interact(..., channel)
service/error/low confidence ─────────┘  (no negative state mutation)
```

### 保存与启动

```text
day transition / key relationship → GameState plain Dictionary
                                   → JSON → user://stranger_save.json
scene bootstrap → version check → field defaults/migration → GameState
```

初始化顺序为：Godot autoload `GameState` → 主场景读取保存 → 构建世界 → 玩家/HUD 订阅信号。
所有现有流程都在主线程；sidecar 工作必须异步，结果以 signal 回到主线程。

## API 边界与不变量

```gdscript
# Domain command. Callers never mutate quest completion directly.
GameState.interact(kind: String, target_id: String, channel: String) -> void

# Optional adapter. Failure is a result, never a gameplay penalty.
SpeechAdapter.recognize(context: Dictionary) -> void
signal recognition_finished(result: Dictionary)

# Versioned persistence of plain values only.
GameState.save_game() -> bool
GameState.load_game() -> bool
```

必须保持的不变量：

1. `channel == "voice"` 的失败不得减少需求、物品、关系或任务进度。
2. 每个关键语言意图都存在 `gesture` 完成路径，且允许再次尝试语音。
3. HUD 只读状态并发出用户意图，不直接写领域字段。
4. 存档只包含 JSON 安全值，不包含 Node、Resource 或场景路径引用。
5. 所有控制由 InputMap action 表达，不在脚本中轮询物理键码。

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
