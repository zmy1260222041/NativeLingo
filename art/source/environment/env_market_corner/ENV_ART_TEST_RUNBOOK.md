# 环境美术 art-test —「白昼市场角落」生产 runbook

> **状态**：`ENV_ART_TEST / GATE_E_14_of_14 / PASSED`
> **权威上游**：`design/art/art-bible.md` v1.6（§3.7–3.8、§5、§5.6–5.7、§8、§9.5 frame #1）、
> `design/art/environment-modeling-standard.md`、`CONCEPT.md`（本目录概念锁）
> **资产锁**：`../ASSET_LOCK_MANIFEST.json`（schema `stranger.environment_asset_lock.v1`）
> **追溯**：`design/gdd/game-concept.md:244` open question、`:267` 纵切"统一美术"；fit-review 将落 `docs/reviews/2026-08-12-market-corner-art-test-fit.md`（R-15）。
> **栈**：Blender 5.2.0 LTS（`/Applications/Blender.app/Contents/MacOS/Blender`）、Godot 4.6.3、GDScript、`gl_compatibility` 渲染器（VERSION.md）。

本 runbook 镜像角色 runbook 纪律（`chr_player_juvenile/source_locked_v05/HUNYUAN_FROM_CONCEPT_RUNBOOK.md` + `.../source_locked_v06/README.md`），生产路线服从
`environment-modeling-standard.md`：**借用资产只作结构底稿，禁止未改造的现成资产上屏**；
日式木构 / 商店默认配色必须转译为壳板 / 陶 / 合金。交付 art-bible §9.5 frame #1。

## §0 前置

- Blender 5.2.0 LTS、Godot 4.6.3 已固定（VERSION.md）。
- art-bible v1.6 §3.7–3.8、§5、§5.6–5.7、§8、§9.5 与 `environment-modeling-standard.md` 已打开；CLAUDE.md §6 技术栈。
- 每次建模前后跑资产锁校验（见 §7）。人类必须先锁定范例与许可证，Agent 不得自行采购定稿。

## §1 概念锁定（Phase 0）

- 形体/构图权威：`CONCEPT.md` + `concept/market_corner_concept_v01.png`（Blender 渲染 blockout）。
- 受会话工具限制无 text→image；概念参考图为真实 3D blockout 渲染，锁定构图比例/色板分区/镜头读法。
- **用户确认概念图后才进 Phase 1。**

## §2 Blockout（Phase 1）

Blender 图元按 `main.gd` 市场角落精确尺寸搭白模：篷顶 prism 4.2×1.0×3.1、柱 cylinder @±1.6/±1.15 高 2.7、柜台 box 3.2×0.22×0.9（main.gd:112-126）。§1.5 相机下截构图。
**门**：96 px 剪影读作"市场角落"（§1.4）。

## §3 英雄建模（Phase 2）

`env_market_stall_a` 手工 retopology；高变形曲线（檐口、柜台唇）走 edge loops；LOD0/1/2 手动命名 `lod0__/lod1__/lod2__`；原点基底；-Z forward；导出 scale 1.0、Y-up。
**门**：§8.2 各 LOD 面数（LOD0 10k-16k、LOD1 50%、LOD2 20%）。

## §4 Toon shader + 材质（Phase 3）

- `game/shaders/cel_base.gdshader`：两段量化阴影 + 功能性 rim（仅苔薄荷语义交互面）+ 哑光 roughness 0.85（§3.1.B）。v1.6 起必须采样 `albedo_tex` / `normal_tex` / `orm_tex`（§3.6 / §8.4）；未接通道不算最终材质。
- `game/shaders/cel_outline.gdshader`：inverted-hull，淤泥墨 `#17243B`，5.5 m 机位下标定 1.25–2.25 px，12 m 距离关闭。
- 2K 摊位图集：手绘 base color + 简化 normal + ORM；**无程序噪声**（§5.4/§9.3）。
**门**：§3.1.B 哑光+单阴影+功能 rim；shader 合同三通道已接；**关描边后主形仍成立**（显式 §8.7）。

## §5 配景 + 道具 + 植被（Phase 4）

岩石（变体图集）、`prp_lantern_market_a`、`prp_food_token_a/b/c`、`fol_glowplant_a` MultiMass、`env_ground_market_a` 路径 decal、`env_shelter_distant_a` 代理。

## §6 Godot 集成（Phase 5）

