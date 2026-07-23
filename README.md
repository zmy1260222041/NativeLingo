# NativeLingo

英语口语**跟读评估**桌面应用。学习者跟读一段参考英语音频,软件对比两段音频,指出**发音准确度**与**流畅度**上的缺陷并给出改进建议。

> 当前版本 **v1.4**(2026-07-23)。近期演进:
> - **v1.2**:SSL 编码器改用中层平均(6–9 层,说话人不变性 +13%、错文区分度 +38%);打分映射改为 speechocean762 拟合的 isotonic 校准(留出验证 PCC:accuracy 0.46→0.60、fluency 0.11→0.43);移除 fluency 重复计算。
> - **v1.3**:真实新闻播报域全链路验证(whisper base.en 够用、MMS 对齐鲁棒、端到端零误报 → FR-M2 解锁);长句在从句边界自动二级切分(105→164 句);学习者词回放改走后端精确切 WAV(采样级精确)。
> - **v1.4**:音素级替换诊断(FR-11,MDD)——对 weak/bad 词给出"/θ/ 读成了 /s/"式诊断,三重门控保证「宁缺毋滥」。
>
> 完整版本演进与技术特点见 [CHANGELOG.md](CHANGELOG.md)。

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

## 验证设计

测试 `backend/tests/test_track_b.py` 把产品假设编码成可执行断言,其中最关键的是
`test_speaker_invariance`:**两个不同嗓音读同一句正确文本必须仍得高分** —— 这是
逆向思路成立(音色被成功剔除)的试金石。

## 改进方向

> NativeLingo 属于发音评估四大流派中的 **D 派(SSL + DTW 参照比较)**:用 SSL 嵌入做 DTW,以距离度量发音差异,无需任何标注数据。最接近的文献是 Richter & Gudnason 2023(wav2vec2 + DTW,几乎就是本方法的学术版)与 Yue et al. 2017(shadowing + DTW,同场景),论文 PDF 见 `reference/`。

逐维度对比当前实现与领域做法(🔴 高优先 / ⚠️ 中 / ✅ 已稳健 / 🟢 优势):

| 维度 | 当前实现 | 领域常见做法 | 评价 → 改进方向 |
|---|---|---|---|
| **编码器** | `wav2vec2-base-960h`,**6–9 层平均**(v1.2,`ssl_encoder.py`) | Kim 2022:大模型 + CTC 微调 + 加权多层;Richter/Pasad:中层最优 | ✅ v1.2 实测选定(`scripts/layer_comparison.py`):不变性/区分度双优;可选 large / xls-r |
| **去音色** | embedding 上 CMVN(`speaker_norm.py`) | Bartelds/Richter:长度归一化 DTW cost + 余弦 | ✅ CMVN + 余弦廉价稳健 |
| **对齐** | 带状 DTW(`band_frac=0.2`)+ 余弦(`align.py`) | 标准 DTW;Richter 用 length-normalized DTW | ✅ 与 SOTA 一致 |
| **打分映射** | **isotonic 校准**(v1.2):speechocean762 真人分拟合,`calibration.json` 随代码分发(`score_b.py`) | D 派用距离/阈值;C 派训回归头到人工分(PCC ~0.82) | ✅ v1.2 解决"阈值靠猜"(PCC 0.60 / 0.43);下一步真实原声重拟合逼近 C 派 |
| **Fluency** | **isotonic GAM**:路径偏离 + 速率 + 停顿单调融合(v1.2,`score_b.py`) | SpeechRater 式特征:停顿次数/时长、语速、犹豫 | ✅ v1.2 去掉 `rate_penalty` 重复计算;逐特征单调,停顿/偏速永不加分 |
| **句子切分** | faster-whisper 句切分 + 长句从句边界二级切分(v1.3,>8s 或 >20 词) | 多数系统按标点切 | ✅ v1.3 新闻长句 105→164 句,最长 22s→7.66s |
| **定位** | DTW 路径投影到转录网格(`detail.py`);MMS 词边界(v1.1) | GOP/MDD 用强制对齐;Richter 同样用路径投影 | ✅ 与 Richter 一致 |
| **反馈** | 逐词韵律 diff(重音/时长/音高/连读)+ **音素替换诊断**(v1.4) | MDD 给音素替换诊断;多数系统只给分数不给建议 | 🟢 **最强差异化点**:v1.4 下探到"/θ/→/s/"音素级 |
| **A/B 回放** | 原声 + 学习者均后端精确切 WAV,采样级一致(v1.3) | 多数系统不支持逐词 A/B | 🟢 独有 |
| **参考** | 单条参考(视频原声) | Richter:参考集(native + non-native);GOP 用音素声学模型 | ⚠️ 单参考受说话人口音/习惯主导(相对 DTW 已降级,见行动项) |
| **音素级诊断** | **假设打分式 MDD**(v1.4,`phoneme.py`):解码参考定 canonical → 学习者 Viterbi 打分 → 替换/删除假设竞争;三重门控 | GOP / 音素声学模型 | ✅ v1.4 已实现(think→sink 精准锁定 /θ/),宁缺毋滥 |
| **内容串扰** | DTW 距离混了"发音差"与"说错词" | MDD/GOP 能区分 | ⚠️ 现以 `cover_ratio<0.35 → missed` 部分缓解 |

据此排出行动项(v1.1 词边界;v1.2 校准/选层/fluency;v1.3 新闻域 + 长句切分 + 采样级回放;v1.4 音素 MDD):

1. ~~**校准打分**~~ —— ✅ v1.2。**后续高 ROI:用真实人声原声(非 TTS)重拟合校准**,逼近 C 派精度。
2. ~~**相对 DTW(双参考集)**~~ —— ⬇️ **v1.2 fit-review R-2 降级**:经典相对 DTW 需"同文本 native + L2 参考集",与"任意网络视频"(FR-M1)冲突。若单参考口音问题真实出现,备选为**多 TTS 声正则**(对任意文本可行,不替换真实原声)。
3. ~~**编码器选层**~~ —— ✅ v1.2(末层 → 6–9 层平均,实测双优)。可选:对比 large / xls-r。
4. ~~**音素级诊断**~~ —— ✅ v1.4(假设打分式 MDD + 三重门控)。
5. **超长选段 MPS OOM**(P2)—— wav2vec2 编码 ~7 分钟连续选段触发内存上限(正常使用 ≤数句不受影响)→ 分块滑窗编码或前端限长。
6. **工程收尾** —— `feedback.llm_hook` 接本地 LLM 生成更丰富教学反馈;PyInstaller 冻结后端为 sidecar 二进制,产出可分发 `.dmg`。
