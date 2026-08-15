# 调试工作流:CLI 接口 + 日志接口 + 数据驱动

本文沉淀 2026-08-12「走路动画头/髋歪斜」bug 的调试经验。核心教训:**不要写一次性
猜测脚本,先搭可组合的调试设施,再用数据驱动迭代,最后用自动测试把判定固化。**

## 背景:一次典型的"症状清楚、根因隐晦"的 bug

玩家角色走路时头向右转 ~90°、髋部旋转 ~180°,但脚掌朝向正常。Idle 正常,只有
走路时坏。直接读代码无法定位 —— 角色是运行时用多个云端 FBX 组装的,动画关键帧
来自另一个骨架,旋转偏差藏在四元数里。

## 调试设施(本仓库已落地)

### 1. CLI 调试接口 — `game/tools/debug_cli.gd`

```
Godot --headless -s res://tools/debug_cli.gd -- <command> [args...]
```

| 命令 | 用途 |
|---|---|
| `rest [fbx]` | 打印骨骼 rest 旋转(模型/源骨架对比) |
| `anim [fbx]` | 打印动画轨道/关键帧统计 |
| `keys <bone> [fbx] [--method=...]` | 打印单骨骼关键帧值(原始/修复后) |
| `probe [--method=...] [--frames=N]` | 播放动画逐帧采样骨骼姿态 |
| `compare [--frames=N]` | 各修复方案 vs idle 的循环均值姿势逐骨骼对比 |
| `selftest` | 自动评估所有方案,输出 PASS/FAIL |

设计原则:每个命令是原子的、可组合的;`selftest` 把判定逻辑(阈值)写死在代码里,
任何人跑一遍就知道当前状态。

### 2. 日志接口 — `game/scripts/debug_log.gd`

- `DebugLog.set_file(path)` / `info` / `warn` / `error`,时间戳 + 级别 + 标签
- 默认 `user://logs/debug.log`;游戏进程可用 `DEBUG_LOG=1` 环境变量开启
- CLI 和测试强制开启并镜像 stdout;日志失败静默,不影响游戏

### 3. 修复逻辑独立模块 — `game/scripts/walk_anim_fix.gd`

修复算法与调用方解耦,CLI、游戏、测试三方复用同一实现(`build_fixed_walk`)。
方案保留为可对比参数:`centered`(剥循环均值)/ `translate`(全局 rest 重定向)/
`rebase`(中立姿势对齐 idle)。

### 4. 自动测试 — `game/tests/test_walk_fix.gd`

走真实 `CharacterVisual` 管线(加载模型 → 重命名动画 → 修复 → 播放采样),
断言走路循环中立姿势与 idle 站姿对齐(躯干 <35°、四肢 <40°)。

## 经验教训

### 1. 先搭设施,再猜根因

最初的尝试是每次重写一个临时测试脚本(一天内写过 5 个 `test_xxx_debug.gd`)。
浪费大量时间在脚本自身 bug 上,而不是问题上。改为 CLI 接口后,一次 `selftest`
拿全部数据,一次 `compare` 看全部方案 —— 迭代速度提升一个量级。

### 2. 测量本身必须先被验证(本案例最大坑)

本案例两次被测量工具欺骗:

- **欧拉角 gimbal lock**:模型 root 骨 rest 有 ~89° X 倾斜,髋部刚好落在 gimbal
  lock 附近,欧拉 y 分量对微小姿态变化产生 230° 的假漂移。曾经据此得出
  "源骨架自己也坏"的错误结论,浪费了数轮迭代。
- **四元数夹角公式**:`2·acos(w)` 对 `w < 0` 会返回 >180° 的补角(实测 341.7°
  其实是 18.3°)。必须用 `2·acos(|w|)`。
- **方向向量投影**:骨骼前向量接近垂直时,水平投影角全是噪声。

教训:**换一种坐标系无关的度量(四元数夹角、循环均值姿势),并先用已知情况
验证测量结果符合直觉,再相信它。**

### 3. 用"循环均值姿势"而不是瞬时值比较动画

