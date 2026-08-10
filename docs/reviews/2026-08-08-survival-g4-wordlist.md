# R-14 / G4（2026-08-08）分级词表授权与体积

> 范围:R-14 的 **G4** 单门 —— FR-20 分级词汇库所依赖的外部词表
> 判据(取自 `docs/reviews/2026-08-08-survival-game-fit.md` §2 G4,一字未改):
> 所选词表的许可**明确允许随包再分发**(逐条核对,含闭源/商业分发场景);解压后体积与
> 首次启动延迟记录在案,不得违反 NFR-3。
> 结论:✅ **G4 通过(2026-08-09)** —— 授权、解压体积、首次启动延迟三项均已实测记录。
> **§8 为实测回填**:三份资产原样落盘(SHA-256 可复现)、解压合计 1.15 MiB、
> 含 CEFR-J 的冷启动 **76.4 ms** vs NFR-3 预算 1,000 ms;复合键与频次/等级分工均由实测
> 改写了原先的设想。CEFR-J v1.6 已由用户手动同意使用許諾后下载,本门最后一项闭合。
> **G4 是前置门,不是 P0 门 —— 它的通过不改变模块的放行状态。**

## 0. 这道门为什么严到这个程度

判据里「**明确**允许」三个字是有先例的:选 Piper `en_US-libritts_r-medium` 时逐条核过
CC-BY 4.0 才写进 NFR-5。本门沿用同一标准 —— **「大概可以」等于不通过**。

因此本文档对每个候选记四件事:许可名称 + 一手来源 + 是否允许闭源商业随包再分发 +
署名义务;并在最后单列**核实不到的**与**互相矛盾的**信息。凡是只能从二手转述、镜像仓库
或社区惯例推出来的授权,一律记为不可用。

方法:全部为一手页面直取与**实际下载并解析数据文件**。WebSearch 后端全程返回 403,
所以本轮没有任何结论来自搜索摘要。

## 1. 结论:选定组合

| 角色 | 选定 | 许可 | 是否可闭源商业随包分发 |
|---|---|---|---|
| **等级骨架(A1–B2)** | **CEFR-J Wordlist v1.6** | 版权方自授权(非 CC/OSS),商用明文许可 | ✅ 明确允许,唯一义务是署名 |
| **等级补充(C1/C2)** | **Octanove Vocabulary Profile C1/C2 v1.0** | CC BY-SA 4.0 | ✅ 明确允许(SA 只约束数据) |
| **频段(可选,见 §5)** | Google Books Ngrams 或 OANC | CC BY 3.0 / 无限制 | ✅ 明确允许 |

**为什么不是 NGSL 单独担纲**:NGSL 家族许可上完全够用(CC BY-SA 4.0,明文
"even commercially"),但它**没有 CEFR 等级**,而 FR-20 的四档要的正是等级切分点。反过来
CEFR-J 有等级、**没有频段**。这两件事不能互相替代,详见 §5 —— 它直接决定 §7.1 的切分点
用什么量来切。

## 2. 逐条核对 —— 可用的

### 2.1 CEFR-J Wordlist v1.6 ✅

| 项 | 内容 |
|---|---|
| 一手来源 | `https://cefr-j.org/download.html`(版权方自有页面,直取) |
| 许可 | **无标准 OSS / CC 许可** —— 版权方在自有页面上的自定义授权声明 |
| 日文原文 | 「本語彙表の著作権は東京外国語大学投野研究室に帰属する」/「適切な引用を行っていただければ研究教育および商用においても無償で利用できる」 |
| 英文原文 | "The copyright of this wordlist belongs to Tono Laboratory at TUFS" / "the list can be used for both research and commercial purposes with a proper acknowledgement of the source" |
| 商用 | **明文许可**,无偿 |
| 改编 | 免責事項 4:「本語彙表を改変して別の語彙表を作ることはかまわないが、必ず本語彙表を適切に引用しなければならない」—— 允许改编另造词表,只要求引用 |
| 义务 | **仅署名**。无 ShareAlike、无 NoDerivatives、无 NonCommercial |
| 规模 | 7,801 条,带词性 |
| 字段 | `headword` / `pos` / `CEFR` / `CoreInventory 1` / `CoreInventory 2` / `Threshold` |
| 等级 | **A1–B2**(无 C1/C2) |
| 频段 | **无** —— 只有等级,没有频次或频段 |
| 格式 | zip(内含 Excel:一张总表 + 每级一张) |
| 获取 | 需在页面同意「使用許諾」后下载 |

