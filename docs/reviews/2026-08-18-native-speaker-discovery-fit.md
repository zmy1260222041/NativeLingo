# R-20 · Godot 对话语料 native-English YouTube 自动发现(2026-08-18)

> 需求来源:用户要求「自动找出 NativeSpeaker 视频,设计一下并实现」。
> 落库为 **FR-39**(`docs/PRD.md` v0.10.1)。
> 本评审覆盖运营侧 `game/speech_service/` 语料工具,不改 Godot 运行时。

## 1. 范围

- **改**:YouTube 研究候选的自动排序与硬拒绝;本地 `info.json` 筛查;可选 yt-dlp 搜索。
- **不改**:Godot 五日情景运行时、200 条 project-authored 回复、`promote` 的人工母语者门、版权/授权规则、玩家语音评分。

## 2. 与既有约束的冲突与解决

| 既有约束 | 本次变化 | 解决方式 |
|---|---|---|
| `native_speaker_verified` 必须由人工独立证据打开 | 用户要求自动找出母语者视频 | 自动层只输出 `reject` / `pending` / `candidate`;`can_auto_verify` 恒为 false |
| 主持人是母语者 ≠ 回应说话人是母语者 | 新闻采访/柜台互动常有第二说话人 | `native_scope` 分开 `host_only` / `channel_org`;回应说话人保持 `not_evidenced` |
| YouTube `language=en` 几乎人人都有 | 不能当母语证据 | 不用该字段做正向加分;只信 `*-orig` 字幕语言、新闻机构、自述出生地 |
| 研究候选不得入库 | 自动短名单可能被误当成发布语料 | `promote` 门不动;stubs 仍是 `research_only` + `native_speaker_verified=false` |

## 3. 门控判据

- **G1 不自动核实**。任何自动路径写入的记录里 `native_speaker_verified=false` 且 `can_auto_verify=false`。
- **G2 硬拒绝**。教学/角色扮演、攻略评测、非英语原声(`zh-orig`/`pt-orig` 等)、双语原声、明确 L2 自述,一律 `reject`。
- **G3 候选范围**。只认美式英语:美国新闻台、美国自述、或美国现场 vlog 可进 `candidate`;英式及其他非美式来源保持 `pending`。回应说话人不得标成已核实。
- **G4 发布门不变**。没有独立母语者证据的候选仍不能 `promote`。
- **G5 离线可跑**。本地 `info.json` 筛查不访问网络;单测不调用 YouTube。

## 4. 设计基线

自动发现只回答「这首视频值不值得人工去核回应说话人」,不回答「这个人是母语者」。

正向信号:英语 `*-orig` 字幕、Inner Circle 新闻机构、频道自述出生地/国籍、已认证新闻分类。
负向信号:教学标记、攻略标题、非英语原声、expat 攻略、旅行 vlog 且无新闻机构。

## 5. 实现后回填

- `game.speech_service.test_native_speaker_screener` + `test_corpus_pipeline` 共 20 项全绿。
- 对现有 35 份 `raw_captions/*.info.json` 本地筛查:`candidate` 5(全部是 CTV / GMA / KSHB / WPRI / Denver7)、`pending` 26、`reject` 4、`auto_verified` 0。
- Hannah Ricketts 的 `learn english` 标签只降分、不按教学片拒绝。
- `promote` 门未改:未独立核实的来源仍不能入库。
