# R-10(2026-07-26)Gate F —— sherpa-onnx Whisper 转写文本 vs faster-whisper 金标准

> **计划里原本没有这道门。** `docs/android-migration.md` §7 的 Phase-0 门只列了 R-5..R-9
> (int8 评分 / Viterbi / MDD 门控 / RAM / Opus),ASR 被当成"输出格式对齐"的中风险机械活
> (§6 模块映射表)。写 `:core-asr` 之前才发现它需要一道自己的门,理由见下。
> 脚本:`/tmp/asr_{sherpa,sherpa_win,sherpa_longform,compare,time}.py`(测量用,未入库)。
> 关联:`docs/PRD.md` FR-2(转写+句切分)、FR-M3(难度适配)、NFR-3(性能)、NFR-4②(包体)。
> 语料:`videos/7.1.mp4`(CBS 新闻,636.1s,金标准 1944 词 / 164 句,即 `videos/7.1.sentences.json`)。

## 为什么需要一道门

macOS 侧的 Whisper **只贡献文本**:词边界一律由 MMS 强制对齐产生(§4 发现⑤),`transcribe_waveform`
在学习者路径上还只是 fallback(`pipeline.py:174`,主路径是把参考文本对齐到学习者音频)。所以
"输出格式对齐"这个描述并不错 —— 错的是由此推论出风险低。

真正的暴露面是**参考转写的文本本身**,它有三条下游:

1. **MMS 对齐消费它**。文本错一个词,对齐器就被要求把从未说出的字符对齐到真实音频上 → 该词的
   `[start,end]` 落在任意位置 → FR-8 回放跳错、FR-6 词级定位错。
2. **FR-2/FR-M3 按 `[.!?]` 切句**。少一个句号就把两个练习单元合成一个,**即使每个词都对**。
   标准 ASR 评测会剥掉标点,把这种情况记为满分 —— 所以现成的 WER 数字回答不了这个问题。
3. **FR-11 的 canonical 音素从文本来**。文本错 → canonical 错 → 诊断错。

第 2 条是这条流水线特有的,也是必须自己量的原因。

## 结论:**Gate F / R-10 PASS ✅ —— 但判据不是文本相等,而是"分歧有界且不影响分数"**

| 检查 | 判据 | 实测(int8 + 长音频循环) | 结果 |
|---|---|---|---|
| 归一化 WER vs 金标准 | ≤5%(见下"判据怎么定的") | **3.14%** | ✅ |
| 终止标点分歧(仅在两侧词相同处统计) | ≤2% | **1.01%**(1890 个匹配词中 19 处) | ✅ |
| 练习单元数(仅文本驱动) | ±5% | 金标准 159 vs **162**(+1.9%) | ✅ |
| int8 相对 fp32 的额外损失 | 不得成为主导项 | WER 3.14% vs fp32 **3.03%** → int8 只贡献 **0.11pp** | ✅ |
| 单窗解码(29s,desktop arm64) | 有数即可,设备侧再测 | **2.36s / RTF 0.081** | ✅ |

**判据是事后定的,这一点必须写明。** R-5..R-9 的判据都能从 macOS 的既有指标推出来(校准分数、
帧误差、LSB),Gate F 不能:两个 base.en 解码器在难音频上本就会分歧,没有"应该是多少"的先验。
所以流程反过来 —— 先量三种切块策略,看分歧的**结构**(下一节),确认它不是系统性错误而是
局部替换,再把判据定在"最好的策略实测值 + 余量"。**这比 R-6 那次改判据更弱,如实记录。**

## 最大的发现:分歧的主因是**我们的切块选择**,不是 sherpa-onnx、不是 ONNX、不是 int8

sherpa-onnx 的离线 Whisper 一次最多吃 30s(超过直接截断并打印警告),所以长音频必须自己切。
按 §4 原本的选型(`OfflineRecognizer` + Silero VAD)切,结果最差。三种策略同一模型同一 int8 权重:

| 切块策略 | 词数 | 归一化 WER | 标点分歧 | 练习单元(金标准 159) |
|---|---|---|---|---|
| **Silero VAD 分段**(§4 原选型) | 1937 | 5.56% | **3.17%**(59 处) | **172**(+8.2%) |
| 固定 29s 窗 | 1879 | 5.56% | 1.25% | 162 |
| **Whisper 长音频循环** | 1926 | **3.14%** | **1.01%** | **162** |

