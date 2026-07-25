# R-6 补完(2026-07-25)Gate B —— MMS 强制对齐 emission 导出 & `:core-align` 落地

> 承接 `docs/reviews/2026-07-25-android-gate-bc-onnx.md`(R-6 算法侧已过、emission 导出受阻)。
> 脚本:`scripts/onnx_export_mms.py`。实现:`NativeLingoAndroid/core-align/`。
> 关联:`docs/PRD.md` §7 R-6(FR-2 词边界 / FR-8 回放区间),`docs/android-migration.md` §5(A)/§6。

## 结论:**Gate B / R-6 PASS ✅(算法 + emission + 端到端,JVM 侧)**

| 检查 | 判据 | 实测 | 结果 |
|---|---|---|---|
| HF 载重保真(fp32,eager) | 与 torchaudio 同分布 | 余弦 **1.000000**,逐帧 argmax **100%** 一致 | ✅ |
| ONNX fp32 emission | 余弦 ≥0.995;字符帧误差 ≤1 | 余弦 **1.00000**,字符帧误差 **0** | ✅ |
| ONNX int8(仅 transformer) | 同上 | 余弦 **0.99896**,字符帧误差 **1** | ✅ |
| 导出图长度泛化 | 非 dummy 长度下仍与 eager 一致 | 3 段真实语料(130/132/148 帧)余弦 1.000000、argmax 100% | ✅ |
| Kotlin 端到端(`:core-align`,int8) | 词边界 ≤1 帧(20ms) | **8/8 测试绿**,词边界在 1 帧内;金标准 emission 上**逐字符精确** | ✅ |
| 体积 | 可下载量级 | 1203MB → **338.6MB** | ✅ |

## 解掉了什么:torchaudio 图不可量化

R-6 上一轮的阻塞点有两层,第二层才是真问题:

1. `_Wav2Vec2Model.forward` 在三处由动态 shape 构造 `List[int]`(长度记账、波形 `layer_norm`、star 列 `cat`),legacy exporter 拒绝。这层可以靠走内层子模块绕过。
2. **绕过之后仍然不可量化**:对导出的 torchaudio 图跑 `quantize_dynamic`,体积 1204MB → 1204MB **零变化** —— 其线性层 op 不匹配量化器的 pattern;强行全量 int8 又在 Conv bias initializer 处崩。1.2GB 的首启下载不可发布,所以这不是"可以接受的次优",是必须解决的阻塞。

**解法:state-dict 载重(re-host)。** MMS_FA 与 HF `Wav2Vec2ForCTC` 是同一架构,而后者是 Gate A/C 已经证明能干净导出且可量化的那条路。键名映射几乎是机械的:

```
feature_extractor.*             -> wav2vec2.feature_extractor.*
encoder.feature_projection.*    -> wav2vec2.feature_projection.*
encoder.transformer.*           -> wav2vec2.encoder.*
aux.*                           -> lm_head.*
```

423 个张量全部一一对应,无缺失、无多余(仅 HF 独有的 `masked_spec_embed` 缺失,SpecAugment 已关,是唯一允许项)。

## 一个会静默出错的坑:`layer_norm_first` 是反的

bundle 声明 `encoder_layer_norm_first=True`,但读 `Transformer.layer_norm_first` 得到 **False** —— torchaudio 把**取反后的值**传给 Transformer 包装层(各 EncoderLayer 拿到 True,Transformer 拿到 `not True`)。真实拓扑因此是「pre-norm 层 + 尾部 encoder layer_norm」,对应 HF **`do_stable_layer_norm=True`**。

**为什么这个坑危险**:若只读包装层的 flag 而设成 `False`,权重会**无报错地全部载入**(两种 encoder 子模块命名完全相同),模型正常跑、正常输出、正常对齐——只是对齐结果是垃圾。没有任何异常可依赖。因此 `verify_parity` 被放在**任何导出动作之前**:先证明载重后的模型能复现 torchaudio,再谈导出。

## 判据本身的一次修正(记录在案)