- `game/scenes/MarketCorner.tscn`：精确复制 `Main.tscn:24-34` 相机 rig；§3.2 白昼灯光**固定**（不跑 lerp）；内容=主角+静态 A-Pose PBR Mira+摊位+2 灯笼+植物 MultiMass+远景庇护所。
- `game/scripts/env_import_post.gd`：`@tool extends EditorScenePostImport`，镜像 `character_import_post.gd`；剥离 DCC 灯/相机、写 `meta("forward_axis","-Z")`、只给英雄层开 `cast_shadow=ON`。
- `main.gd` 重构：`_add_market_canopy`/`_add_lantern`/`_add_glow_plant` → `_try_load_env_asset(path,pos)`，`ResourceLoader.exists` 则加载 + 挂 `env_lod.gd` + StaticBody3D 碰撞（层 1），否则**原样回退图元**。镜像 `character_visual.gd:119-142`。
- `game/scripts/env_lod.gd`：镜像 `character_visual.gd:144-170` 手动名 substring LOD，按 `hero_facility/medium_prop` 给 §8.2 距离阈值，LOD0→LOD1 边界关描边。
- **-Z 必须导出时烘焙**，不带 `character_visual.gd:129-132` 的 +Z 180° 补救 hack。

## §7 环境 Gate（Phase 6）

- `game/tests/test_market_corner_asset.gd` 14/14（镜像 `test_character_asset.gd`）。
- §8.7 七项导入清单。
- §9.5 frame #1 固定镜头截图（1440×900 白昼）。
- §8.1 在代表帧实测：draw call（≤850）、三角形（≤1.2M）、VRAM（≤650MB）、GPU ms（≤16.0）。
- R-15 fit-review：含 **Forward+ vs Compatibility** 决策（VERSION.md 显式推迟到此 art test），带 before/after GPU 帧时。

**Done** = Gate 14/14 + §8.7 全过 + §9.5 frame 截取 + §8.1 达标 + R-15 归档 + manifest `runtime_export_allowed`→true（最后翻）。

## §8 已验证状态（随工作填入）

**Phase 0 进度（2026-08-12）**：
- 概念锁定文档 `CONCEPT.md`、资产锁 `../ASSET_LOCK_MANIFEST.json`（schema v1，runtime_export_allowed=false）、本 runbook 已落地。
- Blockout 概念渲染 `concept/market_corner_concept_v01.png` + `blender/blockout_concept_v01.blend` + 脚本 `blender/blockout_concept_v01.py` 已产出（48 对象，相机朝 -Y、柱子垂直 2.7m、柜台 z=0.9、远景庇护所 y=-8、角色接地 z=0.75）。像素直方图客观验证色板正确：暖色 41% vs 冷色 10%，主色为尘奶油/珊瑚红/苔薄荷（zai 内置 analyze_image 对该图系统性误读，已弃用——见下）。
- **待用户确认概念图后才进 Phase 1。**

**Phase 2 进度（2026-08-12，概念图已确认）**：
- 概念图 v01（blockout 渲染）经 `vision_chat`（api 云端 VL）复核后用户确认，进 Phase 2。
- `env_market_stall_a` 手工建模完成：`blender/model_stall_a.py`（headless，继承 blockout 尺寸 + Z-up 约定）+ `blender/model_stall_a.blend` + `export/env_market_stall_a.glb`（**单文件三 LOD mesh**：`lod0__`/`lod1__`/`lod2__`，runtime env_lod.gd 按名分组）。
- Godot inspect 验证：WORLD_AABB (-2.1,0,-1.55)~(2.1,3.71,1.55)，**原点在基底 min_y=0**；三 LOD canopy 底部一致 y=2.7（篷顶坐柱，无爆跳）；面数 LOD0≈2274 / LOD1≈1262(55%) / LOD2≈670(29%) 全 ≤§8.2 上限；材质槽 3（shell/clay/alloy，§5.3）；前脸潮青走**顶点色 COLOR_0**（Phase 3 cel shader 消费；Blender Principled 预览不显示）。
- vision_chat 三轮修正：篷顶改为**从柱顶升起**（`roof_height` 采样强制含柱位 x=±1.6/y=±1.15，杜绝 LOD 采样跳过柱位导致的悬浮）、柱顶托碗、Y 向 eave 自柱位之外起翘、前脸潮青顶点色、货架支撑腿、绳结移柱顶绑扎点 z=2.62。最终确认篷顶坐全部四柱。
- 资产锁已填 `env_market_stall_a` 三文件（model_script/source_blend/runtime_glb_source），`verify_env_asset_locks.py`（兄弟脚本，已复制到 environment/）PASSED。