**一处必须写清的条款**:免責事項 2「商用利用に関しては、監修などを行う場合には別途相談の
上、必要な経費を請求する」—— 这是**为其编审背书收费**,不是使用数据本身收费。判据要的
「明确允许」由上面两段商用条款直接成立;这一条不构成对随包分发的收费门槛。但它是一句
需要如实记录的条款,而不是可以省略的细节。

**引用格式(必须照抄)**:
`The CEFR-J Wordlist Version 1.6. Compiled by Yukio Tono, Tokyo University of Foreign Studies. Retrieved from <URL> on dd/mm/yy.`
(页面自带的模板里字面写着占位符 `http:XXX`,须替换为真实 URL。)

**功能词与动词覆盖 —— 已实测,不是假设**。在 v1.5 CSV 上统计词性分布:
noun 4,091 / adjective 1,494 / **verb 1,349** / adverb 552 / pronoun 83 / preposition 76 /
determiner 46 / conjunction 37 / number 30 / **modal auxiliary 13** / be-verb 10 /
interjection 9 / do-verb 5 / have-verb 3 / infinitive-to 1。

场景 `slots.accept` 里实际用到的请求构式逐个命中:`can`=A1 modal、`may`=A1 modal、
`must`/`should`/`need`=A1 modal、`please`=A1 adverb(另有 B1 verb)、`want`=A1 verb、
`need`=A2 verb、`give`=A1 verb、`the`=A1 determiner、`of`=A1 preposition。

**一处对实现有直接影响的结构事实**:同形词按词性拆行(`can` 既是 A1 modal 又是 A2 noun;
`please` 既是 A1 adverb 又是 B1 verb)。**`headword` 不是唯一键** —— `game_vocab` 的词表
索引必须以 `(headword, pos)` 为键,否则同形词会互相覆盖,而覆盖方向取决于文件顺序。

版本问题:当前发布版为 **1.6(2020-03-24)**,页面给出 1.4→1.5、1.5→1.6 的逐词变更记录。
**未发现 v1.7**;也**未发现许可文本随版本变动** —— 同一段商用许可措辞出现在 1.6 材料处,
第三方 v1.5 镜像所附条款亦一致。1.5→1.6 变的是词条数据(如 `being`/`having` 补入 A1、
`tonne` 补入 B2、拼写变体合并),不是授权。

### 2.2 Octanove Vocabulary Profile C1/C2 v1.0 ✅

| 项 | 内容 |
|---|---|
| 一手来源 | `openlanguageprofiles/olp-en-cefrj` 仓库 README |
| 许可 | **CC BY-SA 4.0**(原文:"can be used under a Creative Commons Attribution-ShareAlike 4.0 International License") |
| 商用 | ✅ 允许(BY-SA 无 NC) |
| 义务 | 署名 + ShareAlike(见 §4 的 SA 边界分析) |
| 用途 | 补 CEFR-J 缺的 C1/C2 两级 |
| 体积 | `octanove-vocabulary-profile-c1c2-1.0.csv` = **46,462 bytes**(HTTP content-length 实测) |

同一仓库另附 `cefrj-vocabulary-profile-1.5.csv`(**233,214 bytes** 实测)。README 复述的
CEFR-J 条款与官方页面一致:"can be used for research and commercial purposes with no
charge"、"The copyright belongs to Tono Laboratory at TUFS"。

**注意授权不同源**:同一仓库里 CEFR-J 部分走版权方自授权,Octanove 部分走 CC BY-SA 4.0。
**两者不可混为一套许可**,署名与 SA 义务须分别落实。

### 2.3 NGSL 家族 ✅(授权可用,但不承担等级骨架)

| 项 | 内容 |
|---|---|
| 一手来源 | `https://www.newgeneralservicelist.com`(每份列表页各自声明) |
| 许可 | **CC BY-SA 4.0**,五份逐页同文:"New General Service List by Browne, C., Culligan, B., and Phillips, J. is licensed under a Creative Commons Attribution-ShareAlike 4.0 International License." |
| 商用 | ✅ 明确 —— deed 原文 "copy and redistribute the material in any medium or format for any purpose, **even commercially**" |
| 义务 | 署名(作者名 + 版权声明 + 许可声明 + 许可正文链接 + 是否修改)+ ShareAlike |
| 等级 | **无 CEFR** |
| 频段 | ✅ 有,但**只在 "basic statistics" 文件里**(SFI + rank;NAWL / BSL 另有 `Band` 列) |
| 词性 | 不在 stats / lemmatized 文件里;仅 `NGSL_12_with_English_definitions.xlsx` 有 word/POS/definition 三元结构 |
| 获取 | 直链、**无注册无邮箱无 EULA**,全部 HTTP 200 |

