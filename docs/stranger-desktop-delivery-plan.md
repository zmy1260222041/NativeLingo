# 《异乡人 / Stranger》桌面版交付计划（Windows / macOS）

> 状态：**已冻结（2026-08-15，用户已确认 D1–D4）**；Phase 0/1/2（代码侧）已完成。
> 实施进度：分支 `desktop/stranger-delivery` 已创建；Phase 1 代码、导出预设、
> DesktopBetaNoVoiceTest、构建脚本与首次双平台产物已完成；Phase 2 签名/公证待证书，
> Phase 3 GitHub Release 与真机验收待执行。
> 前置状态：网页版工作已提交 `5fc55e0f`（codex/stranger-vertical-slice）。
> 目标：以 Godot 4.6.3 原生桌面导出发放可玩的 Windows / macOS 版本，
> 免去域名、服务器与 ICP 备案；同时继承网页版已验证的构建与验收流程。

## 1. 目标与首版范围

- **玩法**：完整三日纵切片不变，移动/镜头/收集/修理/休息/通关全部保留。
- **交互**：首版无语音，`G` 手势完成 NPC 交互（与 Web Beta 相同；
  桌面后续可选“语音增强版”，见 §6）。
- **存档**：Godot 桌面 `user://` 本地存档；不涉及浏览器站点数据。
- **交付物**：
  - Windows：`stranger-desktop-beta.1-windows-x64.zip`（解压即玩）
  - macOS：`stranger-desktop-beta.1-macos-arm64.dmg`（拖入 Applications）
  - 每个包附带 `SHA256SUMS.txt` 与《下载说明》中文说明。

## 2. 关键决策点（已确认）

| # | 决策 | 结论 |
|---|---|---|
| D1 | 首版语音 | **无语音 + 手势**；`desktop_beta_no_voice` 复用 Web 无语音逻辑 |
| D2 | 分发渠道 | **GitHub Releases**（`zmy1260222041/NativeLingo` 为公开仓库，可提供匿名下载） |
| D3 | 签名与公证 | **macOS Developer ID 签名 + notarytool 公证 + staple；Windows 暂免签名**，下载说明覆盖 SmartScreen |
| D4 | 目标架构 | **macOS arm64（Apple Silicon）+ Windows x64**；首版不覆盖 Intel Mac 与 Windows arm64 |

## 3. 实施阶段

### Phase 0 — 方案冻结（0.5 天）
1. ✅ D1–D4 已确认。
2. 准备 `Stranger` 桌面图标（当前项目没有 `config/icon`，需提供 512×512 源图）。
3. 创建分支 `desktop/stranger-delivery`（从当前 `codex/stranger-vertical-slice` 切出）。
4. 准备 Apple Developer ID 证书/钥匙串与 `notarytool` 凭据（如暂缺，先构建，签名步骤后补）。

### Phase 1 — 桌面导出与无语音改造（1 天）
1. 在 `game/export_presets.cfg` 增加：
   - `Windows Desktop Beta`：release x86_64、Compatibility、
     `desktop_beta_no_voice` feature、输出 `../build/desktop/windows/`。
   - `macOS Desktop Beta`：release arm64、Compatibility、
     `desktop_beta_no_voice` feature、输出 `../build/desktop/macos/`。
2. 代码改造（复用 Web Beta 经验）：
   - `SpeechAdapter.is_available()` 增加对 `desktop_beta_no_voice` 的判断；
     UI/输入/重映射已经统一走 `is_available()`，桌面无语音零新增入口。
   - 构建标签 `desktop-beta.1` 与问卷 URL 复用 `[web_beta]` 项目设置或
     拆成 `[beta]` 通用设置。
   - 存档提示文案从“浏览器本地/清除站点数据”切换为
     “进度保存在本机用户目录（user://）”。
   - 保持 `AnimationDebugBridge` 仅桌面可用？否——**分发包也关闭**
     TCP/WebSocket 调试端口（`desktop_beta_no_voice` 或独立
     `desktop_beta` feature 下短路），避免本地端口监听。
