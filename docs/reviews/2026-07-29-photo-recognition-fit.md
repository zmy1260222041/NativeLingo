# R-13（2026-07-29）端侧识物 + 情景质量门

> 范围：FR-13 / FR-14 / FR-15 / NFR-5
> 当前结论：宏观模型已直接切换为 YOLOE-26S-PF；工程链路完成，正式手标质量门仍待完成。

## 1. 固定实现

- 宏观整件：`core/vision.py`，YOLOE-26S-PF detection-only 动态 ONNX，onnxruntime CPU。
- 微观部件：`core/parts.py`，Florence-2-base-ft，只分析用户点击后的裁剪图。
- 情景例句：`core/scenario.py`，Qwen2.5-0.5B-Instruct Q4_K_M + llama.cpp。
- 接口：`/memorize/analyze`、`/memorize/parts`、`/memorize/scenario`。
- 三类请求均有前端 AbortController 和后端 15 秒 deadline，不允许无限加载。

宏观路径不再调用 Florence 做整图后台补充。上传图片的 YOLOE 结果就是最终结果，
前端也不再轮询 enrichment 接口。

## 2. YOLOE 导出与误报治理

官方来源为 `ultralytics/assets` v8.4.0 的
`yoloe-26s-seg-pf.pt`（32,696,887 bytes）。NativeLingo 导出为
45,190,231 bytes 的 detection-only ONNX，动态矩形输入，proposal confidence
0.10，最多返回 50 个候选。较低的导出阈值只负责保留候选，最终展示仍由每类运行时
阈值控制。

Prompt-Free 原始词表有 4,585 个标签，单纯提高统一阈值无法解决高置信动作词、场景词
和职业词误报。因此使用两层治理：

1. ONNX 图在全局 Top-K 前固化 177 个日常实体类别，避免非实体候选挤掉物品；除首轮的 `tree`、`grass`、`road`、`path`、`coffee machine`、`faucet`、`bus stop` 外，60 图复核又增加 22 个家居、户外、学习和工具词项。
2. 运行时只放行实体词表，按标签设置最小置信度，并做 class-agnostic IoU 0.72
   去重和包含式近义标签去重。

阈值按逐图复核调整。典型收紧项包括 `mirror`、`door`、`juicer`、`sun hat`。
`plaque` 使用 0.35 阈值；大图在主体尺度出现 `clock` / `cabinet` / `showcase` 时，只从同一 YOLOE 的 1280px 细节尺度补充横向牌匾。用户确认时钟下方的城市名牌属于可接受结果。不得用已经叠加检测框的 UI 截图反向校准原照片结果。

## 3. 60 张探索图集

图集位于 `data/photo_gallery/`，包含 30 张室内和 30 张室外公开日常照片。
最终结果见 `baseline-current.json`，复核图见 `review-overlays/`。

| 指标 | 结果 |
|---|---:|
| 图片数 | 60 |
| 最终检测框 | 237 |
| 唯一标签 | 79 |
| 中位延迟 | 54.6 ms |
| P95 延迟 | 242.2 ms |
| 零结果图片 | 6 |
| ONNX 大小 | 45,190,231 bytes |

逐图复核后的代表性结果：

- 浴室：`shower`、`lamp`。
- 洗衣店：6 个 `washing machine`，不再出现 terminal/elevator 等场景噪声。
- 客厅：沙发、时钟、风扇、地毯、音箱；同一风扇的近义重复已去除。
- 超市：购物车、陈列柜。
- 咖啡区和教室：扩词后新增咖啡机、水龙头。
- 公园和街景：长椅、汽车、交通标志、自行车、摩托车、公交车、花、树、草地、
  小路和道路；原 20 图子集仍全部有结果。
- 扩展场景：洗碗机、马桶、毛巾、床头柜、显示器、纸巾、工作台、凿子、
  电钻、锯子、人行横道、栅栏、消防栓、邮箱、跷跷板和滑梯均新增有效框。
- 原问题照片：640px 主体尺度保留 3 个时钟和陈列柜；1280px 细节尺度补充 3 块城市名牌，统一显示为 `plaque`。

这 60 张图没有人工 ground-truth box，因此只能支持模型切换和阈值调试，不能把
“逐图看起来合理”写成 precision/recall PASS。扩词前同一批图片为 208 个框、
62 个唯一标签、8 张空结果；扩词后为 237 / 79 / 6。剩余空结果不再通过统一降阈值
硬凑，因为停车场场景词会在普通道路上误报，而市场摊位、野餐桌等目标连 0.10
proposal 阈值都未达到。

## 4. 正式数字门

| 轨 | 指标 | PASS 判据 | 当前 |
|---|---|---:|---|
| 宏观 | precision（IoU≥0.5 且类正确） | ≥0.80 | 待手标集 |
| 宏观 | recall | ≥0.60 | 待手标集 |
| 宏观 | 单图图集中位延迟 | ≤200 ms | 54.6 ms ✅ |
| 宏观 | 模型体积 | ≤50 MB | 45,190,231 bytes ✅ |
| 微观 | 部件/内容物人工相关性 | ≥0.75 | 待人工评分 |
| 微观 | 不可见项幻觉率 | ≤0.15 | 待人工评分 |
| 情景 | 流畅度（1–5） | ≥4.0 | 待人工评分 |
| 情景 | 图片/部件贴切度（1–5） | ≥3.5 | 待人工评分 |
| 情景 | 对话自然度（1–5） | ≥3.5 | 待人工评分 |
| 情景 | 中英匹配 | ≥0.95 | 待人工评分 |
| 情景 | 图片事实臆造率 | ≤0.10 | 待人工评分 |
| RAM | 同驻峰值 RSS | ≤12 GB | 待测 |

