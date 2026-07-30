# NativeLingo 日常场景测试图集

本地评估图集包含 60 张公开网络照片：

- `indoor/`：30 张室内日常场景
- `outdoor/`：30 张室外日常场景
- `manifest.json`：下载地址、来源页、许可和场景说明
- `baseline-current.json`：当前 60 图、177 类 YOLOE 配置的逐图结果
- `baseline-current-20.json`：扩图前 20 图结果
- `baseline-yoloe-26s-pf.json`：YOLOE-26S-PF 临时 POC 的原始结果
- `baseline-yoloe-filtered.json`：扩图前直接 YOLOE 路径的历史结果
- `contact-sheet-{indoor,outdoor}.jpg`：两个场景各 30 张的原图索引
- `review-overlays/`：六页、每页 10 张的最终检测框复核图
- `REPORT.md`：测试摘要和模型决策

这些图片只用于 NativeLingo 本地模型评估。转载或重新分发前，请逐项遵守
`manifest.json` 中记录的许可和署名要求。原 20 张中的 Pexels 图片适用
[Pexels License](https://www.pexels.com/license/)；新增 40 张来自 Wikimedia
Commons，具体 Creative Commons / 公有领域许可、作者和来源页逐项记录在清单中。

运行当前 YOLOE 宏观识别并生成复核图：

```bash
./.venv/bin/python scripts/photo_gallery_baseline.py \
  --gallery data/photo_gallery \
  --output data/photo_gallery/baseline-current.json

./.venv/bin/python scripts/photo_gallery_overlay.py \
  --gallery data/photo_gallery \
  --baseline data/photo_gallery/baseline-current.json \
  --output-dir data/photo_gallery/review-overlays
```

`scripts/expand_photo_gallery.py` 保存了新增 40 张 Commons 照片的确定性搜索、
许可筛选、下载校验和清单更新流程。重复运行前仍应检查 Commons 页面是否有许可更新。
