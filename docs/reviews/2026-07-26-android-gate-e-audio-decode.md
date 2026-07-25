# R-9(2026-07-26)Gate E —— 音频解码与重采样:FFmpeg NDK 还是 MediaCodec + 自写重采样器

> 关联:`docs/PRD.md` FR-3(跟读录音)、FR-M1(真实视频素材)、FR-M2(素材获取/导入)、
> NFR-1(全离线)、NFR-Q1(评分质量);`docs/android-migration.md` §4 发现②、§6 `audio_io.py`/`video.py` 映射、§7 Gate E。
> 脚本:`scripts/resampler_parity.py`(入库,可复跑)。语料:`videos/7.1.mp4`(44.1kHz 立体声 AAC),三个 25s 片段(t=30/180/400)。
> 这是 Phase 2 最后一个模块 `:core-audio` 动工前的门。

## 计划里的判据先失效了

§7 把 Gate E 写成:**「WebM/Opus blob 经 FFmpeg-NDK 解码 vs macOS `ffmpeg -ar 16000 -ac 1 -f f32le`,样本误差 ≤1 LSB」**。

这条判据只有在**已经选了 FFmpeg** 的前提下才可能通过 —— 换一个重采样核就必然换一批样本值,
1 LSB 由构造上不可达。也就是说它不是在检验路线,而是在假设路线。真正要回答的问题是别的:

> 参考音频用哪个重采样器,会不会改变学习者看到的分数?

判据必须落在**分数域**,不是样本域。下面先把它量出来,再定路线。

## 两条路线

| | A(原计划) | B(候选) |
|---|---|---|
| 解码 | FFmpeg NDK 源码构建 + 薄 JNI | `MediaExtractor` + `MediaCodec`(系统解码器) |
| 重采样 | libswresample `aresample` | 纯 Kotlin 多相 windowed-sinc,放 `:core-scoring` |
| 与 macOS 的关系 | 同一份 libswresample → 样本级一致 | 不同核 → 样本不同,须证明分数不变 |
| 构建成本 | NDK(**当前未安装**)+ buildSrc 交叉编译 + 16KB 页对齐编译参数 | 零原生代码 |
| 许可 | LGPL:动态链接 + 需保留重链接权利(上架应用要认真处理) | 无 |
| 包体 | +2–4MB/ABI 起 | 0 |
| 可测性 | JNI,只能设备侧测 | 重采样器在 `:core-scoring`,JVM 金标准单测 |

## 发现①:发现②的前提在 Android 上已经不存在了

§4 发现② 的原话是「ffmpeg-kit 已退役…**MediaCodec 对 WebM/Opus 覆盖不全**」。这句话默认
WebM/Opus 是**必须**解的格式 —— 因为 macOS 上浏览器 `MediaRecorder` 录出来的就是 webm/opus,
`decode_audio_bytes()` 专为它而写(`video.py:116`)。

**Android 的学习者路径根本不产生编码音频。** `AudioRecord` 以 16kHz 单声道 PCM 直接采集
(§4 已定,也正是 FR-3 的实现),不经过任何编解码器,也不需要重采样。webm/opus 是 WebView 的
产物,随 WebView 一起消失。

于是解码需求只剩**视频音轨**一项:`videos/` 目录里的素材(FR-M1)和用户导入的文件(FR-M2)。

## 发现②:平台强制的容器/编解码覆盖,只差一个 `.avi`

macOS 侧 `VIDEO_EXTS = {.mp4, .mov, .mkv, .m4v, .webm, .avi}`。对照 Android 官方
*Supported media formats*(平台强制项,非厂商可选项):

| 扩展名 | 平台 `MediaExtractor` | 说明 |
|---|---|---|
| `.mp4` / `.m4v` / `.mov` | ✅ | AAC-LC/HE-AAC 全版本强制;xHE-AAC 从 API 28(正好是我们的 minSdk) |
| `.mkv` | ✅ | Matroska 强制,内含 Opus/Vorbis/FLAC/MP3 |
| `.webm` | ✅ | Vorbis/Opus |
| Opus | ✅ **API 21+ 强制解码** | 容器:Ogg / MP4 / Matroska |
| `.avi` | ❌ **平台不保证** | 官方文档全文未列 AVI |

也就是**「MediaCodec 对 WebM/Opus 覆盖不全」这一条,对照官方文档不成立**:Opus 解码自
Android 5.0 起是强制项,远低于我们 API 28 的下限。唯一真实的缺口是 `.avi`,而它属于
FR-M2 的导入面 —— 后果是「这个文件导不进来」,不是「分数算错」。Media3 有实验性的
`AviExtractor` 可作后续补充。

> 运行期不要相信版本表,用 `MediaCodecList(REGULAR_CODECS).findDecoderForFormat(fmt)`
> 探测;探测不到就报「不支持此格式」,这是干净的降级切口。

## 发现③(决定性):重采样器的选择,在分数域上是**零**

`scripts/resampler_parity.py`。同一段音频,四条路径:

