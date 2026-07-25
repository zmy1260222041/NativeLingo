# NativeLingoAndroid

Android 移动端实现 —— **原生 Kotlin + Jetpack Compose + 全端侧推理**(守 PRD NFR-1:录音不出设备、全离线)。完整迁移方案见 [`../docs/android-migration.md`](../docs/android-migration.md),需求追溯见 [`../docs/PRD.md`](../docs/PRD.md) v0.1。

> 这是 v2.0 级重写,不是 macOS 版的移植。Python 后端 + PyInstaller + Tauri-sidecar 架构在 Android 不可行;4 个模型用 ONNX Runtime Mobile / sherpa-onnx int8 重写。**macOS 版继续维护,作为本端数值对齐的金标准源。**

## 模块结构

| 模块 | 阶段 | 职责 | 状态 |
|---|---|---|---|
| `:core-scoring` | **1** | 纯 JVM 评分核心(DTW / CMVN / 校准 / detail / word_diff / feedback / **CtcViterbi**)+ 金标准测试 | 🚧 骨架 + golden 测试 |
| `:core-embed` | 2 | ONNX wav2vec2-base-960h(6–9 层自定义图输出) | ⬜ 待建 |
| `:core-asr` | 2 | sherpa-onnx Whisper + Silero VAD | ⬜ 待建 |
| `:core-audio` | 2 | WAV I/O / 静音裁剪 / FFmpeg JNI | ⬜ 待建 |
| `:core-align` | 2 | ONNX MMS CTC + ForcedAligner(用 core-scoring 的 CtcViterbi) | ⬜ 待建 |
| `:core-mdd` | 3 | ONNX espeak-cv-ft int8 + PhonemeMdd(惰性加载) | ⬜ 待建 |
| `:core-models` | 4 | ModelRegistry(whisper 打包 APK;余首启下载) | ⬜ 待建 |
| `:app` | **4** | Compose UI / ViewModel / DI / AudioRecord / Media3 / Repo / Warmup / FR-12 Room | 🚧 骨架 |

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
