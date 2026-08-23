# R-25 · 柜台开口 ≤ 3 秒(2026-08-20)

> 需求来源:玩家松键后等待 NPC 开口过久,会当成失败并走开。落库为 **NFR-9**,并收紧 **FR-41** 的开口时延。

## 1. 范围

- **改**:`POST /game/dialogue` 对 `grok-4.3` 发送 `reasoning_effort=none`;Grok 超过 1 秒或失败时用 stub 开口,不再 503;对话 JSON 返回后预取 TTS;日志增加 `tts_ms`。
- **不改**:模型仍是 `grok-4.3`(不换 4.6 / Voice);发音分仍来自转写;成交发档仍走 FR-28;Godot 仍只发转写与 `reply_id`。
- **降级**:超时开口用 stub 台词与 stub 地道分,不扣状态。

## 2. 实测瓶颈(改前)

本机预热后两次柜台轮次:

| 步骤 | 实测 | 占比 |
|---|---|---|
| `POST /transcribe` fast Whisper | 428 ms | ~5% |
| `POST /game/dialogue` grok-4.3 默认推理 | 7163 / 8050 ms | ~90% |
| `POST /game/tts` DashScope | 未计时,排在 Grok 之后 | 其余 |

串行总和远超 3 秒。转写已经够快。Grok 默认 `reasoning_effort=low` 才是墙钟。

## 3. 门控判据

- **G1 归因**。开口慢必须能从服务日志拆成 `fast=1 ms=` / `grok_ms=` / `tts_ms=`,不得把 TTS 或 HUD 时钟当成根因。
- **G2 关推理**。发给 xAI 的柜台请求在 `grok-4.3` 上必须带 `reasoning_effort=none`。单测断言请求体。
- **G3 不空等**。Grok 超时或 HTTP 失败时 `generate_dialogue_reply` 返回 stub,不抛 503,Godot 不得因此再等一轮。本机 `reasoning_effort=none` 仍要 3647 ms,必须靠 stub 才能进 3 秒。
- **G4 预热验收**。Whisper 已 ready 后,从松键到 `line_audio_ready` 目标 ≤ 3 秒;若 Grok 仍慢,stub 必须先开口。

## 4. 实现后回填

- `game.speech_service.test_dialogue`:请求体含 `reasoning_effort=none`、timeout 1.0s、Grok `URLError` 回 stub。
- 真 xAI 墙钟与 TTS 毫秒待本机重启服务后从日志回填。
