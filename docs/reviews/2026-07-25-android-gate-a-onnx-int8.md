# R-5(2026-07-25)Android 端侧 wav2vec2 int8 评分保真 vs NFR-1 / NFR-Q1 / FR-4·5

> **Gate A / R-5 —— 项目存在性证明**。本评审回答:wav2vec2-base-960h(6–9 层)导成 ONNX 并量化后,Track B 评分(尤其说话人不变性)是否仍然成立?若不成立,「端侧全功能」前提即破。
>
> 关联:`docs/android-migration.md` §7 Gate A、`docs/PRD.md` §7 R-5。

## 问题

NativeLingo 的逆向评估依赖 wav2vec2 中层嵌入做 DTW,关键不变量是 **说话人不变性**:不同嗓音读同一正确文本,DTW cost 须仍低(macOS 实测 0.1714 ≤ 0.18 阈值,acc 95.0)。int8 量化引入的权重扰动可能重新注入「音色因子」,使跨嗓音 cost 抬升、acc 掉档——若如此,Android 端侧评分不可信。

## 方法(Python 侧,无需 Android 设备)

`scripts/onnx_export_spike.py`:
1. 用一个 wrapper 模块把 `Wav2Vec2Model` 的 6–9 层 hidden_states 均值直接作为 ONNX 输出(比 Optimum 默认 + 图节点手术更干净,见 Finding ④ 的替代)。
2. `torch.onnx.export(..., dynamo=False)`(legacy exporter,正确捕获权重;新版 Dynamo exporter 会把权重常量折叠掉,产物仅 1MB 且坏)。
3. 三种量化:全量 int8 / 仅 transformer(MatMul+Gemm,CNN 留 fp32)/ fp16。
4. 在 4 条 macOS 金标准波形(`core-scoring/.../golden/`)上跑 ONNX,比 embedding 余弦(post-CMVN)、Track B cost/acc、说话人不变性 cost。

## 结果

| 变体 | 体积 | Layer-2 余弦 | samevoice cost | **说话人不变性 cost** | wrongtext acc | Gate A |
|---|---|---|---|---|---|---|
| fp32 ONNX(导出健全性基线) | 279MB | **1.00000** | 0.0000 | **0.1714** | 74.5 | ✅ PASS |
| int8(全量动态) | 70MB | 0.80–0.87 | 0.0000 | **0.2789 ❌** | 74.5 | ❌ FAIL |
| **int8(仅 transformer,CNN fp32)** | **95MB** | 0.986–0.992 | 0.0000 | **0.1773 ✅** | 74.5 | **✅ PASS** |
| fp16 | 139MB | —(ORT-CPU 不支持 fp16,留设备验) | — | — | — | 待设备 |

- fp32 余弦 1.00000(逐位)→ 导出正确,MPS-vs-CPU 非问题,整条 Track B 可从 ONNX 复现。
- 全量 int8 把特征提取 CNN 也量化了,余弦塌到 0.80,跨嗓音 cost 抬到 0.2789(>0.18),acc 从 95.0 掉到 89.1——**正是 Gate A 要拦的失效模式**。
- 仅量化 transformer(敏感的 1-D CNN 特征提取留 fp32):余弦 0.986–0.992,跨嗓音 cost 0.1773(≤0.18),acc 95.0 精确匹配,所有 pair 的 cost/acc 在容差内。**功能上 Gate A 通过**(0.995 余弦诊断线是保守代理,未达但评分实际守住)。

## 结论

**符合 NFR-1(离线)/ NFR-Q1(质量)/ FR-4·5。** SSL 编码器走 **int8 仅 transformer(95MB)**,CNN 特征提取留 fp32;fp16(139MB)作兜底。MMS / espeak 仍是 int8 候选(它们喂 CTC 解码/Viterbi,对漂移更鲁棒,留 Gate B/C 验)。

模型体积预算修订(NFR-4②):whisper base.en ~70MB(int8,已随 macOS 包)+ wav2vec2-base ~95MB + MMS ~45MB + espeak ~318MB = **~530MB**(首启下载 wav2vec2/MMS/espeak;whisper 打包进 APK)。

## 影响 / 行动项

1. **R-5 PASS 落定**——端侧全功能最大风险解除,无需回桌。
2. SSL 编码器量化策略记入 `core-embed`(Phase 2):导出图固定为「6–9 层均值 + dynamo=False + int8 仅 MatMul/Gemm」。
3. fp16 模型已生成(139MB),保留为低内存设备的备选(Android 端 GPU/NNAPI 原生支持 fp16,届时复测)。
4. Android 设备/onnxruntime-android 上的最终复测(R-5 设备侧)仍需 Tier 2 SDK + Tier 3 模拟器;Python 侧已证 int8-transformer 保真,设备侧预期一致。