规模与体积(逐个下载解析,不是页面转述):

| 列表 | 实际条数 | 页面宣称 | stats CSV 体积 |
|---|---:|---|---:|
| NGSL 1.2 | 2,809 | 2809 | 62,566 bytes |
| NGSL-S 1.2 | 721 | — | 17,394 bytes |
| NAWL 1.2 | 957 | — | 25,103 bytes |
| TSL 1.2 | 1,250 | — | 32,010 bytes |
| BSL 1.2 | **1,744** | "1700-word list" | 59,643 bytes |

另 `NGSL_12_lemmatized_for_teaching.csv` = 73,146 bytes。

功能词命中带 rank:`can` 38、`want` 76、`give` 77、`need` 90、`may` 97、`please` 471,
另 `will` 28、`would` 36、`could` 66、`should` 89、`must` 160。

**两处数据脏点,进实现前必须处理**:① BSL 页面宣称 1,700 而 `BSL_120_stats.csv` 实为
1,744 数据行,表头带尾随垃圾列与一个游离值 `581.3333333`;② BSL 文件名用 `BSL_120_*`,
不是其余四份的 `_12_` 模式 —— 按统一模式拼路径会 404。

**一处许可覆盖范围的边界**:页面注明 NGSL 的编制使用了经批准访问的 **Cambridge English
Corpus**。CC 许可覆盖的是**产出的词表**,不是底层语料。我们只分发词表,不触底层语料。

## 3. 逐条核对 —— 不可用的

| 候选 | 许可 | 为什么不可用 |
|---|---|---|
| **Kelly English** | **CC BY-NC-SA 2.0**(`https://ssharoff.github.io/kelly/`,原文 "The lists are available under the CC BY-NC-SA 2.0 license.") | **NC 直接否决**。原文:"You may not exercise any of the rights granted to You in Section 3 above in any manner that is primarily intended for or directed toward commercial advantage or private monetary compensation." SA 另外独立地与闭源再分发冲突 |
| **EFLLex**(UCLouvain CENTAL) | **CC BY-NC-SA 4.0**(下载页原文) | 同上,NC 否决。**且格式不合用**:113 列的**逐级频次矩阵**,不是已判定的 CEFR 等级 —— 等级要自己派生(如取首个非零频次的级),那是净新增的判定逻辑与新的误差来源 |
| **Cambridge EVP / English Vocabulary Profile** | 保留所有权利 | **明文点名本用例**:"any software programmes based on the EVP data intended to be produced, published and made available for sale" 属禁止之列,需 CUP 事先书面同意。且**只能在线浏览,无批量下载** —— 法律门槛之前先卡在工程上 |
| **Oxford 3000 / 5000** | 未授予再分发权 | 无任何允许随包分发的授权文本 |
| **SUBTLEX-US / UK** | **CC BY-NC-ND 3.0**(存档页),现行页**无任何许可文字** | NC 与 ND **各自独立**否决。且这是比「没写许可」更差的一种状态,见 §6 |
| **COCA / wordfrequency.info** | 专有付费 | **付费也买不到再分发权**。原文:"In no case can the word frequency data be distributed beyond the university or company that purchased the data. A small, unique change has been made to each dataset that is sold, and this can serve as a 'fingerprint' to identify you as the unique source of the data." 另有条款禁止让终端用户看到精确频次或排序 |
| **google-10000-english** | 名义免费,实非 | 作者自陈未取得 LDC 许可前不得商用 |
| **wordfreq** | 代码 Apache-2.0 / 数据 CC BY-SA 4.0 | 授权上可商用,但**数据内含 SUBTLEX**,依据的是 Brysbaert 给作者的**私人邮件许可**,那不是可供第三方独立依赖的公开授权。README 另明确拒绝 CSV 转换("The CSV format does not have any space for attribution or license information")。**混合来源不同许可,不满足「逐条核对」** |
| **UD English-EWT** | 标注 CC BY-SA 4.0,底层文本为 LDC2012T13 | 上游有权利负担,不满足「明确允许」 |
| **OPTED** | 公有领域内容,附条件 | "if the material is to be included in commercial products, Project Gutenberg should be contacted first" —— 需先联系,故当前不是「明确允许」 |

