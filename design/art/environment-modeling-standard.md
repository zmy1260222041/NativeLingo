# 《异乡人 / Stranger》环境建模规范

> **2026-09-05 用户批准补充**：遵从 Art Bible v1.7 柔和风格化环境覆盖条款。
> 粗糙度、反光与法线必须真正参与受光；壳板干哑、陶体柔润、旧合金定向反光，纤维深哑。
> 首轮精修入口至 Tavi。源与烘焙写入 `quality_pass_v01`，通过验证后登记新哈希，保留旧基线。

> **版本**：1.0
> **日期**：2026-08-14
> **状态**：ACTIVE / 环境唯一生产规范
> **视觉上游**：`design/art/art-bible.md` v1.6
> **概念锁**：`art/source/environment/env_market_corner/CONCEPT.md`
> **资产锁**：`art/source/environment/ASSET_LOCK_MANIFEST.json`

本规范取代散落的「纯手搓、禁止现成资产」「从 `main.gd` 图元回退继续细化」「未改造的商店包
直接进 Godot」。资产自己的 `CONCEPT.md`、runbook 和 Gate review 只补充场景特有事实，不得
降低这里的生产门槛。角色资产不走本文件，见 `design/art/character-modeling-standard.md`。

## 1. 权威来源与资产保护

1. 世界身份是异星聚落。上屏材料只允许 Art Bible §3.6 五家族：叠压壳板、浇铸陶体、旧合金、
   纤维绳结、活体生态。日式木构、砖石照片、希卡蓝橙、来源库默认皮肤不得作为最终外观。
2. `ASSET_LOCK_MANIFEST.json` 中的概念图、源 `.blend`、导出 GLB、图集与 ORM 为不可覆盖基线。
   任何调整必须写入新的版本文件。
3. 借用资产（Synty、Sketchfab、风格化商店包）只作结构底稿。无许可证记录、无改造清单的源
   不得进入 `game/assets/`。
4. 生成凭据、商店密钥和签名下载 URL 绝不入库。
5. 每次建模前后运行 `python3 art/source/environment/verify_env_asset_locks.py`。失败时立即
   停止，不继续保存或导出。
6. `fol_tree_stranger_a`、`env_rock_facet_a/b`、`env_ridge_distant_a` 必须补进资产锁后才算
   受保护基线；未入锁不得当不可变源。

## 2. 唯一生产路线

```text
人类指定范例 + 许可证
→ 借用结构底稿或手搓灰模
→ remesh / UV / LOD 命名 / 原点与轴向
→ 法线定制（树：球形传递；岩：切面化；其余：家族法线）
→ NPR 手绘 BaseColor + ORM 打包 + 必要 Normal
→ 模块组合 + §5.6 簇散布
→ Godot 导入、cel shader 合同、碰撞、接触 AO
→ Art Bible §8.7 / §8.8 十二项
```

- 原神 / 塞尔达只提供工艺：模块化构造、球形法线、切面岩、ramp 冷暖。不提供日式木瓦外观。
- 方块、球、胶囊、圆柱、棱柱只允许用于碰撞代理、调试 gizmo 和编辑器 blockout。由 primitives
  拼出的运行时房屋、树、岩、地面、英雄设施不得作为最终网格。
- `main.gd` 在 GLB 缺失时回退图元是开发期安全网，不是交付路径。可玩 `Main.tscn` 按 §8.8
  第 10 项验收。
- 旧 runbook 中「纯手工 Blender 建模（无现成资产）」作废。正确表述：**禁止未改造的现成资产**。

## 3. 人类 / Agent 职责

服从 Art Bible §3.8。摘要：

| 阶段 | 人类 | Agent |
|---|---|---|
| 选型 | 指定房屋模块、树、岩、地表簇范例并确认许可证 | 检索与登记，不自行采购定稿 |
| 几何 | 拍板主轮廓、门洞负空间、一处作者痕迹 | remesh / UV / LOD / 原点 / 碰撞 |
| 法线 | 验收树冠连续亮弧与岩体 5–9 个特征面 | 球形法线、切面化、家族法线 |
| 贴图 | 收敛色板，否决来源库配色 | NPR BaseColor 草稿、ORM、三向投影遮罩 |
| 引擎 | 拍板灯光状态与 UI 框 | cel shader、MultiMesh 簇、阴影 / 雾 / Glow |
| 禁区 | 不得降低 §8.8 | 不得图元交付、写实贴图直上线、改锁定角色四视 |

## 4. Gate

环境不使用角色四视门禁。Gate 顺序如下；任一层失败不得覆盖 `game/assets/environment/`。

