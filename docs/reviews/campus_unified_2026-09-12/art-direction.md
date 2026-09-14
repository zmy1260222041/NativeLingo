# 校园美术统一 · 制作说明

状态更新（2026-09-14）：六处背景与八名真实 alpha 人物已接入，用户明确授权后完成本地抠图与边缘检查。详见 [制作与试玩记录](../campus_art_2026-09-12/README.md)。下方 CLI/API 方案为历史计划，实际使用内置 imagegen。

## 已确定的视觉基准

沿用 `game/assets/novel/settlement_atlas.png` 的温暖自然光、手绘建筑细节、植物层次和清晰插画线条；沿用 `cast_atlas.png` 的人物绘制精度及轮廓清晰度。主体为虚构美国本科校园与成年人物，不复制小镇外星角色，也不虚构玩家个人背景。UI 继续使用暖纸白、鼠尾草绿、黄铜棕，宋体叙事与无衬线操作文字。

构图按照已实现的 1440×900 舞台：顶栏 88px；左侧导航覆盖 x24–268；对白覆盖 x292–1416、y572–868。背景的重要地标保留在右上与中央，人物上半身出现在 x760–1310、y180–572。背景不含人物、文字、品牌和 UI。立绘使用透明 PNG，人物轮廓必须可分离；不把纯色背景冒充透明素材。

## 六处背景

每幅 16:9，建议 1536×864 或 2048×1152；输出名称与目的如下。

| 文件 | 内容与构图 |
| --- | --- |
| class.png | 红砖教学楼外的林荫步道、开着的教室门、长椅与暖光窗户；普通美国校园，非真实大学复刻。 |
| study.png | 有木桌、书架、绿植和高窗的学习空间；一角能看见校园草坪，桌面留出未占用的学习位置。 |
| club.png | 社团活动中心的共享起居区；软木板、折叠桌、相机与活动材料，海报不含可读文字。 |
| dining.png | 温暖明亮的校园餐饮区；木质桌椅、明确的食物柜台、窗边安静座位，不画品牌或菜单文字。 |
| sports.png | 树木环绕的校园运动区与多用途活动场地；不强行指定玩家所玩的运动，不画任何不必要的比赛规则。 |
| home.png | 干净但有人生活的学生住处一角；书桌、台灯、床、外套和窗边绿植。画面不推断玩家住宿人数、专业或私人经历。 |

共同提示词：

> Original illustrated visual-novel background for a fictional American undergraduate campus, painted at the same finish as the reference game's warm hand-drawn settlement: confident fine linework, rich but restrained material details, soft golden natural light, layered sage foliage, terracotta and warm stone, gentle atmospheric depth. Comfortable everyday scale, lived-in but orderly. Landscape 16:9. No characters, no lettering, no brands, no UI, no watermark. Keep important landmarks out of the leftmost 20 percent and lower 35 percent because game panels cover them. [Insert location description above.]

## 八名常驻人物

每人独立立绘，建议 1024×1536，膝上构图、自然站姿、可辨认手势和清晰轮廓。角色为成年美国本科生或成年工作人员，画风统一，身体比例可信。

| 文件 | 人物方向 | 固定声音 |
| --- | --- | --- |
| alex.png | 通勤的成年男学生；鼠尾草绿夹克、帆布包、拿着折起的笔记，认真而平等。 | leo |
| maya.png | 喜欢故事与校园广播的成年女学生；赤陶色针织外套、一本书，放松但不过度热情。 | eve |
| jules.png | 喜欢数据与摄影的成年学生；眼镜、蓝灰衬衫、相机带，思考中的中性表情。 | ara |
| sam.png | 兼顾工作的成年男学生；深肤色、燕麦色衬衫、手表和背包，友好但时间有限。 | rex |
| riley.png | 成年男社团组织者；棕绿休闲外套、活动文件夹，自信务实。 | leo |
| casey.png | 成年女运动伙伴；低饱和运动服、棒球帽和水瓶，精神集中、自然健康。 | eve |
| prof_chen.png | 成年男教师；灰绿开衫、眼镜和笔记，专注聆听，不摆讲课姿态。 | rex |
| tavi.png | 成年女餐饮工作人员；燕麦色围裙与深色工作衫，忙碌而专业，不沿用小镇外星人外貌。 | ara |

共同提示词：

> Original adult human character portrait for the same illustrated campus visual novel as the reference game. Detailed hand-drawn linework, softly painted warm light, believable adult proportions, restrained cloth texture, individual facial features, natural hands, calm everyday expression rather than a promotional smile. Standing three-quarter view, knees-up, complete head and hands inside frame, no crop at shoulders. [Insert character description above.] No writing, logo, watermark or scene props beyond the specified held items. Final project deliverable must have clean genuine alpha transparency.

同一群聊中的音色已通过目录检查，均互不重复。角色分配不定义玩家身份；后续图像生成结果仍需逐图检查轮廓、透明边缘、手部、多人比例与小窗口画面。

## 接入和验收

- 使用已授权的 imagegen CLI，模型 `gpt-image-2`，以原小镇图集作为风格参考，分别生成六张背景和八张角色原图。原图保存在 `output/imagegen/campus/`。背景 2048×1152，角色 1024×1536，quality high。
- `gpt-image-2` 不支持 API 原生透明背景。本轮角色先生成纯洋红底原图，再进行本地抠图输出真实 alpha；必须检查发丝、手部、衣服边缘、轮廓空隙与残色。不得直接把纯色底原图作为透明立绘交付，也不切换未经用户指定的图像模型。
- 最终文件位于 `game/assets/novel/campus/`，需纳入导出预设并记录实际生成方式、最终提示词和来源。
- 原图保留，裁切和透明边缘修整使用独立产物；不得覆盖小镇原素材。
- 六地点分别检查，另检查三人群聊、大字号长对白、住处、昼夜光线和 960×640 小窗口。
- 未获得新插画前，美术验收保持未完成；界面与程序的通过结果单独记录。
