# 《异乡人 / Stranger》角色建模规范

> **版本**：1.0
> **日期**：2026-08-11
> **状态**：ACTIVE / 跨角色唯一建模规范
> **视觉上游**：`design/art/art-bible.md`
> **资产锁**：`art/source/characters/ASSET_LOCK_MANIFEST.json`

本规范取代散落的“程序化几何体拼角色”“从运行时占位网格继续细化”“生成结果直接进 Godot”以及
未经实际验证的私钥 API 参数说明。资产自己的 `README.md`、reference manifest 和 Gate review 只补充
角色特有事实，不得降低这里的生产门槛。

## 1. 权威来源与资产保护

1. 只有用户批准并进入 `source_locked_vXX/` 的四视图是形体权威；被拒绝、被替代的概念图不得参与生成或建模。
2. `ASSET_LOCK_MANIFEST.json` 中的概念图、生成器（Rodin/Tripo）原始 GLB、干净导入 `.blend` 和
   normalized GLB 均为不可覆盖的基线。任何调整必须写入新的版本文件；必要时升 `source_locked_vXX`。
3. Gate A 雕刻从 `sculpt/<asset_id>_gate_a_v01.blend` 开始，不在生成器源（`rodin_source/`/`tripo_source/`）
   基线上直接保存。
4. 生成凭据、trial key、subscription key 和签名下载 URL 绝不入库；任务 UUID 只可作为无秘密审计编号。
5. 每次建模前后运行 `python3 art/source/characters/verify_asset_locks.py`。失败时立即停止，不继续保存或导出。

## 2. 唯一生产路线

```text
用户批准的标准四视图
→ 视图注册与部件/左右映射
→ Tripo 生成可雕刻基础网格
→ 干净 Blender 导入与四视 clay 证据
→ Gate A 雕刻 / remesh / 形体精修
→ 手工 retopology 与面部/关节 edge loops
→ UV、图形化 PBR 材质
→ 绑定、面部、动画
→ 手工 LOD
→ Godot wrapper、碰撞与运行验证
```

> **生成器决策（ADR-0001）**：主角角色细化全面改用 **Tripo** 生成基础网格（替代原 Rodin 唯一路线）。
> 理由见 `docs/architecture/adr-0001-character-refinement-tripo.md`。Rodin/Hunyuan 已锁基线保留为
> 资产锁不可变基线，但新角色的基础网格生成统一走 Tripo（多视图图→3D，DashScope 变体复用
> `DASHSCOPE_API_KEY`，或 Tripo 原生 API 单图/文生）。生成凭据绝不入库。

- Tripo 只提供 Gate A 基础表面，不提供最终比例、拓扑、材质、绑定或 LOD。
- Blender 中的 sculpt、remesh、retopology、edge loops、face topology 和 subdivision 是必需生产步骤。
- 方块、球、胶囊、圆柱只允许用于临时尺寸/碰撞 blockout。由 primitives 拼出的运行时角色不得作为
  sculpt source、retopo source 或最终网格。
- 当前 Godot 程序化 NPC 是可删除的运行占位，不属于资产链，也不作为任何造型判断依据。
- 当 Tripo 基础网格已具备可修复的整体体积时，优先在版本化副本上雕刻修复；不得因局部错误反复随机生成。

## 3. 四视约束与 Gate A

四视顺序固定为正面、角色左侧、背面、角色右侧。正面锁定 X/Z，侧面补充 Y/Z，背面复核宽高、
头顶层级和后部结构。每个角色必须在 reference manifest 中写明物理左右、可见部件与遮挡规则。

Gate A 必须同时满足：

- 正、左、背、右 clay 与锁定图逐视图叠加；包围盒、中心和 IoU 使用资产 manifest 的阈值，不凭感觉通过。
- 头、颈、肩、胸/主躯干、腰/连接段、骨盆/下部结构、肘、腕、膝、踝、手和脚均有概念图对应 landmark。
- 眼睛位于眼窝结构中，具备眼球/瞳孔/眼睑所需空间；嘴不是贴片，也不是无法变形的表面划线。
- 手掌、指根与准确指头数可辨；脚掌、后跟和准确趾数可辨。不得用手套 blob 或脚块替代。
- 薄片、环、头冠、甲片和挂件按遮挡关系分层；生成器误填的孔洞、尾巴、融合片和锯齿伪影全部修正。
- 96 px 纯黑前/侧/背剪影保留角色主形与负空间；修好一个视角不得破坏其他视角。

Gate A 失败时，retopology、绑定、动画、LOD 和 runtime export 全部阻断。

