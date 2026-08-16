# ADR-0001: 主角角色细化改用 Tripo 生成基础网格

## Status
Accepted

## Date
2026-08-12

## Engine Compatibility

| Field | Value |
|-------|-------|
| **Engine** | Godot 4.6.3-stable |
| **Domain** | Asset pipeline (character modeling) |
| **Knowledge Risk** | LOW — Tripo 是外部 API 服务，由官方文档（platform.tripo3d.ai/docs）验证；Godot 4.6.3 是 pinned 版本 |
| **References Consulted** | `docs/engine-reference/godot/VERSION.md`；Tripo 官方文档 `https://platform.tripo3d.ai/docs/generation`、`https://docs.tripo3d.ai/get-started/quick-start.html` |
| **Post-Cutoff APIs Used** | Tripo API（`POST /v2/openapi/task`，image_to_model / text_to_model）；Godot 侧无新 API |
| **Verification Required** | Tripo 生成的 GLB 需过角色 Gate A（四视叠加 / landmark / 剪影）；`art/source/characters/verify_asset_locks.py` 前后校验 |

## ADR Dependencies

| Field | Value |
|-------|-------|
| **Depends On** | None（首个 ADR） |
| **Enables** | 主角（Player Juvenile）后续细化；Mira/Rowan 等角色的后续细化 |
| **Blocks** | 主角 face-morphs 细化（test_character_asset morphs=0 缺口的补齐路径） |
| **Ordering Note** | 需先更新 `design/art/character-modeling-standard.md` §2 生产路线，再执行 Tripo 生成 |

## Context

### Problem Statement

主角 `chr_player_juvenile` 的 runtime 装配已完成（Gate D 15/16），但存在两个缺口：
1. `test_character_asset.gd` 断言 **LOD0 facial morphs ≥ 3**，实际 **morphs=0**（Tencent FBX 无 blend shapes）——主角缺眨眼/口型，垂直切片可用但非 art-bible 完整
2. 当前 `character-modeling-standard.md` §2 **唯一生产路线写死 Rodin**，但 Rodin base / Gate A 对主角 FAIL（资产锁记录），主角正需"版本化雕刻"细化

用户决定：**主角后续细化全面改用 Tripo 生成基础网格**（有 Tripo API key）。

### Constraints
- 保留已 source_locked 的 Rodin/Hunyuan 基线与资产锁不可变（`ASSET_LOCK_MANIFEST.json`）
- 四视图仍是形体权威（character-modeling-standard §1.1：只有批准的 source_locked 四视图参与生成）
- Godot 4.6.3 pinned；运行时 GLB 契约（LOD `lod0__/lod1__/lod2__`、材质槽 ≤3、-Z forward）不变
- Tripo 异步任务 API：提交→轮询→下载，模型 URL 5 分钟过期

### Requirements
- 主角（及后续角色）细化能用 Tripo 从四视图/单图生成可雕刻基础网格
- 生成的 GLB 需进入既有角色管线：Gate A → 雕刻/remesh → retopology → 绑定 → 动画 → LOD
- 资产锁纪律不变：生成凭据/API key 绝不入库；建模前后跑 `verify_asset_locks.py`

## Decision

主角角色细化**全面改用 Tripo** 生成基础网格，替代原 Rodin 路线作为**唯一生产路线**。

### 生成方式（Tripo 多视图 → 3D）

走 Tripo 的 DashScope 变体（复用现有 `DASHSCOPE_API_KEY`），多视图输入直接匹配现有四视图概念图：

```
POST https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/3d-generation
X-DashScope-Async: enable
Authorization: Bearer $DASHSCOPE_API_KEY
{
  "model": "Tripo/Tripo-H3.1" 或 "Tripo/Tripo-P1.0",
  "images": ["<front>", "<left>", "<back>", "<right>"]   // 恰好 4 张：前/左/后/右
}
```

或走 Tripo 原生 API（`POST https://api.tripo3d.ai/v2/openapi/task`）：
- `image_to_model`：单图（JPEG/PNG ≤20MB），参数 `face_limit`/`texture`/`pbr`/`texture_alignment`/`orientation`
- `text_to_model`：文本 prompt

产出 GLB（OBJ/FBX 可选）→ 进角色管线（Gate A 起）。

### 关键接口

