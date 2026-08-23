# R-27 · 柜台流式首音(2026-08-22)

> 需求来源:NFR-9 开口 ≤ 3 秒在 Gemini 完整 JSON + 整段 TTS 串行时守不住(本机冷 stub ≈ 3.5s)。对照 VoxEMW 首句流式与 GPT-Live「实时路径 / 工作路径拆开」,仍走云端 Gemini API,不把音频发给对话模型。落库为 **FR-41 / NFR-8 / NFR-9**。

## 1. 范围

- **改**:`POST /game/dialogue` 对 Gemini 使用 `streamGenerateContent`;首句就绪即签发 `reply_id` 并开口;地道分 JSON 走工作平面,可晚于开口。`Accept: text/event-stream` 时推 SSE(`speaking` / `score` / `done`);无该头仍返回一次性 JSON。T_speak≈1s 无首句则 stub,禁止再空等满 2s。
- **不改**:发音分仍来自转写;成交发档仍走 FR-28;Godot 仍只发转写与 `reply_id`;按 `V` 仍是计分话轮;无 key 时 stub 仍可离线成单。
- **降级**:T_speak / 429 / 503 / 解析失败立刻 stub 开口;已承诺台词不替换;player_turn 可随后补回。不扣状态。

## 2. 门控判据

- **G1** Godot / PCK 不含 `GEMINI_API_KEY` / `GOOGLE_API_KEY` / `XAI_API_KEY`。
- **G2** 发给 Gemini 的请求只有转写、角色卡、最近 8 轮;payload 不含 wav/audio/base64。
- **G3** 请求体 `generationConfig.thinkingConfig.thinkingLevel` 必须是 `LOW`;URL 为 `streamGenerateContent`。
- **G4** T_speak 内必有 `speaking`(gemini 首句或 stub);HTTP 层不因模型超时对 Godot 回 503。
- **G5** 未成交 / 走开 / 低分仍不发物资;`gesture_fallback` 三日可通关。
- **G6** 服务日志能拆 `transcribe` / `gemini_first` 或 `gemini` / `tts_first` 或 `tts` / `first_audio`。

## 3. 实现后回填

- `game.speech_service.test_dialogue`:流式 URL、T_speak stub、SSE 事件序、已开口后丢弃晚到台词但保留 player_turn、附和首轮不成交。26 项 unittest 全绿。
- Godot `test_npc_dialogue_assets.gd`:一次性 JSON 契约仍走 `_validate_reply`;桌面运行态用 HTTPClient SSE,headless/Web/request_override 保持 JSON。

## 4. 降延迟机制追记（2026-08-23）

R-27 落地后发现桌面 SSE 链路存在两处断点（服务端 SSE 无分帧致 Godot 读到空 body、客户端 HTTPClient 流未接线），修复后按 GPT-Live「实时/工作平面 + 常连」思路补齐五项机制：

1. **自适应阈值**：`_gemini_speak_window()` / `_gemini_socket_timeout()` 按最近 12 次成功首句的 P90（墙钟，含代理建连）滚动推导——speak 窗 clamp( P90+0.35s, 1.6, 2.6 )，socket 超时 clamp( P90+2.0s, 3.0, 6.0 )；连续 3 次未命中清样本回退短窗。`GEMINI_SPEAK_SECONDS` / `GEMINI_TIMEOUT_SECONDS` 环境变量可钉死。启动时 `gemini_probe` 一次连通性探测（顺带预热共享连接，代理路径 795ms 实测）。
2. **thinking 档位**：实测 gemini-3.7-flash 拒绝 `minimal`/`none`（HTTP 400），`thinkingBudget: 0` 被接受但不生效（thoughts 仍 110–128）。**LOW 即当前模型地板**，默认不变；`GEMINI_THINKING_LEVEL` 环境变量保留给未来模型。G3 断言改为允许清单 `{"none","minimal","LOW"}` 且默认 LOW——门控本意是防重思考，更低档不违反其精神。
3. **连接常驻**：Gemini 侧换 `requests.Session` 连接池（走环境代理、空闲连接失效时重试一次）；TTS 侧用 DashScope SDK 自带 `SpeechSynthesizerObjectPool`（预连 + 自动重连，端点为阿里云北京、国内直连，热池回合实测合成 498–571ms，对齐旧 `call()` 的 ~1068ms 近乎减半）。
4. **TTS 流式 + 音频随 SSE**：`iter_dialogue_events` 在 `speaking` 后内联流式合成，事件序 `speaking → audio_begin → audio* → audio_end → score → done`（PCM 剥头、~8KB/块、base64）；Godot 端 `feed_reply_pcm` 直接喂 AudioStreamWAV 播放，**消灭 `/game/tts` 往返**。`audio_failed` / score 先到无音频 / 3.5s 安全计时器三重回退至原 `/game/tts` 取数（服务端缓存兜底），旧服务端与 Web/headless JSON 路径零改动。
5. **V 键预热**：按下 V 即 POST `/game/prewarm`（10s 节流、仅服务点 NPC、专用 HTTPRequest 节点），借还一次 pool 合成器保温 WS；说话期间顺带完成全部建连。

### 实测（本机、走 127.0.0.1:7890 代理）

| 指标 | 改造前 | 改造后（11 回合窗口探针） |
|---|---|---|
| 台词就绪（dialogue_ready） | ~3.5s（等 Gemini 超时后 stub） | **1.63–1.65s**（stub 即时承诺） |
| 可听（audio_ready） | 3.5s + ~1.0s TTS + HTTP | **2.15–2.23s**（tts_stream 498–571ms 全走 SSE） |
| 每回合 /game/tts 请求 | 1 | **0**（回退路径保留） |
| 上游 503/超时时段 | 体验波动 | 稳定 stub 开口（自适应保持短窗） |

Gemini 真台词在健康时段（首句 1.9–2.5s、热连接）可落入自适应放开的 2.6s 窗内；上游高负载时段（当晚实测 503 频发）自动回短窗保 stub 开口。首句计时统一为墙钟口径（含代理建连），避免窗口被低估。
