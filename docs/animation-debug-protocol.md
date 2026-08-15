# 主角动画调试协议

本地调试桥只监听 `127.0.0.1`，使用 JSON-RPC 2.0 over WebSocket。

## 6505 — control

用于操控游戏和查看画面。

```json
{"jsonrpc":"2.0","id":1,"method":"control.animation_probe","params":{
  "animation":"anim_chr_player_walk_forward","frames":32,"fps":30,"capture":true}}
```

返回每帧的动作时间、角色状态和可选 JPEG 截图元数据。截图由运行进程写入
`user://logs/animation_probe/`，响应只返回 `frame`、`format`、`path`、`bytes`，避免
多帧 Base64 令 WebSocket 响应过大。常用方法：

- `control.run` / `control.stop`
- `control.freeze`，参数 `{ "frozen": true }`
- `input.simulate_action` / `input.simulate_key` / `input.simulate_sequence`
- `game.capture_frames`
- `control.animation_probe`

方向移动回归使用 `input.simulate_action` 依次按住一个方向、松开、再按相反方向。
`anim_chr_player_turn_180` 和 `anim_chr_player_jump` 也可直接交给
`control.animation_probe` 做确定性逐帧截图。
探针激活期间拒绝外部 reaction，并强制显示蒙皮 LOD0；否则远距离静态 LOD 会让所有
动作截图看起来都像同一个站姿。探针结束后恢复原冻结状态和正常 LOD 选择。
键盘模拟同时设置逻辑和物理 keycode，适用于项目中 Space/G/W 这类
`physical_keycode` InputMap；建议 one-shot 按键都发送 press 和 release。

## 6506 — telemetry

只读状态端口。`animation.get_state` 返回最近缓存帧的当前动作、播放位置、速度倍率、角色速度、
Armature scale、Hips position 和默认的 Head/双脚姿态。请求参数可用
`{"bones":["Hips","LeftHand","RightHand","LeftLeg","RightLeg","LeftFoot","RightFoot"]}`
调用 `animation.sample` 做实时指定骨集合采样；每根骨骼返回 local `position`/`rotation` 以及 skeleton-space
`global_position`/`global_rotation` 和实际场景中的 `world_position`/`world_rotation`。
`animation.subscribe` 会以
默认 30Hz 推送 `animation.frame` 通知；`log.subscribe` 会推送 `log.event`。
`player` 子对象还包含 `facing_direction`、`turn_target_direction`、
`turn_requested_direction`、`requested_move_direction`、`turning_around`、
`turn_time_remaining`、`facing_error_degrees`、Jump 物理高度/冲量和
`visual_yaw_degrees`，用于核对动画结束后 Walk 是否真的朝速度方向播放。顶层还包含：

- `jump_stage`、`jump_takeoff_time`、`jump_landing_time`、
  `jump_authored_airborne_lift_m`、`jump_chain_entry_time`、
  `jump_chain_pose_error_m`、`jump_chain_rotation_error_deg`、
  `jump_chain_count`、`reaction_locked`；
- `turn_to_locomotion_phase_seconds`、原始/校正后脚位误差、转向校正向量及当前衰减值。

每帧事件形如：

```json
{"type":"animation_frame","animation":"anim_chr_player_walk_forward",
 "animation_position":0.533,"speed_scale":1.0,"motion_speed":5.4,
 "armature_scale":[1,1,1],"hips_position":[0.012,0.041,-0.006],
 "bones":{"LeftFoot":{"global_position":[0.07,-0.29,0.18],
 "global_rotation":[-0.66,-0.10,0.74,0.03],
 "world_position":[12.4,0.02,-3.1]}}}
```

同时写入 `user://logs/animation_telemetry.jsonl`。

## 6507 — test

测试端口只允许：

- `test.list`：列出 `res://tests/*.gd`；
- `test.write_inline`：写入 `user://mcp_tests/*.gd`，文件名不能包含路径穿越；
- `test.run`：只执行 `res://tests/` 或 `user://mcp_tests/` 下的脚本；
- `test.status` / `test.result`：读取退出码、是否通过和输出。

测试进程使用当前 Godot 可执行文件以 headless 模式运行，返回 `run_id`。

四肢折叠回归的固定流程是：6505 `control.animation_probe` 播放 Walk；6506 对比左右
手、膝、脚的 `global_position`；6507 运行 `res://tests/test_walk_fix.gd`。截图只在
普通渲染窗口可用，headless 运行时 `game.capture_frames` 会返回无法捕获图像。

方向回归额外运行 `res://tests/test_directional_locomotion.gd`：6505 复现前↔后和
左↔右；6506 断言转身期间平面速度为 0、动画为 `anim_chr_player_turn_180`、
Armature scale 为 1；转完后断言 Walk 的面对方向与速度同向。Jump 期间应看到
`jump_stage` 依次为 `anticipation → airborne → recovery → idle`；`velocity.y` 只能在
动画时间到 `jump_takeoff_time` 后变为正值，物理接地必须与 `jump_landing_time` 对齐。
空中发送 G 后，动作必须仍为 Jump，`player.gesture_rejection_count` 增加；落地后发送 W
应恢复 Walk。连跳时可在下落接地前 `0.2s` 内再次发送 Space，随后应看到
`jump_chain_count` 增加、`jump_chain_entry_time < jump_takeoff_time`，并进入内部交叉
淡化动作后正常完成第二次起跳。
Turn→Walk 的 `turn_to_locomotion_aligned_foot_error_m` 应小于 1 cm，切换后的
`turn_transition_correction` 必须在约 0.2 秒内回到零。
