# Mira 录音后重复欢迎语修复

根因：Mira 不在交易角色表中，2D 录音识别成功后进入旧 GameState 固定台词路径，未向实时对话服务提交。服务恢复只解决了识别，未修复该路由。

修复：为 Mira 添加 market_conversation 社交情景；2D 录音与识别路由使用独立情景选择，保留原交易角色表。开启/恢复录音会话不重播入场语。社交回复不显示点单与交付提示，不授予物资；空识别显示实际原因，提交失败有明确反馈。

验证：MiraLiveTest 使用两段合成 WAV 经过真实 AudioEffectRecord、结束录音上传、本地 Whisper、实时 Gemini、xAI 回复播放。两轮均识别、生成并播放完成，沿用同一会话，没有物品变化或点单提示，0 失败。此测试不冒充真人麦克风验证。

第一轮：Hi Mira, how are you today? → I'm doing great, thanks for asking!
第二轮：I have had a tiring day. What do you like about working here? → I'm sorry you're tired, but I love meeting new people here every day.

NovelTest 单独复测通过；首次与音频测试同时运行触发既有播放计时断言，保留两个日志。git diff --check 通过。macOS 2D Novel 重新导出，确认包内含新情景 JSON。已打开的旧进程须退出再启动。
