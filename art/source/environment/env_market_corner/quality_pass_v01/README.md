# 入口 → Tavi 柔和风格化样板 · quality_pass_v01

2026-09-05。用户批准的独立版本；原 110 个锁定文件不修改。
运行导出沿用原文件名，三件商品为新增文件。当前角色、交互锚点、交易与存档格式不变。

## 资产与尺寸

| 资产 | 内容 | 图集 |
|---|---|---|
| env_market_stall_a | 保留弯月篷；85 mm 壳厚、承重斜撑、厚陶台、青釉唇、缝补、备货箱 | 2048 |
| env_ground_market_a | 单层连续地面；压实芯、松土边、矿物/苔带；路芯标称 2.9 m | 2048 |
| fol_tree_stranger_a | 保留树冠主轮廓、焊接法线分裂、分枝与根撑接地 | 1024 |
| fol_ground_tufts_a | 路缘成簇半埋碎石与折叶 | 1024 |
| env_plaza_market_a | 替换方格广场为低矮磨损门槛片 | 1024 |
| prp_market_burger_v01 | 托盘、面包、夹馅、叶片、芝士、高模芝麻 | 512 |
| prp_market_wrap_v01 | 托盘、卷饼、纸带、切口馅料 | 512 |
| prp_market_drink_v01 | 托盘、空心陶杯、饮品液面、把手、细芦管 | 512 |

商品对应 `food_counter.json` 中的 burger / burrito / coffee、water 等现有库存，
只作营业陈列，不添加可拾取目标或交易种类。

柜台顶高 1.10 m，商品原点就在盘底；台面向顾客侧移 0.35 m，给未改变的 Tavi
锚点 `(-1.8, 1.0, -2.75)` 留出身体空间。中部保留至少 0.82 m 的交付空区。
原社交中点集合会穿过柜台，运行时仅将 Tavi/Mira 这一组集合点约束到服务台两侧。
入口主树位于 `(4.5, 0, 6.0)`；碰撞仅包树干，树冠与根撑的风动幅度在底部归零。

## 可复现制作

Blender 5.2.0 LTS，Z-up，米制。固定旧源来自上一级 `export/`，绝不读取已替换的运行 GLB 作建模底稿。

```sh
/Applications/Blender.app/Contents/MacOS/Blender --background --python build_market_finish.py -- stall
/Applications/Blender.app/Contents/MacOS/Blender --background --python build_market_finish.py -- food
/Applications/Blender.app/Contents/MacOS/Blender --background --python build_market_finish.py -- tree
/Applications/Blender.app/Contents/MacOS/Blender --background --python build_market_finish.py -- ground
/Applications/Blender.app/Contents/MacOS/Blender --background --python build_market_finish.py -- edges
/Applications/Blender.app/Contents/MacOS/Blender --background --python pack_source_maps.py
```

以上命令用于再现制作方法。**登记锁后不能在本目录重做**；继续精修先复制为新的版本目录。
`deploy.py` 只发布列出的 8 个 GLB，并使可再生的环境导入缓存失效。Godot 重新导入保留 `.import` UID。

每份 `.blend` 内都有独立 `HIGH_BAKE_SOURCES` 集合和低模，图像已打包。高模以 SIMPLE 2 级
细分采样材质微表面，汉堡另有高模专属芝麻。Cycles selected-to-active 投射，法线烘焙与导出
使用同一低模三角化；设施保留手工命名 LOD0/1/2，静态地面及小商品只有 LOD0。

Base Color 只烘 DIFFUSE COLOR（无直接/间接光）；AO 独立烘焙，不乘进颜色。
Normal 为 OpenGL +Y，线性 ORM：R=AO、G=粗糙度、B=金属度；金属度用独立 emission 数据通道
投射后打包，不按颜色猜测。粗糙度按陶、干壳、旧合金、纤维分配，并有低幅表面变化。
缺贴图时引擎使用白颜色、平法线与 `(1,1,0)` ORM，保存 glTF 颜色和粗糙/金属因子。

## 验收证据

实机截图、原始帧时、行走轨迹和自动化回归位于：
`docs/reviews/market_finish_2026-09-05/`。Compatibility 的 GPU 时间查询在此 Apple M5 上返回 0，
不将其当作“GPU 0 ms”；验收采用实际帧间隔、渲染 CPU 时间与真实 draw-call 计数。
当前轮次不包含 Git 提交或推送。

2026-09-06 源文件复核：五张烘焙层均使用持久数据块并打包，避免独立 AO/粗糙度在重开
Blender 后因无材质引用而丢失；贴图外部路径改为相对路径。只调整源文件归档，GLB 未改变。