可用但本轮不选的频段源(留作 §5 的备选):**Google Books Ngrams**(CC BY 3.0,最干净)、
**OANC**(无限制、明确允许商用,TAB 分隔 word/lemma/POS/count,239,208 词型)、
**Open English WordNet**(CC BY 4.0,词性最佳)、**hermitdave/FrequencyWords**
(内容 CC BY-SA 4.0,`en_50k.txt` 623 KB / `en_full.txt` 20 MB,**无词性**)、
**BNC Leech/Rayson**(CC BY-SA 2.0 UK,18,089 行 / 447 KB,**带词性**)。

## 4. ShareAlike 的边界(影响选型,必须写死)

选定组合里 Octanove 与(若采用)NGSL 都是 CC BY-SA 4.0。SA 约束到哪为止,直接决定它能不能
用在闭源商业产品里:

- SA 约束的是**词表数据及其改编物**,不是本 App 的源码。把词表文件**原样**随包分发在专有
  代码旁边属于聚合(4.0 正文虽已不用 3.0 的 "Collection" 一词,聚合本身仍不产生
  Adapted Material),**不传染源码**。
- 重排、合并、加列则产生 **Adapted Material**,该派生词表必须以 BY-SA 4.0 或更高版本发出。
- 因此**实现约定**:词表以**原样资产文件**随包,派生索引在运行时构建、不落盘、不分发。
  不要在构建期把它转成自有格式再打包 —— 那就是在分发 Adapted Material。
- 4.0 正文另有 "No downstream restrictions":不得对许可材料附加额外条件或施加有效技术措施
  以限制被许可权利的行使。词表资产因此**不能加密或混淆**。

以上是对许可文本的技术性阅读,不是法律意见。

## 5. 频段 vs 等级 —— 一个会波及 42 个场景的选择

CEFR-J **只有等级、没有频段**;NGSL **只有频段、没有等级**。这不是可以含糊过去的字段差异,
因为场景库已经在用频段说话:

对 `desktop/backend/core/game_scenarios/` 全部 42 个场景统计
`provenance.frequency_basis` 的措辞 —— **42/42 引用「需求金字塔」层级,其中 25 个明确以
「频段」为依据**(如「所需词汇全部落在分级词表最低频段」)。

后果是确定的:**只选 CEFR-J,这 25 条 `frequency_basis` 声明就核不了** —— G3 要求逐条核
provenance,而「最低频段」在一份没有频次列的词表上不是一个可判定的命题。三条出路,选哪条
属于设计决策,须在进入实现前定:

1. **改写这 25 条 provenance,把「频段」换成 CEFR 等级。** 最小改动,且让声明与实际数据源
   对齐。代价:改的是已通过结构核对的场景文件。
2. **同时随包 NGSL stats,频段与等级各司其职。** 两份许可分别落实署名(一份自授权、一份
   BY-SA)。代价:体积与两套键对齐(NGSL 是 lemma,CEFR-J 是 `(headword, pos)`)。
3. **以 Google Books Ngrams / OANC 作频段源。** 许可最干净,但要自己做频段切分,又多一个
   派生步骤。

本文档不替这个决定拍板 —— 它改的是 §7.1 切分点用什么量来切,以及 G3 的 provenance 是否
逐条可核。**但必须在实现前定,不能留给实现时随手选一个。**

## 6. 核实不到的 / 互相矛盾的（如实记录）

- ~~**CEFR-J v1.6 zip 的实际解压体积未核实。**~~ —— **已闭合(2026-08-09)**,见 §8.1 / §8.2。
  当时的情况如实保留:官方下载需在页面同意使用許諾,两个猜测的直链
  (`CEFRJ_wordlist_ver1.6.zip`、`CEFR-J_Wordlist_Ver1.6.zip`)均 **HTTP 404**;
  `download.html` 本体 HTTP 200(70,960 bytes);当时唯一实测到的是第三方镜像的
  **v1.5 CSV = 233,214 bytes**。用户已在官方页面同意許諾后手动下载 v1.6,
  实测 zip 1,089,155 bytes / 解压 1,097,188 bytes、含它的冷启动 76.4 ms ——
  判据要求的两个数字**均已记录**。
  留作方法论记录:这一项从头到尾**不可脚本化**,绕过许可门本身就是本门禁止的事。
