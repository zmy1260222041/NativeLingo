# R-35 — 美国 TTS 与 2D 口语闭环

需求：FR-46 口语闭环及美国 API 补充。分支：`codex/stranger-2d-dialogue`。结论：本轮工程验收通过；没有提交或推送。

## 产品行为

成长页选择单词，听准确单词示范，可重听；V 开始录音、再按 V 结束。评分达到原阈值后进入 spoken，再到商店按真实需求开口，真实模型评分后进入 used。没有教学式纠错或假分数，失败免费重试。小剧场只观察已经呈现的句子，不预先解锁未来词汇。

商店先听角色招呼，再录音回答；泛类 food 请求保持对话，明确要 taco 后，NPC 具名交付并真正播放结束才结算。物资仍经过原领域规则，可打包和消耗。语音在线时手势不能替代正常交谈领奖。

## 修复

- 默认语音后端改为 xAI 美国 us-east-1，NPC 日常、招呼、单词示范与动态回复均走同一后端。五个角色使用已核验的系统声音，24kHz/mono/16-bit PCM 转有效 WAV，限制体积、奇数字节和错误响应，错误不回退到北京端点。
- 保留 `STRANGER_TTS_PROVIDER=qwen` 作为显式旧版调试配置，默认不使用。xAI 密钥继续只在服务器，通过已有 XAI.csv/环境读取；TTS 仅接收服务器已知文字，不接收玩家音频。
- 修复原迁移中缺失/不匹配的社会对白配音 ID、无单词示范、录音误采集 NPC 配音、空转写等待、评分先到即丢弃待收流音频、旧 Qwen 磁盘缓存混用。
- Gemini 已用真实生成检查恢复。2D 请求要求真实模型响应，不能静默用 stub 的模拟地道度结算；状态检查区分本地进程、配置与模型可用，设置提供重查。
- `game/run_novel.command` 自动启动本地语音后打开独立应用。专用导出补上 `NSMicrophoneUsageDescription`，避免编辑器有录音声明但独立包缺失。

## 实际证据

| 验收 | 结果 | 证据 |
|---|---|---|
| 美国 TTS 五角色有效音频 | 5/5 HTTP 200，24kHz/mono/16-bit，完整音频就绪 610–810ms | `speaking_us_2026-09-11/voice-probes.json` |
| 真实录音链路 | 2D record 按钮 → AudioEffectRecord → finish_recording WAV 上传 → Whisper/DTW；输入注入静音录音总线 | `speaking_us_2026-09-11/live-speaking.log` |
| 词汇闭环 | water 示范只 heard；实际 DTW 65.2 后 spoken；实际 Gemini 对话后 used | 同上 |
| 水需求交谈 | “may i have some water please” → “Sure thing, I can get you that water.”；实际播放开始 1338ms | 同上 |
| 多轮餐摊 | “can i have some food please” → 介绍 burgers/tacos/pizza，不发物资；第二轮 “I'll take a taco to go, please.” → “Sure thing, here is your taco.”，播放开始 1336ms，播完才发 | 同上 |
| 奖励可使用 | 音频播放前数量不变；结束后柜台产生物资，可打包、可消耗 | 同上 |
| 非目标语音 | 食物请求送入 water 词级评分：33.3、accepted=false，不推进习得 | 当次真实 `/score_word` 探测 |
| Python | 126 tests passed；包括美国端点、PCM 完整性、无北京回退、完整音频才缓存、目录文字一致、禁止假模型成交 | `speaking_us_2026-09-11/python-regression.log` |
| Godot 回归 | Novel、NpcVoice、WordPractice、WordAcquisition、VoiceTargetCancel 通过 | 同目录对应日志 |
| 独立 macOS | 专用预设导出通过，独立二进制启动无脚本错误，麦克风用途说明存在 | `export-smoke.log`、`export-privacy.txt` |

可移植联调命令另一次实跑也全部通过，水请求/第二轮 taco 的实际开口为 1402/1364ms，记录在 `speaking_us_2026-09-11/portable-live-probe.log`。

真实服务指 Whisper、SSL/DTW、Gemini、xAI 均实际调用。测试输入是参考/合成 WAV，经游戏录音效果器录入；不是一名真人对着物理麦克风完成的口音评测，不据此声称所有设备/口音通过或公网延迟具有 SLA 保证。首次实际录音仍由用户授予 macOS 麦克风权限。

## 复现

```sh
# 从仓库根目录启动本地语音与游戏
./game/run_novel.command
# 真实 API、音频录入、多轮交谈、可用奖励与词汇闭环（不读取玩家存档）
.venv/bin/python game/speech_service/probe_novel_live.py
# 离线回归
.venv/bin/python -m unittest discover -s game/speech_service -p 'test_*.py'
/Applications/Godot-4.6.app/Contents/MacOS/Godot --headless --path game res://tests/NovelTest.tscn
```

配音样本：`speaking_us_2026-09-11/tavi-us-sample.wav`。

当前官方依据：[xAI TTS API](https://docs.x.ai/developers/model-capabilities/audio/text-to-speech)、[us-east-1 区域](https://docs.x.ai/developers/models/text-to-speech)、[Godot macOS 录音导出要求](https://docs.godotengine.org/en/4.7/tutorials/export/exporting_for_macos.html)。Context7 工具不可用，使用官方资料并以 Godot 4.6.3 的实际导出包复核。
