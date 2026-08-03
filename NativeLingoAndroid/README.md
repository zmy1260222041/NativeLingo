# NativeLingoAndroid

Android 移动端实现 —— **原生 Kotlin + Jetpack Compose**。完整迁移方案见 [`../docs/android-migration.md`](../docs/android-migration.md),需求追溯见 [`../docs/PRD.md`](../docs/PRD.md) v0.1。

> 这是 v2.0 级重写,不是 macOS 版的移植。Python 后端 + PyInstaller + Tauri-sidecar 架构在 Android 不可行。**macOS 版继续维护,作为本端数值对齐的金标准源。**

## v0.7 — 云端跟读架构(2026-08)

参照 Duolingo 的云端评分模式,跟读模块迁移到自建服务器(`server/`,部署于 `124.220.234.178:8756`):

- **服务器负责**:视频转写(whisper)、MMS 词对齐、SSL 评分、**FR-11 音素级诊断**(`/θ/ 读成了 /s/` 中文提示)。
- **App 变瘦客户端**:上传录音 WAV → `POST /analyze_video`;视频本身仍在设备端,本地解码用于 A/B 回放。
- **识物模块(FR-13/FR-17)保持全本地**(用户决策):照片不出设备,YOLOE + 发音评分不变。
- **删除的本地推理**:`core-align`(MMS)、`core-asr`(whisper/VAD)、espeak。APK 从 ~1 GB 缩到 **~270 MB**(w2v2 146MB + YOLOE 45MB + Piper 片段 + 语料)。
- 服务器地址/令牌由 gradle 属性注入(`-PNATIVELINGO_SERVER_URL=... -PNATIVELINGO_SERVER_TOKEN=...`),明文 HTTP + bearer token(TLS 为后续项)。
- 服务器端 `server/` 是桌面 torch 后端的 **ONNX Runtime 变体**(同安卓已验证的 int8 导出,3.7GB RAM 部署机装得下 torch 原版;奇偶校验:嵌入余弦 1.000000,评分输出一致)。

**需要联网**:跟读必须连服务器;识物仍离线可用。

## 模块结构

| 模块 | 阶段 | 职责 | 状态 |
|---|---|---|---|
| `:core-scoring` | **1** | 纯 JVM 评分核心(DTW / CMVN / 校准 / detail / word_diff / feedback / **CtcViterbi**)+ 金标准测试 | ✅ 金标准对齐 |
| `:core-embed` | 2 | ONNX wav2vec2-base-960h(6–9 层自定义图输出)——识物 FR-17 发音评分复用 | ✅ |
| `:core-audio` | 2 | MediaExtractor/MediaCodec 音频解码 + 重采样 | ✅ |
| `:core-models` | 4 | ModelRegistry + AssetsModelSource(APK 内模型首启解压) | ✅ |
| `:core-vision` | 4 | YOLOE-26S-PF 识物(FR-13) | ✅ |
| `:app` | **4** | Compose UI / ViewModel / DI / AudioRecord / Media3 / Repo / Warmup + **云端跟读**(v0.7) | ✅ v0.7.0 |

**不变量**:`:core-scoring` 零 Android 依赖(纯 Kotlin stdlib),可在 JVM CI 用 macOS 金标准文件单测 —— 评分保真的所有逻辑都在这里。

## 构建前置

本仓库当前开发机无 JDK/Android SDK/Gradle,故脚手架未本地编译验证。**首次构建需:**

1. **JDK 17**(`temurin-17`)。
2. **Android Studio**(Ladybug+)或 Android SDK(`compileSdk=35`, `minSdk=28`)。
3. **生成 Gradle wrapper**:`gradle/wrapper/gradle-wrapper.properties` 已就位,但 wrapper jar 需一次 `gradle wrapper`(或 Android Studio 打开工程自动生成)。
4. 版本(`gradle/libs.versions.toml`)为 2024Q4 已知稳定组合,Android Studio 打开时可升级到当前最新。

```bash
cd NativeLingoAndroid
gradle wrapper            # 一次,生成 ./gradlew
./gradlew :core-scoring:test    # 跑金标准 smoke 测试(JVM,无需设备)
./gradlew :app:assembleDebug    # Phase 4 起
```

## 金标准数值对齐(核心机制)

macOS 后端是"金标准源";Android 端评分须与它在容差内一致。流程:

1. macOS 上跑 `../scripts/capture_golden.py` 产出 `core-scoring/src/test/resources/golden/`(已生成并提交):
   - `emb/*.npy` —— wav2vec2 6–9 层嵌入(Gate A · Layer 2)
   - `pair/*.json` + `*_path.npy` + `*_costs.npy` —— DTW 分数与路径(Gate A · Layer 1)
   - `mms/*_emission.npy` + `*_spans.json` —— MMS 对齐(Gate B · Layer 2)
   - `espeak/*_emission.npy` + `*_decode.txt` —— 音素 CTC(Gate C · Layer 2)
   - `manifest.json` —— 语料索引 + 容差 + provenance
2. `:core-scoring:test` 用相同算法处理相同输入,在容差内断言(cost ±0.02 / accuracy ±2.0 / fluency ±3.0 / 嵌入余弦 ≥0.995)。
3. 容差即 int8 量化漂移的捕获点。

**说话人不变性试金石**(Gate A 的存在性证明):macOS 上跨嗓音对 `speakervariance` 的 DTW cost = **0.1714**(≤0.18 阈值),accuracy 95.0。Android int8 必须守住。

## Phase 0 — spike 门(go/no-go,先做完才动其他)

5 个 make-or-break 风险,每门一份符合性评审(`docs/reviews/R-5..R-9`):

- **R-5 / Gate A** —— wav2vec2 int8 端侧评分对齐(accuracy ±2.0 / fluency ±3.0 / cost ±0.02 / 不变性 cost ≤0.18)。**项目存在性证明。**
- **R-6 / Gate B** —— 手写 CTC Viterbi 词边界 ≤1 帧。
- **R-7 / Gate C** —— 音素 MDD int8 门控仍成立。
- **R-8 / Gate D** —— 6GB 设备 RAM 无 OOM。
- **R-9 / Gate E** —— Opus/WebM 解码样本 ≤1 LSB。

详见 `../docs/android-migration.md` §7。