机制清楚:**VAD 在句子中间下刀,而 Whisper 会给它拿到的任何一段结尾加标点。** 于是 VAD 的每个
切口都变成一个假句末 —— 59 处标点分歧里绝大多数落在切口上(`president` → `president.`、
`News.` → `News`),这也正是 172 vs 159 的来源。固定窗把标点问题减轻了(切口少),但**切在词中间**,
丢了 65 个词(1879 vs 1944),WER 靠删除撑着,更差。

**长音频循环**是 Whisper 自己的做法,也是 faster-whisper 内部在做的事:解码 29s 窗 → **丢掉最后一个
segment(它是被窗口切断的那个)→ 把游标推进到倒数第二个 segment 的结尾** → 下一窗从那里重开。
切口因此落在 Whisper 自己认为的短语边界上,不发明任何边界。sherpa-onnx 恰好提供了实现它所需的
`enable_segment_timestamps`(暴露 `segment_timestamps` / `segment_durations` / `segment_texts`)。

**免费换来一半的差距**(WER 5.56%→3.14%,标点 3.17%→1.01%),代价只是几十行 Kotlin 游标逻辑。
**§4 的选型行必须改**:"`OfflineRecognizer` + Silero VAD" 对参考路径是错的。VAD 保留给学习者
录音(单句、几秒、一段,不存在切块问题)和"有没有人在说话"的判断。

**够不到的那一项:** faster-whisper 默认 `condition_on_previous_text=True`(把上文喂给下一窗),
sherpa-onnx 的 `from_whisper` 没有 prompt/prefix 参数,**没有办法开**。残余 ~3% 里有多少是它造成的
无法在不改 sherpa-onnx 的前提下拆开 —— 这是本门唯一一处"知道有影响但量不出来"的地方,如实标注。

## 第二个发现:**int8 不是问题,而且它一点也不更快**

| | 体积 | WER vs 金标准 | 29s 窗解码 |
|---|---|---|---|
| int8(encoder 29.1MB + decoder 130.7MB) | **159.8MB** | 3.14% | 2.36s(RTF 0.081) |
| fp32(95.1MB + 196.5MB) | 291.6MB | 3.03% | 2.42s(RTF 0.083) |

两条都与 Gate A/B/C 的经验相反,所以值得单独记:

- **fp32 只买回 0.11pp WER,要多付 132MB。** 这与 Gate A 完全不同 —— 那里 int8 会**破坏**说话人不变性
  (cost 0.1773 → 0.2789),fp16 是真兜底。这里 int8 的损失是**噪声级**,fp32 兜底没有意义。
  转写 int8 **确认锁定**,且不需要留 fp32 退路。
- **int8 几乎不省时间**(0.081 vs 0.083 RTF)。自回归解码器是内存带宽受限的,瓶颈在 51864×512 的
  embedding 表(fp32 就有 106MB,量化后仍是 decoder 130.7MB 的主体)而不是算力。
  **推论:如果设备上转写太慢,量化不是那根杠杆,换档位(`tiny.en`)才是。**

## 第三个发现:**包体估算错了,whisper 是 160MB 不是 70MB**

`docs/android-migration.md` §12 和 [[android-migration]] 记的都是 "whisper base.en int8 ~70MB(打包 APK)"。
实测 **159.8MB**,差 2.3 倍。原因是 decoder 量化率很低(196.5→130.7MB,仅 1.5×):token embedding 表
按 fp32 保留,它一项就占 106MB。

**连带两个后果:**
1. **首启下载 737MB → ~827MB,整包 ~897MB。**(wav2vec2 95.8 + espeak 302.9 + MMS 338.6 + whisper 159.8)
   上一版已经写了"接近可接受上限",现在是越过了。
2. **160MB 进不了 base APK。** Play 的 base APK 压缩后上限 150MB;install-time asset pack 上限 1.5GB
   但会算进安装体积。所以 whisper 从"打包 APK"改为**首启下载**,或走 asset pack —— 这条要落 PRD NFR-4②,
   不在本门内擅自决定。

## 分歧的结构:38 处差异逐条归类

判"有界"不能只看 3.14% 这个数,得看错在哪。38 处差异分三类:

**(a) 只是分词不同,字符相同 —— 11 处,而且金标准是难看的那一方:**

```
金标准 'U .S.'          sherpa 'U.S.'
金标准 'long -held'     sherpa 'long-held'      (另有 -considered / -running)
金标准 'the 250 ,000,'  sherpa '250,000,'
金标准 '5 -4.'          sherpa '5-4.'           (另有 6 -3. / 7-2)
金标准 "O 'Keefe."      sherpa "O'Keefe."
```

