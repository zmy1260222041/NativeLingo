# R-15 — 场景美术升级「白昼市场角落」art-test fit-review

- **日期**：2026-08-12
- **范围**：`docs/PRD.md` §7 追溯镜像（游戏受 GDD 管辖，非桌面 PRD）
- **追溯链**：`design/gdd/game-concept.md:244` open question（"现成资产能否统一成原创动画风格？"）→ `:267` 纵切"统一美术" → `systems-index.md` #11 聚落与环境风险 → art-bible §9.5 frame #1（白昼市场角落）
- **交付物**：独立验收场景 `game/scenes/MarketCorner.tscn` + 10 个手工建模环境 GLB + cel toon shader 对 + 环境 Gate `test_market_corner_asset.gd`
- **状态**：✅ **Gate E 14/14 通过**

## 需求落地

| GDD / art-bible | 落点 |
|---|---|
| `game-concept.md:244` 用一个角色+一个市场角落回答"统一美术" | MarketCorner.tscn 组合主角+摊位+配景 |
| art-bible §9.5 frame #1 白昼市场角落固定镜头 | `§9.5 frame` 截图（见下） |
| §3.1.B 哑光+单层阴影+极少功能高光 | `cel_base.gdshader`（roughness 0.85 + 量化阴影 + 功能 rim） |
| §8.2 网格预算 / 材质槽 | 各资产 LOD 面数 + 材质槽 ≤ cap（Gate 断言） |
| §8.4 2K 图集 + 顶点色调色 | `stall_atlas_2k.png` + `stall_orm_2k.png` + 顶点色（前脸/ground/shelter/token） |
| §8.6 命名 / 坐标 / 单位 | `env_/prp_/fol_` 前缀、-Z forward（import post meta）、origin 基底 |
| §8.7 七项导入清单 | 见下逐项 |
| §9.3 审美禁则 | 无程序噪声（图集为色块分区，非噪声纹理）、无照片写实、无地球物件 |

## 资产清单（game/assets/environment/，10 GLB）

| asset | 类别 | LOD0 tris | 材质槽 | 备注 |
|---|---:|---:|---|
| env_market_stall_a | hero | 2274 | 3 | 三 LOD 共享 3 材质；前脸潮青顶点色；2K 图集 |
| prp_lantern_market_a | prop | 348 | 2 | LOD0/1 共享；emissive 灯泡顶点色 |
| env_ground_market_a | ground | ~3k | 1 | 顶面 y=0 厚度沉地；路径/篦顶点色 |
| env_shelter_distant_a | shelter | ~1k | 1 | 远景剪影；roof/window 顶点色 |
| env_rock_market_a/b | rock | 320/320 | 1 | LOD0(细)/LOD1(粗) 共享 |
| fol_glowplant_a | veg | ~100 | 1 | MultiMesh 24 株；bulb 顶点色 mint |
| prp_food_token_a/b/c | token | <1.8k | 1 | 种荚/莓簇/陶碗（顶点色） |

**帧内 LOD0 总面 = 2782**（§8.1 上限 1.2M 的 **0.23%**）
**draw calls = 43**（§8.1 上限 850 的 **5%**；hero 描边 pass ≤ 6）
**VRAM 估算**：atlas 2K×2 + 各资产小贴图 ≈ **≤ 50 MB**（上限 650 MB）

## Gate E（test_market_corner_asset.gd）14/14

```
MARKET_CORNER_ASSET_TEST_PASS
MARKET_CORNER_ASSET_EVIDENCE lod0_tris=2782 draw_calls=43 cel=true assets=10
```

断言覆盖：10 资产 GLB 加载 / MeshInstance3D / 原点在基底（ground 顶面）/ -Z forward meta / 前缀 / hero 三 LOD / 材质槽≤cap / 材质名非空 / 各 LOD 面数≤cap / 帧内 LOD0 面≤200k / draw call≤60 / 至少一个 cel_base 材质。

## §8.7 七项导入清单

