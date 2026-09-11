# FR-44 物品界面视觉回归

日期：2026-09-07  
Godot：4.6.3-stable  
窗口：1152×648；随身物品证据使用 HUD 150% UI 缩放。

运行命令：

```bash
/Applications/Godot-4.6.app/Contents/MacOS/Godot --headless --path game --script res://tests/test_item_usage_runtime.gd
```

结果：`PASS: Item runtime 38 checks, 0 failures`。

新增视觉/无障碍断言覆盖：

- 外层不是 `StyleBoxFlat`，使用项目折角墨线 StyleBox；
- 每个条目包含非颜色类别图形；
- 打开面板后焦点进入面板；
- 世界交互提示与全局 toast 在面板期间让出视觉优先级，关闭后恢复；
- 1152×648 / 150% 下遵守视口 90%×75% 预算；
- 标题、容量、滚动区、详情、主动作、关闭按钮均留在面板内部；
- 键盘与 D-pad 六向焦点路径形成面板内部闭环。

带渲染窗口的同一套测试重新生成 `counter.png`、`home.png` 与 `inventory-150.png`，并由人工检查层级、
剪影、对比度、空白与遮挡。
