# R-30 — 可支配生存物品实施符合性

日期：2026-09-06。需求：FR-44（用户授权继续检查和实施）。引擎：Godot 4.6.3-stable，macOS / OpenGL Compatibility。

结论：**核心可玩链路通过本轮自动化与渲染检查；不是完整 GDD 最终表现验收。**

## 已落地

- `ItemCatalog` 将全部角色卡具体库存别名映射为 19 个稳定定义（含旧档迁移食物）；不同食物、饮品和日用品独立效果。
- `ItemState` 持有逐份实例、来源、剩余次数、位置、供应与交易账本；一次成交只在柜台创建物件，不直接加需求或词汇。
- 柜台逐份吃喝/打包与整批打包，4+1 分类容量，水壶两次使用，满需求拒绝、部分浪费确认。
- 住所床铺、电力位、维修位先放置再启用；毯子可停用/收回，零件安装，电池在住所使用；领取箱可存放及取回。
- 当前建筑没有可进入室内，物品放在住所外侧可见生活区，睡眠入口独立且可交互。不是隔墙看不见的“已放置”。
- SAVE_VERSION 5，完整 JSON 账本；旧资源超量进住所领取箱，需求不重复恢复；校验异常记录后才替换状态，保存先写临时文件。
- 按住 Tab / RB 查看随身物品，支持切换模式及重映射。E / X 主动作，R / 十字键右次动作，T / 十字键左整批打包。
  左肩键 LB 保留录音。昏倒、暂停、日切与服务会话关闭物品界面；领域入口重新验证安全与距离。

所有权决策：[ADR-0009](../architecture/adr-0009-item-lifecycle.md)。[GDD](../../design/gdd/item-usage.md)、
[UX](../../design/ux/item-usage.md)、[资产规格](../../design/art/item-usage-assets.md)同步修订。

## 检查中发现并修复

| 问题 | 修复与证据 |
|---|---|
| 服务点按 NPC 桶发资源、成交即加需求 | 具名 alias → 具体定义 → 柜台实例；只有消费命令提交效果 |
| 文档把“物品不发词汇奖励”写成“服务交流也不能 used” | 明确原词汇观察/练习/后续真实交流异步推进；物品事件无词汇依赖 |
| 旧测试直接写计数或用原始 voice 表达绕过具名成交 | 更新为真实服务成交与实例操作；仍保留具名承诺、同轮自然音频结束门禁 |
| `_actions` 返回动态数组导致运行期类型错误 | 修正返回类型，场景真实按钮验证吃一份/带一份 |
| 新手引导没有显式取物步骤 | 增加 use_item，领取或食用后才进入睡眠教学 |
| 多次容器使用可能拆堆导致容量溢出 | 水壶逐壶占位；部分饮用前后占位不增加 |
| 柜台初次展开，自动换行引起最小高度膨胀、动作被裁切 | 随视口重新约束布局；对有物品的柜台及 150% 列表做几何断言和截图 |
| 原手柄数值不是肩键，且不能占用已有录音肩键 | 对照运行时 JoyButton 常量，用真实 RB/X/D-pad 事件测试，而非仅模拟 InputEventAction |
| 住所放置点埋入墙体或与岩石相交 | 渲染近景迭代移位；床铺/箱子/电力位可见，入口仍能触发睡眠 |
| 待领柜台可能抢走进行中的同 NPC 会话目标 | 活动会话只选择对应 NPC 节点，不选择同 ID 的柜台投影 |

## 测试结果

完整结果摘要见 [regression.md](item_usage_2026-09-06/regression.md)。没有把仅退出码 0 当作成功：同时检查 PASS 和脚本错误输出。

| 验证 | 结果 |
|---|---|
| `test_item_usage.gd` | 180 项 / 0 失败 |
| `test_item_usage_runtime.gd`，真实渲染器 | 26 项 / 0 失败 |
| 游戏状态、新手引导、存档迁移、语音奖励、NPC 对话门禁 | 5 套件通过 |
| Vocabulary、WordAcquisition、WordPractice、GuidedWordPractice | 4 套件通过，原异步词汇玩法未删除 |
| WebBetaNoVoice、DesktopBetaNoVoice、HUD、VoiceTargetCancel | 4 套件通过 |
| 编辑器导入 / `git diff --check` | 通过 |

三夜模拟分别覆盖 fallback / sparse / generous，每 10 秒调用原生需求衰减，按需取得并明确消费，直到真实睡眠时间；
不重置需求、不跳过时钟，不修加热器、不帮助 Rowan，三条路径均三夜完成且零昏倒。它证明数值与供给可行，不代表独立玩家寻路或往返体验已经验证。

场景测试从 Main 实例化，禁用持久化、使用不存在的独立测试存档路径、关闭在线服务和社会音频；
在进程内恢复出厂物品输入映射，测试切换模式不写玩家设置。包含真实最近目标 + interact、手柄按钮、远程伪造住所上下文拒绝、
已放置但未生效、激活后可见、昏倒关闭、装满列表缩放、暂停以及睡眠入口。

渲染证据：

- [柜台实物近景](item_usage_2026-09-06/counter-objects.png)：客户侧托盘的两份实例可见；后排原装饰餐品不属于玩家库存。
- [柜台分份界面](item_usage_2026-09-06/counter.png)。
- [住所毯子与床铺](item_usage_2026-09-06/home-object.png)、[住所使用界面](item_usage_2026-09-06/home.png)。
- [1152×648 / 150% 有物品列表](item_usage_2026-09-06/inventory-150.png)。

复现：

```sh
/Applications/Godot-4.6.app/Contents/MacOS/Godot --headless --path game --script res://tests/test_item_usage.gd
/Applications/Godot-4.6.app/Contents/MacOS/Godot --headless --path game --script res://tests/test_item_usage_runtime.gd
ITEM_USAGE_EVIDENCE_DIR=/Users/a86138/Developer/NativeLingo/docs/reviews/item_usage_2026-09-06 /Applications/Godot-4.6.app/Contents/MacOS/Godot --path game --script res://tests/test_item_usage_runtime.gd
```

## 明确未完成的验收

GDD 33 条验收标准没有被整体标成全绿。当前仅对上述具体断言和截图作通过判断：

- 逐物品独立图标、准确手持/吃喝/包装动画、材质拟音、兼容位置轮廓、屏幕阅读器走查尚未完成；日用品/床铺为程序占位，食物复用三种模型。
- 主线程同步事务不暴露跨帧活动预留；异步网络预留的超时/断线验收不适用于本轮实现，扩展时仍需实现，不冒充已测。
- 没有重跑在线 Gemini/TTS 端到端请求；本轮成交门禁证据来自现有离线可控回复/音频测试。
- 未进行物理手柄人工游玩、导出构建、性能预算或独立三夜体验验收。后续目标应是表现补完和人工可玩性，而不是改写词汇或新增生存系统。

没有提交或推送代码；未改动任务范围外的既有美术、云服务和角色工作。