1. **轮廓与交互可读**：Blender 组合渲染 `market_corner_composite_v01.png` + vision_chat 复核——前景角色/中景摊位/远景庇护所三段式读法成立（§1.5）
2. **无复制 IP**：全部手工原创建模（`model_stall_a.py`/`model_env_props.py`），无现成资产
3. **轴向/单位/原点/碰撞/材质槽**：import post 写 `forward_axis=-Z`/`units=metres`；Gate 断言 origin 基底；hero 挂 AABB box 碰撞（层 1）；材质槽 ≤ §8.2 cap
4. **LOD 不爆跳**：三 LOD canopy 底部一致（y=2.7，采样含柱位）；LOD1/2 简化保留主形
5. **夜间/低配**：本次为白昼 frame（§9.5 白昼），夜间留待日制集成（R-14 范围外）；cel 平涂无透明排序问题
6. **动画标记**：环境资产为静态，不适用
7. **目标硬件实测**：draw=43 / tri=2782（Gate EVIDENCE）；GPU ms 与 VRAM 精确值需用户在编辑器 F6 + profiler 实测（headless 无法渲染），见已知缺口

## §9.5 frame #1 固定镜头

`art/source/environment/env_market_corner/concept/market_corner_composite_v01.png`
（1440×900，Blender EEVEE 组合渲染：§1.5 机位 + §3.2 白昼灯光 + 全部环境资产 + 主角/植物占位）

**Godot cel 观感**（描边/量化阴影）需用户在编辑器 `F6` 打开 `MarketCorner.tscn` 确认——headless 无法离屏渲染（强制 dummy 驱动）。

## 渲染器决策：**Forward+ vs Compatibility → 保持 Compatibility**

VERSION.md 显式把此决策推迟到"最终 toon 灯光 art test"。本次即决策点。

**依据**：
- 场景极轻：**2782 tris / 43 draw calls**，Compatibility（gl_compatibility）下轻松 60 FPS（§8.1 预算 1.2M/850 的 <5%）
- cel shader 是简单 `spatial` shader（量化阴影 + inverted-hull 描边），Compatibility 完整支持；无 Forward+ 独有特性需求（无 SSS、无体积光、无复杂反射）
- 卡通平涂对高级光照无增益；Forward+ 的 GPU 开销纯属浪费

**结论**：**保持 `gl_compatibility`**。若 Phase 6 后 Godot profiler 实测（F6）显示 Compatibility 描边开销异常（预计不会，draw call 余量 20 倍），再评估 Forward+。

## 已知缺口 / 后续

1. **Godot cel 描边 + 量化阴影最终观感**：需用户 F6 确认；描边宽度 0.008（≈1.5px @5.5m）待实测标定到 1.25–2.25px
2. **GPU 帧时 / VRAM 精确值**：headless 无法 profiler；待用户 F6 + profiler 记录（§8.1 before/after）
3. **Mira 帧内为程序化剪影**：本次只验证 ENV 美术（计划已声明）
4. **主角 face morphs = 0**（`test_character_asset` Gate D 既有缺口）：Tencent FBX 无 blend shapes；属主角管线范围，非本 art-test；R-15 记为范围外
5. **`test_runtime_yaw.gd` headless 挂起**：既有工作区测试问题（未跟踪文件），非本次引入
6. **夜间灯光未验证**：本次为 §9.5 白昼 frame；日制集成时需复查 cel 阴影在黄昏/夜间的表现（风险 6：shadow_threshold 软化吸附已实现）

## 追溯记录

- 资产锁 `art/source/environment/ASSET_LOCK_MANIFEST.json`：`runtime_export_allowed=true`（Gate E 14/14 后翻），`gate_e_status=14_of_14_checks_passing`，`verify_env_asset_locks.py` PASSED（24 文件）
- runbook `art/source/environment/env_market_corner/ENV_ART_TEST_RUNBOOK.md`：状态 `GATE_E_PASSED`