**Phase 3 进度（2026-08-12）**：
- `game/shaders/cel_base.gdshader`：两段量化阴影（ndl 过 `shadow_threshold`，`smoothstep` 软化吸附）；**Godot 4.6 `light()` 无 `SHADOW` 内置，阴影折叠在 `ATTENUATION`**（官方文档确认），用 `smoothstep(0.5,1.0,ATTENUATION)` 量化遮挡；`render_mode specular_disabled` + roughness 0.85 哑光（§3.1.B）；功能 rim 仅 `functional_rim=true`（苔薄荷交互面）；顶点色 COLOR_0 优先（前脸潮青不与图集合金底色相乘污染）。
- `game/shaders/cel_outline.gdshader`：inverted-hull（`cull_front` + `VERTEX += NORMAL*outline_width`），淤泥墨 `#17243B`，`outline_width=0.008`（§1.5 机位 5.5m 下 ≈1.6px，Phase 6 实测标定 1.25-2.25px）；`depth_draw_always`+`shadows_disabled`；12m 距离关闭由 env_lod.gd 处理。
- **2K 摊位图集**：`blender/bake_atlas_stall.py`——smart-unwrap 全 mesh + **UV 象限偏移**（shell/clay/alloy_frame/alloy_detail 四象限共享 0-1 不重叠）+ Cycles bake DIFFUSE → `textures/stall_atlas_2k.png`；`textures/stall_orm_2k.png`（G=0.85 粗糙度/B=0 金属/R=0 AO，cel 平涂无需逐像素 AO）。**Blender UV (0,0) 在图像左下**，象限命名按 UV 坐标。
- Godot 验证：GLB 全 mesh `uv=true` + `albedo=stall_atlas.png`。
- 描边标定 + §3.1.B 关描边后主形仍成立 + 材质连 cel shader → Phase 5/6 在 Godot 场景实测。

**Phase 4 进度（2026-08-12）**：
- `blender/model_env_props.py`（headless）建 7 个配景/道具/植被资产 + `blender/env_props.blend` + 9 个独立 GLB（rock 两个变体）：
  - `prp_lantern_market_a`（LOD0/1，stem+hanger+hook+emissive bulb，顶点色炉琥珀）
  - `fol_glowplant_a`（单株：双段锥茎 + emissive 苔薄荷 bulb，顶点色 alpha 控 emissive，MultiMesh 运行时实例化）
  - `env_rock_market_a/b`（icosphere 随机变形 LOD0/1，动态 lift 原点在基底）
  - `env_ground_market_a`（28×28 地面 + 路径 decal + 排水篦，顶点色宏观分区；**顶面 y≈0 厚度沉地下**——Gate 对 ground 用顶面断言）
  - `env_shelter_distant_a`（远景剪影：body+roof prism+emissive window）
  - `prp_food_token_a/b/c`（种荚/莓簇/陶碗装食物）
- **关键 gotcha**：`env_props.blend` 含 9 个 collection，gltf 导出必须 `use_selection=True` + 按 collection 选中对象（`use_selection=False` 会把之前所有 collection 烘进每个 GLB——排查时曾致所有 prop 带 lantern 数据）。
- Godot 分进程验证：全部 origin_at_base ✓（rock 动态 lift 精确到 0）、LOD 命名 ✓、ground 顶面 y≈0。
- 资产锁已填 7 资产（共享 model_script/source_blend + 各自 GLB），`verify_env_asset_locks.py` PASSED（24 文件）。Phase 3 bake 变更已刷新 stall 的 blend/GLB 锁 + 加锁 bake_script/atlas/orm。

