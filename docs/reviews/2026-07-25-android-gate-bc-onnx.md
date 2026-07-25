# R-6 / R-7(2026-07-25)Android 端侧 MMS 强制对齐 / espeak 音素 CTC 的 int8 保真

> Gate B(MMS,R-6)与 Gate C(espeak,R-7)。承接 R-5(SSL 编码器 int8 已过)。`scripts/onnx_gate_bc_spike.py`。
> 关联:`docs/android-migration.md` §7,`docs/PRD.md` §7 R-6/R-7。

## Gate C(espeak,R-7)—— PASS ✅

espeak-cv-ft(Wav2Vec2ForCTC,HF)导出 ONNX + int8,在 macOS 金标准 `ref_samantha_raw` 上比:

| 变体 | 体积 | emission 余弦 | CTC 贪解串 | Gate C |
|---|---|---|---|---|
| fp32 | 1205MB | 1.00000 | 与 fp32 完全一致 | ✅(导出健全) |
| **int8(全量)** | **303MB** | 0.99462 | **完全一致(exact)** | **✅ PASS** |

**判定**:espeak 的功能门控是「贪解串精确」(manifest:`espeak_decode_exact`)——MDD 消费的就是 canonical IPA 串 + Viterbi 打分的 emission,二者被「exact 贪解 + 0.9946 余弦」守住。0.9946 比 0.995 诊断线低 0.0004,属保守代理的微差,不影响功能。**espeak 走 int8 全量,303MB**(比 Finding ③ 估的 318MB 略小)。

> MDD 完整替换诊断(think→sink)需真实误读音频(`say` 合成不出误读),留 Phase 3 用真机/真实语料复测;此处验的是**模型保真**(canonical 解码 + emission),已过。

## Gate B(MMS,R-6)—— 算法已验,导出待 Phase 2

- **算法侧已过(JVM)**:`CtcViterbi.kt` 在 `:core-scoring` 复现 torchaudio `get_aligner()` 每字符帧边界 ±1 帧(`CtcViterbiParityTest` 1/1 绿)。即:给定相同 emission,Kotlin Viterbi 与 torchaudio 对齐完全一致。
- **emission int8 保真:导出受阻,风险低、待 Phase 2**。torchaudio 的 MMS_FA 模型图含 `prim::ListConstruct → List[int]`,legacy ONNX exporter 拒绝(`do_constant_folding=False`、改 opset 均无效);新 Dynamo exporter 会把权重常量折叠(R-5 已证不可用)。
  - **解法(Phase 2 `:core-align`)**:把 MMS 权重载入 HF `Wav2Vec2Model`(与 facebook/wav2vec2-base-960h 同架构,后者已干净导出),或用 `torch.export` 新路径。属工程实现,非研究风险。
  - **风险评估**:MMS 是 CTC 强制对齐,对量化漂移鲁棒(余弦小抖动 → Viterbi 路径不变);同族 CTC 的 espeak int8 已 decode-exact 过。预期 MMS int8 ~45MB 同样可过,设备侧 R-6 复测收尾。

## 模型包体预算落定(NFR-4②)

| 模型 | 方案 | 体积 | Gate |
|---|---|---|---|
| whisper base.en | int8(随 macOS 包已验) | ~70MB | — |
| wav2vec2-base-960h(6–9 层) | **int8 仅 transformer**(CNN fp32) | **95MB** | R-5 ✅ |
| espeak-cv-ft | **int8 全量** | **303MB** | R-7 ✅ |
| MMS FA | int8(Phase 2 验) | ~45MB(估) | R-6 算法✅/emission 待 |

**首启下载总量 ~440MB**(wav2vec2 + espeak + MMS;whisper 打包进 APK ~70MB)。**总包体 ~510MB**,优于初估的 ~530MB,且其中 espeak 可惰性加载、按词批释放(Gate D/R-8 RAM 收尾)。

## 影响

1. 三大模型量化策略落定:SSL= int8 transformer-only、espeak = int8 全量、MMS = int8(待导出解法)。
2. R-5/R-7 PASS,R-6 算法 PASS + emission 导出列入 Phase 2 任务。
3. 下一步:Phase 1 收尾(word_diff/feedback)、Tier 2 SDK、Tier 3 模拟器(设备侧 R-5/R-6/R-7 复测 + Gate D RAM + Gate E Opus)。
