# R-36 — 生活化对话与行囊体验

需求：FR-47；延续 FR-44 实物账本、FR-46 纯 2D 分支和原语音成交门。本轮验收通过；改动保留在当前工作区，未提交或推送。

## 用户可见变化

行囊、柜台和小屋采用分类列表与物品详情。相同物品按状态、所在位置和剩余次数合并显示数量，不合并真实实例。详情说明用途、来源、剩余次数和当前实际恢复量；食物、饮品和住所用品共用原有容量与堆叠规则。柜台顶栏可全部收好，容量不足则禁用；仍可现场使用或逐件领取。空行囊提供真正可用的补给入口。

吃喝、收纳、安放、安装和收回给出具名回执及真实效果，满状态不消耗，效果浪费需明确确认；物品版本变化后旧确认失效。半壶水仍保留一次使用机会；毯子启用才增加入睡温暖，收回即停止生效。需求条平滑变化、主要操作强调、独立反馈底板、模态遮罩与键盘焦点让反馈更清楚；减少动态设置仍有效。

日常扩展为九段、共 36 句，覆盖问候、打包午餐、修暖气、饮品、邻里帮忙、选餐、电池、毯子和门廊闲聊。场景背景与双方立绘随片段呈现，显示句数，支持逐句重听及返回现场。各地点的开口灵感提供表达与对应片段入口，不提交玩家转写或伪造评分。

`game/data/dialogue/novel_daily_life.json` 同时提供屏幕文字和服务端 TTS 白名单。词汇仅在对应句子已经呈现后观察。角色卡的 situation 现在实际传入模型，限制额外购买选项；已明确的堂食/打包信息作为会话提示，清晰点单要求直接交付。提示不修改成交判定，最终仍需原具名承诺、评分及真实音频播放结束。

## 验收证据

证据目录：`docs/reviews/everyday_inventory_2026-09-11/`。

| 需求 | 当前证据 | 结果 |
| --- | --- | --- |
| 分类、合并数量、半壶水分组与实际效果 | `NovelEverydayTest`，`bag.png`、`canteen.png` | 通过 |
| 柜台批量领取、满容量保护、逐件消耗与浪费确认 | 同套件；`counter.png`、`full-counter.png`；确认前与陈旧确认均不消耗 | 通过 |
| 住处放置、启用、收回与收纳 | 同套件；毯子实际睡眠加成 20→0，收纳后住所用品占用归零；`home.png` | 通过 |
| 可执行空态、模态输入与焦点 | 同套件；真实鼠标事件不能穿透，连续 12 次 Tab 保留面板焦点；`empty.png` | 通过 |
| 桌面与小窗口、大对话字号 | 1440×900、1152×720 渲染截图人工逐图检查；`bag-1152.png`、`daily-dialogue.png` | 通过 |
| 九段文本/音频一致、只观察当前句、无物资和技能冒领 | Python 共享目录契约、Godot 全部 36 句遍历与账本对比 | 通过 |
| 真实生活对话 | `live-dialogue.json`；Gemini 三场景各两轮，泛需求/询问不交付，明确 sandwich/batteries/blanket 后交付 | 通过 |
| 新目录实际配音 | 同 JSON 与 `daily-life-sample.wav`；xAI 美国端点，2.154 秒有效 WAV | 通过 |
| 游戏录音及物资/词汇闭环 | `voice-integration.log`；真实录音效果器→ASR/评分→模型→播放结束→柜台物资，第二轮 taco 开口 1385ms | 通过 |
| 原领域与三夜兜底 | `regression-1.log` 至 `regression-9.log`：ItemUsage、Novel、NpcVoice、WordPractice、WordAcquisition、VoiceTargetCancel、SocialDialogue、NpcDialogueAssets、VoiceGatedRewards | 通过 |
| Python 回归 | `python-regression.log`：129 项通过；后续目录校验另行通过 | 通过 |
| 独立桌面交付 | `export.log`、`export-smoke.log`；专用包显式包含新行囊脚本、图标和台词目录，运行时无缺失资源/脚本错误 | 通过 |

## 联调中发现并处理的问题

真实模型曾在玩家说过 to go 后重复追问、要求选择未建模的电池型号、用“还需要别的吗”拖延交付。新增已回答选项及明确点单提示，保留询问/否定/犹豫时的正常对话；提示只是生成约束，未移除原有质量与物资门控。通过上述六轮真实对话和完整语音链路复验。模型生成仍具有随机性，这些样本不代表对所有可能表达的穷尽证明。

首次导出烟测还发现新行囊脚本未被专用资源清单带入，已显式补齐；同时把日常 JSON 从字节码静态初始化移到场景启动时读取，避免导出包文件系统尚未就绪。重新导出并重新运行验证；没有用“导出命令返回成功”代替启动验证。

真实对话探测输入为文字测试样本；完整语音探测使用参考/合成 WAV 经游戏录音效果器，不是用户真人麦克风或口音评测。本轮未改变语音分档、物资幂等、三夜规则、用户旧存档或 3D 资产。

## 运行

双击 `game/run_novel.command` 使用最新的 `build/novel/Stranger2D.app` 与本地语音服务。

```sh
/Applications/Godot-4.6.app/Contents/MacOS/Godot --path game res://tests/NovelEverydayTest.tscn -- --everyday-capture
.venv/bin/python -m unittest discover -s game/speech_service -p 'test_*.py'
.venv/bin/python game/speech_service/probe_everyday.py
.venv/bin/python game/speech_service/probe_novel_live.py
```
