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

1. **自适应阈值**：`_gemini_speak_window()` / `_gemini_socket_timeout()` 按最近 12 次成功首句的 P90（墙钟，含代理建连）滚动推导——speak 窗 clamp( P90+0.35s, 1.9, 2.1 )，socket 超时 clamp( P90+2.0s, 3.0, 6.0 )；连续 3 次未命中清样本回退短窗。`GEMINI_SPEAK_SECONDS` / `GEMINI_TIMEOUT_SECONDS` 环境变量可钉死。启动时后台重试轻量 model GET，顺带预热共享代理连接。
2. **thinking 档位**：2026-08-23 真实对照中 `gemini-3.7-flash/LOW` 仍出现约 3–5.6s 首句抖动，改用面向低延迟的 `gemini-3.1-flash-lite/MINIMAL`。请求仍是 Gemini `streamGenerateContent`、仍只发文本；`GEMINI_DIALOGUE_MODEL` / `GEMINI_THINKING_LEVEL` 覆盖口保留。模型替换没有改变实时平面 / 工作平面边界。
3. **连接常驻**：Gemini 侧换 `requests.Session` 连接池（走环境代理、空闲连接失效时重试一次）；TTS 侧用 DashScope SDK 自带 `SpeechSynthesizerObjectPool`（预连 + 自动重连，端点为阿里云北京、国内直连，热池回合实测合成 498–571ms，对齐旧 `call()` 的 ~1068ms 近乎减半）。
4. **TTS 流式 + 音频随 SSE**：`iter_dialogue_events` 在 `speaking` 后内联流式合成，事件序 `speaking → audio_begin → audio* → audio_end → score → done`（PCM 剥头、~8KB/块、base64）；Godot 端 `feed_reply_pcm` 直接喂 AudioStreamWAV 播放，**消灭 `/game/tts` 往返**。`audio_failed` / score 先到无音频 / 3.5s 安全计时器三重回退至原 `/game/tts` 取数（服务端缓存兜底），旧服务端与 Web/headless JSON 路径零改动。
5. **V 键预热**：按下 V 即 POST `/game/prewarm`（10s 节流、仅服务点 NPC、专用 HTTPRequest 节点），并行预热 Gemini 共享 HTTPS session（轻量 model GET，不消耗生成 token）与 TTS pool；说话期间顺带完成全部建连。

### 实测（本机、走 127.0.0.1:7890 代理）

| 指标 | 改造前 | 改造后（11 回合窗口探针） |
|---|---|---|
| 台词就绪（dialogue_ready） | ~3.5s（等 Gemini 超时后 stub） | **1.63–1.65s**（stub 即时承诺） |
| 可听（audio_ready） | 3.5s + ~1.0s TTS + HTTP | **2.15–2.23s**（tts_stream 498–571ms 全走 SSE） |
| 每回合 /game/tts 请求 | 1 | **0**（回退路径保留） |
| 上游 503/超时时段 | 体验波动 | 稳定 stub 开口（自适应保持短窗） |

上表记录的是 3.7 Flash 阶段的历史结果（当时健康首句 1.9–2.5s、窗口上限 2.6s）；首句计时统一为墙钟口径（含代理建连），避免窗口被低估。当前 Flash-Lite 结果见下方复验。

### Flash-Lite 真模型复验（2026-08-23）

验收明确排除 stub：先 `/game/prewarm`，再对 Tavi 发同一条合法点单，连续 3 轮均要求 `speaking.source=gemini`、`score.source=gemini`、`score.model=gemini-3.1-flash-lite`。结果 3/3 通过：`speaking` 665.7 / 938.2 / 855.3ms，`audio_begin` 1035.2 / 1311.5 / 1217.7ms，整轮 `done` 1716.4 / 1924.1 / 1841.8ms；首音频中位数 **1217.7ms**，无 stub。实际台词 `Sure thing, one coffee coming right up.` 符合短、自然、在角色的美式柜台口吻。日志的真实 `first_audio` 与客户端 `audio_begin` 只差约 1–2ms。

原 GPT-Live 式五点不变：Gemini SSE 首句即承诺、实时/工作平面拆分、晚到工作面不得反转已说事务、连接池常驻、内联 TTS 音频；stub 仅保留为断网/上游故障与离线测试的生存回退，不作为配置正常时的在线验收结果。

### 最终尾延迟与完整句补强（2026-08-24）

扩大样本后又暴露两个不能靠挑样本掩盖的问题：进程第一条真实 POST 偶发超过短窗，以及 SSE partial 在句末标点到达前被误读成完整台词。最终实现保留 token-free model GET，再增加最多 16 output tokens、30 秒限频的流式数据平面探针；实时面同时启动两条同模型请求，350ms 后仍无合格句才启动第三条。赢家筛选只读取已有句末标点的完整句；流完成后才允许无标点但完整的最终文本。安全门可跳过同一候选里编造位置的第一句，继续选择后续模型原文中的安全协助句。

固定 10 条、每条只跑一次的最终验收为 10/10 Gemini，`audio_begin` p50 1286.3ms / max 1588.6ms；真 Godot 桌面 SSE `audio_ready_ms=1949`。所有台词完整，事务布尔 10/10 正确，无价格、品牌、库存数量、等待时间、政策或未知位置编造。完整证据见 R-28。