这是 **faster-whisper `word_timestamps` 的切词产物**,即 §4 发现⑤(Whisper 词时间戳不可靠)在
*文本*层面的同一个毛病 —— 它把 `U.S.` 切成 `U` + `.S.`。sherpa 侧更干净。
**顺带一个对 `:core-scoring` 的观察:** `golden/seg/` 的金标准里存在 `long -held` 这类 token,
是 faster-whisper 分词器造成的,**Android 永远不会产生这种形状**。这不影响
`SegmentationParityTest` 的有效性(它测的是 merge 函数,不是分词器),但金标准语料的 token 分布
与 Android 实际输入不同,记在这里以免日后误读。

**(b) 数字/百分号的书写规范 —— 4 处**(`seven`↔`7`、`%`↔`percent`)。两种都是对的读法。

**(c) 真实识别差异 —— 约 23 处**,全是局部替换/增删,**没有一处是整段崩坏**:
`because`→`As`、`some,`→`sum,`、`dissents`→(VAD 版才有的)`descents`、`You`→`I`、`What`→`But`、
删掉 `Congress` / `ago, or announced just`。
**其中有几处 sherpa 更对**:金标准 `Correspond,` 被截断,sherpa 给出完整的 `correspondent,`;
金标准 `gonna`,sherpa `going to`。
**所以这不是"Android 更差",是两个 int8 base.en 解码器在难音频上以 ~3% 的比例各自出错。**

## 决定(需要用户拍板的用 ❓标出)

> ⚠️ **决定 1 在当天晚些时候被推翻,替换方案见文末「补记」。** 其余决定不变。

1. ~~**参考路径改用 Whisper 长音频循环,不用 VAD 分段。**~~ **不可实现** —— v1.13.4 的 Android AAR
   不暴露 segment 时间戳。改为 **VAD 段合并成 29s 窗**(`vadwin`),见「补记」。
2. **转写文本不作为平台间的对等目标 —— 不设文本相等的门。** 三个理由:两个解码器的分歧不可消除
   (fp32 也只买 0.11pp);金标准自己在分词上更差;而分歧**不改变分数**——分数是学习者音频与
   *同一段* 参考音频的比较,参考切分不同只是给出**另一个同样有效的练习单元**,不是错的分数。
   `:core-scoring` 的金标准测试喂固定词表,不受影响。
3. **FR-11 已经自带防线,无需新增。** MDD 的 canonical 自拟合门控(增益 >0.05 就 `return ""`)正是
   为"文本/解码不可信"设计的:参考文本错时 canonical 拟合不上参考音频,诊断静默降级。
   这是既有设计吸收了一个当时没预见的风险,写下来以免日后有人"优化"掉这个门控。
4. ❓**建议:随包/随下载分发 `videos/*.sentences.json`,内置语料不在设备上转写。** 理由三重:
   (i) 内置语料的练习单元与 macOS **完全一致**(缓存已经存在,零成本);
   (ii) 省掉 636s 视频 × RTF 0.081 ≈ **52s 桌面级**、手机上数分钟的首次转写(NFR-3);
   (iii) 用户导入的视频(FR-M2)仍走端侧转写,NFR-1 不受影响。
   **这是产品行为的改变(内置素材的转写从"设备生成"变为"随包提供"),按流程需用户确认。**
5. ❓**whisper 从"打包 APK"改为首启下载或 asset pack**,并把 NFR-4② 的包体数字改为 ~827MB 首启下载。
   需落 PRD。

## 没做的事

- **设备侧未测**。以上全部在 macOS arm64 + PyPI `sherpa-onnx==1.13.4` 上测得。Android AAR 是同一份
  C++ 实现,但 arm64 手机的 int8 kernel 可能与桌面不同(与 R-5/R-6/R-7 同一个待办)。
- **只有一段语料**(636s / 1944 词 / 单一新闻域)。单一素材足以证明"分歧是局部替换而非系统性错误",
  不足以给出 WER 的置信区间。语料扩充与 Tier 3 设备复测一并做。
- **`condition_on_previous_text` 的贡献量不明**(见上)。

---

## 补记(同日,写 `:core-asr` 之前)——**决定 1 落不了地,换第四种策略**

上面的三种策略都是在 **PyPI 的 `sherpa-onnx`** 上量的。开始写 Kotlin 适配层时先去核对 AAR 的 API,
结果长音频循环**在 Android 上根本写不出来**:

