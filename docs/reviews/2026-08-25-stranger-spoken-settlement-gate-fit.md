# R-29 — NPC 具名口头交付后结算资源

**日期**：2026-08-25  
**结论**：**PASS**  
**范围**：FR-41 动态服务点对话的事务完成语义、NPC 音频边界与资源结算

## 1. 复现与根因

旧在线日志复现：玩家说 `can i have some food please`，NPC 实际说
`Sure thing, what kind of food can I get for you?`，但服务端仍记录
`speech_act=confirm_order complete=1`，游戏随后会在音频结束时发食物。

根因是实时 Gemini 首句只替换 stub 的 `text`，却沿用 stub 的
`speech_act/next_state/player_turn`；归一化只检查玩家有没有提到库存，不检查 NPC
实际说出的 committed 台词。Godot 随后只信 `transaction_complete`，Runner 和
GameState 也只按 NPC 身份与分数发资源。

## 2. 写死的结算不变量

资源只允许在以下条件全部成立后结算：

1. 玩家当前轮或明确的多轮上下文解析出一个具体库存项；`food`、`snack`、
   `parts` 等泛类词不算。
2. 已承诺播放的 NPC 台词明确说出同一具体物品。
3. 台词包含接单/交付承诺（如 `I'll get`、`here you go`、`coming right up`），
   且不是问句。
4. speech act 属于场景角色卡的 `completion_speech_acts`，并且不是
   off-inventory。
5. 同一 reply 的 score 已到达，NPC 对应音频已真实播放结束。
6. Runner 与 GameState 再次校验具名物品属于该 NPC 场景库存；缺字段、泛类词、
   伪造物品或身份不匹配一律返回 `none`。

## 3. 实现

- `server.py` 从 committed speaking 文本生成
  `spoken_delivery_confirmed/requested_item/confirmed_item/transaction_evidence_reason`；
  模型即使声称 complete，只要口头证据不完整就降级到
  `awaiting_follow_up`。
- 成交轮若 Gemini 第一短句只有 `Coming right up.`，实时平面可在同一低延迟
  窗口等待最多第二短句，选择包含具名交付证据的最短安全前缀；仍不满足就走明确
  具名的 deterministic fallback，不拿泛化首句成交。
- `npc_dialogue_service.gd` 保存实际 speaking 文本并独立复核物品、承诺、问句、
  completion act；只有 score 与音频完成两门都过才调用 Runner。
- `npc_scenario_runner.gd` 与 `game_state.gd` 各自重验 confirmed item；最底层在
  autoload 尚未 ready 的纯状态环境也只读同一场景 JSON，不绕过校验。

## 4. 验收证据

真实 Main 场景 + localhost Gemini/TTS 桌面 SSE：

| 玩家输入 | NPC 实际开口 | 播放中 | 播放结束后 |
|---|---|---|---|
| `Can I have some food, please?` | `Sure, I've got burgers, sandwiches, pizza, and tacos.` | 资源不变 | 资源不变，会话继续 |
| `I'll take a taco to go, please.` | `Sure thing, one taco to go coming right up.` | 资源不变 | 食物增加，会话关闭 |

- provider/model：`gemini` / `gemini-3.1-flash-lite`
- Godot `line_audio_ready`：2659ms（≤ 3000ms）
- 服务端事务：generic `complete=0 evidence=no_specific_requested_item`；taco
  `complete=1 requested=taco confirmed=taco evidence=confirmed`
- 最终在线日志：`/private/tmp/stranger_speech_server_settlement_final2.log`
- Python dialogue + TTS：65/65 PASS
- Godot `test_npc_dialogue_assets`、`test_voice_gated_rewards`、`test_game_state`、
  `VoiceTargetCancelTest`、`SocialDialogueTest`、`MainEnvIntegration`：PASS
- `git diff --check`、`py_compile`：PASS

## 5. 结论

旧的“NPC 还在追问就先发资源”路径已被服务端、Godot 服务、Runner、GameState
四层同时封死。安全拒绝不会关闭会话；具名成交也不会在 NPC 说完之前结算。

