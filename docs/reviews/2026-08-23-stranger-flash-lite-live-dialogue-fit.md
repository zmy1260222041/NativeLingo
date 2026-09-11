# R-28 — Flash-Lite 在线实时 NPC 对话符合性复验

**日期**：2026-08-23（2026-08-24 最终复验）  
**结论**：**PASS**  
**范围**：FR-41、NFR-9，以及提交 `ebe0e107` 引入的服务点 NPC 流式首音路径

## 1. 发现并修复的问题

审查不是只跑 happy path。最初版本在真实并发、断流和模型尾延迟下存在以下缺陷：

- 玩家在生成冻结期走开时没有取消会话，晚到的结果仍可能结算资源。
- SSE 以 HTTP 200 开始后异常断流且没有 `done/error` 时，客户端可能挂到 90 秒会话超时。
- TTS 局部故障没有正确打开手势降级；重复按 `V` 还可能覆盖正在播放的回复。
- `first_audio` 日志在没有真实 PCM 时也会假报成功。
- stub 把多句截断且忽略历史；库存使用子串匹配，`seafood` 会误命中 `food`。
- 在线模型的首句、score 与 reply 身份缺少一致性检查，旧回复可能污染新会话。
- Gemini 偶发输出未提供的价格、库存数量或具体货架位置。
- 流式 partial 曾被误当成完整句，实际出现过 `We don`、`I'`、`Sorry,` 等不可播放残片。
- 仅做 TLS GET 预热仍会让进程第一条真实生成遇到约 3.6 秒冷尾延迟并回退 stub。

修复后，走开取消、异常断流重试/失败、真实音频日志、短语边界、reply 身份、完整句门槛和安全事实门全部有回归覆盖。

## 2. 实时策略与 GPT-live 学习点

原有实时策略保持不变并补强：

1. Gemini 仍走 `streamGenerateContent`，不是等完整 JSON 后才开口。
2. 实时平面只负责第一条可说的模型原句；工作平面继续完成 idiomaticity/事务 JSON。
3. 已开口的确定性事务结论不能被晚到模型 JSON 反转。
4. 按 `V` 仍并行预热共享 Google HTTPS session 与 TTS websocket；另加一个最多 16 output tokens、30 秒限频的流式数据平面探针，避免第一条 POST 冷启动。
5. 同一 `gemini-3.1-flash-lite` 请求做尾延迟竞速：两条立即启动，350ms 后仍无完整安全句才启动第三条；赢家必须是完整结束、符合请求且不编造事实的模型原文。
6. 第一条模型句立即进入并行 TTS；stub 只保留作断网、限流、服务故障或无 key 的保活路径，不计入在线验收。

模型固定为 `gemini-3.1-flash-lite` + `thinking_level=MINIMAL`。Google 官方文档把 Flash-Lite 定位为低延迟模型，并说明该型号支持 `MINIMAL` thinking；这使它比此前 `gemini-3.7-flash` + `LOW` 更适合短柜台应答：

- <https://ai.google.dev/gemini-api/docs/generate-content/thinking?hl=en>
- <https://ai.google.dev/gemini-api/docs/generate-content/whats-new-gemini-3.5?hl=en>

system prompt 与服务端 gate 同时要求短、日常、带缩写的自然美式柜台口吻，并禁止编造价格、品牌、库存数量、等待时间、政策和未知具体位置。

## 3. 固定 10 轮在线验收

验收前同时确认：`tts_pool=true`、`gemini_session=true`、`gemini_model=true`。以下 10 条固定输入各运行一次，不重试、不替换失败样本。

| # | Gemini 实际开口 | complete/off | Speaking | Audio begin |
|---|---|---:|---:|---:|
| 1 | Sure thing, one cheeseburger. | T/F | 1145.6ms | 1588.6ms |
| 2 | Sure thing. | T/F | 711.9ms | 1128.7ms |
| 3 | Sorry, we don't carry those. | F/T | 823.8ms | 1262.7ms |
| 4 | We don't carry flashlights here. | F/T | 747.7ms | 1169.2ms |
| 5 | Sure, what can I get for you? | F/F | 948.3ms | 1336.3ms |
| 6 | Sure thing, one burger. | T/F | 862.9ms | 1206.8ms |
| 7 | Sure, I've got those. | T/F | 908.6ms | 1278.4ms |
| 8 | Do you want me to show you where that is? | F/F | 1137.2ms | 1572.6ms |
| 9 | I've got those alloy parts. | T/F | 880.4ms | 1294.2ms |
| 10 | Yeah, I can lend you an extra blanket. | T/F | 960.5ms | 1366.4ms |

硬门结果：

- `speaking.source=gemini`：10/10
- `score.source=gemini`：10/10
- `score.model=gemini-3.1-flash-lite`：10/10
- `audio_begin < 3000ms`：10/10
- 完整句、事务 complete/off 正确：10/10
- 不支持事实或未知位置编造：0/10
- Speaking：p50 894.5ms，max 1145.6ms
- Audio begin：p50 1286.3ms，max 1588.6ms
- Audio end：p50 1668.3ms，max 2071.7ms
- Done：p50 1781.9ms，max 2502.9ms

原始日志：`/private/tmp/stranger_speech_server_flashlite_final6.log`。

## 4. 游戏端与回归

- 真桌面 Godot SSE：final6 `audio_ready_ms=1949`；仅把三项预热改为并行后的 final7 再测为 `audio_ready_ms=2027`。两次均 `PASS`、`source=gemini`、`model=gemini-3.1-flash-lite`，且 final7 无警告。
- Main 场景 180 帧 smoke：`PASS`。
- Godot NPC dialogue assets：`PASS`。
- 冻结期间走开取消/不结算：`PASS`。
- Python dialogue + TTS：60/60 `PASS`。
- `git diff --check`：`PASS`。

在线 SceneTree 探针立即退出时 Godot 会打印一条 `ObjectDB instances leaked at exit` 警告；主场景 smoke 和三个 headless 套件均无该警告，也无 `ERROR`/`SCRIPT ERROR`。它属于测试进程退出清理噪声，不影响游戏运行或本门结论。

## 5. Gate 结论

FR-41/NFR-9 的在线动态 NPC 对话可以进入下一门：真实模型路径、地道美式回复、事务语义和 3 秒首音频预算均已在同一最终构建上通过。离线/故障 stub 仍保留，但不能用于在线性能签收。