- Tripo 原生：`POST /v2/openapi/task` + `GET /v2/openapi/task/{task_id}`（轮询至 `success`，`data.output` 取模型 URL）
- DashScope 变体：上述 `3d-generation` 端点 + `X-DashScope-Async: enable`（与既有多模态理解同平台）

### 资产锁影响

- `art/source/characters/ASSET_LOCK_MANIFEST.json` 中 Rodin 原始 GLB / Hunyuan 高模**保留为基线**（不可覆盖）
- 新增 Tripo 生成的 GLB 作为新的 source_locked 版本（`source_locked_vXX`）进入锁
- **生成凭据（Tripo/DashScope API key）绝不入库**（policy 现有规则）

## Alternatives Considered

### Alternative 1: 保留 Rodin 作为唯一生成器（现状）
- **Description**: 维持 `character-modeling-standard.md` §2 的 Rodin 唯一路线
- **Pros**: 已建立管线；资产锁基线匹配
- **Cons**: Rodin base / Gate A 对主角 FAIL（已记录）；缺 face morphs；无法利用用户已有的 Tripo key
- **Rejection Reason**: 主角细化正被卡在 Rodin 基线上；Tripo 是用户明确的更优生成器

### Alternative 2: Rodin 为主 + Tripo 补充
- **Description**: Rodin 负责常规角色，Tripo 仅用于主角细化
- **Pros**: 保留既有管线惯性
- **Cons**: 两条生成路线并存增加维护；角色来源不一致
- **Rejection Reason**: 用户明确选择全面迁移 Tripo

## Consequences

### Positive
- 主角细化（含 face-morphs 补齐）可用 Tripo 生成，绕开 Rodin Gate A FAIL
- Tripo 多视图输入直接匹配现有四视图概念图，无需重绘参考
- 复用既有 DashScope key，无额外平台

### Negative
- 需更新 `character-modeling-standard.md` §2（Rodin → Tripo）及资产锁记录
- Tripo 生成结果仍需 Gate A 雕刻/retopology（生成器不提供最终拓扑）

### Risks
- **Tripo 生成质量不稳定** → 用四视图输入降低方向歧义；Gate A 四视叠加验证
- **模型 URL 5 分钟过期** → 下载流程要即时；用 Python SDK 封装轮询+下载
- **与既有资产锁冲突** → 保留 Rodin/Hunyuan 基线不可变，Tripo 新版本入锁；建模前后 `verify_asset_locks.py`

## GDD Requirements Addressed

| GDD System | Requirement | How This ADR Addresses It |
|------------|-------------|--------------------------|
| `game-concept.md` §角色 | 主角需完整角色模型（含面部/动画） | Tripo 生成基础网格 → 后续雕刻/绑定可补 face morphs |
| `systems-index.md` 角色系统 | 角色资产走统一生产管线 | 统一到 Tripo 生成器，符合"统一美术" |

## Performance Implications
- **CPU**: 无（生成在云端，本地仅下载+导入）
- **Memory**: GLB 入内存量级与 Rodin 相当（LOD 由管线处理）
- **Load Time**: 下载+导入步骤异步，不影响运行时
- **Network**: 提交/轮询/下载走 HTTPS；模型 URL 短期有效需及时拉取

## Migration Plan
1. 更新 `design/art/character-modeling-standard.md` §2：`Rodin 生成可雕刻基础网格` → `Tripo 生成可雕刻基础网格`（§1/§3 相关引用同步）
2. `art/source/characters/ASSET_LOCK_MANIFEST.json`：新增 Tripo 生成的 source_locked 版本条目；保留 Rodin/Hunyuan 基线
3. 写 Tripo 生成脚本（封装提交/轮询/下载，DashScope 变体），跑主角细化
4. 生成结果走 Gate A → 后续管线

## Validation Criteria
- 主角细化用 Tripo 生成的 GLB 通过 Gate A（四视叠加 / landmark / 96px 剪影）
- `test_character_asset.gd` 的 face-morphs 断言（≥3）随细化补齐
- `art/source/characters/verify_asset_locks.py` 建模前后 PASS

## Related Decisions
- `design/art/character-modeling-standard.md`（本 ADR 迁移其 §2 路线）
- `art/source/characters/ASSET_LOCK_MANIFEST.json`（Tripo 新版本入锁）
- 主角 `chr_player_juvenile` source_locked_v04-v06（既有 Rodin/Hunyuan 基线）
