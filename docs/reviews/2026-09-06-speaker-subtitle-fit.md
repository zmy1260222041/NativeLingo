# R-32 · 说话人字幕卡 + 词汇档位出站 + 词汇回灌(2026-09-06)

> 需求来源:R-31 证据基线第 1/4/6/7 条的首批落地(用户拍板 2026-09-06)。设计稿中的回声卡/显式 hint 方案被用户否决——「系统直接指出错误实际上可能影响用户学习的积极情绪」,改为**说话人字幕卡 + 红色显著性标记**(noticing-by-salience):标记让玩家注意到差异,规则由玩家下一轮自我修正领悟。对应 **FR-45 / NFR-8 增补 / FR-38·FR-24 修订**,PRD v0.10.11。

## 1. 范围

- **T1-A 词汇档位出站**:`game_context.player_level`(infant/toddler/youth/professional 四档枚举)随 `/game/dialogue` 出站;服务端 `_scene_card` 与系统提示词按档位追加 NPC 用词约束——infant/toddler/youth 有条款,**professional 与缺省档提示词与现状逐字一致**(不追加任何文字)。
- **T1-B 说话人字幕卡**:玩家转写就绪即显示底部居中字幕卡(中性色,不等待工作平面、不阻塞实时平面);工作平面 `player_turn.errors` 到达后对应片段改红+下划线。服务端标记规则:仅 idiomaticity<85 的轮次;每轮 ≤2 个 span、每个 ≤4 词、≤40 字符;**必须是玩家转写的精确子串**(normalize 后大小写不敏感匹配;模型改写/幻觉 span 丢弃);去重。SSE 晚到评分路径以晚到 player_turn 的 idiomaticity+errors 为权威。客户端:stub/无 key 轮显示中性转写、不标记(source 门控);字幕卡非模态(mouse_filter=IGNORE),下一轮开口即替换,会话结束 3 秒消散;转写恒按原文显示,`[`/`]` 转义防 bbcode 注入;只标每个 span 的首个命中,重叠 span 去重。
- **T1-C 词汇回灌**:服务对话每轮真评分转写回灌 `Vocabulary.record_words_used_from_text`(仅 spoken→used,initial 永不推进,不设分数门——口语产出本身就是产出)。

## 2. 门控判据(实现前经用户拍板,冻结)

**G-A 档位出站**
- G-A1 请求体新增仅 `game_context.player_level` 一个字段,其余出站不变。
- G-A2 toddler/youth/infant 档系统提示词含对应用词条款;professional 与缺省档提示词与改动前逐字一致。
- G-A3 首音 ≤3s 不回退(R-28 回归);stub 路径零改动。

**G-B′ 字幕卡与标记**
- G-B1 对话流内零纠错文本/解释/分数;唯一显性元素是玩家转写与红+下划线标记。
- G-B2 标记仅来自真评分轮(source=gemini/grok);stub 轮只显示中性转写。
- G-B3 span 与转写精确匹配:服务端校验丢弃不匹配项,客户端只标首个命中。
- G-B4 每轮 ≤2 处标记、仅 idiomaticity<85;标记=红色+下划线双重编码(非仅颜色)。
- G-B5 字幕卡转写就绪即显示、不等待不阻塞实时平面;非模态。
- G-B6 NPC 台词仍纯语音;会话结束 3 秒消散、下一轮替换。
- G-B7 转写按原文显示(恒英文),bbcode 注入转义。

**G-C 词汇回灌**
- G-C1 每轮真评分转写回灌。
- G-C2 仅 spoken→used,initial 永不推进(阶梯不变)。
- G-C3 三态只前进、奖励单调(既有 FR-36 不变量)。
- G-C4 存档 round-trip 保留状态。
- G-C5 word practice 既有流程回归全绿。

## 3. 实现后回填(2026-09-06)

- **server.py**:`_VALID_PLAYER_LEVELS`/`_PLAYER_LEVEL_CLAUSES`/`_player_level_from_body` + `_scene_card(player_level)`(仅带条款档位入卡)+ `_dialogue_system_prompt(player_level)`(errors 生成指令 + 分档条款,professional/缺省与旧提示词逐字一致)+ `_validated_error_spans`(精确子串/≤2 个/≤4 词/≤40 字符/去重/idiomaticity<85)+ `_normalise_player_turn` 携带 `errors` + SSE 晚到 player_turn 的 `errors` 随权威 idiomaticity 一并覆盖。stub 路径零改动(errors 恒空表)。
- **npc_dialogue_service.gd**:请求体 `game_context.player_level`(仅四档枚举,非法档丢弃);`player_turn_displayed`/`player_turn_scored` 信号;`current_turn_transcript` 贯穿晚到评分;`_apply_score` 内 source 门控(errors 仅 gemini/grok)+ `_record_vocabulary_use` 回灌。
- **hud.gd**:`SpeakerSubtitleCard`/`SpeakerSubtitleLabel`(代码构建,底部居中,MOUSE_FILTER_IGNORE,非模态)两阶段渲染 `_render_speaker_subtitle`(首命中标记、重叠去重、bbcode 转义、红+下划线);会话结束/失败 3 秒消散,下一轮替换。
- **测试**:Python `test_dialogue.py` 57/57 绿(新增 6 项:档位出站/提示词分档逐字一致/errors 精确子串/上限与阈值门控/normalise 携带/stub 零标记)。Godot:`test_npc_dialogue_assets.gd` PASS(新增 12 断言:G-A1 档位出站与非法档丢弃、G-B2/G-B3 标记与 stub 门控、G-B5 即时镜像、G-C1 spoken→used 回灌);`test_hud.gd` PASS(新增 10 断言:卡构建隐藏/非模态/两阶段渲染/精确 span 标红/不匹配不标/中性卡/3 秒消散);回归 `test_voice_gated_rewards.gd` PASS、`VocabularyTest.tscn` PASS。
- **已知遗留(非本批引入)**:`SocialDialogueTest.tscn` 1 项失败「Understood retry closes the session and applies the monotonic reward」——HEAD 干净树该项通过,失败源于本分支未提交的 FR-41/物品改造把旧语音路径改为「请在柜台对话中确认具体物品」后不再直接发物资,`game_state.gd` 与该测试断言未同步。该调用链(game_state `_interact_food_supplier`/`Dialogue.player_acted`)不在本批改动文件内,留待 FR-44 收口时同步修正测试断言。
