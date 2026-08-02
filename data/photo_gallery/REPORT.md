# 日常场景图集识别报告

测试日期：2026-08-02
样本：30 张室内照片 + 30 张室外照片

## 当前配置

宏观整件识别使用 YOLOE-26S-PF detection-only ONNX，不使用 Florence 做整图后台补充。
ONNX 在 Top-K 前放行 546 个实体类别，proposal confidence 保持 0.10；运行时继续使用
逐标签阈值、class-agnostic IoU 0.72、同名/嵌套别名包含度 0.82 和最多 40 框。

所有生产请求、自动化测试、离线基准和发布验收统一复用
`desktop/backend/core/memorize_image.py::canonicalize_upload`（契约
`memorize-image-v1`）：原始文件字节在后端完成 EXIF 纠正、LANCZOS 长边 1920px 缩放，
再固定编码为 JPEG quality 90、4:2:0 并重新解码为模型输入。前端不再预处理常规
JPEG/PNG/WebP。详细约束见 `docs/DEVELOPMENT.md`。

短边场景只执行一次全图 640 pass。图片长边达到 1280px 时，额外执行全局精细切片：
切片边长为长边的 `5/12`，相邻切片 50% 重叠，每块以 1280 输入推理。切片内部边缘
`max(2px, 边长×0.5%)` 内的疑似截断框被丢弃，原图边缘不受此限制；其余完整候选统一
映射回原图后去重。

## 60 图结果

| 指标 | 当前结果 |
|---|---:|
| ONNX 大小 | 45,190,233 bytes |
| 图片 | 60（室内 30 + 室外 30） |
| 小图（全图 pass） | 22 |
| 小图中位 / P95 / 最大延迟 | 67.7 / 93.7 / 121.6 ms |
| 大图（全局精细切片） | 38 |
| 大图中位 / P95 / 最大延迟 | 3754.8 / 4015.7 / 4145.3 ms |
| 最终检测框 | 513 |
| 唯一标签 | 139 |
| 零结果图片 | 5 |

空闲机器基准满足小图 P95 ≤200ms、大图 P95 ≤8s 且单图最大值 <12s。本轮基准直接
读取每张原图字节并调用生产 canonicalizer；相较此前由脚本近似预处理得到的 534 框，
统一输入后为 513 框、139 个标签，零结果仍为 5 张，且没有原先非空的图片退化为空。
最终包含度去重继续消除由相邻切片定位漂移产生的重复框。逐图可视化检查见
`review-overlays/`，预览按 canonical `size` 映射到经 EXIF 纠正的原图。

一次高 CPU 争用下的完整运行曾得到大图 P95 14985.0ms、最大值 15376.6ms，发布因此
按闸门暂停。关闭高负载程序后的本次发布重跑恢复至上表结果，检测输出保持完全一致，
三个延迟门槛均通过。

## 安装包验收

后端重新冻结并构建为 NativeLingo 0.5.0 arm64 DMG。挂载最终 DMG 后直接启动镜像内
后端，将下载目录中的原始 `IMG_0753.jpg`（未经测试脚本预处理）作为 multipart 文件
上传。请求在 5.013s 内返回 HTTP 200，响应确认 `memorize-image-v1` 和
`image_size=[1440,1920]`。`squid` 分数为 0.519，框为
`[284.2, 908.4, 274.1, 112.2]`；没有 `sausage`，`tea pot`、`herb` 和 `plate`
同时保留。App 深度签名校验与 DMG CRC 校验均通过。

## 限制

这是无人工框标注的探索性测试，逐图检查只能用于词表筛选、重复框检查和延迟回归，
不能替代 precision/recall。正式 R-13 仍需手机实拍手标集计算 precision ≥0.80、
recall ≥0.60。切片会放大小目标，也会放大已有开放词汇误报；本轮遵照验收约束没有
修改任何逐标签阈值或重新导出 ONNX。

YOLOE 能力与导出支持见
[Ultralytics YOLOE 文档](https://docs.ultralytics.com/models/yoloe)。
闭源商业分发前还需评估
[Ultralytics 许可要求](https://www.ultralytics.com/license)。