走路循环有大量摆动,逐帧比较噪声大。取每根骨骼在循环内的**球面均值四元数**
作为"中立姿势",比较的是"动画 A 的中立姿势 vs 动画 B 的中立姿势" —— 一个数字
量化"这动画在骨架上摆得多偏"。修复效果的判定由此变得简单可读。

### 4. 数学正确 ≠ 目标正确

`translate`(用全局 rest 把动画精确重定向到模型骨架)数学上完全正确,但实测
效果更差 —— 因为源骨架本身就是"坏"的(髋 rest yaw 166°),精确重现源可见姿势
毫无意义。最终方案 `rebase`(把走路循环中立对齐到 idle 站姿)直接以"正确参照"
为目标,而不是追求数学等价。**先定义"什么是对的"(idle 站姿),再设计公式。**

### 5. 自动测试是调试的终点

方案确定后,把测量逻辑和阈值固化进 `test_walk_fix.gd`:每次改动跑一遍就知道
是否回归。`selftest` 保留所有候选方案(含失败的),历史结论可复现、可解释。

### 6. 残留警告要分清来源

测试输出里有 `_add_lod_from` 的 reparent 警告(已知问题,与本次无关),不影响
判定。自动测试的 PASS/FAIL 要基于明确的指标,而不是日志清洁度。

## 2026-08-13: 主角动作触发时突然放大

### 症状与复现

- 在游戏内按住移动键触发 Walk，或按 `G` 触发 Pointing Gesture。
- 动作开始时主角突然放大，动作结束或切回 Idle 后恢复。
- 复现入口：`game/tests/test_walk_fix.gd`，以及 `game/tests/test_anim_debug.gd` 的运行时采样。

### 根因

`retarget_mixamo_actions.py` 生成的骨骼旋转本身没有缩放，但 Blender FBX bake
阶段仍为 NLA 动作补出了 `Armature` 对象的 scale 轨道。该轨道在 Godot 中被导入为
`Animation.TYPE_SCALE_3D`，关键值是 `(100, 100, 100)`，源于 FBX 的厘米单位换算；
因此 Walk/Run/Pointing 开始时会把整个 `Armature` 放大 100 倍。这个问题不是 Mixamo
骨骼比例或世界空间重定向误差。

### 修复

1. `retarget_mixamo_actions.py` 对待导出的动作数据只保留 pose-bone rotation channels；
2. Blender 的 FBX bake 仍可能重新物化单位换算轨道，因此
  `CharacterVisual._sanitize_runtime_animation_tracks()` 在 Godot 导入后剥离所有
  scale 和 Armature 对象级 position；Hips 骨骼的周期性局部 position 保留；
3. `PlayerController` 继续独占 `CharacterBody3D` 的世界位移，不从动画读取 root 位移。

### 回归约束

- `game/tests/test_walk_fix.gd` 要求 Walk、Run、Pointing 三个动作存在；Walk/Run
  必须循环，Pointing 必须单次；三个动作均不得包含 `TYPE_SCALE_3D` 或非 Hips 的
  `TYPE_POSITION_3D` 轨道。
- `test_walk_fix.gd` 会实际播放 Walk 和 Pointing，并断言 Armature scale 在动作
  播放后仍约为 `(1, 1, 1)`，不再出现 `(100, 100, 100)`。

## 使用建议

- 新 bug 先在 CLI 里加一个最小复现命令(数据说话),不要写临时脚本
- 测量指标先做"已知正确"的冒烟验证
- 方案对比进 `selftest`,判定阈值写进自动测试
- 游戏内日志用 `DEBUG_LOG=1` 开启,`user://logs/debug.log` 查

## 2026-08-13: 动作预览正确、游戏内不像人的根因

### 根因

原始 Mixamo 动作的 `Hips.location` 不是错误数据。Walk、Run、Point 都包含小幅
周期性位移，分别用于髋部起伏和重心转移。之前的重定向脚本把所有骨骼位移删掉，
Godot 的 FBX 导入后处理又把所有 `TYPE_POSITION_3D` 一并删掉，最终只剩骨骼旋转，
所以预览中的步态缓冲在游戏内消失。

### 当前规则

- Blender 重定向保留 Hips 的局部位移，并按首帧/末帧做线性去漂移；世界位移仍由
  `CharacterBody3D` 负责。