- **A** libswresample 44.1k→16k(macOS 真相,金标准就是这么抓的)
- **B** 多相 windowed-sinc(`scipy.signal.resample_poly`,即 Kotlin 会写的东西)
- **C** `soxr_hq`(`librosa.resample`)—— 注意 **macOS 自己就不自洽**:`audio_io.py` 的上传路径用 soxr,`video.py` 的视频路径用 swresample
- **D** 同 B,但输入先量化成 int16 PCM(MediaCodec 的默认输出编码)

### 样本域:差得很远

| t=30s | SNR | maxΔ | ≈ int16 LSB |
|---|---|---|---|
| B poly | 43.0 dB | 1.15e-2 | ~377 |
| C soxr | 39.1 dB | 2.33e-2 | ~763 |
| D int16 | 43.0 dB | 1.15e-2 | ~377 |

t=180/400 更差(30.5–37.7 dB)。**「≤1 LSB」离得有三个数量级** —— 而且 C 这一列说明,
macOS 自己两条路径之间就已经差这么多了。

### 嵌入域与分数域:差不多是零

三个片段,`:core-scoring` 的口径(CMVN 后逐帧余弦 / DTW path cost / 校准后 accuracy):

| 片段 | 路径 | cos 均值 | cos<0.99 帧数 | DTW cost | accuracy |
|---|---|---|---|---|---|
| t=30 | B / C / D | 0.9986 / 0.9998 / 0.9987 | 5 / 1 / 5 (共 1250) | 0.0006 / 0.0002 / 0.0005 | 95.0 / 95.0 / 95.0(A 也是 95.0) |
| t=180 | B / C / D | 0.9983 / 0.9992 / 0.9985 | 6 / 3 / 6 | 0.0011 / 0.0008 / 0.0009 | 全部 95.0 |
| t=400 | B / C / D | 0.9996 / 0.9996 / 0.9996 | 3 / 4 / 2 | 0.0004 / 0.0004 / 0.0004 | 全部 95.0 |

余弦均值 **0.9983–0.9998,全部 ≥0.995**(Layer-2 判据)。掉到 0.99 以下的是每 1250 帧里的
1–6 帧,脚本会打印最差帧的能量:**无一例外落在低能量帧**(0.01–0.20× 片段 RMS),即 CMVN
在近乎静音处放大了噪声,不是语音内容分歧。

**int16 量化是免费的**:D 与 B 在四位小数上一致。MediaCodec 默认输出 16-bit PCM 不构成风险。

### 但上表处在 cost 地板上,校准曲线在那里是平的 —— 所以还得测真实档位

Android 上**学习者音频永远不重采样**(AudioRecord 直采 16kHz),只有**参考音频**会。
所以固定一个学习者,只换参考的重采样器,在真实读音会落到的 cost 区间(0.30–0.39)复测:

| 学习者(合成扰动) | ref=A | ref=B poly | ref=C soxr | max Δcost | max Δacc |
|---|---|---|---|---|---|
| time-stretch 1.08 | 0.3918 / 86.5 | 0.3923 / 86.5 | 0.3917 / 86.5 | **0.0006** | **0.00** |
| time-stretch 0.92 | 0.3679 / 88.6 | 0.3679 / 88.6 | 0.3678 / 88.6 | **0.0000** | **0.00** |
| pitch +2 | 0.3934 / 86.5 | 0.3940 / 86.5 | 0.3935 / 86.5 | **0.0006** | **0.00** |
| (t=180 同三项) | 0.3383 / 0.3008 / 0.3044 | — | — | **≤0.0011** | **0.00** |

**Gate A 的容差是 cost ±0.02 / accuracy ±2.0。实测最大 0.0011,余量 18×;accuracy 一位小数上纹丝不动。**

## 结论:**走路线 B,Gate E 判据改写 —— PASS(桌面侧),设备侧留一项待测**

**判据改写(替换 §7 原 Gate E):**

| 原 | 新 |
|---|---|
| WebM/Opus 经 FFmpeg-NDK 解码 vs `ffmpeg -ar 16000` 样本误差 ≤1 LSB | ① 同一视频片段,Android 解码+重采样 vs macOS `extract_audio()`:CMVN 后逐帧嵌入余弦均值 **≥0.995**;② 固定学习者、只换参考解码路径:DTW cost 差 **≤0.005**、accuracy 差 **≤0.5**(即 Gate A 容差的 1/4);③ 目标格式集在设备上 `findDecoderForFormat` 全部命中 |

判据②取 Gate A 容差的 1/4,理由是解码只是链条的第一环,不该吃掉留给 int8 的预算;实测 0.0011
在这条线下仍有 4.5× 余量。**和 R-10 一样,这也是事后定的判据,如实记录。**

**这条门在桌面侧 PASS**:重采样核的选择对分数无影响,已量化。

### 路线 B 的代价,写清楚

1. **失去「所有设备样本一致」的保证。** FFmpeg 走到哪台机器都是同一份 libswresample;系统
   解码器是各家 OEM 的实现。AAC 解码有一致性容差但不是逐位规定的。**这是路线 B 唯一真实的
   风险,而且只能在设备上测** → 进设备清单:同一视频在 3–5 台机器上解码,两两比嵌入余弦。
   量级参考:本文测到的重采样核差异(40dB SNR)只值 0.0011 cost,而合规解码器之间的差异应当
   远小于换核,所以先验上安全 —— 但这是推断,不是测量。