## 4. 雕刻、重拓扑与细分

1. 在 Gate A 副本中先修最大轮廓与比例，再修连接结构，最后修脸、手脚和次级表面；禁止先做纹理遮错。
2. 可使用 voxel remesh / multires / sculpt，但每次 remesh 后重新检查四视 silhouette 和薄片厚度。
3. LOD0 必须手工 retopology。眼睑、口轮、肩、肘、腕、髋、膝、踝具有连续变形环；避免把三角扇放在变形区。
4. Subdivision 仅用于检查曲面连续性与高模烘焙，不以不可控细分替代合理低模拓扑。
5. 极限姿势检查覆盖闭眼、张口、举臂、交叉手臂、深屈膝、脚掌接触和角色专属姿势。

预算沿用 Art Bible §8：主角 LOD0/1/2 分别 ≤32k/16k/6k 三角面；关键 NPC LOD0 24k–30k、
LOD1 ≤13k、LOD2 ≤5k。LOD 必须手工保留轮廓，不依赖自动 decimate 产生凹痕。

> **例外（chr_player_juvenile v06，2026-08-11）**：主角 LOD0/1/2 改由腾讯云 ai3d
> `SubmitReduceFaceJob`（Polygen 1.5）从 v05 Hunyuan 高模自动减面生成，三档分别落在
> 11.3k / 8.9k / 5.7k 三角面，全部低于上限。此举经资产负责人拍板，刻意偏离上述"LOD0 必须
> 手工 retopology"条款，以换取云端管线的端到端自动化。代价：变形区（肘/腕/膝/踝）的边流
> 不及手工 retopology，走路动画在极端关节角度可能出现轻微凹痕——在 v06 验收里作为已知
> 妥协记录，若不可接受须回退到手工 retopology 重做 LOD0。其余 NPC 仍遵守手工 retopology 规则。

## 5. 材质、绑定与动画

- 生成器（Rodin/Tripo）PBR 只用于辨识生成表面，最终 Base Color、Normal、ORM 按 Art Bible 重绘；单角色材质槽 ≤3。
- 不用噪声、毛孔、随机磨损或弥漫互渗伪装造型。色块边界、单层硬阴影和少量中尺度结构承担完成度。
- 主角 deform bones ≤72，NPC ≤68；每顶点最多 4 权重，清除 `<0.02` 权重。
- 面部最少支持独立眨眼、眉、下颌和嘴角；口型按角色需要建立，不把整张脸作为刚性片旋转。
- Blender 动作以 30 fps 整数帧烘焙。glTF 不把 Blender timeline marker 当可靠事件数据；脚步、交互和
  释放事件在 Godot 导入后处理或 sidecar 中建立并测试。

## 6. 坐标、LOD 与 Godot 交付

- 源模型以米为单位、应用变换、脚底中点为原点、运行朝向 `-Z`、scale 1.0。
- 不在 GLB 内为现有胶囊碰撞体硬加 0.9 m 偏移；Godot wrapper 将 `CollisionShape3D` 放在角色局部
  `y=0.9 m`（或依实际身高重新求值），网格仍保持脚底原点。
- LOD 切换由 Godot wrapper 明确定义：主角 10 m / 22 m；关键 NPC 9 m / 20 m。不能假设 GLB 后缀会
  自动得到精确切换距离。
- 导出只包含变形骨、运行网格、材质、morph 和批准动作；不含参考图、相机、灯、控制器或测试道具。
- 只有 Gate A–D、Godot 导入、固定镜头、早晚灯光、碰撞和 LOD 验证全部通过，才允许生成
  `game/assets/characters/<asset_id>.glb` 并把 `runtime_export_allowed` 改为 `true`。

## 7. 当前资产状态

| 资产 | 锁定版本 | 当前状态 | 下一步 |
|---|---|---|---|
| Player Juvenile | `source_locked_v06` | Hunyuan cloud / Gate D 15-of-16 | LOD0 面部 blendshape（blink/jaw/viseme）手工待办 |
| Mira | `source_locked_v06` | Rodin base / Gate A FAIL | 版本化雕刻：脸、三肩片、三指手、腿脚、背带 |
| Rowan | `source_locked_v04` | Rodin base / Gate A FAIL | 版本化雕刻：开放下环、非对称脸、三指手、关节 |
| Tavi | `source_locked_v06` | Concept source locked / reference prep pending | 确定目标身高；拆分、注册并测量四视后才可提交 Rodin |

四者都不是 runtime asset；当前禁止覆盖游戏角色资产。
