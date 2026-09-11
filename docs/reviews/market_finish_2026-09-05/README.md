# 入口至 Tavi 摊位：柔和风格化质感升级

2026-09-05 制作与固定机位实测；2026-09-06 行走复测、源文件复核和版本登记。
追溯 FR-43（职场可读性）、FR-42（需求与路线）、Art Bible v1.7 用户批准覆盖条款。

本轮环境样板通过下列限定验收并保存到工作区，**没有 Git 提交或推送**。
角色资产、NPC 职场锚点、交易规则、存档格式保持不变；不含 Ori 店面、其他 NPC 重建和大地图重构。

## 已完成

- 公共导入保留 glTF 颜色、粗糙度/金属度及贴图因子；缺图使用白色、平法线、非金属 ORM。
  ORM 保持 R=AO、G=粗糙度、B=金属度。陶器宽高光、旧合金反光、干壳与纤维哑光可区分。
- 环境使用连续柔和体积、暖主光/冷填充，树冠清除分裂法线；夜灯照到柜台与地面，
  加热器只在热源区域自发光。同步修订美术规范的环境硬阶梯/禁反光条款。
- 道路改成连续压实尘土、松散边缘和岩缘苔带；主路路芯标称 2.9 m。
  清除旧市场方格，保留磨损门槛，路缘植被和半埋碎石成簇。
- 主树移到 `(4.5, 0, 6)`，保留树冠轮廓、补根撑接地；摊位保留弯月篷并加厚至约 85 mm，
  增加承重连接、陶质柜沿、一处缝补和备货箱。
- 汉堡、卷饼、饮料与陶盘为真实烘焙模型，对应现有库存，无新增交易机制；柜台中部保留交付空区。
  Tavi 社交集合改为服务台两侧，修正旧的中点集合穿过柜台问题，不改变职场锚点。
- 手工 LOD 同时只显示一个等级，描边幂等生成并跟随等级；远处细描边关闭。
  旧静态建筑/道具按 LOD、材质、语义与顶点格式合批，保留原几何、UV 和三角形总数。

## 实机画面与行走

`before_*` 为修改前留存画面（1280×800），`after_*` 为同位置/朝向/FOV 的完成画面（1440×900），
二者均为 16:10；不得将不同分辨率视为逐像素比较。所有画面来自 Godot，不是 Blender 效果图。

| 机位 | position → target | FOV | 验证时段 |
|---|---|---:|---|
| 入口 arrival | `(0,2.8,13.4)` → `(0,1.2,0)` | 68 | 白昼/黄昏/夜间 |
| 柜台 counter | `(0,2.6,1.3)` → `(-1.8,1.5,-2.2)` | 60 | 白昼/黄昏/夜间 |
| 全景 overview | `(18,15,24)` → `(0,1,0)` | 65 | 白昼/夜间 |
| 水站 water | `(10,2.6,12.4)` → `(9.7,1,8)` | 65 | 白昼/夜间 |
| 加热器 heater | `(-1,2.7,9.5)` → `(-6.1,1.2,7.2)` | 65 | 白昼/夜间 |

入口白天树冠保留连续明暗；夜间柜台及返程道路可辨认。固定画面和移动视角中未见新增道具漂浮、
地面闪烁或 LOD 重影。商品不占用中间交付空间。水站与全景检查公共材质修改的区域外影响。

`walk_runtime.py` 在初始定位后通过真实移动输入、CharacterBody3D 碰撞和镜头转向完成
入口 → 柜台、左右转镜头、夜间返程。五段路线全部到达，98 个遥测样本；截图为 `walk_00` 至 `walk_07`。
制动后终点会越过目标，保留原始轨迹而非将角色瞬移回验收点。实测路线无新障碍，角色最终恢复可行走。
这不是任意路径的穷尽碰撞测试，也不是长时间压力测试。

## 1440×900 性能实测

Godot **4.6.3 Compatibility**，Apple M5，OpenGL 4.1 Metal；可见主窗口与根 viewport 都为 1440×900。
每组预热 90 帧、采集 360 帧，共 2160 帧；测量时临时关闭 VSync/帧率上限，并移除截图 SubViewport，
避免第二机位额外渲染。采用真实 `Time.get_ticks_usec()` 帧间隔和渲染计数，不使用 draw_estimate。

