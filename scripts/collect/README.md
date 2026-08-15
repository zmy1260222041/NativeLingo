# Survival 语料采集页 —— R-14 G1 / G2

评审工具,**不是产品代码**。R-14 的 P0 三门(G1/G2/G3)未过,产品实现不得开始
(`docs/reviews/2026-08-08-survival-game-fit.md` §5)。本目录只为采集 G1 与 G2
共同缺的那批真实 L2 录音。

采集规格由两份文档定义,本页只是执行它们的工具,**不重复也不改动其中任何数字**:

- G1(意思传达判准):`scripts/fixtures/game_delivery/README.md`
- G2(ASR 关键词召回):`scripts/fixtures/game_asr/README.md`

## 跑法

```sh
python3 scripts/collect/serve.py           # 然后打开它打印的 127.0.0.1 地址
```

只用标准库,不需要 venv。默认采集探针档(infant 10 + toddler 10),按 tier 覆盖:

```sh
python3 scripts/collect/serve.py --port 8080 --out /tmp/probe
# 浏览器里 /?tiers=youth:6,professional:6
```

## 为什么是一个本地服务器,而不是双击打开的 HTML

**为了让「不显示答案」成为结构性保证,而不是渲染时的自觉。** 受试者一旦看过
`slots.accept`,他标出来的就不是「他自己会怎么说」,G1 的 precision 会系统性偏高;
同理他会照着 accept 说,G2 的关键词命中率也失真。

所以 `serve.py::_strip` 在**读取场景时就丢弃**这些字段,而且用的是**白名单**:只复制
页面允许渲染的六个字段,其余一概不出现在 HTTP 响应里。将来给场景 schema 加字段,
默认是不泄露。除 `accept` / `reference_answer` 外,一并丢弃的还有:

| 丢弃 | 理由 |
|---|---|
| `npc.responses` | `hit` 台词点名了目标物("Bread? Here you are.") |
| `new_words` | 那就是目标词表本身 |
| `situation.en` | 可照抄的英文措辞;规格要的是「中文情境 + 意图」,不给英文范例 |
| `slots`(含 `zh_hint`) | 整个字段不出 |

实测服务出的 45 个场景,payload 里 `accept` / `reference_answer` / `new_words` /
`responses` / `slots` / `zh_hint` / `persona` 七个串**一次都不出现**,键只有
`id` / `tier` / `need` / `maslow_level` / `situation_zh` / `greeting`。

第二个理由平淡些:120+ 条录音走浏览器下载不如走一次 loopback POST。

## 为什么不用外部录音工具

`collect.js` 的 recorder 是 `desktop/src/modules/recording.js` 那条 MediaRecorder
路径的**逐条移植** —— 同样的 `pickMime()` 候选顺序(`audio/mp4` 优先)、同样不加
constraint override 的 `getUserMedia({ audio: true })`、同样的 `start(500)` 时间片、
同样的 `requestData()` → `stop()` → 800ms `_finalize()` 兜底(WKWebView 不保证
`onstop` 一定触发)。

理由写在 G2 规格 §3 里:WKWebView 下 MediaRecorder 的实际编码容器与码率会影响转写,
而外部工具采到的音质会**略优于**生产路径。那个偏差方向会让 G2 系统性偏乐观 ——
**一个偏乐观的门比没测更糟,因为它看起来像测过了。**

同理页面不关 `echoCancellation` / `noiseSuppression` / `autoGainControl`:App 没关,
这里也不能关。

**移植而非 import 的理由**:从 `../../desktop/src/` import 会让评审脚本成为产品代码的
消费者,而该模块还会带进 `runtime.js`(bearer-token 的 `apiFetch`),在这里没有意义。
代价是两边可能漂移 —— 如实记在这里:**改了 `recording.js` 的采集契约,这里要跟着改。**

## 产出

```
scripts/fixtures/game_asr/
  clips/                    录音(不入 git —— 含可识别声纹)
  manifest.json             G2 骨架,严格照 game_asr/README.md §4 的字段,无多余键
  responses.skeleton.csv    G1 骨架,严格照 game_delivery/README.md 的列
  capture_log.jsonl         采集元数据(代号 / L1 / mime / 时长)
```

`manifest.json` 不夹带额外键,所以支撑「≥8 位说话人、≥3 种母语」的采集元数据放在
`capture_log.jsonl`,而不是塞进 manifest。

**`expected_keywords` 与 `delivered` 一律留空。** 它们由人填:前者靠**听录音**
(不是听转写)、后者靠人判断「一个包容的母语者会不会把对的东西递过来」。
从提示词自动填等于让 G2 给自己打分。实测:未标注的骨架喂给
`scripts/game_delivery_gate.py` 会**退出码 2、不给裁决**,而不是产出一个 0 分的假结果。

`clips/` 里的录音**不提交进仓库**(含可识别人声,同意书范围通常不含公开再分发)。
仓库里只留 manifest 与规格。

## 采集顺序

页面按说话人代号做**确定性**打散,并在该 tier 的场景间**轮转**取,而不是取前 N 个 ——
两份 README 都要求别让单个场景的 `accept` 集合支配某一 tier 的数字。实测:infant 与
professional 各 10 条都落在 8 个场景上,单场景最多 2 条,不会出现 1 个场景占 3 条。
同一代号重跑得到同一顺序,中途崩了可以接着采。

professional 之所以也是 8 个,是这一轮补出来的 —— 原先 5 个,10 条摊下去有场景要占 2 条
以上。**轮转只能摊平,摊不出场景来**:场景数不够时,单个 `accept` 集合支配该 tier 数字
这件事在采集端无解,只能在场景库端补。

按计划 §4.4,**先采 40 条探针(infant / toddler 各 20),再拍板两个待定的 schema 决策,
再采满 200** —— schema 一改,已标注的样本可能要重标,那是最贵的返工。
**探针数字与合成数字一样不可回填 PRD 与 R-14。**