## 5. 工程状态与后续

Phase F 工程决策已经锁定：

- YOLOE 直接替换 YOLOv8n，不做双模型整图协作。
- Florence 仅用于点击后的部件分析。
- Qwen Q4_K_M 实时生成多角色日常对话（2 位说话人 A/B、2–3 轮），不读取预制例句。
- 模型文件有固定大小、SHA-256 和 ONNX 元数据校验。
- 错误、模型缺失和超时均返回可读状态并清除前端加载遮罩。

剩余 Phase E 是正式质量评估：制作带框的手机实拍宏观集、部件人工参考集和情景盲评
集，运行 `scripts/photo_gate.py`，回填 precision/recall、微观幻觉率、情景评分与 RSS。

### 校准补充（2026-07-31）—— 装饰类物品阈值与前端降采样（终版）

`data/photo_gallery`（60 张）未覆盖 vase / sculpture / statue 类，故这三类的
`min_score` 一直是未校准的保守默认值（0.55 / 0.58 / 0.58）。

前端降采样是真实问题：`main.js` 的 `MEMO_MAX_DIM=1280` 把 1920 宽照片缩到 1280 再以
JPEG0.9 重编码，插值模糊小物体，使 IMG_0518 上装饰品分从 0.429 跌到 0.359。修复为
`MEMO_MAX_DIM` 1280 → **1920**（≤1920 宽照片不再降采样）。

曾尝试把三类 `min_score` 降到 0.35 以回收装饰品，经用户验证为**错误方向**：YOLOE 会
把雕塑摆件按形状归为 `vase`（0.43），在整图上画出误导性的花瓶框。因此：
- `yoloe_labels.json` **恢复原值**：vase 0.55 / sculpture 0.58 / statue 0.58。
- 装饰品不再由 YOLO 整图承担，改由 FR-14 **容器内容物增强**（Florence 命名 +
  phrase grounding）在点击容器后给出正确名称（statue / award）。
- 证据：恢复后 IMG_0518 无 vase 框，仅 clock×3 / cabinet / plaque×3；内容物视图仍
  正确返回 `statue`（雕像）+ `award`（奖章）。
- 待办：正式 R-13 手标集补入含这些类的实拍图，重跑 `scripts/photo_gate.py` 复核。

### 方案补充（2026-07-31）—— 容器内容物只做一层按需增强

IMG_0518 暴露了宏观检测与微观描述之间的职责缺口：YOLOE 整图能稳定定位时钟、
柜子、花瓶和牌匾，但漏掉柜内金色雕塑；对整图或柜子裁剪直接使用 Florence
`<DENSE_REGION_CAPTION>` 均只返回 shelf，不能把“详细描述里说出 statue”等同于
获得了可靠定位。柜子裁剪后再跑 YOLOE 也未找回雕塑，反而出现 book /
picture frame 等误报。

实测可行路径是：Florence 详细描述在柜子裁剪中给出 `gold statue` / `awards`，
再把候选合并为一次 `<CAPTION_TO_PHRASE_GROUNDING>` 请求；模型热态 grounding
约 0.2–0.5 秒，并能为本图的金色雕塑与奖项返回分离框。据此 FR-14 采用：

1. YOLOE 仍是唯一整图检测器，不恢复 Florence 整图后台补充。
2. 仅在用户点击显式容器标签后运行内容物增强，不阻塞第一屏。
3. Qwen 从详细描述中只提取独立、可见、有形实体；Florence 对全部候选联合
   phrase grounding。候选必须同时具备描述证据和有效框。
4. 结构词、泛化词、超大/超小框和重叠项经门控后剔除，最多保留 8 项。
5. 内容物以 `parent_id`、`relation=inside`、`depth=1` 返回；前端仅允许选择它生成
   情景，不允许再次打开详情。普通部件维持原流程，从数据契约上切断递归。

实现复核时，Qwen2.5-0.5B 对本图的内容物提取返回空数组，因此加入精度优先的
确定性回退：只从 Florence 详细描述中匹配实体词表里**明确出现**的名词，保留描述中
的复数形式用于 grounding，最终显示再归一为单数；该回退仍必须通过同一套 grounding、
父框几何和重叠门控，不能凭词表单独生成内容物。真实 `/memorize/analyze` →
`/memorize/parts` API 复跑为 200 / 200，总耗时 6.882 秒，返回：

- `statue`：`parent_id=3`、`relation=inside`、`depth=1`；
- `award`：同一父关系与深度；
- `shelf` 仍留在结构部件列表，不混入 contents。

该方案改善的是容器详情页的召回，不改变 FR-13 宏观 precision / recall 基线。
正式 R-13 微观集需增加陈列柜、书架、展示柜等含小物件照片，分别统计结构部件与
内容物的相关性、不可见项幻觉率和 grounding 定位有效率。