| 机位/时间 | 平均 FPS（未限帧） | 帧时 P95 / 最大 ms | 渲染 CPU P95 ms | 最大 draw calls |
|---|---:|---:|---:|---:|
| 入口 12:12 | 172.0 | 8.827 / 10.607 | 2.502 | 707 |
| 柜台 12:12 | 196.5 | 6.376 / 7.423 | 1.867 | 476 |
| 入口 19:04 | 205.8 | 7.619 / 9.427 | 2.253 | 712 |
| 柜台 19:04 | 158.6 | 7.683 / 10.153 | 2.197 | 531 |
| 入口 21:18 | 208.3 | 7.673 / 9.809 | 2.191 | 734 |
| 柜台 21:18 | 169.5 | 7.179 / 7.606 | 2.074 | 486 |

本机六组固定机位均满足 60 FPS 的 16.67 ms 帧预算及 850 draw-call 目标；
行走遥测 draw calls 为 156–734。硬件结论不外推到其他设备或尚未测试的地图路线。
Compatibility 的 GPU 查询返回全零，**GPU 独立耗时不可用**，不是“GPU 耗时 0 ms”。
渲染 CPU 值包含 viewport CPU 测量和帧设置时间；它不等于完整游戏逻辑 CPU 时间。

原始数组及尺寸/时钟记录：`frame_measurements.json`；静态合批前实测：`frame_measurements_pre_batch.json`。
合批前入口为 1094–1121 draw calls，合批后 707–734；这里的“合批前”不是原始美术基线。

## 自动化与源文件校验

2026-09-06 重跑六组回归：全部 exit 0，无 SCRIPT ERROR 或引擎 ERROR。

| 回归 | 结果 | 证据 |
|---|---|---|
| 材质默认值/贴图通道/单级 LOD/描边幂等/合批保面数 | PASS | material_lod.log |
| 环境运行资产 | PASS | environment_assets.log |
| 主场景集成 | PASS | main_integration.log |
| NPC 职场与对话资产 | PASS | npc_workplace.log |
| Tavi 服务台两侧社交站位 | PASS | social_counter_clearance.log |
| 无语音三日主线 | PASS | desktop_no_voice.log |

`regression_results.json` 保存实际命令、退出码及错误检查。运行方式（仓库根目录）：

```sh
python3 docs/reviews/market_finish_2026-09-05/run_qa.py
/Applications/Blender.app/Contents/MacOS/Blender --background --python-exit-code 1 --python docs/reviews/market_finish_2026-09-05/validate_sources.py
python3 art/source/environment/verify_env_asset_locks.py
```

源校验重开全部 8 个 `.blend`：高模集合保留且隐藏、只有 LOD0 可见，5 张烘焙图均打包且色彩空间/尺寸正确，
每个导出只有 1 个材质槽及 3 张运行贴图，运行 GLB 与源 GLB 哈希一致。详见 `source_validation.json`。
颜色只烘材质色，不含照明或 AO；法线和独立 AO 由高模投射，粗糙度按材料家族烘焙。
接地尺寸记录是制作约束，结合实机目视和行走验证，不冒充穷尽几何交叉检测。

原 110 个保护条目保持原哈希；追加 8 个资产各 8 个文件以及 5 个公共制作文件，合计 179 个保护条目。
新源保存在 `art/source/environment/env_market_corner/quality_pass_v01/`，后续修改须创建新版本，旧源不覆盖。

## 已知边界

Ori 店面和其他未成品 NPC 仍为旧资产；本轮不宣称全地图美术完成。
实机 `runtime_final.log` 还记录了 `npc_voice_adapter.gd:358` 读取语音 WAV 的长度/seek 错误；
这条音频链路本轮未改动、未纳入环境修复范围。无语音主线回归通过不代表带语音路径已通过，
因此本报告不声称整个游戏日志零错误。

技术依据：Godot 4.6 [spatial shader](https://docs.godotengine.org/en/4.6/tutorials/shaders/shader_reference/spatial_shader.html)、
[Performance](https://docs.godotengine.org/en/4.6/classes/class_performance.html) 与
[RenderingServer](https://docs.godotengine.org/en/4.6/classes/class_renderingserver.html)。Context7 MCP 当前不可用，使用版本化官方文档。
