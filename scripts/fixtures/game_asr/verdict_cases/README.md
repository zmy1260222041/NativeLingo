# `well_pronounced` 标注格式示例 + 裁决逻辑回归 fixture

这四份 manifest 同时承担两件事:

1. **格式示例** —— `../README.md` §4.1 只用文字描述 `well_pronounced` 的标注口径,
   而 `../manifest.json` 尚待采集,标注者没有可照抄的东西。`labelled-full.json`
   就是那份可照抄的样例(含 (A)/(B) 两类各自的标法)。
2. **回归 fixture** —— 覆盖 `game_asr_gate.py` 裁决分支的四条路径。
   跑法:`python -m scripts.game_asr_gate --self-test`(不加载 whisper)。

**零音频、零隐私成本**:`transcript` 字段是手写的,不对应任何真实录音。因此这四份
**不是语料**,任何数字都不可回填 R-14 —— 它们只证明打分与裁决逻辑本身没写错。

| 文件 | 标注覆盖 | 判据口径 | 期望裁决 | 测到什么 |
|---|---|---|---|---|
| `labelled-full.json` | 5/5 | 发音合格词 1.000(7/7);合并 0.700(7/10) | **PASS** | (A) 类漏词((B) 全中)不拉低判据数字 —— 判据口径与合并口径分离成立 |
| `labelled-full-fail.json` | 2/2 | 发音合格词 0.500(2/4) | **FAIL** | (B) 类失效全额受门,并打印降级路径 (a)(b)(c)。另无 `scenario` 字段,顺带测「无槽位归属」警告 |
| `labelled-none.json` | 0/3 | 合并 0.833(5/6),标注为**退化** | **FAIL** | 全无标注时按评审文档退回合并口径,**仍出裁决**但口径标为退化 |
| `labelled-partial.json` | 2/3 | 已标注子集 0.667(2/3),**不构成裁决** | **INCONCLUSIVE** | 部分标注比全无更糟 —— 自选择子集上的数字看起来跟真判据一样。另含一处标注错误(`please` 不在 `expected_keywords` 里),顺带测 stray 警告 |

`labelled-none.json` 的合并召回 0.833 是**故意压在 0.85 之下**的:若它给 PASS,
「退化口径」这个标注就成了摆设 —— 退化口径同样要能出 FAIL。