2. **`.avi` 导不进来**(FR-M2 面)。当前 `videos/` 里没有 avi;建议 Android 的导入白名单直接
   去掉 `.avi`,并在 PRD 的素材获取一节注明。需要时再接 Media3 `AviExtractor`。
3. **seek 语义必须照抄。** `video.py:88` 是 `container.seek(...)` 到 `start` 之前最近的关键帧
   且**不丢弃 start 之前解出来的样本**(docstring:「any pre-start samples decoded are kept」)。
   Android 对应 `MediaExtractor.seekTo(us, SEEK_TO_PREVIOUS_SYNC)` 后同样从首个解出样本开始保留。
   这决定句子片段的起点,**属于「决定音频在哪里被切」的范畴,按 R-10 立下的规矩要能在 JVM 上验**
   —— 切片策略进 `:core-scoring`,`MediaExtractor` 只提供关键帧时间。

### 顺带消掉的东西

- `buildSrc/` 的「NDK FFmpeg 构建」没了 —— **Phase 2 不再需要安装 NDK**(当前也确实没装)。
- LGPL 的重链接义务没了。
- §4 发现② 的结论作废(前提消失);16KB 页对齐这条约束对本模块不再适用(无自带 .so)。
- `:core-audio` 变薄:`WavIo`/`Trim` 早已在 `:core-scoring`(Phase 1 完成),剩下的是
  `MediaExtractor`/`MediaCodec` 胶水 + 重采样器调用。

## 落地清单

- [x] `:core-scoring/.../resample/PolyphaseResampler.kt`(2026-07-26)—— **`scipy.signal.resample_poly`
      默认 Kaiser(5.0) 设计的 1:1 移植**,连 `firwin` 的 DC 归一化、`h *= up`、
      `n_pre_pad = down - half_len % down` 的前置补零与 `n_pre_remove` 裁剪都照抄。
      **为什么钉 scipy 而不是"写个够好的重采样器"**:上文那组分数域测量就是用它做的 —— 钉住它,
      测量才转移得过来,否则"够好"是个没有判据的问题。金标准 `golden/resample/`(4 例,float64,
      `capture_golden.py:dump_resample`),**逐样本 |Δ| < 1e-12**。另加三组不依赖 fixture 的检查:
      firwin 的 DC 增益/线性相位对称性、`numpy.kaiser` 与 `i0` 的定点值、1kHz 通带 SNR >40dB 与
      11kHz(超出输出 Nyquist)混叠泄漏 <0.02。`:core-scoring` **53/53 全绿**。
      - 顺带记一个 scipy 的非直觉之处:48k→16k 是 `up=1, down=3` → 61 抽头;44.1k→16k 是
        `up=160, down=441` → **8821 抽头**。差 145 倍,是 `half_len = 10*max(up,down)` 的直接后果。照抄不改。
      - 金标准用 float64,生产路径是 float32。**故意的**:float32 金标准会把"算法错了"和"累加顺序不同"
        混成一件事,只有前者值得测;float32 路径另测,判据是相对 float64 的 SNR >100dB。
- [x] `:core-audio/.../MediaAudioDecoder.kt`(2026-07-26)—— `MediaExtractor` + `MediaCodec` 同步循环
      → int16/float PCM → 声道平均下混 → `PolyphaseResampler`。`findDecoderForFormat` **前置探测**
      (否则 `createDecoderByType` 只抛裸 `IOException`,读起来像"文件坏了"而不是"这台机器没有解码器",
      FR-M2 要能区分)。采样率/声道数取 **输出格式**(`INFO_OUTPUT_FORMAT_CHANGED`)而非轨道格式 ——
      解码器有权给回别的。`assembleDebug` 通过;**JNI/框架调用一次都还没在设备上跑过**。
- [x] 切片语义:`DecodedAudio.startS` 返回**首个解出样本的真实时间戳**(seek 落在前一同步样本,
      pre-start 样本保留,与 `video.py` 同),比 macOS 多给一个信息 —— FR-8 回放区间需要它。
- [ ] 设备清单加一项:多机解码一致性(上文代价 1)。
- [ ] 改 `docs/android-migration.md`:§4 发现②、§6 `video.py`/`audio_io.py` 映射行、§7 Gate E 判据、
      §8 模块树(去掉 buildSrc 的 NDK 构建)。
- [ ] 改 `docs/PRD.md`:FR-M2 导入格式集去掉 `.avi`(用户可见的能力变更)。

## 待用户拍板

本文的路线切换本身属于「技术变更须追溯到 FR 并过 fit-review」的范畴,证据已在上文;
若无异议按路线 B 实施。**另有三项此前挂起的 ❓ 决策仍未拍板**(见 `docs/android-migration.md` §12):
预置语料的 `.sentences.json` 随包、whisper 移出基础 APK(需改 NFR-4②)、仅发 arm64-v8a。