- 所有骨骼 scale 和 Armature 对象级变换都删除，避免 FBX 厘米换算生成 `(100,100,100)`。
- Godot 的 FBX 导入器对根骨位移不稳定，因此 Blender 同时输出
  `game/assets/characters/chr_player_juvenile_mixamo_retarget.json`；
  `CharacterVisual` 导入后将 Hips 关键帧恢复到
  `Armature/Skeleton3D:Hips`。
- `test_walk_fix.gd` 必须看到 Walk/Run 的动态 Hips position track，且所有动作不得有
  scale 或非 Hips position track。

### 三端口调试工作流

游戏运行时 autoload `AnimationDebugBridge` 在 localhost 提供三个 WebSocket 端口：

| 端口 | 用途 | 关键方法 |
|---|---|---|
| `6505` | 游戏输入、冻结、画面和确定性动画探针 | `input.simulate_action`, `game.capture_frames`, `control.animation_probe` |
| `6506` | 日志与逐帧动画遥测 | `log.tail`, `log.subscribe`, `animation.get_state`, `animation.subscribe` |
| `6507` | 测试枚举、临时测试写入和运行 | `test.list`, `test.write_inline`, `test.run`, `test.result` |

编辑器空闲时由 Godot MCP 插件占用相同端口；开始运行游戏时插件释放端口，运行时
autoload 接管。遥测写入 `user://logs/animation_telemetry.jsonl`，普通调试日志写入
`user://logs/debug.log`。

推荐复现顺序：先用 6505 的 `control.animation_probe` 固定播放 Walk，再从 6506
取 Hips、Head、双脚和 Armature scale，最后用 6507 运行 `res://tests/test_walk_fix.gd`。
这样可以区分“资源轨道丢失”“播放控制覆盖姿态”和“画面/相机误判”三类问题。

## 2026-08-13：Walk 中双手双脚折叠/交叉

### 症状与真正根因

源 `Walking.fbx`、`Standard Run.fbx`、`Pointing Gesture.fbx` 使用同一套 25 骨
Mixamo T-pose 骨架，层级和 rest pose 一致；动作文件没有损坏。游戏 mesh 则绑定在
另一套 28 骨、垂手站立 rest pose 的旧骨架上。旧 `world_rest` 算法把“Mixamo
T-pose → 动作姿势”的旋转增量叠加到已经垂手站立的游戏 rest pose，导致四肢被多转
一次。Walk 的客观结果是骨骼方向平均误差 31.02°、P95 76.37°，右上臂平均误差
77.65°；旧报告却为 0°，因为它用同一个公式同时生成候选和 ground truth，属于循环
自证。

### 修复与新判据

- `retarget_mixamo_actions.py` 新增并选择 `pose_direction`：先让目标骨骼 +Y 方向与源
  动作当前帧的骨骼方向一致，再只传递源骨骼沿自身 Y 轴的 twist。这样不依赖两套骨架
  是否共享 T/A/垂手 rest pose，同时保留手腕和脚掌翻转。
- 报告现在读取 Blender 实际求解后的姿态，计算 bone-direction 角误差、完整旋转误差、
  按目标骨长换算的端点误差和逐骨统计。Walk/Run/Point 的选中结果方向 P95 均为 0°，
  端点最大误差不超过 0.003 mm。
- 6506 的骨骼遥测增加 `global_position` 与 `global_rotation`，可直接检查左右手、膝、脚
  是否越过身体中线。
- `test_walk_fix.gd` 同时断言离线报告选择 `pose_direction`、P95 ≤ 0.5°、端点误差
  ≤ 5 mm，并在 0/25/50/75% 四个 Walk 相位检查左右手、膝和脚不交叉。

三端口复现仍按 6505 → 6506 → 6507：6505 固定播放并截图；6506 读取全局关节位置；
6507 运行 `res://tests/test_walk_fix.gd`。普通窗口才能截图，headless 模式没有可读的
viewport texture，但遥测和测试端口仍可使用。

## 2026-08-13：移动方向与角色朝向脱节、缺少 180° 转身

### 症状与资源验证