第一版 `verify_parity` 用 `max|Δ| < 1e-3` 判定,结果对**正确**的映射报 FAIL(1.03e-3)。诊断后发现:最大绝对偏差落在 **log p = −13.75(p≈1e-6)** 的深负尾部,是 24 层 fp32 累积 + 注意力 kernel 不同(HF sdpa vs torchaudio 手写 matmul)的无害差异;同一组输出的余弦是 1.000000、逐帧 argmax 100% 一致。

→ **绝对值上界是错的判据**:它被强制对齐根本不消费的尾部主导。改判为余弦 + 逐帧 argmax(强制对齐真正消费的是分布形状),`max|Δ|` 降级为诊断量。这不是放宽标准:错误的映射(如上面的 `do_stable_layer_norm`)会把余弦打到远低于 1、argmax 打到随机水平,新判据抓得更准而非更松。

## 三个外置到 Kotlin 的算子(`MmsEmitter.kt`)

动态 shape 算子不进图,在 Kotlin 复刻;三者都是承重的:

| 算子 | 说明 |
|---|---|
| 波形 `layer_norm` | 整段零均值单方差,**eps 1e-5、无 affine**。注意与 `:core-embed` 的 `Wav2Vec2FeatureExtractor` 归一化(eps **1e-7**)不同 —— 看着可互换,实则各自对齐各自的上游。漏掉它不会崩,只会让每次对齐静默变差。 |
| `log_softmax` | **保留在图内**(可正常导出),减少 Kotlin 面。 |
| star 列 | MMS_FA 追加全零第 29 列。log 域的 0 即 p=1,是能吸收任意帧的通配符。我们从不把 star 放进目标序列,但 emission 宽度必须与金标准一致。 |

另外 legacy exporter 对 sdpa 的 `is_causal` 发了 TracerWarning(由 dummy 长度烘成 Python 常量)。它对我们喂的任何输入都恒为 False(非因果、不传 mask),但"应该是常量"是论证不是证据 —— 因此加了 `verify_generalizes`:用 3 段**非 dummy 长度**的真实语料跑导出图 vs eager,余弦 1.000000。

## 帧→秒的约定被逐字复刻(不"修正"上游)

torchaudio `TokenSpan.end` 是**开区间**(= 末帧+1),macOS `align_words` 再 `+1` 帧尾:`end = (f1 + 1) * spf`。这多出的一帧被**原样保留** —— 金标准词边界就是这么产生的,而 FR-8 的 A/B 回放会 seek 到这些边界。此处"更正确"只会与 macOS 失同步。`spf` 同样由 `wav.size / nframes` 实时推导而非硬编码 0.02。

## 包体预算修正(NFR-4②)

| 模型 | 方案 | 体积(MiB) |
|---|---|---|
| whisper base.en | int8(打包 APK) | ~70 |
| wav2vec2-base-960h(6–9 层) | int8 仅 transformer | 95.8 |
| espeak-cv-ft | int8 全量 | 302.9 |
| **MMS FA** | **int8 仅 transformer(HF 载重)** | **338.6** |

**首启下载 ≈ 737MB**(三项之和 737.3;此前按 MMS ~300MB 估作 ~700MB),整包 ≈ 807MB。仍属可后台预下载的量级,但**已接近可接受上限** —— 若 Gate D(RAM)或用户侧反馈要求压缩,MMS 是下一个该动的对象(可评估仅保留对齐所需精度的更激进量化)。

## 遗留 / 下一步

1. **设备侧复测仍未做**:以上全部在 JVM(macOS 原生 onnxruntime)上完成。arm64-v8a 上的 int8 kernel 可能与桌面不同 → Tier 3 模拟器/真机复测(R-6 设备侧)。
2. `verify_generalizes` 只覆盖 2.6–3.0s 片段。长选段(macOS 侧已知 MPS OOM 风险,R-3)在 Android 上的分段策略未验证。
3. Phase 2 余项:`:core-asr`(sherpa-onnx Whisper)、`:core-audio`(FFmpeg NDK)。
