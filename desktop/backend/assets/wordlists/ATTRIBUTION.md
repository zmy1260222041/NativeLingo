# 分级词表 —— 授权与署名

本目录的词表资产用于 FR-20 的分级词汇库。授权逐条核对记录在
`docs/reviews/2026-08-08-survival-g4-wordlist.md`(R-14 / G4)。

**三份资产走两套互不相同的许可。不可混为一套处理。** CEFR-J 是版权方在自有页面上的
自定义授权(非 CC、非 OSS);Octanove 与 NGSL 是 CC BY-SA 4.0。署名义务分别落实如下。

## 分发约定(适用于全部三份)

- **原样随包。** 词表以未修改的资产文件分发。派生索引在运行时构建,不落盘、不分发。
  **不得在构建期转成自有格式再打包** —— 那是在分发 Adapted Material,会触发
  BY-SA 的 ShareAlike 义务。
- **不得加密或混淆。** CC BY-SA 4.0 的 "No downstream restrictions" 条款禁止对许可材料
  附加额外条件或施加有效技术措施以限制被许可权利的行使。
- 重排、合并、加列会产生 Adapted Material,该派生词表必须以 CC BY-SA 4.0 或更高版本发出。

以上是对许可文本的技术性阅读,不是法律意见。

---

## 1. CEFR-J Wordlist Version 1.6

**文件**:`CEFRJ_wordlist_ver1.6.zip`(需人工从下载页同意使用許諾后取得)
**许可**:版权方自授权 —— **无标准 OSS / CC 许可**
**一手来源**:<https://cefr-j.org/download.html>

**授权原文**(版权方自有页面):

> The copyright of this wordlist belongs to Tono Laboratory at TUFS.
> The list can be used for both research and commercial purposes with a proper
> acknowledgement of the source.

日文原文:

> 本語彙表の著作権は東京外国語大学投野研究室に帰属する。
> 適切な引用を行っていただければ研究教育および商用においても無償で利用できる。

**义务:仅署名。** 无 ShareAlike、无 NoDerivatives、无 NonCommercial。

**必须照抄的引用格式**(页面自带模板,占位符已替换为真实 URL):

```
The CEFR-J Wordlist Version 1.6. Compiled by Yukio Tono,
Tokyo University of Foreign Studies.
Retrieved from https://cefr-j.org/download.html on 09/08/26.
```

**一条需如实记录的条款**(免責事項 2):

> 商用利用に関しては、監修などを行う場合には別途相談の上、必要な経費を請求する。

这是**为版权方的编审背书收费**,不是为使用数据本身收费。上面两段商用许可条款直接成立,
本条不构成对随包分发的收费门槛。

改编条款(免責事項 4)允许改编另造词表,只要求引用本表。

---

## 2. Octanove Vocabulary Profile C1/C2 v1.0

**文件**:`octanove-vocabulary-profile-c1c2-1.0.csv`(2,136 词条)
**用途**:补 CEFR-J 缺失的 C1 / C2 两级
**一手来源**:<https://github.com/openlanguageprofiles/olp-en-cefrj>

**许可**:**CC BY-SA 4.0**
许可正文:<https://creativecommons.org/licenses/by-sa/4.0/legalcode>

> Octanove Vocabulary Profile C1/C2 by Octanove Labs is licensed under a
> Creative Commons Attribution-ShareAlike 4.0 International License.

**修改声明**:本项目**未修改**该文件,原样随包分发。

注意:同一仓库同时托管 CEFR-J 词表与本文件,但**两者授权不同源** —— CEFR-J 部分走
第 1 节的版权方自授权,本文件走 CC BY-SA 4.0。

---

## 3. New General Service List (NGSL) 1.2 — basic statistics

**文件**:`NGSL_12_stats.csv`(2,809 词条,含 SFI Rank 与频次)
**用途**:提供频次排序量 —— CEFR-J 只有等级、没有频次列
**一手来源**:<https://www.newgeneralservicelist.com>

**许可**:**CC BY-SA 4.0**
许可正文:<https://creativecommons.org/licenses/by-sa/4.0/legalcode>

> New General Service List by Browne, C., Culligan, B., and Phillips, J.
> is licensed under a Creative Commons Attribution-ShareAlike 4.0
> International License.

**修改声明**:本项目**未修改**该文件,原样随包分发。

**引用一律使用 `.com` 域名。** `newgeneralservicelist.org` 已过期并被重新注册,现供
赌博联盟垃圾内容 —— 而 NAWL 与 BSL 的官方推荐引用格式仍指向那个已死域名。任何文档或 UI
**不得**把用户导向 `.org`。Wayback 快照确认旧 `.org` 声明的是同一份 CC BY-SA 4.0,
域名迁移**没有**改变授权。

**一处许可覆盖范围的边界**:NGSL 的编制使用了经批准访问的 Cambridge English Corpus。
CC 许可覆盖的是**产出的词表**,不是底层语料。本项目只分发词表,不接触底层语料。

---

## 未采用的候选(为何不在此目录)

逐条理由见 `docs/reviews/2026-08-08-survival-g4-wordlist.md` §3。摘要:
Kelly English 与 EFLLex 带 **NonCommercial**;Cambridge EVP 保留所有权利且其禁止条款
字面点名「基于 EVP 数据、拟出版销售的软件程序」;Oxford 3000/5000 未授予再分发权;
SUBTLEX 为 **NC-ND**;COCA 付费亦不含再分发权(且售出数据带指纹水印);wordfreq 混合
不同许可来源且内含依私人邮件许可的 SUBTLEX 数据;UD English-EWT 底层文本有 LDC 权利负担。
