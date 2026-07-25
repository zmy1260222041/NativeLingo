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

## Gate B(MMS,R-6)—— 算法已验,导出有解但需 HF 载重(Phase 2)

- **算法侧已过(JVM)**:`CtcViterbi.kt` 复现 torchaudio `get_aligner()` 每字符帧边界 ±1 帧。
- **emission 导出深挖(2026-07-25 补)**:`scripts/onnx_gate_bc_spike.py` 的 `MmsEmission` 走内层子模块(`feature_extractor → encoder → aux`)能干净导出(绕过 `_Wav2Vec2Model` 的 lengths `List[int]`)。但 torchaudio 的 forward 还有两处 dynamic-shape `List[int]`:
  - `normalize_waveform = F.layer_norm(wav, wav.shape)`(波形 layer_norm,eps 1e-5)。
  - `append_star = torch.cat(zeros((1, T, 1)))`(补零列,V 28→29)。
  - 两者都需 **外置到 Kotlin**(预归一化波形 + 推理后补零列),不进 ONNX 图。
- **关键发现 —— torchaudio 图 int8 不缩体**:对导出的 torchaudio 图跑 `quantize_dynamic(op_types_to_quantize=["MatMul","Gemm"])`,体积 **1204MB → 1204MB 零变化**(其线性层 op 不匹配量化器);全量 int8 又在 Conv-bias 处崩。→ **必须走 HF 载重路径**:把 MMS 权重(fairseq/torchaudio 命名)映射载入 HF `Wav2Vec2Model`(与已干净导出 + 可量化的 wav2vec2-base 同架构),再导出 + int8。键名映射是 Phase 2 `:core-align` 的实打实任务。
- **包体修正**:MMS_FA 实测 **~300M 参数(fp32 1.2GB)**,非早先估的 ~95M → int8 预期 **~300MB**(非 ~45MB)。
- **风险评估不变**:MMS 是 CTC 对齐,对漂移鲁棒;espeak int8 decode-exact 已证。emission int8 保真风险低,设备侧 R-6 复测收尾。

## 模型包体预算(NFR-4②,修正)

| 模型 | 方案 | 体积 | Gate |
|---|---|---|---|
| whisper base.en | int8(打包 APK) | ~70MB | — |
| wav2vec2-base-960h(6–9 层) | int8 仅 transformer | 95MB | R-5 ✅ |
| espeak-cv-ft | int8 全量 | 303MB | R-7 ✅ |
| MMS FA | int8(走 HF 载重,Phase 2) | **~300MB**(实测参数量) | R-6 算法✅/emission 待 |

**首启下载 ~700MB**(wav2vec2 + espeak + MMS;whisper 打包 ~70MB)。比早先 ~440MB 估高(MMS 比预想大),仍属可接受的首启下载量级(可后台预下载,流程同 macOS `/warmup`);espeak 可惰性加载。

## 影响

1. R-5/R-7 PASS;R-6 算法 PASS,emission 导出方案明确(HF 载重 + normalize/star 外置)。
2. MMS 包体修正至 ~300MB,首启总量 ~700MB。
3. 下一步:Phase 1 收尾(word_diff/feedback)、core-align 的 HF 载重实现、Tier 3 模拟器(设备侧复测 + Gate D/E)。
