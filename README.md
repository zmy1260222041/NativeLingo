# NativeLingo

英语口语**跟读评估**桌面应用。学习者跟读一段参考英语音频,软件对比两段音频,指出**发音准确度**与**流畅度**上的缺陷并给出改进建议。

> 当前公开版本 **v0.5.0**(2026-07-25)——**首个可分发预览版**(.dmg;前端尚未打磨,1.0 留待前端优化后)。近期演进:
> - **Android v0.7.0**(2026-08-03)——安卓端跟读模块迁移云端(Duolingo 式评分,自建服务器 `server/`,含 **FR-11 音素诊断**),识物模块保持全本地;APK 缩至 ~270MB。见 [NativeLingoAndroid/README.md](NativeLingoAndroid/README.md)。
> - **v0.5.0**:首个可分发 macOS `.dmg`(PyInstaller 冻结后端 + Tauri 打包 + ad-hoc 签名);普通用户见下方[下载与安装](#下载与安装)。
> - **v0.4**:音素级替换诊断(FR-11,MDD)——对 weak/bad 词给出"/θ/ 读成了 /s/"式诊断,三重门控保证「宁缺毋滥」。
> - **v0.3**:真实新闻播报域全链路验证 + 长句在从句边界二级切分 + 学习者词采样级回放。
> - **v0.2**:中层 SSL 编码器(6–9 层)+ speechocean762 拟合的 isotonic 校准。
>
> 完整版本演进与技术特点见 [CHANGELOG.md](CHANGELOG.md)。

## 下载与安装

> 面向**普通用户**。开发者从源码运行见下方[运行](#运行);从源码构建 .dmg 见[打包](#打包构建-dmg)。

1. **下载**:到本仓库的 **Releases** 页下载 `NativeLingo_<版本>_aarch64.dmg`(约 380MB)。
2. **安装**:打开 `.dmg`,把 NativeLingo 拖入「应用程序」。
3. **首次打开**(应用未公证,Gatekeeper 会提示一次,二选一,仅一次):
   - 访达里**右键 NativeLingo → 打开 → 确认**(最简单);或
   - 终端:`xattr -dr com.apple.quarantine /Applications/NativeLingo.app`
4. **转写模型(whisper base.en)已预装**——选视频转写无需联网。分析所需的对齐/音素模型(MMS ~1.2GB + 音素 ~2.4GB)在**应用启动后后台预下载**并显示进度(通常选片+跟读时就下完),之后**完全离线**。应用**每次启动**需约 1-3 分钟加载本地引擎,属正常。
5. **素材**:把你的英语视频(新闻播报、演讲、访谈等)放入 `~/Library/Application Support/com.nativelingo.app/videos/`,应用内即可选片跟读。

**系统要求**:macOS 13+(Apple Silicon;Intel Mac 暂不支持)。麦克风权限在首次录音时授权。

## 核心思路:从语音克隆原理"逆向"评估

现代语音克隆 / 表现力 TTS 之所以可行,是因为模型内部学到了一个**解耦潜空间**,把语音拆成「内容 / 说话人音色 / 韵律」三类独立因子:

```
克隆:   (内容, 参考韵律, 新音色)  →  波形
评估:   学习者波形  →  (内容偏差, 韵律偏差)   ※ 主动剔除音色因子
```

两者共享同一层表示。NativeLingo 不训练 TTS,而是直接复用**支撑这种能力的自监督语音表示(wav2vec2 / WavLM)**:把参考和学习者音频编码进同一空间 → DTW 对齐 → 归一化掉音色 → 逐帧测内容与时间偏差。

## 三条轨道

| 轨道 | 作用 | 实现 |
|------|------|------|
| **B(核心)** | SSL 潜空间逆向评估 | `ssl_encoder` → `speaker_norm` → `align`(DTW) → `score_b` |
| **A(辅助)** | 韵律校准锚点(F0/能量/停顿/语速) | `prosody`(Parselmouth) |
| **C(反馈)** | 把客观指标翻译成教学建议 | `feedback`(规则引擎,预留 LLM 钩子) |

设计原则:**LLM 不打分,只生成反馈** —— 研究表明 Audio-LLM 直接评分不稳、易受先验干扰。

## 技术栈

- 桌面壳:Tauri v2(Rust)
- 后端:Python + FastAPI,作为本地 sidecar(绑定 `127.0.0.1` + 每次启动随机 token)
- 前端:原生 HTML/JS + Web Audio 录音
- 语音/ML:torch · torchaudio(MMS 强制对齐) · transformers(wav2vec2 编码 + espeak-cv-ft 音素 MDD) · faster-whisper(转写) · librosa · praat-parselmouth

## 运行

```bash
# 1. Python 环境
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. 后端(单独验证)
.venv/bin/python -m backend.main      # http://127.0.0.1:8756

# 3. 桌面应用(自动拉起后端)
npx tauri dev

# 测试
.venv/bin/python -m pytest backend/tests/ -v
```

## 打包(构建 .dmg)

发布用 `.dmg` 由 `scripts/build_dmg.sh` 一键构建:PyInstaller 冻结后端(`backend/freeze.spec`,`--onedir`)→ 暂存进 Tauri 资源 → `tauri build --bundles app` → 逐文件 ad-hoc 签名 → `hdiutil` 出 ULFO 压缩 dmg。**视频/音频解码走 PyAV(`av`,随 faster-whisper 已在冻结包内),不依赖 ffmpeg CLI**——干净 Mac 零额外依赖。

```bash
scripts/build_dmg.sh
```

产物:`src-tauri/target/release/bundle/dmg/NativeLingo_<版本>_aarch64.dmg`(~560MB,含预装的 whisper base.en)。

**体积优化(已固化进脚本)**:干净 `.venv-freeze` 冻结(排除 datasets/pyarrow 等脚本依赖;**onnxruntime 必留**——faster-whisper VAD 要用)、ULFO(LZMA)压缩、从**仅 `.app` 的干净 staging** 成像(避免 Tauri 残留的 `rw.*.dmg` 污染源目录致 3x 虚胖)、**逐文件 ad-hoc 重签**(`codesign --deep` 漏签 PyInstaller 深层 `.so`/`.dylib` 会致无日志崩溃)。曾用 `strip -x` 省体积,但它破坏部分 `.dylib` 签名("Invalid Page")、干净 Mac 启动即崩,已移除。

**可选:公证**(让用户免右键绕过):设 `DEVELOPER_ID_APPLICATION` 与 `NOTARY_KEYCHAIN_PROFILE` 环境变量后重跑脚本,即自动走签名 + `notarytool` 公证 + `stapler` 装订。

## 验证设计

测试 `backend/tests/test_track_b.py` 把产品假设编码成可执行断言,其中最关键的是
`test_speaker_invariance`:**两个不同嗓音读同一句正确文本必须仍得高分** —— 这是
逆向思路成立(音色被成功剔除)的试金石。

## 改进方向

> NativeLingo 属于发音评估四大流派中的 **D 派(SSL + DTW 参照比较)**:用 SSL 嵌入做 DTW,以距离度量发音差异,无需任何标注数据。最接近的文献是 Richter & Gudnason 2023(wav2vec2 + DTW,几乎就是本方法的学术版)与 Yue et al. 2017(shadowing + DTW,同场景),论文 PDF 见 `reference/`。

逐维度对比当前实现与领域做法(🔴 高优先 / ⚠️ 中 / ✅ 已稳健 / 🟢 优势):

| 维度 | 当前实现 | 领域常见做法 | 评价 → 改进方向 |
|---|---|---|---|
| **编码器** | `wav2vec2-base-960h`,**6–9 层平均**(v0.2,`ssl_encoder.py`) | Kim 2022:大模型 + CTC 微调 + 加权多层;Richter/Pasad:中层最优 | ✅ v0.2 实测选定(`scripts/layer_comparison.py`):不变性/区分度双优;可选 large / xls-r |
| **去音色** | embedding 上 CMVN(`speaker_norm.py`) | Bartelds/Richter:长度归一化 DTW cost + 余弦 | ✅ CMVN + 余弦廉价稳健 |
| **对齐** | 带状 DTW(`band_frac=0.2`)+ 余弦(`align.py`) | 标准 DTW;Richter 用 length-normalized DTW | ✅ 与 SOTA 一致 |
| **打分映射** | **isotonic 校准**(v0.2):speechocean762 真人分拟合,`calibration.json` 随代码分发(`score_b.py`) | D 派用距离/阈值;C 派训回归头到人工分(PCC ~0.82) | ✅ v0.2 解决"阈值靠猜"(PCC 0.60 / 0.43);下一步真实原声重拟合逼近 C 派 |
| **Fluency** | **isotonic GAM**:路径偏离 + 速率 + 停顿单调融合(v0.2,`score_b.py`) | SpeechRater 式特征:停顿次数/时长、语速、犹豫 | ✅ v0.2 去掉 `rate_penalty` 重复计算;逐特征单调,停顿/偏速永不加分 |
| **句子切分** | faster-whisper 句切分 + 长句从句边界二级切分(v0.3,>8s 或 >20 词) | 多数系统按标点切 | ✅ v0.3 新闻长句 105→164 句,最长 22s→7.66s |
| **定位** | DTW 路径投影到转录网格(`detail.py`);MMS 词边界(v0.1) | GOP/MDD 用强制对齐;Richter 同样用路径投影 | ✅ 与 Richter 一致 |
| **反馈** | 逐词韵律 diff(重音/时长/音高/连读)+ **音素替换诊断**(v0.4) | MDD 给音素替换诊断;多数系统只给分数不给建议 | 🟢 **最强差异化点**:v0.4 下探到"/θ/→/s/"音素级 |
| **A/B 回放** | 原声 + 学习者均后端精确切 WAV,采样级一致(v0.3) | 多数系统不支持逐词 A/B | 🟢 独有 |
| **参考** | 单条参考(视频原声) | Richter:参考集(native + non-native);GOP 用音素声学模型 | ⚠️ 单参考受说话人口音/习惯主导(相对 DTW 已降级,见行动项) |
| **音素级诊断** | **假设打分式 MDD**(v0.4,`phoneme.py`):解码参考定 canonical → 学习者 Viterbi 打分 → 替换/删除假设竞争;三重门控 | GOP / 音素声学模型 | ✅ v0.4 已实现(think→sink 精准锁定 /θ/),宁缺毋滥 |
| **内容串扰** | DTW 距离混了"发音差"与"说错词" | MDD/GOP 能区分 | ⚠️ 现以 `cover_ratio<0.35 → missed` 部分缓解 |

据此排出行动项(v0.1 词边界;v0.2 校准/选层/fluency;v0.3 新闻域 + 长句切分 + 采样级回放;v0.4 音素 MDD):

1. ~~**校准打分**~~ —— ✅ v0.2。**后续高 ROI:用真实人声原声(非 TTS)重拟合校准**,逼近 C 派精度。
2. ~~**相对 DTW(双参考集)**~~ —— ⬇️ **v0.2 fit-review R-2 降级**:经典相对 DTW 需"同文本 native + L2 参考集",与"任意网络视频"(FR-M1)冲突。若单参考口音问题真实出现,备选为**多 TTS 声正则**(对任意文本可行,不替换真实原声)。
3. ~~**编码器选层**~~ —— ✅ v0.2(末层 → 6–9 层平均,实测双优)。可选:对比 large / xls-r。
4. ~~**音素级诊断**~~ —— ✅ v0.4(假设打分式 MDD + 三重门控)。
5. **超长选段 MPS OOM**(P2)—— wav2vec2 编码 ~7 分钟连续选段触发内存上限(正常使用 ≤数句不受影响)→ 分块滑窗编码或前端限长。
6. **工程收尾** —— `feedback.llm_hook` 接本地 LLM 生成更丰富教学反馈;PyInstaller 冻结后端为 sidecar 二进制,产出可分发 `.dmg`。
