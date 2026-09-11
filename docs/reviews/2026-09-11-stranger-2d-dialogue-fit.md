# R-34 · Stranger 2D 对话与养成迁移

需求：FR-46。分支：`codex/stranger-2d-dialogue`，从当时工作中的 `feat/stranger-core-gameplay` 新建，保留现有未提交改动。未提交或推送。

默认入口为 `game/scenes/Novel.tscn`。六个 2D 地点、五个人物立绘、逐字对白、双人社会小剧场、养成/词汇面板、背包/柜台/住所、回看与设置替代 3D 世界。旧 `Main.tscn` 和美术源文件保留用于参考，不进入专用 2D 构建。

## 功能对应

| 既有功能/内容 | 2D 入口与实现 | 验证 |
|---|---|---|
| 五名 NPC、三个服务角色卡、全部具体库存 | 地点选择、交谈、查看柜台；原 `NpcScenarioRegistry` 与 JSON | 原角色卡测试、新 2D 测试 |
| 三项需求、三夜、睡觉、温暖设施 | 左侧状态、住处等待/睡眠/维修；原 `GameState` / `ItemState` | 三夜完整命令路径通过 |
| 手势兜底与语音成交档 | 手势/录音按钮；原 `SpeechAdapter` / `NpcDialogueService` / Runner | 可用语音不能绕门、晚到旧对象回调无奖励、原单调奖励测试 |
| NPC 配音与玩家显著性字幕 | 非空间 `AudioStreamPlayer`；独立玩家字幕保留到下轮/换场 | NPC 配音、词级、云适配器测试 |
| 五段社会对白 | 可选择、推进、重看的双立绘小剧场 | 观察词汇、切换发言者、正常退出 |
| 三态词汇与三份词表 | 成长面板主动练习；原词汇/评分服务 | 原词汇/词级测试；初始已知词不降级 |
| 领取、打包、使用、容量、浪费确认 | 柜台与行囊 | 180 条物品账本断言、新远程位置拒绝/防重复使用/住所存取 |
| 家居、毯子、电池、加热器、邻居送水 | 住所物品面板与罗文手势/语音 | 安放/安装、送水关系验证 |
| 关系、记忆、情景进度与旧存档 | 独立 `stranger_novel_save.json`，首次导入旧档 | 原迁移测试、新导入测试逐字比对旧档未修改 |
| 可访问性、云激活、存读档、重开 | 设置；Tab/方向键/确认键和原 InputMap 手柄按钮 | 重映射过滤、面板构建与实际桌面渲染；物理手柄未实测 |

## 行为边界

- 阅读/对话/词汇练习不流逝时间。普通换地点推进 6 秒原压缩时间；住处休息到晚上的需求消耗为等长外出时间的 20%。领域的睡眠时刻和三夜结束规则不变。
- 没有创建新的支付或资源旁路。柜台显示库存，只能在原有真实成交/不可用语音兜底后得到物品；点击菜单不生成发音成绩。
- 2D 物品命令由地点身份验证取代距离验证；仍经过 `GameState.item_command`，不直接写账本。
- 换场景、打开管理面板、重开会取消录音、动态会话及配音队列。旧目标回调不能给新地点发货。
- 原静态 NPC 台词新增只读 `npc_line_presented` 信号，2D 对话框与配音共用内容；不依赖旧版仅语音 HUD。
- `presentation_state` 为 v5 存档的向后兼容附加字段；保留既有领域数据。新入口不显示移动/跳跃教学。

## 验证证据

本机 Godot 4.6.3、Apple M5 / OpenGL Compatibility：

- `NovelTest.tscn`：通过。额外完成转写 → 原对话边界 → 模拟合法服务回复/评分 → 真实 AudioStreamPlayer 播放 200ms PCM → 播完才按原评分交付两份 → 柜台整批打包的集成验证，headless 与桌面模式均通过（不冒充外部模型或真实麦克风验证）。包括读取不扣需求、纯 2D 场景、非空间音频、柜台与携带物品、远程命令拒绝、送水、维修、词汇、晚到回调、所有管理面板、独立存档及三夜流程。
- `test_game_state.gd`、`test_save_migration.gd`、`test_voice_gated_rewards.gd`、`test_item_usage.gd`（180 checks）、`test_npc_dialogue_assets.gd`：通过。
- `NpcVoiceTest.tscn`、`VocabularyTest.tscn`（toddler 2637 entries）、`WordPracticeTest.tscn`、`CloudVoiceTest.tscn`：通过。
- 已渲染检查 `novel_2d_2026-09-11/{plaza,food,growth,home}.png`，1152×720。修正 atlas 边界、Noto Sans SC 默认极细字重，并保留高对比焦点。
- 专用 `macOS 2D Novel` 使用显式资源列表和角色卡/词表过滤。资源包约 22 MB，独立启动无脚本或资源加载错误。初次选择场景导出遗漏动态依赖，已通过明确列举所需脚本/字体/翻译修复。macOS 应用约 198 MB（包含引擎），已独立启动。
- 原 NPC 配音与角色卡测试退出时有 ObjectDB 泄漏提示；断言通过，新 2D 套件没有该提示。

本次未进行真人麦克风/远端 Gemini 与 TTS 实时验收，未实测物理手柄；保留现有经过测试的适配器契约，不把接口回归等同线上音质或延迟验收。新立绘是一套静态姿态，含入场淡入与双人发言状态；表情差分、口型和更丰富剧情属于后续内容迭代。

## 文档核对

Context7 MCP 在本次会话不可调用，使用 Godot 4.6 官方 `TextureRect`、`RichTextLabel`、`AudioStreamPlayer`、`FontVariation` 文档核对接口，并以本地 4.6.3 编译运行结果验收。

- https://docs.godotengine.org/en/4.6/classes/class_texturerect.html
- https://docs.godotengine.org/en/4.6/classes/class_richtextlabel.html
- https://docs.godotengine.org/en/4.6/classes/class_audiostreamplayer.html
- https://docs.godotengine.org/en/4.6/classes/class_fontvariation.html
