# R-34 / R-36 补充：2D 按钮冲突试玩修复

对应 FR-46 / FR-47。保留工作区已有启动与录音修复；本轮没有提交或推送。

## 发现与修复

- 原生窗口复现「成长 → morning 练习 → 行囊 → Esc」：领域已退出练习，画面仍保留练习角色说明、提示和结束练习按钮。现在所有管理面板统一结束临时活动，恢复现场对白、角色说明和操作区，不自动播放新的开场语音。
- 回看原先未取消活动，可能将进行中的录音及其结束按钮一起遮住；现在和其他管理面板一致地取消录音、语音请求及临时活动。
- 原先录音按钮的互斥检查没有覆盖交谈、手势与重听，手势可以取消播放和玩家录音，重听连点会反复重启音频。现在三类操作复用控制器检查，并随运行状态禁用按钮、提供原因提示；录音的结束操作始终保留。键盘入口也经过同一控制器。
- 统一按钮分发检查：禁用、隐藏、已从界面移除，或位于当前面板背后的按钮不能通过晚到 pressed 回调执行操作。关闭面板也具有重复调用保护，延后的焦点请求不能再聚焦已关闭面板。
- 「显示全文」立即更新文本显示状态，同一帧内的后续推进不会仍误判成第一次补全文字。

## 验证

- 新增 `NovelInteractionTest.tscn`：修复前 18 个断言失败，修复后通过。覆盖四类面板的练习退出、关闭后的旧按钮、同帧补全/推进、实际 AudioStreamPlayer 播放期间连续操作、语音待取状态，以及独立静音总线录音期间的互斥和回看取消。
- `NovelTest.tscn` 通过：原有录音保护、库存、词汇、取消、存档迁移及三夜流程。
- `NovelEverydayTest.tscn` 通过：柜台、分类、浪费确认、容量、住处、焦点、鼠标遮挡及对白阅读。
- 原生窗口通过 cua 实际点击验证修复前后的练词→行囊→返回；另验证小剧场推进、打开回看及返回现场、打开设置。试玩入口使用 `--interaction-playtest`，关闭存档读写，不修改玩家存档。

录音回归使用独立静音音频总线，不采集真人麦克风，也不宣称重新验证了在线 ASR、模型评分或物理手柄。本轮无需修改共享语音服务。

```sh
/Applications/Godot-4.6.app/Contents/MacOS/Godot --path game res://tests/NovelInteractionTest.tscn
/Applications/Godot-4.6.app/Contents/MacOS/Godot --headless --path game res://tests/NovelTest.tscn
/Applications/Godot-4.6.app/Contents/MacOS/Godot --path game res://tests/NovelEverydayTest.tscn
# 独立临时状态的手动试玩窗口
/Applications/Godot-4.6.app/Contents/MacOS/Godot --path game res://tests/NovelInteractionTest.tscn -- --interaction-playtest
```