- **Cambridge EVP 的条款currency 未核实。** englishprofile.org 已重建为 JS 渲染的
  Bubble.io 应用,所试的每个条款 URL 均 404;`vocabulary.englishprofile.org` 不再解析,
  存档副本 HTTP 401(原本在免费注册后才可见)。§3 引用的是 CUP 自有页面的**存档**
  (2019 / 2021 / 2023 三个快照文本一致)。**措辞的时效性标记为未核实**,实质内容是 CUP 自己
  的原文。这不影响结论 —— 它本来就不可用。
- **SUBTLEX 的 NC-ND 结论来自 Wayback 快照,因为原站已不存在。** crr.ugent.be 已下线
  (Brysbaert 的占位页称站点 "under reconstruction"),现行 UGent 托管的 SUBTLEX-US 页面
  **零许可文字**(licen / copyright / commercial / cite 全部无命中)。所以现存的唯一许可
  证据就是那份 NC-ND。这比「没写许可」更差:不能推定宽松。
- **Kelly Swedish 与 Kelly English 的许可自相矛盾。** Språkbanken 页面正文写瑞典语表为
  "CC-BY-SA 3.0, LGPL 3.0",而同页下载表把 `kelly.xml` 与 `Swedish-Kelly_M3_CEFR.xls`
  标为 **CC-BY-4.0**。两者互相矛盾。**都不适用于英语表** —— 英语表按 Leeds 页面是 NC。
  不要被瑞典语侧较宽松的元数据误导成「Kelly 项目是 CC BY」。
- **`newgeneralservicelist.org` 已失效并被重新注册,现供赌博联盟垃圾内容**(标题
  "Chicken Road Game Gambling 2025",页脚 "Copyright © 2026 Chicken Road Game Gambling")。
  而 **NAWL 与 BSL 的官方推荐引用格式仍指向这个已死域名**。因此:**引用一律写 `.com`**,
  且**任何文档或 UI 都不得把用户导向 `.org`**。已通过 Wayback 快照(`web/20190601000000`)
  确认旧 `.org` 声明的是同一份 CC BY-SA 4.0,所以域名迁移**没有**改变授权。
- **GitHub 镜像不具授权效力。** `yuliu142/ngsl-learn`、`evan-007/ngsl-dictionary`、
  `David-Waite/SpellingApp` 等第三方应用内嵌 NGSL 数据且**完全没有 LICENSE 文件**
  (API 的 license 字段为空)。不存在官方 Browne/Culligan 仓库。**不得从这些镜像取数据,
  也不得依赖它们暗示的许可。**
- 两个项目(NGSL、Kelly)都**没有独立的 LICENSE 文件或正式使用条款文档**,授权仅依赖网页上
  的一句内联声明。这一点如实记录,但不改变结论 —— 判据要的是「明确允许」,一句明确的内联
  声明满足这一点。
- 未核实 Kelly 的希腊语、挪威语、意大利语等其他语言表(与本模块无关)。
- anc.org 的 **TLS 证书已过期**(核对 OANC 时是刻意绕过的)。若日后采用 OANC 作频段源,
  这一点会影响下载脚本。

## 7. 结论与放行状态

**G4 授权侧:通过。** CEFR-J v1.6(商用明文许可,仅署名)+ Octanove C1/C2(CC BY-SA 4.0)
构成一个满足判据的组合;NGSL 家族(CC BY-SA 4.0)作为频段侧的可用选项。所有结论均来自
一手来源,矛盾与不可核实项已在 §6 单列。

**G4 体积与延迟侧:通过(2026-08-09 补测,含 CEFR-J)。**

| 项 | 状态 |
|---|---|
| Octanove C1/C2 CSV | ✅ 46,462 bytes 实测 |
| CEFR-J v1.6 zip 解压体积 | ✅ **1,097,188 bytes 实测**(zip 1,089,155) |
| NGSL 1.2 stats CSV | ✅ 62,566 bytes 实测 |
| **随包三份合计(解压后)** | ✅ **1,206,216 bytes(1.15 MiB)** |
| **首次启动延迟 vs NFR-3** | ✅ **冷启动 76.4 ms** vs 1,000 ms 预算 —— 余量 13× |

参考:CEFR-J v1.5 CSV(第三方镜像)233,214 bytes、NGSL 家族其余 stats CSV
17,394–62,566 bytes,均为选型期实测,不属随包资产。

以上体积量级(合计约 1.15 MiB)相对 NFR-4② 的 935 MiB 模型总量可忽略,**因此 §1「附带影响」
里担心的「词表体积会改动分发体积数字」在这个组合上不成立** —— PRD 的体积记录无需修正。
这句话现在覆盖**全部三份随包资产**,不再有未核实的缺口。