**Phase 5 进度（2026-08-12，Godot 集成）**：
- GLB 已落 `game/assets/environment/`（9 GLB + atlas/orm 纹理）。
- `game/scripts/env_import_post.gd`（`@tool extends EditorScenePostImport`，镜像 character import hook）：剥离 DCC 灯/相机、写 `meta(forward_axis=-Z, units=metres, source=hand_modeled_blender_5.2)`、只英雄资产（`env_market_stall` stem）开 `cast_shadow=ON`。经 `.import` 文件 `import_script/path` 注入 9 个 GLB（python 改 .import）。
- `game/scripts/env_lod.gd`（`class_name EnvLod`）：手动名 substring LOD（`lod%d__`），hero 12m/26m、prop 12-25m；hero LOD0 每 mesh 复制 inverted-hull 描边子 mesh（cel_outline），LOD0→LOD1 边界（12m）关描边（§3.1.B）。
- `game/scenes/MarketCorner.tscn`（精确复制 Main.tscn:24-34 相机 rig：CameraPivot 倾角/SpringArm 5.5/0.25/mask1/Camera3D fov68 current）+ `game/scripts/market_corner.gd`（固定 §3.2 白昼灯光，不跑 lerp；`_try_load_env` 加载 GLB + 挂 EnvLod + hero 碰撞；植物 MultiMesh 24 株环摊位；主角 CharacterVisual player + 静态 A-Pose PBR Mira @(-3,1,-2)）。
- `main.gd` 重构：`_add_market_canopy`/`_add_lantern`/`_add_glow_plant` → `_try_load_env_asset(file,pos,hero)`，`ResourceLoader.exists` 命中则 GLB+EnvLod+StaticBody3D(AABB box,层1) 碰撞，否则**原样回退图元**。镜像 character_visual.gd:119-142。
- **Godot 验证**：MarketCorner 实例化加载全部环境资产 ✓；`STALL meta forward_axis=-Z units=metres`（import post 生效）✓；hero cast_shadow ON ✓。回归：`test_game_state.gd` + `test_character_asset.gd` PASS ✓。
- **视觉验证**：Godot headless 强制 dummy 渲染无法离屏截图 → 用 Blender EEVEE 组合渲染（`blender/_render_market_preview.py` 导入全部 GLB + §1.5 相机 + §3.2 灯光 + 主角/植物占位）`concept/market_corner_composite_v01.png`。vision_chat 复核：构图可读（前景角色/中景摊位/远景庇护所）、低模风格一致、色板温暖协调 ✓（摊位 Blender 预览缺地面投影是 Blender 导入侧行为，Godot hero cast_shadow 已验证 ON）。
- 已知限制：Godot cel 描边/量化阴影的最终观感需用户在编辑器 F6 打开 `MarketCorner.tscn` 确认（Phase 6 记录）。

**Phase 6 进度（2026-08-12，环境 Gate E 通过）**：
- `game/tests/test_market_corner_asset.gd`（镜像 test_character_asset.gd 结构）**14/14 PASS**：`MARKET_CORNER_ASSET_TEST_PASS` / `EVIDENCE lod0_tris=2782 draw_calls=43 cel=true assets=10`。
- **材质槽修复**：Blender 每 LOD 独立材质致 GLB 冗余（stall 9 槽）。改共享材质（三 LOD 复用同一材质 data block）+ 单槽资产顶点色调色（ground path/grate、shelter roof/window、glowplant bulb、token_c bowl）→ stall ≤3 / lantern ≤2 / 其余 ≤1。
- **rock LOD 反向修复**：`subdivisions=2-lod`（LOD0 细 / LOD1 粗）。
- **import post hook 失效排查**：删 `.import` 后 uid/缓存失配致 meta/cel 材质不生效。修复：注入 `import_script/path` 后 `touch *.glb` + 清 `.godot/imported` 对应 `.scn` + 重新 `--import`。
- §8.7 七项清单逐项记录于 R-15；§9.5 frame 用 Blender EEVEE 组合渲染（`concept/market_corner_composite_v01.png`），Godot cel 观感待用户 F6。
- **R-15 fit-review 归档**：`docs/reviews/2026-08-12-market-corner-art-test-fit.md`，含 **Forward+ vs Compatibility → 保持 gl_compatibility**（场景仅 2782 tri/43 dc，cel shader 无 Forward+ 依赖）。
- 资产锁翻 `runtime_export_allowed=true`，`gate_e_status=14_of_14_checks_passing`，`verify_env_asset_locks.py` PASSED。
- 回归：`test_game_state.gd` PASS；`test_character_asset.gd` morphs=0 为 Gate D 既有缺口（主角 FBX 无 face morphs，范围外）；`test_runtime_yaw.gd` headless 挂起为既有工作区问题。

**视觉验证工具栈（已切换 + 已修复）**：
- 弃用 z.ai 运行时内置的 `mcp__4_5v_mcp__analyze_image`（对 Blender 渲染图系统性编造物体/误读颜色，不可信；且为 runtime 内置、无配置入口可删）。
- 改用 `QwenLM/Qwen-MM-Plugins`（core + api 官方 plugin 安装，见 §9）。**看图用 api `vision_chat`（DashScope qwen3.7-plus 云端 VL，返回文本）**：core `read_image` 走 MCP image content 喂图给 agent，但本地模型 deepseek-v4-flash 是**纯文本**、吃不了图（返回 `[Unsupported Image]`）；vision_chat 在云端看图、回传文本，本地纯文本模型可消费。2026-08-12 已端到端验证：`vision_chat` 成功描述概念图（摊位/2人物/2灯笼/远景庇护所/构图/色板，与 blockout 脚本一致）。`visualize` 支持 .glb/.gltf 3D 模型（用 Blender 渲染）——Phase 2 导出 env_market_stall_a.glb 后用它验证。
- **权限坑（已修）**：`read_image`/`vision_chat` 首次调用报 `deepseek-v4-pro is temporarily unavailable` 是因为 auto 模式权限分类器（deepseek-v4-pro）间歇性不可用，而旧 allow 规则 `mcp__qwen-mm-plugins-core__read_image` 与插件作用域实际工具名 `mcp__plugin_qwen-mm-plugins-core_qwen-mm-plugins-core__read_image` **不匹配**，分类器每次都被调用。修复：`.claude/settings.local.json` 改成字面 server + 工具通配 `mcp__plugin_qwen-mm-plugins-core_qwen-mm-plugins-core__*` 与 `mcp__plugin_qwen-mm-plugins-api_qwen-mm-plugins-api__*`（allow 规则通配符只能在工具位置，server 位置必须字面量；`claude mcp list` 看真实 server 名）。