- `javap` 反编译 v1.13.4 AAR 里的 `OfflineRecognizerResult`,字段只有
  `text / tokens / timestamps / durations / lang / emotion / event` —— **没有 `segmentTimestamps`**,
  尽管 `OfflineRecognizerConfig` 里那个 `enableSegmentTimestamps` 开关是有的。**Kotlin binding 落后于
  Python binding**,开关开了也读不回来。
- 两条退路都是死的:**v1.13.4 已经是最新 release**(不是我们用了旧版);**token 级时间戳恒为空** ——
  现成的 base.en 模型没有导出 cross-attention 输出,`timestamps` 返回空数组,没法拿它近似 segment 边界。
- 从源码构建 sherpa-onnx 能解决,但那是把 `:core-asr` 从"贴一个 AAR"变成第二个 NDK 构建工程
  (`:core-audio` 的 FFmpeg 已经有一个),为 0.9pp WER 不值。**等 `:core-audio` 的 NDK 工具链搭好之后
  再回来重估。**

**所以约束是:Android 侧只拿得到 `r.text`。** 在这个约束下重新找策略,量了第四种:
**用 VAD 找语音段,再把相邻段贪心合并成 ≤29s 的连续窗**(不是拼接,窗内含段内静音)。

| 切块策略 | 词数 | 归一化 WER | 标点分歧 | 练习单元(金标准 159) | Android 可行 |
|---|---|---|---|---|---|
| Silero VAD 分段(§4 原选型) | 1937 | 5.56% | 3.17% | 172 | ✅ |
| 固定 29s 窗 | 1879 | 5.56% | 1.25% | 162 | ✅ |
| Whisper 长音频循环 | 1926 | **3.14%** | **1.01%** | 162 | ❌ **AAR 没有 segment 时间戳** |
| **VAD 段合并成 29s 窗**(`vadwin`) | 1939 | **4.01%** | **1.65%** | **158** | ✅ |

**`vadwin` 过本门的全部三条判据**(4.01% ≤5%、1.65% ≤2%、158 vs 159 = −0.6%),而且**练习单元数是四种
里最接近金标准的一种** —— 比长音频循环还近(158 vs 162)。这是巧合,不是它更好:两者都在 ±5% 带内,
差别在噪声里。**别把 158 当成"比 3.14% 那条更优"的理由** —— WER 上它确实差 0.87pp。

它为什么比另外两种 text-only 策略好,机制上是清楚的:**切口既少又落在静音里**。77 个 VAD 段合并成
27 个窗,切口数比 VAD 分段少 2.8 倍;而每个切口都在 VAD 判定的静音处,不像固定窗那样切在词中间
(固定窗丢了 65 个词)。**Gate F 结论(PASS)不变,变的是实现路径。**

**顺带发现:`max_speech_duration = 25.0` 是个建议值,不是约束。** 77 个 VAD 段里有两个超过 29s
(29.91s / 30.17s),其中一个超过 30s,被 sherpa 静默截断 —— 636s 里丢了 **0.166s**(0.03%),
上面的 4.01% 已经包含这点损失。合并**不会**造出超长窗(边界是相对窗首判的),所以超长窗只可能是
单个超长 VAD 段直通。`AsrWindowPlanner.overlong()` 把这种窗报出来给 `:core-asr` 记日志 ——
**C++ 那句警告在 Android 上没人看得见。**

### 这件事对模块划分的影响(是好事)

切口位置决定练习单元切分,所以**切块逻辑属于 `:core-scoring`**,不属于 `:core-asr` ——
落为 `segment/AsrWindowPlanner.kt`(纯 Kotlin,零 Android 依赖),金标准
`golden/asr/vadwin_trace.json`(实测那次运行的 77 个 VAD 段 → 27 个窗),
`AsrWindowPlannerParityTest` 6 项断言逐窗精确比对,`:core-scoring:test` **48/48 绿**。

这么划之后 **`:core-asr` 里没有值得测的东西了** —— 它只剩"喂 VAD、按给定边界调 recognizer、收 text"。
本来担心的"`:core-asr` 没有 JVM 对齐故事"因此不成立:**需要对齐的部分不在 `:core-asr` 里。**

### 待办(不阻塞 Phase 2)

- **`:core-audio` 的 NDK 工具链就绪后**,重估从源码构建 sherpa-onnx(拿回 segment 时间戳 → 长音频
  循环 → 4.01% 回到 3.14%)。或上游 Kotlin binding 补上这些字段后直接升版本。
- **`max_speech_duration` 为何不生效**没有深究(0.03% 的损失不值得)。若日后语料里出现更长的连续
  语音,先看 `overlong()` 的日志。
