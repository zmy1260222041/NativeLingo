# ADR-0009 — 生存物品生命周期

日期：2026-09-06。状态：Accepted（依据用户“继续检查和实施”）。来源：FR-44 / item-usage GDD。

`ItemState` 是 GameState 持有的 RefCounted 纯数据域，拥有物品实例、交易账本、供应提交计数、住所位置/设施进度。
GameState 仍拥有需求、日夜、存档与关系，负责把物品命令与需求效果同步提交；世界投影和 UI 只查询与发送意图。
采用每份一个稳定实例，兼容实例在携带容量和 UI 上组成堆叠；来源交易永远保留，不为合堆丢失来源。
短事务在 Godot 主线程同步完成，中间不 await、不发信号；变更完成后才发 item_changed。
Runner 每次新服务会话分配持久递增交易 ID；同一 ID 重放返回原结果。现有语音具名门禁继续位于服务/Runner/领域入口。

具体物品通过定义表将角色卡 alias 映射到稳定 ID。语音高分不能把毯子复制两件，零件按住所尚缺数量封顶。
库存预留与提交在同一同步领域命令内完成，不跨帧保存活动预留。使用前验证上下文及版本，失败零变更。
所有数字、字符串、数组和字典以 SAVE_VERSION 5 保存。旧计数迁移为携带物；容量外物件进住处领取箱，保留总量和原需求。
`berries/scrap/water` 仅保留读取兼容投影，写入旧字段不作为生产使用入口。

世界实物缺模型时保持领域记录并用明确的占位模型；节点卸载与声音失败不撤销领域结果。
设施激活效果由状态推导，重载不重放。毯子影响下一次睡眠的温暖恢复；电池只在住所为休息提供一次额外精力；零件安装增加维修进度。

引擎依据：[Godot 4.6 RefCounted](https://docs.godotengine.org/en/4.6/classes/class_refcounted.html)、
[InputEvent](https://docs.godotengine.org/en/4.6/tutorials/inputs/inputevent.html)。Context7 在本会话无可调用工具，使用官方版本文档及本机 4.6.3 验证。
