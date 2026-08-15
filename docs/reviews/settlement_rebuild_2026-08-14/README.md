# 主场景聚落重建审查记录（art-bible v1.4 对标）

*日期：2026-08-14 · 分支：codex/stranger-vertical-slice · 评审模式：solo*
*上游标准：`design/art/art-bible.md` v1.4（§3.6 材质家族 / §5 环境 / §8.8 验收）+
`art/reference/aaa_settlement_study/AAA_SETTLEMENT_STUDY.md`（五案例基准）*

## 结论

主场景按 v1.4 完成聚落重建，**四信号口径 A–G 七项全部 PASS**（qwen3.7-plus 视觉评审，
对照 AAA 聚落研究五维口径）。Gate E 回归 `MARKET_CORNER_ASSET_TEST_PASS`
（draw_calls=49 ≤60 预算）；主场景粗估 529 surface（含未剔除 LOD，实际 draw 低于此，
§8.1 实测留待代表帧跑分）。

| 项 | 基线 | 终版 |
|---|---|---|
| A 积木判定（盒+锥换色/门洞厚度/板缝可数） | FAIL | PASS |
| B 构造可读（陶基座→柱梁→壳板墙→出挑屋顶） | FAIL | PASS |
| C 接触接地（接地条/柱根阴影） | FAIL* | PASS |
| D 材质家族（浅陶/珊瑚壳板/深框架/浅合金 分档） | FAIL | PASS |
| E 地面三层（磨损带/粉尘/碎簇边+过渡带） | FAIL | PASS |
| F 使用痕迹（晾晒架/陶罐簇/堆货箱/柜台食物） | FAIL | PASS |
| G 市场密度（核心 4×4m 中型道具） | FAIL | PASS |

*基线 C 为大物体 PASS、小道具悬浮。前后对比图见本目录 before_/after_。

## 交付物

**新环境资产**（`art/source/environment/env_market_corner/`，headless Blender 5.2 建模，
`blender/model_env_settlement.py`，GLB 落 `game/assets/environment/`）：

- `env_hut_residential_a` — 矩形住宅：陶体基座+垫唇+接地条 / 四角柱+圈梁 /
  三层叠压壳板墙（板缝 0.05 + 逐板明度抖动 + 暗色背衬墙）/ 门框+门楣+31° 微开门扇+
  门槛石 / 窗框+内退暗面 / 双层出挑歇山顶+脊梁 / 合金补片+铆钉 / 陶通风塔。LOD0/1/2。
- `env_hut_residential_b` — 八边形变体住宅：八边陶基座+6 柱+三层收分陶环带（内芯
  防透视）+三段阶梯锥顶+合金补丁。LOD0/1/2。
- `env_ground_market_a` **v2 三层地表**：磨损路网（11 条路径，顶点色梯度 中心压实→
  边缘粉尘）+ 摊位前弯月磨损带 + 广场磨损环 + 淡出过渡带（杀刀切边）+ 排水篦。
- `fol_ground_tufts_a` — 第三层碎簇带：沿路网每 0.33m 双侧 + 外圈 + 广场环的青绿草锥
  与卵石（独立资产，保住地面 GLB 的"顶面 y≈0"Gate E 契约）。
- `prp_crate_stack_a`（板条箱×3+麻袋×2+压条/板缝）、`prp_drying_rack_a`（晾晒架+
  三色挂布+绳结+苔薄荷三角旗）、`prp_amphora_cluster_a`（陶罐簇×3+托盘）。各 LOD0/1。

**代码**：`main.gd` 聚落重建（`_add_residence`/`_build_usage_traces`，图元回退保留）；
摊位柜台食物陶碗；`animation_debug_bridge.gd` 新增 `game.debug_view/restore_view/
set_property/env_stats/capture_view/bring_to_front` RPC；`tools/rpc_env_review.gd`
批量评审客户端；`blender/render_settlement_review.py` Blender 合成评审渲染器（7 机位）。

## 过程关键发现（复用价值）

1. **Blender 5.2 glTF 导出器顶点色陷阱**：默认 `export_vertex_color='MATERIAL'` 会生成
   全白假 COLOR_0，把作者色挤到 Godot 不读的 COLOR_1。修复：
   `export_vertex_color="ACTIVE"`（本仓 v1 资产的"前脸潮青/骨白路径"在引擎里其实
   从未生效——stall 重导出为遗留跟进项）。
2. **Godot 窗口被完全遮挡时渲染管线停摆**（含 SubViewport UPDATE_ONCE、
   `frame_post_draw` 永不触发；仅主循环逻辑存活）。因此评审主通道改为
   **Blender 合成渲染**（`render_settlement_review.py`，EEVEE + 顶点色×材质色），
   与游戏窗口 z-order 完全解耦。游戏内截图链路保留（窗口可见时可用，
   `_capture_view` 落盘返回路径，绕开大 payload WebSocket 丢包）。
3. **文件名后缀**：`_try_load_env` 静默回退图元——新资产调用漏 `.glb` 后缀时无任何
   日志（本次排查消耗三轮截图）。建议后续给 `_instantiate_env` 加存在性断言。

## 已知缺口 / 跟进项

1. **资产锁未重锁**：`ASSET_LOCK_MANIFEST` 校验 41 处失配，含会话前漂移（整个
   `art/source/environment/` 目录尚未入 git）。7 个新资产未登记。需要一次
   重锁 + git 提交决策（用户定夺）。
2. **stall 前脸潮青顶点色**在引擎中缺失（见发现 1），需用 ACTIVE 选项重导出
   `env_market_stall_a`（涉 bake 管线，单独做）。
3. Gate E 测试清单仍为 v1 的 10 资产；新资产（huts/tufts/crate/rack/amphora）
   未纳入 gate 断言与 §8.2 预算行。
4. §8.8 九项中的跨日状态（D1/D3 同机位归档）、关 HUD 5 秒导航实测、灯光三态截图
   归档需在游戏窗口可前台时补做（截图链路已就绪）。
5. qwen 锦上添花建议（非阻塞）：柜台再放 1–2 件陈列；碎簇尺寸/成簇随机性再加强；
   cel 阴影之外的接触 AO 属风格内取舍，维持圣经 §3.1.B 哑光单影不动。

## 复现命令

```sh
# 建模/导出（含顶点色 ACTIVE 修复）
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python art/source/environment/env_market_corner/blender/model_env_settlement.py
# Blender 合成评审渲染（7 机位，无需游戏窗口）
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python art/source/environment/env_market_corner/blender/render_settlement_review.py -- --out /tmp/env_review/blender
# 游戏内批量截图（窗口可见时）
cd game && /Applications/Godot-4.6.app/Contents/MacOS/Godot --headless \
  -s res://tools/rpc_env_review.gd -- --views <views.json> --out <dir>
```
