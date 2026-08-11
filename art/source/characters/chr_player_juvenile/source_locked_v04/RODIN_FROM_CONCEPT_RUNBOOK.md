# Rodin 从概念四视图生成角色基础网格

> 唯一有效的主角建模入口。输入、Rodin 原始结果、可编辑 Blender 源文件和验证输出均保存在
> `source_locked_v04/`。不要从仓库其他角色网格反推或拼装主角。

## 1. 唯一源图

- `reference/figure_view_0.png`：正面，主角 v04 实际 Rodin 生成输入。
- `reference/figure_view_1.png`：左侧，用于生成后的形体校验。
- `reference/figure_view_2.png`：背面，用于生成后的形体校验。
- `reference/figure_view_3.png`：右侧，用于生成后的形体校验。
- `reference/figure_contact_sheet.png`：人工并排复核。

四张图必须共享地面线、头顶线、眼线、肩线、骨盆线和膝线。Rodin 只负责生成可雕刻的初始
表面；任何单图幻觉都服从四视图和 `design/art/art-bible.md`。

## 2. Rodin 提交与下载

主角 v04 使用 Blender Copilot 内置的 Hyper3D free-trial 入口生成，用户无需手工填写私有 API key。
启用操作会把插件自带的试用凭据放进当前 Blender 场景；凭据不得抄入仓库、`.blend`、报告或日志：

```python
import bpy
bpy.context.scene.copilot_use_hyper3d = True
bpy.ops.copilot.set_hyper3d_free_trial_key()
```

当前 MCP 的路径转图片适配层可能返回 `Unsupported or invalid image`。可靠路径是在 Blender 内部读取
锁定图片字节并调用同一个 Copilot executor。主角 v04 的既有基础网格来自正面输入；侧背图是 Gate A
校验合同：

```python
from pathlib import Path
import bpy

front = Path(
    "art/source/characters/chr_player_juvenile/source_locked_v04/reference/figure_view_0.png"
)
job = bpy.types.copilot_server.executor.cmd_create_rodin_job(
    images=[(".png", front.read_bytes())]
)
submission_uuid = job["uuid"]
subscription_key = job["jobs"]["subscription_key"]
```

使用 executor 轮询；完成后下载原始 GLB。任务 UUID 可以写进审计报告，试用 key 与
`subscription_key` 不得持久化：

```python
status = bpy.types.copilot_server.executor.cmd_poll_rodin_job_status(
    subscription_key=subscription_key
)
```

Mira/Rowan 的新运行提交了四张已注册图片到同一个 Sketch/Raw 任务；详见
`art/source/characters/npcs/RODIN_NPC_PIPELINE.md`。仓库不保留未经本项目实际生成验证的私钥 API
脚本或参数假设。

下载的原始文件固定保存为：

- `rodin_raw/base_basic_pbr.glb`
- `rodin_raw/preview.png`

## 3. 干净导入、修复和渲染

不要在长期运行、状态不明的交互场景里直接渲染。使用唯一的幂等脚本：

```bash
/Applications/Blender.app/Contents/MacOS/Blender \
  --background --factory-startup \
  --python art/source/characters/chr_player_juvenile/blender/import_render_rodin_v04.py
```

脚本会：

1. 从空场景导入原始 GLB。
2. 显式恢复对象、Collection 和 LayerCollection 可见性。
3. 以 `1e-6 m` 阈值焊接 Rodin 的同位置属性边界，重算法线。
4. 将模型归一化为 1.78 m、双脚落地、水平居中。
5. 渲染 Workbench clay 四视图和 EEVEE PBR 正面/三分之四视图。
6. 保存可编辑 `.blend`、导出 normalized GLB，并写入验证报告。

唯一有效输出：

- `rodin_source/chr_player_juvenile_rodin_v04.blend`
- `rodin_processed/chr_player_juvenile_rodin_v04_normalized.glb`
- `rodin_import_report.json`
- `rodin_raw/view_{ny,px,nx,py}.png`
- `rodin_raw/beauty_front_v3.png`
- `rodin_raw/beauty_3qtr_v3.png`
- `rodin_raw/views_contact.png`
- `validation/rodin_*`

## 4. 当前已验证状态

- Blender 源网格：11,668 顶点 / 23,332 三角面。
- 拓扑：1 个闭合连通体、0 非流形边、0 孤立点。
- 尺寸：1.78 m，脚底 `z=0`，模型中心归零。
- 材质：1 个 Rodin PBR 材质，三张内嵌 512² 贴图。
- 原始朝向：面向 Blender `-Y`；运行资产导出阶段才转换为 Godot `-Z`。
- `runtime_export_allowed=false`：当前只是可编辑的 Gate A 基础网格。

## 5. 进入生产阶段

后续按 `design/art/character-modeling-standard.md` 与 `RODIN_PRODUCTION_PIPELINE.md` 执行。优先删除 Rodin 误生成的尾巴，修正眼窝、头冠、
三指手、三趾脚和左右不对称；Gate A 未通过前禁止绑定、动画、LOD 或覆盖游戏运行资产。