按后方向键时，`CharacterBody3D` 向后移动，但可见模型仍面向前方播放 Walk，形成倒滑。
新加入的 `Walking Turn 180.fbx` 经 Blender 分阶段探针确认是 31 帧真实转身，首尾朝向
相反；`Jumping.fbx` 是 98 帧完整起跳—腾空—落地周期。两者都使用与现有动作相同的
Mixamo 骨架，因此进入同一个 `pose_direction` 重定向和 FBX 安全轨道流程。

### 控制规则

- `CharacterBody3D` 的 yaw 只服务镜头；`CharacterVisual` 保存独立的世界朝向，镜头旋转
  不再带着人物原地转。
- Walk/Run 的可见朝向始终对齐实际平面运动方向。
- 新方向与当前朝向夹角 `< 135°` 时不插入转身动作，但也不再瞬间修改 yaw；朝向以
  `360°/s` 逐物理帧收敛，平面速度矢量同步旋转，因此人物不会横着滑向尚未面对的方向。
- 夹角 `>= 135°` 时冻结平面位移，单次播放 `anim_chr_player_turn_180`；动作结束后把
  外层 yaw 原子切到动作严格对应的反方向。若请求是 150° 等近似反向，剩余角度随后按
  小转规则平滑完成，避免 Turn 动作的 180° 末姿态跳到 150°。
- Turn 末帧不能直接从 Walk 第 0 帧假定连续。运行时对 Walk/Run 各采样 64 个相位，比较
  `LeftFoot/LeftToeBase/RightFoot/RightToeBase`；当前 Turn→Walk 选择 `0.000s`，未校正
  平均脚位差约 29 mm。切换帧施加约 29 mm 的整体模型惯性校正后，双脚残差约 0.1 mm，
  校正在 0.2 秒内线性衰减。即使按着冲刺，也先进入相位匹配的 Walk，再随速度混合到 Run。

### Jump 的接触帧与高度分工

- Blender 报告按双脚/脚趾离地间隙检测接触：阈值为角色高度的 2%，并要求连续 3 帧。
  当前 `Jumping.fbx` 的起跳帧是 40（`1.300s`），落地帧是 59（`1.933s`）。按键只启动
  下蹲蓄力，不立即写 `velocity.y`。
- Jump 分为 `anticipation → airborne → recovery`。蓄力段以 `1.6x` 播放；第 40 帧才
  给物理冲量；第 40→59 帧按物理腾空时间缩放；物理接地时 seek 到第 59 帧，再以
  `1.25x` 播放落地恢复。
- 高度补偿只计算“脚离地以后”的 Hips 抬升；下蹲到伸腿发生在脚仍着地时，不算额外
  跳高。当前动画离地后的自带抬升为 `0.09534548m`，物理高度为
  `JUMP_VELOCITY²/(2g) - authored_airborne_lift`，避免动画与抛物线重复叠高。
- 连跳不能把恢复帧硬切回 Jump 第 0 帧。最终运行 FBX 的 Blender 实测中，接触帧 59
  直接切第 1 帧约有 `0.130m / 76.3°` 的全身姿态误差。运行时因此保留 `0.2s` 落地
  输入缓冲，在蓄力段采样 40 个候选相位，以双脚/脚趾对齐后的全身位置和旋转选优，
  再用 `0.18s` 交叉淡化。当前固定复现选择约 `0.455s`，不再出现首帧跳变。

### 空中 G 覆盖 Jump 的卡死根因

- 旧日志显示 `jump_stage=airborne` 后紧接着
  `transition=anim_chr_player_gesture_point reason=reaction`。Point 播完后
  `jump_active=true`、`jump_stage=anticipation/recovery` 仍保留，运行时优先级持续返回，
  所以玩家看起来无法再移动。
- 现在 Jump 整段（蓄力、腾空、落地恢复）禁止 G。控制器记录
  `gesture_rejected`；视觉层再次校验 `can_play_reaction()`，并在发现
  `jump_active` 搭配非 Jump 动作时恢复正确动作和阶段时间。