**进入实现前仍须定的三件事**(都不属于本门,但由本门的结论逼出来):

1. **§5 的频段/等级取舍** —— 直接决定 §7.1 切分点与 25 条 `frequency_basis` 是否可核。
   **已定(2026-08-08):两份都随包,但分工与本节原先的设想相反,见 §8。**
2. **词表索引以 `(headword, pos)` 为键** —— CEFR-J 同形词按词性拆行,`headword` 不唯一。
   **已实测证实,见 §8。**
3. **词表以原样资产文件随包,不在构建期转格式** —— §4 的 SA 边界要求。
   **已落实**:`scripts/fetch_game_wordlists.py` 原样落盘,
   `desktop/backend/assets/wordlists/ATTRIBUTION.md` 分别落实两套署名。

**G4:通过(2026-08-09)。** 判据两条 —— 授权明确允许随包再分发、体积与首次启动延迟
记录在案 —— **均已成立**,且延迟数字含 CEFR-J,不再是「不含它的那个 5.6 ms」。

此前记为「授权通过、体积部分通过、延迟待测」的那一半,是靠**用户手动完成官方許諾同意流程
并落盘 v1.6** 才闭合的 —— 这一步无法脚本化,而绕过许可门本身就是本门禁止的事。
如实记录:G4 是本轮唯一从「部分通过」走到「通过」的门。

**G4 的通过不改变模块的放行状态。** 它是前置门,不是 P0 门;R-14 的 P0 三门(G1 / G2 / G3)
仍无一完成,**模块仍不得进入实现**。

## 8. 实测回填(2026-08-08 本轮)

用户已拍板 **CEFR-J(等级)+ NGSL(频次)两份都随包**。资产落盘与两个数字的测量脚本:
`scripts/fetch_game_wordlists.py`(原样获取 + SHA-256)、`scripts/game_vocab_gate.py`
(体积 + 冷启动索引耗时)、`scripts/game_provenance_check.py`(42 场景逐词查 NGSL)。

### 8.1 已获取资产(SHA-256 可复现)

| 资产 | 字节 | 与本文档 §7 记录 | SHA-256 |
|---|---:|---|---|
| `octanove-vocabulary-profile-c1c2-1.0.csv` | 46,462 | ✅ 一致 | `18c33a40…f7b380` |
| `NGSL_12_stats.csv` | 62,566 | ✅ 一致 | `2098bab8…5a0b44` |
| `CEFRJ_wordlist_ver1.6.zip` | 1,089,155 | ✅ **已由用户手动下载并落盘** | `c837d2c0…03a37a` |

三份资产字节数与 §7 记录**逐字节一致**,故本文档的体积数字可复现。CEFR-J 由用户在官方
页面同意使用許諾后下载(2026-08-09),zip 内单一成员 `CEFR-J Wordlist Ver1.6.xlsx`。

### 8.2 体积与首启延迟:**两个数字均已完整实测(含 CEFR-J)**

原先只有 Octanove + NGSL 的 5.6 ms,已作废并替换 —— 那个数字不含 CEFR-J,不构成
G4 延迟侧的证据。补入 CEFR-J 后重测:

| 项 | 实测 | 判据 |
|---|---:|---|
| CEFR-J v1.6 解压后 | 1,097,188 bytes | —— |
| Octanove C1/C2 | 46,462 bytes | —— |
| NGSL 1.2 stats | 62,566 bytes | —— |
| **三份合计(解压后)** | **1,206,216 bytes(1.15 MiB)** | 相对 NFR-4② 的 935 MiB 模型总量可忽略 |
| **冷启动构建完整索引** | **76.4 ms**(warm 72.4 / 65.7) | NFR-3 参考预算 1,000 ms —— **余量 13×** ✅ |

含 xlsx 解析的完整索引仍在预算内一个数量级以上,**G4 判据要求「记录在案」的两个数字
至此都有真实测量值**,PRD 体积记录无需修正(仍不足 1.2 MiB)。

### 8.3 `(headword, pos)` 复合键:实测证实,且不止 CEFR-J

原判断的依据是 CEFR-J 同形词按词性拆行。实测发现**仅 Octanove 一份**就有 **121** 条会在
裸 `headword` 键下互相覆盖(2,076 条 → 1,955 个不同 headword)。复合键因此不是
CEFR-J 专属的处置,而是**所有等级资产的共同要求**。

