# R-26 · 柜台对答改 Gemini 3.7 Flash(2026-08-21)

> 需求来源:玩家要求柜台台词更像美国人说话,并改用 Gemini。对照榜单与本机测速后,主模型从 grok-4.3 改为 `gemini-3.7-flash`。落库为 **FR-41 / NFR-8 / NFR-9**。

## 1. 范围

- **改**:`POST /game/dialogue` 在配置了 Gemini key 时调用 `gemini-3.7-flash` `thinkingLevel=LOW`;超时约 2 秒、HTTP 429/503 或失败时 stub 开口,不再排队重试;有 Gemini key 时不调用 Grok。
- **不改**:发音分仍来自转写;成交发档仍走 FR-28;Godot 仍只发转写与 `reply_id`;无 key 时 stub 仍可离线成单。
- **降级**:超时开口用 stub 台词与 stub 地道分,不扣状态。

## 2. 本机对照(同一句 `Can I get a burger to go?`)

| 模型 | 成功延迟 | 开口 | 成交 |
|---|---|---|---|
| grok-4.3 `none` | 1.74 / 1.84 s | “Burger to go?” | 否 |
| gemini-3.7-flash `LOW` | 1.68 / 1.88 / 5.11 / 7.92 s | “Sure thing, one burger to go! Here you are, enjoy.” | 是 |

Gemini 口吻更好,但有 503 高峰与 Free 档 429。NFR-9 仍靠 stub 守 3 秒,不能空等。

## 3. 门控判据

- **G1** Godot / PCK 不含 `GEMINI_API_KEY` / `GOOGLE_API_KEY` / `XAI_API_KEY`。
- **G2** 发给 Gemini 的请求只有转写、角色卡、最近 8 轮;payload 不含 wav/audio/base64。
- **G3** 请求体 `generationConfig.thinkingConfig.thinkingLevel` 必须是 `LOW`(`minimal` 会报错)。
- **G4** 超时 / 429 / 503 返回 stub,HTTP 层不 503 给 Godot。
- **G5** 同时存在 Gemini 与 xAI key 时只打 Gemini。

## 4. 实现后回填

- `game.speech_service.test_dialogue`:Gemini 请求体、超时 stub、Gemini 优先于 Grok、Godot 脚本无云端对话 key。
