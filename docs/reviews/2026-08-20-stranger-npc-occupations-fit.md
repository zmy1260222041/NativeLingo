# R-24 · NPC 职业与职场成对符合性评审(2026-08-20)

> 需求来源:用户指示「理想状态应有可以点餐的柜台 + 可以点单的店员;主线改过之后把每个角色的职业/设定固化下来」。
> 落库为 **FR-43**。覆盖角色卡、出生点、市场摊位配对。
> 判据在实现前写死;实现后回填 §6。

## 1. 范围

- **改**:五名 NPC 的职业、职场、主线职责、出生锚点;塔维站到 `env_market_stall_a`;社会闲聊不得把店员说成顾客。
- **不改**:FR-42 需求驱动主线、FR-28/FR-41 发物资、Tavi v06 锁定形体、不新建便利店/零件柜建筑。

## 2. 锁定的职业表

| 角色 | 职业 | 职场 | 主线 | 卖什么 |
|---|---|---|---|---|
| 塔维 | 食物柜台店员 | `env_market_stall_a` 服务口内侧 | 饿了来此点餐 | 食物 |
| 奥里 | 便利店收银 | 便利店(资产 pending;暂驻蓄水器旁) | 渴了来此买水 | 水/饮料 |
| 米拉 | 市场引导 | 市场广场、摊位顾客侧旁侧 | 无;可选问候 | 无 |
| 维什 | 五金零件柜店员 | 零件柜(资产 pending) | 无 | 零件(可选) |
| 罗文 | 住户邻居 | 广场住户点 | 无 | 无 |

Tavi v06 美术 DNA 仍是「种壳 + 弯月维修夹」。本轮**不改锁定四视**;玩法职业以食物柜台店员为准。夹具是角色剪影,不是她的工作内容。

## 3. 门控判据

- **G1 职业唯一**。五份角色卡都有 `occupation` / `workplace` / `mainline` / `sells`;没有两个人 `sells` 含同一主线物资 `food` 或 `water`。
- **G2 柜台+店员**。塔维锚点与 `env_market_stall_a` 原点水平距离 < 2.0 m。
- **G3 米拉不抢岗**。米拉 `sells` 为空;其锚点不在摊位内侧(相对摊位原点 z 大于塔维)。
- **G4 奥里 pending 店面**。职业是便利店收银;`workplace.asset` 标明 pending,不得用图元盒子冒充店面。
- **G5 出生点读卡**。`Main._add_npc` 使用角色卡 `workplace.anchor`;测试断言与卡上坐标一致。
- **G6 回归**。`test_npc_dialogue_assets`、`test_main_env_integration`、`test_dialogue`、社会对话套件全绿。

## 4. 非目标

- 不绘制店招 logo(Art Bible 仍禁止地球店招与源资产 logo)。
- 不本轮建模便利店或零件柜。
- 不重做 Tavi v06 形体。

## 5. 实现后回填

| 门 | 结果 | 证据 |
|---|---|---|
| G1 | ✅ PASS | 五份角色卡 occupation/workplace/mainline/sells 齐全;只有塔维卖食物、只有奥里卖水 |
| G2 | ✅ PASS | 塔维锚点 `(-1.8, 1.0, -2.75)`,与摊位原点水平距离 < 2 m |
| G3 | ✅ PASS | 米拉 sells 为空,z 在顾客侧 |
| G4 | ✅ PASS | 奥里 `workplace.status=workplace_pending`,`asset=pending_convenience_store` |
| G5 | ✅ PASS | `Main._npc_anchor` 读角色卡;MainEnv 断言出生点 |
| G6 | ✅ PASS | `test_dialogue` 职业项、`test_npc_dialogue_assets`、MainEnv、SocialDialogue 全绿 |

**结论(2026-08-20):六门代码侧放行。** 便利店/零件柜建筑与 Tavi 维修夹具形体仍是后续美术债,不挡本门。