**补入 CEFR-J 后的完整索引形状**(替代上面那组仅 Octanove 的数字):
**9,962 条词条 / 8,827 个不同 headword → 1,135 条同形词会在裸键下丢失**。
两个点名探针现在各自独立成条:`can` = A1 modal auxiliary + A2 noun,
`please` = A1 adverb + B1 verb —— 此前报「未收录」正是因为它们的 A1/A2 义项在
CEFR-J 里,而 Octanove 只有 C1/C2。请求构式所需的八个功能词
(`can` / `may` / `must` / `should` / `need` / `please` / `want` / `give`)**全部 A1**。

### 8.3.1 解析 v1.6 xlsx 时踩到的两件事(会影响数字正确性)

1. **只能读 `ALL_sep` 一张表。** v1.6 把同一份词汇以三种重叠形态装在 11 张表里:
   `ALL`、按级子集 `A1`..`B2`、以及各自的 `_sep` 变体。读全部表会把每条词条**重复计三次**
   (首轮误算为 10,209 条 / 1,144 同形词)。选 `ALL_sep` 而非 `ALL` 的理由是前者
   **一行一个 headword**,而 `ALL` 把拼写变体压在同一格里(`adviser/advisor`、
   `a.m./A.M./am/AM`,179 处),复合键无法为其建索引。
2. **`README` 表会污染等级分布。** 该表的日文说明段落与 Excel 序列号日期(`42554`)会落进
   被当作等级的列。已按「等级值必须是 A1..C2 之一」过滤;实测该过滤在 `ALL_sep` 上
   **丢弃 0 行**,即它只挡文档表,不误伤词条。

### 8.3.2 两份词表对 95 个词给出**冲突等级** —— 优先级决定 tier 准入

这是补入 CEFR-J 才暴露的问题:**95 个 `(headword, pos)` 被两份词表同时收录且等级不一致**
(重叠 95 个,无一相同)。样例:`battery` CEFR-J A2 / Octanove C1,`agency` A2 / C2,
`complexity` B2 / C1。

按 §7.1「等级定准入」,**谁赢就决定 `infant` 档能不能说这个词** —— 因此这不是实现细节。
已在 `build_index` 里**显式写死 CEFR-J 优先**并附理由:CEFR-J 是按教学习得顺序定级的
A1–B2 骨架,Octanove 在本项目的职责只是**向上补 C1/C2**,不重新给 CEFR-J 已判定为
学习者可及的词升级。此前该优先级由两次 `extend` 的先后顺序**偶然**决定,与
`(headword, pos)` 键的教训同类:**依赖读取顺序的正确性不算正确性。**

实测这 95 个里**只有 1 个出现在任何场景的必需槽位**:`safety-report-lost-bag` 的
`lost_event` 槽用到 `behind`(CEFR-J A1 / Octanove C1),采用 A1 —— 方向正确,
"behind the seat" 的方位义确实是 A1,Octanove 的 C1 针对的是引申义。
**即 95 条冲突对现有 45 个场景的准入判定实际影响面为 1 个词,且该词判对了。**

### 8.3.3 §7.1「等级定准入」现在是可执行判据,不只是文档主张

词表落盘后,§7.1 的四档准入表第一次可以**在真实场景上验证**而不是声明。
`game_vocab_gate.py::check_tier_reachability` 实测 **109 个必需槽位**:

| 结果 | 数 | 含义 |
|---|---:|---|
| 至少一条该 tier 可达的说法 | **109** | ✅ |
| 全部说法都超出准入上限 | **0** | 该 tier 学习者按定义说不出 —— 会是场景 schema 缺陷 |
| 无法判定(全部说法都不在两份词表内) | **0** | 零证据,既非通过也非失败 |