3. 测试：
   - 新增 `DesktopBetaNoVoiceTest`（复用 `WebBetaNoVoiceTest` 逻辑，
     校验重映射 14 行、语音入口隐藏、手势通关）。
   - 保留现有 7 套 Godot 测试全绿。

### Phase 2 — 构建脚本与打包（0.5–1 天）
1. 新增 `scripts/build_stranger_desktop.sh`，沿用网页版结构：
   - 校验 Godot `4.6.3-stable`；
   - `--import` + 7 套测试 + `DesktopBetaNoVoiceTest`；
   - 导出 Windows/macOS Release；
   - macOS：`hdiutil` 制作 DMG；
   - Windows：`ditto -c -k` 或 `zip` 打包；
   - 生成 `SHA256SUMS.txt` + `build-info.json`；
   - 校验压缩包体积与关键文件存在。
2. 签名（已确认）：
   - macOS：Developer ID Application 签名 + `notarytool` 公证 + staple；
   - Windows：首版免签名，下载说明中写明 SmartScreen 处理方式。

### Phase 3 — GitHub Releases 分发与验收（1 天）
1. 在 `zmy1260222041/NativeLingo` 创建 draft release
   `stranger-desktop-beta.1`，上传两个包 + `SHA256SUMS.txt` + 下载说明；
   release body 使用中文写清系统要求、macOS 公证说明、Windows SmartScreen
   说明、存档位置与问卷链接。
2. 真机验收矩阵：
   - macOS（Apple Silicon）+ Windows 11 x64；
   - 分辨率 1366×768 / 1440×900 / 1920×1080；
   - 首次启动、键盘鼠标、暂停/重映射、通关、存档重启恢复、
     问卷新标签页/浏览器打开；
   - 无麦克风请求、无 127.0.0.1/17831 请求、无调试端口监听；
   - 性能目标 60 FPS、无明显 shader/资源错误。

### Phase 4 — 放量内测（持续）
1. 先 2 个内部账号冒烟，再按 10–20 人放量。
2. 收集问卷与日志；问题严重时回滚到上一构建/上一分支。
3. 完成后评估 Phase 2：桌面语音增强版。

## 4. 发布门槛（数字）

- 包体：单包 ≤ 300 MiB（当前 PCK 约 50 MiB + 引擎运行时，预计 120–180 MiB）。
- macOS：启动到可操作 ≤ 10 秒（Apple Silicon 本地 SSD）；Windows 同类。
- 测试：8 套 Godot 测试全绿；桌面真机验收矩阵全绿。
- 安全：分发包不含 `tests/tools/addons/speech_service` 开发文件；
  SHA-256 随包分发。
- 存档：`user://` 写读正常，重开进程恢复。

## 5. 风险与应对

| 风险 | 应对 |
|---|---|
| macOS 未公证被 Gatekeeper 拦截 | D3 选公证；否则右键打开 + 下载说明 |
| Windows SmartScreen 提示 | 下载说明给出“仍要运行”步骤；后续补 Authenticode |
| Intel Mac 用户无法运行 arm64 包 | 明确首版仅 Apple Silicon，或追加 universal/x86_64 包 |
| 用户预期语音交互 | 首版 UI 明确“本测试版仅手势交互”，问卷收集语音需求 |
| Godot Windows 导出从 macOS 交叉打包异常 | 在 Windows 真机或 CI 复核；必要时增加 Windows 构建机 |
| 调试端口/日志残留 | 复用 Web 禁用逻辑，验收检查监听端口 |

## 6. 后续可选：桌面语音增强版（不在首版）

- 打包本地 `game/speech_service`（faster-whisper base.en）为随包 sidecar：
  - macOS：PyInstaller 冻结 + 模型 145 MiB；
  - Windows：需 Windows 构建环境交叉冻结；
- 或改用 Godot 内建音频输入 + 新接口，避免 Python sidecar；
- 始终保持手势完整可玩，语音服务失败静默降级。
