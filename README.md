# NativeLingo

英语口语**跟读评估**桌面应用。学习者跟读一段参考英语音频,软件对比两段音频,指出**发音准确度**与**流畅度**上的缺陷并给出改进建议。

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
- 语音/ML:torch · transformers(wav2vec2) · librosa · praat-parselmouth

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

## 后续

- 把 `feedback.llm_hook` 接到本地 Qwen2-Audio 生成更丰富的教学反馈
- 用 WhisperX 强制对齐 + GOP 音素级打分,把问题区间定位到具体单词/音素
- PyInstaller 冻结后端为独立 sidecar 二进制,实现真正可分发的 `.dmg`