判据取「**存在可达路径**」而非「每条说法都在纲内」:`accept` 集合是多选一,
单个超纲同义说法不构成缺陷。实测确有 18 处超纲**单项**(如 youth 档 `throat`#B2、
toddler 档 `freezing`#B1),但它们所在槽位都另有 A1/A2 说法,因此**不是缺陷** ——
这正是把判据定在「路径」而非「逐词」的理由。

**这个检查自己先没通过负向对照。** 首版把「整条说法一个词都没有等级」与「可达」合并,
结果给一个**故意构造为不可满足**的 infant 槽位(`accept` 只留 B2 词)判了通过。
修正为三值:`within` / `above` / `ungraded`,并把「全部说法皆无等级」单列为**无法判定**。
负向对照现在三条都成立:B2-only 槽位→检出、全无等级→标记无法判定、有 A1 路径→通过。
如实记录,因为它是 R-12 那条教训的同类:**一条绿着的测量可能在报它没测的数。**

另记一处必须处理的查表假象:必需槽位里有 58 个词以**屈折形**出现(`days` / `hurts` /
`wrote` / `shoes`),而两份词表都是 lemma 键 —— 不做还原就会报成「58 个词无等级」。
已按查表侧的粗还原处理(仅用于放宽查询,**不写回场景数据**),与
`game_provenance_check.py` 里 NGSL 侧的同类假象是同一处理原则。
真正两份词表都不收的只有 6 个:`porridge` / `cord` / `walkway` / `pills` / `tablets` / `aches`。

另记一处**上游数据脏点**:`octanove-…csv` 第 2129 行 `remonstrate,vern,C2` ——
`vern` 是 `verb` 的拼写错误。**不修**:改动即产生 Adapted Material(§4),
对齐层须容忍该值。

### 8.4 频段与等级的分工,与 §5 的设想相反

§5 假定两份词表「各司其职」即可,并把频段留作可选。实测推翻了其中一半:
**频次排名不能用于四档准入切分,只能用于同级内排序。**

`scripts/game_provenance_check.py` 对 42 个场景的必需槽位逐词查 NGSL SFI 排名,
结果是频次与本模块的场景难度**方向相反**:

| 类别 | 实测 NGSL 排名 |
|---|---|
| 请求构式(功能词) | `can`#38、`want`#76、`give`#77、`need`#90、`may`#97 —— 全在首百词 |
| 场景要求说出的具体物名 | `cup`#1491、`coat`#1863、`bread`#2262、`rice`#2695 —— 第二至三千段 |
| 完全不在 NGSL 2,809 词内 | `toilet`/`bathroom`/`restroom`/`washroom`/`wc` 五种说法**无一收录**;另 `soap`、`towel`、`blanket`、`apple`、`soup`、`porridge`、`fever`、`sore`、`thirsty`、`hungry` 等,共 **25 个内容词** |

NGSL 是为**阅读覆盖率**而建的 general service list,其结构性不收三类词,而这三类恰好是
生存场景的高频需求:

1. **基数词** —— `two`/`three`/`four`/`five`/`ten` 全不在表内,而 `one`#35 在
2. **星期与月份** —— 整类不收(`Thursday`、`Saturday` 场景各有一处依赖)
3. **低频具体家居物件** —— 上表第三行

后果直接:**若按频次排名做准入,`infant` 档会拿到 `can`/`want` 却拿不到 `bread`** ——
一个能说出请求句式、却没有任何东西可以请求的词汇库。等级表不存在这个问题(CEFR-J 按
教学习得顺序定级,具体物名在 A1 即有)。§7.1 的切分点因此**只用等级定准入**,
频次收窄为同级内排序与 NPC 用词「+N」上限。**这是被数据改掉的设计,不是偏好选择。**

### 8.5 那 25 条 `frequency_basis` 的实际核对结果

用户的两份都要决策让这些声明**重新可判定**,但可判定 ≠ 已判定 —— 场景写在词表选定
之前,「所需词汇全部落在最低频段」当时是作者判断而非查表结果。首轮核对结果:
**声明自列词越界 16 个、必需槽位词越界 19 个**,即**过半声明不成立**。
`please`#471 早已是那个提醒:直觉上的「最基础词」未必在最低频段。

已按实测改写 **23 个**场景的 `frequency_basis`(`scripts/reword_frequency_basis.py`,
其中 22 个为越界项、1 个为「低频段」歧义措辞的澄清)。改写机制上做了两处约束:

- 每条改写里引用的每个 `word#rank` **在写盘前逐个与 NGSL 实测排名校验**,
  任一不符即中止且不写任何文件 —— 避免把含糊声明换成错误数字。
- **只改 `provenance.frequency_basis`**,`slots` / `npc` / `reward` 逐字节不变;
  改写后重新核对 42 个场景的结构facts(层级 `{1:18, 2:12, 3:12}`、tier
  `{infant 8, toddler 15, youth 14, professional 5}`、`provenance` 42/42、`id` 唯一)
  **全部与 G3 已通过时一致**。

复核后 `game_provenance_check.py` 的两项越界计数**均为 0**。剩余 25 个 NGSL 未收录内容词
按结论归入等级侧定级,并在报告中单列 —— **不得当作「最低频」或「最高频」处理**,
把频次表的盲区当成场景难度是这一轮最容易犯的错。
