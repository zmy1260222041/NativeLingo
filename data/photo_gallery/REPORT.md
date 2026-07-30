# 日常场景图集识别报告

测试日期：2026-07-30
样本：30 张室内照片 + 30 张室外照片

## 结论

宏观整件识别已从 YOLOv8n 直接切换为 YOLOE-26S-PF，不使用 Florence 做整图后台补充。
最终 ONNX 在 Top-K 前仅放行 177 个实体类别，proposal confidence 为 0.10；
运行时再用日常实体词表、逐标签阈值、class-agnostic IoU 0.72 和包含式近义词
去重控制误报。

## 最终结果

| 指标 | YOLOE-26S-PF 最终配置 |
|---|---:|
| ONNX 大小 | 45,190,231 bytes |
| 图片 | 60（室内 30 + 室外 30） |
| 中位延迟 | 54.6 ms |
| P95 延迟 | 242.2 ms |
| 最终检测框 | 237 |
| 唯一标签 | 79 |
| 零结果图片 | 6 |

逐图可视化检查见 `review-overlays/`。扩图前配置在 60 图上得到 208 个框、
62 个唯一标签和 8 张空结果；扩词后得到 237 个框、79 个唯一标签和 6 张空结果，
中位延迟没有回退。

本轮增加 22 个运行时词项：

- 家居：`dish washer`、`toilet bowl`、`towel`、`nightstand`、
  `bedside lamp`、`lamp shade`、`tissue`、`shower curtain`、
  `kitchen counter`、`computer screen`。
- 户外：`crosswalk`、`fence`、`hydrant`、`mailbox`、`seesaw`、`slide`。
- 学习与工具：`pen`、`pencil`、`chisel`、`drill`、`saw`、`workbench`。

其中 19 个词在本轮图片中实际产生结果，共新增 29 个框。六页逐图复核中，
这些新增框均落在相应实物上；`bedside lamp`、`lamp shade` 和 `pencil`
在最终词表中可用，但本轮没有独立越过阈值与去重。阈值不是统一下调，而是按词设置：
例如洗碗机 0.65、工作台 0.60、消防栓 0.50、人行横道 0.24、栅栏 0.18。

剩余 6 张空结果集中在远景超市、游乐设施局部、市场摊位、俯拍停车场和石制野餐桌。
审查候选输出后没有继续降阈值：`parking lot` 在目标停车场虽有 0.679，但在多张普通
道路照片上也产生 0.1–0.34 的整图误框；`market stall`、`picnic table` 和
`supermarket` 在目标图中没有达到 ONNX proposal 0.10。仅降运行时阈值无法恢复
后者，强行加入前者则会扩大误报。

复核也保留两个已知错误作为后续改进样例：道路隔离栏被旧词 `washing machine`
误识别，以及红色邮筒被旧 COCO 词 `parking meter` 误识别。它们不是本轮新增词造成，
也无法通过一个不伤害真实洗衣机/停车计时器的全局分数阈值可靠解决。

## 限制

这是无人工框标注的探索性测试，逐图检查只能用于词表筛选和阈值调节，不能替代
precision/recall。正式 R-13 仍需手机实拍手标集计算 precision ≥0.80、
recall ≥0.60。

YOLOE 能力与导出支持见
[Ultralytics YOLOE 文档](https://docs.ultralytics.com/models/yoloe)。
闭源商业分发前还需评估
[Ultralytics 许可要求](https://www.ultralytics.com/license)。
