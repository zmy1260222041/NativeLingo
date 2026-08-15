# Stranger Desktop Beta 真机验收清单

> 发布门槛：所有条目为 ✅ 才允许把 GitHub draft release 转为正式发布。

## A. 产物与静态校验

- [ ] `scripts/build_stranger_desktop.sh` 完整跑通（8 套测试全绿）
- [ ] `build/desktop/SHA256SUMS.txt` 存在且包含 Windows ZIP 与 macOS DMG
- [ ] `shasum -a 256 -c SHA256SUMS.txt` 校验通过
- [ ] Windows ZIP ≤ 300 MiB；macOS DMG ≤ 300 MiB
- [ ] macOS 二进制为 arm64（`lipo -info`）
- [ ] macOS pck 不含 `res://tests|tools|addons|speech_service`
- [ ] 分发包不含 `tests/tools/addons/speech_service` 源文件
- [ ] macOS 已用 Developer ID 签名并 notarize + staple（或已记录为 ad-hoc 回退）

## B. Windows 10/11 x64 真机

- [ ] 解压 ZIP 后 `stranger.exe` 可直接启动，无需管理员权限
- [ ] 首次启动进入主场景，无黑屏/崩溃；SmartScreen 说明与实际一致
- [ ] WASD/鼠标/E/G/Space/Shift/Esc 全部可用
- [ ] 输入重映射可改键并保存，重启后生效
- [ ] 暂停菜单无“说话方式”，重映射共 14 行，显示桌面无语音说明
- [ ] 游戏内不请求麦克风；任务管理器/网络工具确认无 127.0.0.1:17831 连接
- [ ] 手势可完成完整三日流程并出现通关页
- [ ] 问卷按钮打开浏览器新标签
- [ ] 保存后退出重启，进度恢复；删除 `%APPDATA%\Godot\app_userdata\Stranger` 后进度重置
- [ ] 1366×768、1440×900、1920×1080 三档分辨率下 HUD 不越界、画面正常
- [ ] 无持续控制台/shader 报错（如启动 exe 日志干净）

## C. macOS 11+ Apple Silicon 真机

- [ ] 打开 DMG、拖入 Applications 后首次启动成功（若未公证则记录右键打开路径）
- [ ] 未公证构建：右键 → 打开可运行；公证构建：双击直接运行
- [ ] WASD/鼠标/E/G/Space/Shift/Esc 全部可用
- [ ] 输入重映射、减少动态、界面缩放可用
- [ ] 暂停菜单无语音入口，重映射 14 行，显示“首轮桌面内测暂不包含语音”
- [ ] 无麦克风权限弹窗；无 127.0.0.1/17831 请求
- [ ] 手势完成完整三日流程
- [ ] 问卷按钮打开浏览器
- [ ] 存档：`~/Library/Application Support/Godot/app_userdata/Stranger`
  写入成功；退出重启恢复；删除目录后重置
- [ ] 1366×768、1440×900、1920×1080 分辨率下正常
- [ ] `log stream` 或 Console 无持续引擎错误

## D. 发布页验收

- [ ] GitHub draft release 标题、正文、三个附件正确
- [ ] 下载说明包含 SmartScreen/公证说明、存档位置、SHA-256 校验方法
- [ ] 匿名用户可下载附件（仓库 public）
- [ ] 问卷链接已回填，不是占位符
- [ ] 备案号相关文本不出现（桌面版无需备案）