- 6505 的键盘事件必须同时写 `keycode` 与 `physical_keycode`；否则本项目 InputMap
  中的 Space/G/W 不会被模拟。`simulate_sequence` 的字符串按键分支也必须返回事件。

### 固定复现与判定

1. Blender Copilot headless 直接运行 `retarget_mixamo_actions.py`，确认报告中 Turn/Jump
   均选择 `pose_direction`、有 Hips 动态位移且无 scale。
2. 6505 发送“保持一个方向 → 松开 → 按相反方向”，在转身中段截图；转身期间速度必须
   为 0，结束后动画必须为 Walk 且速度方向与 `player.facing_direction` 一致。
3. 6506 检查 `turn_active`、`player.turning_around`、`visual_yaw_degrees`、
   `turn_to_locomotion_*`、`jump_stage`、`jump_takeoff_time`、`jump_landing_time` 及
   `armature_scale == [1,1,1]`。骨骼同时输出 skeleton-space 与 world-space 位置/旋转。
4. Jump 腾空时由 6505 发送真实 `G` key press/release；6506 必须看到动作仍为 Jump、
   `gesture_rejection_count` 增加，落地后 W 可恢复 Walk。下落接近地面时再发 Space，
   必须看到 `jump_chain_count` 增加并完成第二次起跳。
5. 6507 运行 `test_walk_fix.gd` 与 `test_directional_locomotion.gd`。前后/左右反向必须
   触发 Turn；90° 和 120° 必须直接转；150° 必须触发 Turn。

这类问题必须同时看 Blender 源动作、Godot 实际画面和运行时朝向/速度，单看动画名或
控制器速度无法判断人物是否真的朝运动方向行走。

6507 的 headless 子进程仍可能输出既有 LOD reparent owner/global-transform 警告；只要
动作断言退出码为 0，这些警告单独归入 LOD 管线，不作为本次方向/Jump 回归失败。

## 2026-08-15：替换站立常态、观察与采集动作

新增源文件为 `Standing Idle.fbx`（96 帧）、`Looking Around.fbx`（191 帧）和
`Picking Up.fbx`（146 帧）。Blender 源探针确认三者都使用现有 Mixamo 骨架；新待机
首尾回环，观察和采集都在完成动作后回到站姿。旧运行时 Idle 在四分之一到四分之三
相位包含明显侧倾/转身，不适合作为站立常态，因此不再从目标 FBX 继承，而由
`Standing Idle.fbx` 在同一个 `anim_chr_player_idle_neutral` 合约名下完整替换。

运行时映射固定为：

- `berry`、`scrap`、`water` → `anim_chr_player_interact_gather`；
- `heater`、`shelter` 及其他固定环境设施 → `anim_chr_player_interact_observe`；
- `npc` 继续使用 greet/offer/clarify/point，不被环境动作替换。

Observe/Gather 是单次动作，持续时间直接读取导入动画长度，不再使用手写计时；Idle
保持循环。三个动作继续只保留骨骼旋转和去漂移后的 Hips 局部位移，剥离所有 scale、
Armature 对象变换和非 Hips 位移。最终 FBX 复导后，源/目标五相位独立 bone-direction
对比结果为：Idle P95 `0.000225°`、Observe P95 `0.003912°`、Gather P95
`0.005926°`；最大端点误差均小于 `0.075 mm`。`test_walk_fix.gd` 同时锁定动作存在性、
循环语义、安全轨道、Armature scale 和环境类型映射。

复现仍遵循固定闭环：先在 Blender 对源 FBX 与最终运行 FBX 以相同标准化相位截图，
再用 6505 零混合播放 Idle/Observe/Gather、6506 读取 Hips/手脚/scale，最后由 6507
运行 `res://tests/test_walk_fix.gd`。

本次实机闭环还修正了两个会制造假阴性的探针缺陷：动画探针现在强制蒙皮 LOD0 并
拒绝外部 reaction，避免远距离静态 LOD 把所有动作显示成站姿；逐帧 JPEG 写入
`user://logs/animation_probe/`，RPC 只回路径和大小，避免多帧 Base64 响应挤断 6505。
6506 的 `animation.sample` 也改为实时按请求骨集合采样，不再错误返回默认缓存骨集合。