| Gate | 名称 | 必须成立 | 失败后果 |
|---|---|---|---|
| E0 | 概念锁 | `CONCEPT.md` 构图、色板分区、形状词汇获人类确认 | 不得开始英雄建模 |
| E1 | 构造灰模 | 关颜色后读出门洞厚度、板缝、承重链；无未转换原始体与地球物件 | 不得画贴图 |
| E2 | 家族材质 | 主家族 ≥ 60%，同屏家族 ≤ 3；`albedo_tex` + `normal_tex` + `orm_tex` 已接；灰阶下壳 / 陶 / 合金可分 | 不得进运行场景 |
| E3 | 接触与痕迹 | 底部接触影或 AO 贴花；英雄资产 ≥ 1 处作者痕迹；簇符合 §5.6 | 不得标完成 |
| E4 | 运行导入 | 轴向 / 原点 / LOD / 压缩正确；§8.7 七项 + §8.8 十二项；代表场景有 profiler 记录 | 不得把 `runtime_export_allowed` 置 true |

借用资产额外提交：许可证、来源 URL、改造前后对照（轮廓、配色、材料家族）、第一读感记录。
评审者先报出来源库名或「塞尔达村」即 E2 FAIL。

## 5. 几何、法线与 LOD

1. 住宅最小构造服从 Art Bible §5.3：有厚度门洞、可数板缝、折片屋顶、至少一处异星开口与一处修补。
2. 树冠必须做球形法线传递（§3.7.A）。面片自身法线只给描边壳。
3. 岩体保留 5–9 个宏观特征面（§3.7.B），禁止 icosphere 随机变形充当切面岩。
4. LOD 手工保留轮廓。预算沿用 Art Bible §8.2。不得用自动 decimate 在门洞和板缝上挖凹痕。
5. 模块化套件：墙板段、柱、篷片、门槛共享 + 顶点色 tint + 少量独有件。不逐栋独立建模。

## 6. 材质、地面与散布

- 英雄环境必须满足 Art Bible §3.6 / §8.4 shader 合同：采样 BaseColor、Normal、ORM。
  顶点色只作分区 tint 或地面层权重，不得整面替换英雄 albedo。
- 金属度只允许旧合金家族。
- 地面走 §5.7：三层手绘 BaseColor + 顶点色权重 + 斜率混合。整块染色平面 FAIL。
- 散布走 §5.6 簇配方。禁止 `_ready()` 里 `i / N * TAU` 画圆，禁止无变体连续复制同一 GLB。
- 不用噪声、毛孔、随机磨损伪装构造。完成度来自接缝、家族受光和作者痕迹。

## 7. 坐标、碰撞与 Godot 交付

- 源模型以米为单位、应用变换、原点在基底中点、运行朝向 `-Z`、scale 1.0、Y-up。
- `-Z` 必须在导出时烘焙，不在运行时补 180°。
- 碰撞与视觉分离：可见网格不得靠 Box/Cylinder 冒充；碰撞可以用简化凸包或盒。
- 英雄层开 `cast_shadow`；小型装饰灯默认不投影。
- 导出只包含运行网格、材质、LOD 和批准的顶点色；不含参考图、相机、灯或测试道具。
- 只有 Gate E0–E4 通过，才允许更新 `game/assets/environment/<asset_id>.glb` 并把
  `runtime_export_allowed` 改为 `true`。

## 8. 当前资产状态

| 资产 | 锁定版本 | 当前状态 | 下一步 |
|---|---|---|---|
| `env_market_stall_a` | `source_locked_v01` | Gate E 几何/测试曾过；shader 未接 Normal+ORM | 按 §3.6 合同补通道，重跑 E2 |
| `env_ground_market_a` | `source_locked_v01` | 顶点色平面，未达 §5.7 | 三层手绘 + 斜率混合 |
| `env_hut_residential_a/b/c` | `huts_v02` 未入锁 | 三栋不同造型；晶体/种荚贴图 | 补锁 |
| `env_shelter_distant_a` | 旧盒锥已替换 | 与住宅同套件，暖窗导航，不再染黑 | 补锁 |
| `fol_tree_stranger_a` | 未入锁 | 球形法线已做 | 补锁 + NPR BaseColor |
| `env_rock_facet_a/b` | 未入锁 | 切面化已做 | 补锁；停止把旧 icosphere 岩当英雄件 |
| `env_ridge_distant_a` | 未入锁 | 远景剪影可用 | 补锁 + 雾层校验 |
| `env_terrace_market_a` / `env_plaza_market_a` | 未入锁 | 0.5 m 台阶台 + 陶盘广场 | 补锁 |
| `prp_heater_old` / `prp_reservoir_a` / `prp_beacon_market_a` | 未入锁 | 已替换圆柱图元 | 补损坏态细节 |
| 簇散布 | 无 | 6 组不规则簇，圆环已删 | 簇内再补作者痕迹 |
| 地面贴图 | 草稿 | 三向投影尘土平铺 | §5.7 三层手绘混合 |

上表资产在补锁与 E2 完成前，都不是最终 runtime 完成件。当前禁止以「Gate E 14/14 曾经通过」
为由跳过 v1.6 的 shader 合同、图元禁令和地面条款。
