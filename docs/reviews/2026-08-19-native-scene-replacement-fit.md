# R-21 · Source-first Native 情景替换(2026-08-19)

> 需求来源:用户要求「从生活对话视频中找到真实场景对话，固化成 Native 的场景，替换不常见的原来的场景」。
> 对应 PRD **FR-40**。本评审先放行研究候选层，不把未经独立核验的视频直接写入 Godot 运行时。

## 1. 决策

旧流程是「固定五个设计情景 → 为每个情景硬搜字幕」。新流程是：

```text
真实视频中的相邻请求/回应
  → 排除教学、旁白、游戏、歌曲和评测
  → 按重复互动归纳 scene family
  → 人工核对场景、双方说话人、美国英语和版权
  → 映射到 Godot 场景 ID并重写 project-authored patterns
```

原五个转换情景继续保留稳定 ID 作为兼容性资产。经过本轮 source-first
筛选，`food_ask_bread` 暂时映射到 `counter_order`，
`belonging_small_talk_waiting_line` 暂时映射到 `waiting_line_small_talk`；
两者仍标记为 `provisional_source_first_pending`，不会被描述为已完成
Native/版权核验。水、保暖和进屋三个 ID 没有用低质量结果硬填。该阶段不会改变
三日生存主线或资源奖励。

## 2. 当前证据

本地 Filmot Chrome 第二轮与 YouTube 字幕补搜显示：

| 互动族 | 观察结果 | 当前判断 |
|---|---:|---|
| `counter_order` | 7 个独立视频保留为研究候选 | 已暂时映射 food pilot，待回应者/版权审核 |
| `hotel_extra_item` | 真实前台请求/回应片段存在，但来源含挑战型 vlog | 研究候选，需核回应者母语与脚本性 |
| `waiting_line_small_talk` | 2 个独立视频保留为研究候选 | 已暂时映射 waiting-line pilot，需核采访对象而非只核记者 |
| `request_drink` | 精确 `can I get a water` 结果主要是游戏、整蛊、直播或旁白 | 暂不替换，改搜更宽的服务互动 |
| `ask_for_directions` | 旧水情景的部分表达可迁移，但尚无合格 source-first 证据 | 暂不替换 |
| `ask_for_help` | 当前报告没有足够的可核双人片段 | 暂不替换 |

可复核的研究链接示例：

- [Mo's Tasting · NYC burger](https://www.youtube.com/watch?v=-xRARWomIII&t=46s)
- [Alexandra Lourdes · donut counter](https://www.youtube.com/watch?v=FNKWnGUNYPU&t=35s)
- [POVintheCity · NYC pizza](https://www.youtube.com/watch?v=Zvdhic-3NmI&t=15s)
- [KSHB 41 · first person in line](https://www.youtube.com/watch?v=8ewi1TByt90)
- [CTV News · person waiting in line](https://www.youtube.com/watch?v=4dK6e1yEzAM)

这些链接只能证明「值得人工检查」，不能证明回应者已经通过
`native_speaker_verified` 或版权审核。

## 3. 实现范围

- `native_scene_queries.json` 定义不依赖旧五个 ID 的互动族。
- `native_scene_discovery.py` 从本地 Filmot/YouTube 报告提取研究候选。
- 每条证据保留视频 ID、URL、时间戳、字幕摘录、来源报告和人工门状态。
- 可选的 `native_speaker_screen.json` 只补充标题、频道和主办方筛选信息；它不能
  代替回应者的母语核验。
- `review-template` 生成逐条人工审核表，要求重复互动至少来自两个独立视频，且
  必须显式填写替换目标；审核表不会自动修改候选或 Godot 资源。
- `native_speaker_verified` 固定为 `false`，`rights` 固定为 `research_pending`。
- 研究候选不会自动写入 `game/data/dialogue`；本轮两个映射由项目编辑手工落到
  稳定 ID 的项目自有语境和回应模式，且 provenance 明确保留研究状态。

## 4. 放行标准

只有同时满足以下条件，候选互动族才可以替换 pilot：

1. 至少两个独立视频中出现同一类真实互动。
2. 视频是现实事件，不是语言课程、角色扮演、游戏、歌曲、评测或旁白。
3. 请求者和回应者是可区分的两个人，字幕窗口相邻。
4. 回应者有独立的美国英语母语证据；记者是母语者不等于受访者已核实。
5. 来源版权允许使用，或仍明确标记为 research-only，不进入发布语料。
6. 先由用户确认情景名称、目标词槽和游戏资源映射，再改写 40 条项目自有回应模式；
   本轮仅对 `counter_order` 和 `waiting_line_small_talk` 执行了暂时映射。

## 5. 验证

研究候选提取器由 `test_native_scene_discovery.py` 覆盖：场景族推断、教学片过滤、旁白排除、Native/版权门保持关闭。该评审不宣称任何 YouTube 候选已达到运行时发布资格。
