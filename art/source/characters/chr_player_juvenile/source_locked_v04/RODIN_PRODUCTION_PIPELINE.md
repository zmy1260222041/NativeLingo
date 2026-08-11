# Rodin 主角生产流水线

> 本文件只记录主角特例；跨角色权威流程为
> `design/art/character-modeling-standard.md`。所有阶段仍以
> `reference/figure_view_{0,1,2,3}.png` 和 `design/art/art-bible.md` 为视觉合同。

## Stage 0 — 可复现基础网格

运行 `../blender/import_render_rodin_v04.py`，确认：

- `rodin_source/chr_player_juvenile_rodin_v04.blend` 存在；
- 1.78 m、脚底原点、单闭合流形、0 非流形边；
- Workbench 四视图与 EEVEE 两张材质图均能看到模型；
- `runtime_export_allowed=false`。

## Stage 1 — Gate A 形体修复

从焊接后的不可变源网格另存为
`sculpt/chr_player_juvenile_gate_a_v01.blend` 后雕刻，不覆盖 baseline，也不随机重新生成另一版角色：

1. 删除概念图不存在的尾巴并修复腰带/臀部表面。
2. 恢复额头到口鼻的楔面、嵌入式眼窝和可动眼睑。
3. 分离三片后掠头冠，避免合成单片鳍或侧耳。
4. 修正肩胛、肘、膝、后跟和小腿 taper。
5. 保证每手三指、每脚三趾，并在 96 px 保持负空间。
6. 对正面、左侧、背面、右侧逐视图叠加比较。

使用 `../blender/extract_silhouette_mask.py` 从概念视图和 clay 渲染生成同尺寸剪影，再计算
overlay、bbox、centroid 和 IoU；不要凭肉眼宣告通过。

Gate A 必须同时通过：主要轮廓和 landmark 与四视图一致；尾巴不存在；三片头冠、三指、三趾
全部可辨。任何单视图改善不得破坏其他视图。

## Stage 2 — 动画拓扑

- 保留高模为 sculpt source，另建 LOD0 quad retopo。
- 在眼、嘴、肩、肘、腕、髋、膝、踝建立连续 deformation loops。
- LOD0 不超过 32k 三角形；最多 3 个材质槽。
- 检查极限姿势，不用隐藏穿模替代权重修复。

## Stage 3 — 材质

- 最终材质重新按 Art Bible 绘制；Rodin PBR 只作几何识别参考。
- 体表暖灰杏 `#BFA982`，暗面树皮梅 `#5A3F58`。
- 头冠暮靛 `#34335E` 与克制信号兰 `#9A6ACB`。
- Base Color 使用 sRGB；ORM/Normal 使用 linear；角色总材质槽 ≤3。

## Stage 4 — 绑定、面部和动画

- ≤72 deform bones，每顶点 ≤4 权重，清理 `<0.02` 权重。
- 三指手、三趾脚；头冠和织带次级骨总量受 Art Bible 约束。
- 面部包含眨眼、眉、下颌、嘴角和必要 viseme。
- 五个运行时动画：idle、walk、greet、offer、clarify；30 fps、整数帧、移动原地循环。

## Stage 5 — LOD 与 Godot GLB

- LOD0 ≤32k、LOD1 ≤16k、LOD2 ≤6k 三角形。
- 网格节点名称分别包含 `lod0__`、`lod1__`、`lod2__`。
- 米制、Y-up、面向 `-Z`、双脚中点原点、scale 1.0。
- 导出只含变形骨、网格、材质、morph 和五个动作；不含相机、灯光、参考图或控制器。

## Stage 6 — Gate D

只有以下项目全部通过，才将最终文件写入 `game/assets/characters/chr_player_juvenile.glb`：

1. Gate A–C 已通过并留有四视图证据。
2. 运行 GLB 具有三档 LOD、合格骨骼/材质/morph 和五个动画。
3. Godot 导入测试、游戏内固定镜头、早晚灯光和 LOD 距离均通过。
4. 将源 `.blend` 的 `runtime_export_allowed` 明确设为 `true`。
