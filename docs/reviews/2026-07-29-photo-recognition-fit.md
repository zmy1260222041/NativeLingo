# R-13(2026-07-29)端侧识物 + 情景质量门 vs FR-13 / FR-14 / FR-15 / NFR-5

> 日期:2026-07-29 · 评审依据:`docs/PRD.md` FR-13(整件识别+定位)、FR-14(部件级微观)、FR-15(情景例句记忆强化)、NFR-5(端侧智能·无云无密钥)
> 实现(计划):`backend/core/vision.py`(YOLOv8n-onnx)、`backend/core/parts.py`(Qwen2.5-VL-3B)、`backend/core/scenario.py`(Qwen2.5-Instruct),端点 `/memorize/{analyze,parts,scenario}`
> 结论:**待实测回填。** 本评审为骨架 —— 数字门与判据先行,实测证据在 Phase E 由 `scripts/photo_gate.py` 跑出后填入 §3、§4,结论回填 §5 并回写 PRD §7。

---

## 1. 问题与事实

Memorizing 模块是 NativeLingo 首个**非语音**智能能力,且要求**全端侧**(NFR-5:无云、无 API key、无联网)。三个子能力各有不确定性:

- **宏观整件识别(FR-13):** 用户明确「识别准确率低则倾向 YOLO 等传统方法」。候选 = YOLOv8n-onnx(COCO 80 类,onnxruntime CPU,~12MB,自带 box 可做可点热点)。**风险:** COCO 覆盖面(强于家具/餐具,弱于特定食品/文具/电子子类)。
- **部件级微观(FR-14):** 无通用「部件检测」数据集,只能靠 VLM 对裁剪后的物品命名。候选 = Qwen2.5-VL-3B-Instruct(fp16,MPS)。**风险:** 小 VLM 部件命名的相关性/幻觉率。
- **情景例句(FR-15):** 用户要求 LLM「越小越好」。候选最小档 Qwen2.5-0.5B-Instruct,逐级升 1.5B/3B。**风险:** 极小模型的英语流畅度与情境贴切度。

NFR-5 的 RAM 约束:Memorizing 三模型 + Speaking 现有模型(whisper+wav2vec2+MMS+phoneme)同驻峰值须 ≤12GB,否则前端强制 tab 互斥驻留(`/memorize/release`)。

## 2. 方法

新增 `scripts/photo_gate.py`(风格镜像既有 `scripts/mdd_margin_sweep.py` / `ref_swap_experiment.py`),三个手标小集:

- **宏观集(~50 张):** 手机实拍,跨厨房/办公/街道/交通/客厅;手标 ground-truth box + 类名。
- **微观集(~30 个裁剪物件):** 跨 8–10 类(自行车/汽车/狗/吉他/笔记本/马克杯/植物…),人工参考部件表。
- **情景集(~40 对 `(label_en, label_zh)`):** 跨类别。

人工评分列(相关性/流畅度/贴切度)填入 CSV,沿用既有 gate 的「脚本出客观量 + 人工填主观量」做法。

## 3. 数字门(判据先行;实测回填)

| 轨 | 指标 | PASS 判据 | 实测 | 结果 |
|---|---|---|---|---|
| 宏观(YOLO) | precision(IoU≥0.5 ∧ 类正确) | **≥ 0.80** | _待填_ | _待填_ |
| 宏观 | recall | **≥ 0.60** | _待填_ | _待填_ |
| 宏观 | 单图延迟(CPU) | **≤ 200 ms** | _待填_ | _待填_ |
| 宏观 | 模型体积 | **≤ 50 MB** | _待填_(yolov8n ~12MB) | _待填_ |
| 微观(VLM) | 人工相关性(1/0.5/0 均值) | **≥ 0.75** | _待填_ | _待填_ |
| 微观 | 幻觉率(列出不可见部件) | **≤ 0.15** | _待填_ | _待填_ |
| 微观 | 单裁剪延迟(MPS,加载后) | **≤ 4 s** | _待填_ | _待填_ |
| 情景(LLM) | 流畅度(人工 1–5 均值) | **≥ 4.0** | _待填_ | _待填_ |
| 情景 | 情境贴切度(人工 1–5 均值) | **≥ 3.5** | _待填_ | _待填_ |
| 情景 | 中英匹配(人工二元) | **≥ 0.95** | _待填_ | _待填_ |
| 情景 | 单次延迟(MPS) | **≤ 3 s** | _待填_ | _待填_ |
| RAM | 同驻峰值 RSS | **≤ 12 GB** | _待填_ | _待填_ |

## 4. R-13 要决定的两件事

1. **宏观:YOLO vs 整图 VLM caption。** 若 YOLO recall < 0.60,则探测「整图 VLM caption 作文字标签」路径(降级:无 box 热点、仅标签列表);若该探测 recall 更高则切换,否则保留 YOLO 并接受覆盖面缺口。
2. **小 LLM 选型。** 先跑 0.5B;流畅度 < 4.0 升 1.5B;仍不达标升 3B。锁定后回写 `freeze.spec`/`memorize_warmup`/PRD §7。

## 5. 结论(待 Phase E 回填)

_待实测后填写:逐轨「符合/不符合 FR-x」,降级动作,以及上述两个决定的最终选择。_

## 6. 影响 / 行动项

- 实测前:完成 Phase C 后端三模型 + `scripts/photo_gate.py`,准备三手标集。
- 实测后:回填本文件 §3/§4/§5、PRD §7 R-13 条目;据结论锁定模型 id 并更新 `freeze.spec`/`memorize_warmup`。
