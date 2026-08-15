# Stranger 桌面内测版 desktop-beta.1（Windows x64 / macOS Apple Silicon）

《异乡人 / Stranger》三日生存竖切片桌面内测版。首轮桌面内测**不包含语音**，
与居民交流请使用 `G` 手势；游戏可完整通关。

## 下载与校验

| 平台 | 文件 | SHA-256 |
|---|---|---|
| Windows 10/11 x64 | `stranger-desktop-beta.1-windows-x64.zip` | 见 `SHA256SUMS.txt` |
| macOS 11+（Apple Silicon） | `stranger-desktop-beta.1-macos-arm64.dmg` | 见 `SHA256SUMS.txt` |

校验（终端）：

```sh
shasum -a 256 -c SHA256SUMS.txt
```

## 安装与启动

### Windows
1. 解压 ZIP 到任意目录；
2. 运行 `stranger.exe`；
3. 若出现 SmartScreen 提示：`更多信息` → `仍要运行`（首版 Windows 包未做代码签名）。

### macOS
1. 打开 DMG，把 `Stranger` 拖入 `应用程序`；
2. 首次启动如果提示“无法验证开发者”：`系统设置 → 隐私与安全性 → 仍要打开`
   （正式公证配置完成后会移除该步骤）。

## 操作

- `WASD` / 左摇杆：移动
- 鼠标 / 右摇杆：镜头
- `Shift`：冲刺，`Space`：跳跃
- `E`：互动 / 观察
- `G`：手势（与 NPC 交流，本版可完成全部关键交互）
- `Esc`：暂停菜单（含输入重映射、减少动态、界面缩放、内测问卷）
- `F9`：重置三日流程与存档

## 存档

- Windows：`%APPDATA%\Godot\app_userdata\Stranger`
- macOS：`~/Library/Application Support/Godot/app_userdata/Stranger`

删除该目录会重置进度。桌面版不访问麦克风、不连接本地语音服务，也不上传任何数据。

## 反馈

请通关后填写内测问卷：<问卷链接待回填>

已知限制：
- 首版无语音；`G` 手势为完整替代路径。
- 仅支持 Apple Silicon Mac；Intel Mac 不在本版范围。
- Windows 包未代码签名，SmartScreen 提示属预期。