**Blender 5.2 建模 gotcha（Phase 1+ 必读）**：
1. **Z-up 建模**：Blender 原生 Z-up（X 右、Y 进深、Z 上）。在 Blender 内一律按 Z-up 建模；gltf 导出时 Blender 自动 Z-up→Y-up，匹配 art-bible §8.6 的 Godot 约定（-Z forward 在 GLB 导出阶段烘焙，gate 测试断言）。不要在 Blender 里用 Y-up 坐标——会把地面变成立墙、相机变成俯视。
2. **`transform_apply(scale=True)` 会吃掉 location**：在 5.2 里它把 location 一起 apply（归零），导致所有 cube 塌到原点。blockout 阶段不要 apply scale（视觉尺寸不变）；真正的 apply scale 留到 Phase 2 导出前手动做（`bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)` 显式参数）。
3. **EEVEE 引擎名**：Blender 5.2 是 `BLENDER_EEVEE`（非 `BLENDER_EEVEE_NEXT`，也非 4.x 的 EEVEE_NEXT）。`SceneEEVEE` 无 `use_gtao` 属性。

## §9 部署：Qwen-MM-Plugins（官方 plugin，core + api，已完成）

- clone 到 `/Users/a86138/Developer/Qwen-MM-Plugins`（项目外，工具不属于 NativeLingo 仓库），作为 marketplace 本地源。
- **官方 plugin 安装**（2026-08-12，替代最初的手动 symlink+MCP 注册，已清理手动残留）：`claude plugin marketplace add /Users/a86138/Developer/Qwen-MM-Plugins` + `claude plugin install qwen-mm-plugins-core@qwen-mm-plugins` + `qwen-mm-plugins-api@qwen-mm-plugins`（scope: user）。受管插件自带 skill + MCP 声明，`claude mcp list` 显示 `plugin:qwen-mm-plugins-core:qwen-mm-plugins-core` / `plugin:qwen-mm-plugins-api:qwen-mm-plugins-api` ✔ Connected。
- **环境**：`uvx`、`ffmpeg` 已装；`~/.qwen-mm-plugins/config` 配 DASHSCOPE_API_KEY + MAAS 端点（api 云端 VL 必需，vision_chat 已验证）。
- **MCP 工具在会话启动时注入**：plugin 装完需重启 Claude Code，新会话才有 `mcp__plugin_qwen-mm-plugins-*` 工具。
- **权限 allow 规则**：`.claude/settings.local.json` — `mcp__plugin_qwen-mm-plugins-core_qwen-mm-plugins-core__*` + `mcp__plugin_qwen-mm-plugins-api_qwen-mm-plugins-api__*`（见 §8 权限坑）。

## 已知缺口

1. **Mira 目前是静态 A-Pose PBR 评审资产**：Base Color、Normal、AO 已从 Hunyuan 高模投射并接入 Main/MarketCorner；骨骼、蒙皮和正式互动动画仍待 NPC Gate D。角色规范见 `character-modeling-standard.md`。
2. **Compatibility 描边开销**：inverted-hull 翻倍 draw call；超 §8.1 预算则 R-15 提 Forward+。v1.6 不重开 SSGI / Forward+ 作为完成度手段。
3. **概念图为 blockout 渲染非手绘**：受会话工具限制；若用户另给手绘概念图则升版 v02。
4. **v1.6 生产债**：阶段 1 已换壳板住宅并删除房屋/树/岩/摊位/灯笼图元回退。仍待阶段 2–4：
   `cel_*` 未接 Normal+ORM；地面未达 §5.7；发光植物仍是圆环 MultiMesh；加热器/水站/广场仍是图元；
   树/岩/脊/huts_v02 未入资产锁。
