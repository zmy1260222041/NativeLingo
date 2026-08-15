# 场景风格化升级评审记录（v1.5 · 2026-08-14）

> 依据：用户提供的《原神/塞尔达》风格化技术方案 + 美术圣经 v1.5（本次新增 §3.7）。
> 通道：Blender 合成评审渲染（窗口无关），qwen-mm 视觉批判逐轮迭代。
> 结论：四轮迭代后构图四项（分层/树冠体积/色彩分块/接触）全 PASS，Gate E 与回归测试全 PASS。

## 一、方案 → 落地映射

| 用户方案条目 | 落地 |
|---|---|
| 植被球形法线传递（Data Transfer） | `fol_tree_stranger_a`：树冠 7 瓣 + 垂挂信号兰种荚，全部顶点法线从包裹球径向传递（`normals_split_custom_set_from_vertices`，§3.7.A）；Blender 端等价于 proxy sphere 法线烘焙 |
| 岩石切面化 + 硬边倒角 | `env_rock_facet_a/b`：凸包 + limited dissolve 出大块面，flat shading，锐利转折（§3.7.B） |
| 斜率混色（坡度草皮） | 岩顶按面法线 z + 高度权重烘入 暮靛+苔薄荷 苔带（§5.4 新条款） |
| Ramp/Step 光照 | 已有 `cel_base` 三段量化；新增 `cel_foliage`（同光照 + 顶点风摆） |
| 冷暖分层（暗冷亮暖） | `cel_base/cel_foliage` 暗带乘数 (0.14,0.16,0.24) 蓝最高、中间带暖灰 (0.66,0.62,0.58) —— §3.7.C 正式成文 |
| 描边系统 | 近/中景 inverted hull（`cel_outline` 新增可选风摆同步，防描边壳与摆动树冠分离）；远景 Sobel 后处理按 §3.7.D 默认不启用（gl_compatibility + §8.4 预算约束） |
| Kitbash/模块化 | 痕迹道具从 7 组扩到 15 组复用现有 GLB；5+1 棵树、5 块切面岩 |
| 借用资产二次元化 / AI 重绘 | 圣经 §3.7.E 成文（decimate→法线定制→色板重映射→§8.7/§8.8 验收；AI 图集仅作草稿）——本轮未采购外部资产，纯手搓 |
| 大地形/山脉 | `env_ridge_distant_a`：12 段切面山脊环（半径 27–33m，§3.4 轮廓层）+ 80m 基座地面解决悬空 |

## 二、四轮视觉迭代（qwen-mm 批判）

| 轮 | 主要 FAIL | 修复 |
|---|---|---|
| R1 (v15) | 构图平/无地平线；树冠"扁平 2D" | 发现评审通道未隐藏 lod1/2（三重嵌套渲染）；LOD 隐藏 + 切面岩换装 + 远脊 v1 |
| R2 (v15b) | 远脊悬空（地面 34m 外是虚空）；密度稀疏 | 80m 基座 + 脊下沉 + 基面片 + 8 组新痕迹 |
| R3 (v15c) | 脊被我沉了 5m 全埋；市场镜屋檐裁框 | 下沉改 1.2m、脊高 3.5–9m；market_core 机位后拉 |
| R4 (v15d) | **全 PASS**：脊可见且接地、无裁框、市场镜头 lived-in | 残留三条 nit（合金补片读作"斜靠板"、发光植物球茎、摊位桌腿）均为 authored 特征/子像素级 |

单资产预审：树（球形法线 ✓ 单一圆润体积）、岩 A/B 两轮修订后 PASS（苔色增强、侧脊 ledge 变化）。

## 三、游戏内验证

- 重启后 0 脚本/着色器错误；三端口 6505/6506/6507 全部监听。
- `ENV_STATS`：meshes 1094（原 885）、draw_estimate 706（含未剔除 LOD 上界，§8.1 ≤850 达标）、灯光 6。
- `fol_tree_stranger_a`（+@Node3D@122/125/128 等按位确认）×6、`env_rock_facet_a/b` ×5、`env_ridge_distant_a` 均在树中可见。
- 测试：`MARKET_CORNER_ASSET_TEST_PASS`（EVIDENCE lod0_tris=2782 draw_calls=49 cel=true assets=10）、`test_game_state` PASS、`test_hud` PASS（6507 test.run）。
- 风摆：树冠 material_override → `cel_foliage`（每实例 phase_offset 错相），描边壳同步 sway 参数。注意 Godot 4 兼容渲染器 vertex 阶段无 `MODEL` 内建（编译失败教训），相位偏移改用 uniform。

## 四、发现的可复用结论

1. **评审通道必须隐藏 lod1__/lod2__**：glTF 导出全 LOD 后 Blender 直渲会三重嵌套，直接污染构图批判（本轮最大假阳性来源）。
2. **重复实例化实例名会被 Godot 丢弃**：同名 GLB 第二次 add_child 后名字变 `@Node3D@N`（主.gd 一直如此，lantern 亦然）——按名探针找不到，需按位置或路径计数验证。
3. `fpos()` 不是 GDScript 函数；`MODEL` 不在兼容渲染器 vertex 内建里。
4. EEVEE 5.2 无 `scene.eevee.use_gtao`（legacy API 已移除）。

## 五、遗留跟进项（待用户决策）

- 新资产入锁：`fol_tree_stranger_a / env_rock_facet_a/b / env_ridge_distant_a` 未登记进 `ASSET_LOCK_MANIFEST.json`；`art/source/environment/` 整体仍未入 git（沿用上次 41 项漂移的待决状态）。
- Gate E 覆盖扩展：把树/岩/脊纳入断言（当前 assets=10 计数未含新资产）。
- §8.8 需前台窗口的三项（D1/D3 同机位、HUD-off 5s 导航、三态灯光截图）工具已备，待执行。
- 远脊目前无雾衰减校验：in-game fog 距离参数与 27–33m 脊环的配对未截图验证。

## 六、复现

```bash
# 建模导出（树/岩/脊）
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python art/source/environment/env_market_corner/blender/model_env_stylized.py
# 评审渲染（--out 输出 8 视图）
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python art/source/environment/env_market_corner/blender/render_settlement_review.py -- --out /tmp/env_review/v15d
# 游戏 + 测试
cd game && /Applications/Godot-4.6.app/Contents/MacOS/Godot --path . &
/Applications/Godot-4.6.app/Contents/MacOS/Godot --headless --script res://tools/rpc_tests.gd --path .
```
