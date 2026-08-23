# R-22 · 情景角色对话 + Grok 地道度发物资(2026-08-18)

> 需求来源:用户停掉离线撰稿与 YouTube 字幕主路径,改为铺服务情景、NPC 接 Grok、按会话地道度发物资。
> 落库为 **FR-41**(`docs/PRD.md` v0.10.3),并修订 **NFR-8**。

## 1. 范围

- **改**:3 张角色卡(食物柜台 / 便利店 / 零件前台);`POST /game/dialogue` 改为 Grok 结构化对答 + 玩家轮次地道分;成交后 `GameState` 按 FR-28 档发物资。
- **不改**:三日生存环、手势兜底、Qwen TTS、`/game/evaluate` 发音分、Speaking/Memorizing 的「LLM 不打分」。
- **降级**:FR-39 / FR-40 仍可作研究工具,不再挡发动物资对话。OpenAI 对话路径删除。

## 2. 与既有约束的冲突与解决

| 既有约束 | 本次变化 | 解决方式 |
|---|---|---|
| LLM 不打分,只生成措辞 | Grok 评地道度 | 原则继续管 Speaking/Memorizing;Stranger 明文例外,且只评转写 |
| NFR-8 仅 TTS + score_word | 对话要出站到 xAI | NFR-8 增补文本白名单;音频仍不到 Grok |
| 客户端只发台词 ID | NPC 回复是自由生成 | 服务器签发 `reply_id`,客户端仍不发自由文本给 TTS |
| 固定句换物资 | 同柜台不同意图 | 角色卡库存短名单,不锁标准句 |
| 无语音必须可通关 | Grok 会断 | `gesture_fallback` 仍给最低生存档 |

## 3. 门控判据

- **G1 凭据**。Godot 脚本与 `res://data/dialogue` 不含 `XAI_API_KEY` / `xai-` 密钥。key 只在服务器环境或 gitignored `XAI.csv`。
- **G2 音频隔离**。发给 xAI 的 payload 只有转写、角色卡、对白历史。单测断言请求体无 WAV / base64 音频字段。
- **G3 角色**。NPC `text` 含教学/分数/纠错标记则拒收。分数只进 HUD / 发物资。
- **G4 意图**。食物柜台「要汉堡」与「来杯咖啡」都能成交;便利店要水能成交、要修暖炉不能成交。
- **G5 发物资**。只在 `transaction_complete && next_state=closed` 时按会话分发档。走开不发。低分不扣需求/关系。
- **G6 降级**。无 key 时本地 stub 可测;无语音构建仍走 `gesture_fallback` 通关。

## 4. 实现后回填

- `game.speech_service.test_dialogue`: 13 项全绿(汉堡/咖啡同店成单、便利店要水成单/修暖炉不成单、教学台词拒绝、mock xAI 请求体无音频、runtime 无 key)。
- Godot `test_npc_dialogue_assets` / `test_voice_gated_rewards` / `test_save_migration` / `test_onboarding` / `VoiceTargetCancelTest` 全绿。
- 真 `XAI_API_KEY` 手跑与云端 `/game/dialogue` 部署仍是外部闭环。
