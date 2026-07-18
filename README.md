# NativeLingo

英语口语**跟读评估**桌面应用。学习者跟读一段参考英语音频,软件对比两段音频,指出**发音准确度**与**流畅度**上的缺陷并给出改进建议。

> 当前版本 **v1.1**(2026-07-08):词边界改用 torchaudio MMS 强制对齐,原声词 / 学习者词回放不再被截断。版本演进与完整技术特点见 [CHANGELOG.md](CHANGELOG.md)。

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
- 语音/ML:torch · torchaudio(MMS 强制对齐) · transformers(wav2vec2) · faster-whisper(转写) · librosa · praat-parselmouth

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
| **编码器** | `wav2vec2-base-960h`,默认最后一层(`ssl_encoder.py`) | Kim 2022:大模型 + CTC 微调 + 加权多层;Richter/Pasad:中层最优 | ⚠️ 末层 + base 不是发音最优表征 → 改用中层(如第 13–16 层)或加权多层,几乎零成本提精度 |
| **去音色** | embedding 上 CMVN(`speaker_norm.py`) | Bartelds/Richter:长度归一化 DTW cost + 余弦;或微调压制 speaker | ✅ CMVN + 余弦合理且廉价,但不如相对 DTW 鲁棒 |
| **对齐** | 带状 DTW(`band_frac=0.2`)+ 余弦(`align.py`) | 标准 DTW;Richter 用 length-normalized DTW | ✅ 选择稳健,与 SOTA 一致 |
| **打分映射** | 路径平均余弦距离 → 手工线性映射(0.10→100, 0.55→0,`score_b.py`) | D 派直接用距离/阈值;C 派训回归头到人工分(PCC ~0.82) | 🔴 **最弱环节**,阈值是猜的、绝对分未校准 → 用 speechocean762 拟合 isotonic 回归替换 `_lin_map` |
| **Fluency** | DTW 路径偏离对角线 + 语速惩罚(`score_b.py`) | SpeechRater 式特征:停顿次数/时长、语速、犹豫 | ⚠️ 路径几何做 fluency 较少见;语速惩罚与路径偏离**重复计算** → 去掉 `rate_penalty` 或改用停顿/语速特征 |
| **定位** | DTW 路径投影到转录网格(`detail.py`) | GOP/MDD 用强制对齐;Richter 同样用路径投影 | ✅ 技巧正确,与 Richter 一致 |
| **反馈** | 逐词韵律 diff:重音/时长/音高/连读(`word_diff.py`) | MDD 给“音素替换诊断”;多数系统只给分数不给建议 | 🟢 **最强、最稀缺的差异化点,应放大** |
| **参考** | 单条参考(视频原声) | Richter:参考集(native + non-native);GOP 用音素声学模型 | ⚠️ 单参考会被该说话人口音/习惯主导 → 引入相对 DTW(双参考集) |
| **音素级诊断** | 词边界已有(v1.1 MMS 对齐),无音素诊断 | MDD 家族:能说“/θ/ 发成了 /s/” | ⚠️ 仍缺音素替换诊断 → wav2vec2 + CTC 头做 MDD,定位到音素 |
| **内容串扰** | DTW 距离混了“发音差”与“说错词” | MDD/GOP 能区分 | ⚠️ 现以 `cover_ratio<0.35 → missed` 部分缓解 |

据此排出行动项(v1.1 已落地第 4 项的词边界部分,见 [CHANGELOG.md](CHANGELOG.md)):

1. **校准打分**(最高 ROI)—— speechocean762 上跑现有 pipeline,用 isotonic 回归拟合距离→人工分,替换 `score_b.py` 的手工 `_lin_map`。
2. **相对 DTW** —— 预算一个小参考库(native + L2),取 Richter 差和比 `(Cost_other − Cost_std)/(Cost_other + Cost_std)`,提升 speaker-independence,仍零标注。
3. **编码器选层/换模型** —— `ssl_encoder.py` 取中层或加权多层,对比 large / xls-r。
4. **音素级诊断**(可选轨)—— 词边界已由 v1.1 MMS 强制对齐提供;仍缺音素替换诊断 → wav2vec2 + CTC 头做 MDD,定位到音素。
5. **工程收尾** —— 把 `feedback.llm_hook` 接本地 Qwen2-Audio 生成更丰富的教学反馈;PyInstaller 冻结后端为独立 sidecar 二进制,实现真正可分发的 `.dmg`。
