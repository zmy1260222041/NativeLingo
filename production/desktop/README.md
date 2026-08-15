# Stranger Desktop Beta 发布与验收

- 构建脚本：`scripts/build_stranger_desktop.sh`
- 产物目录：`build/desktop/`
- 发布渠道：GitHub Releases（仓库 `zmy1260222041/NativeLingo`）
- 构建标签：`desktop-beta.1`

## 发布流程

1. 本地构建：
   ```sh
   scripts/build_stranger_desktop.sh
   # 若已配置 Apple 公证：
   MACOS_SIGN_IDENTITY="Developer ID Application: ..." \
   APPLE_ID=... APPLE_APP_PASSWORD=... APPLE_TEAM_ID=... \
   scripts/build_stranger_desktop.sh
   ```
2. 校验产物：
   ```sh
   cat build/desktop/SHA256SUMS.txt
   shasum -a 256 -c build/desktop/SHA256SUMS.txt
   ```
3. 发布 GitHub draft release：
   ```sh
   GH_TOKEN=<token 或已 gh auth login> \
   DESKTOP_TAG=desktop-beta.1 \
   production/desktop/publish_github_release.sh
   ```
4. 复核 release 页面正文、三个附件（Windows ZIP / macOS DMG /
   SHA256SUMS.txt），确认后取消 draft 转为正式发布。

## 下载说明

维护在 `production/desktop/release_notes.md`，每次发布时把问卷链接、签名状态
和已知问题补上后作为 GitHub release body。

## 真机验收清单

见 `production/desktop/acceptance-checklist.md`。发布前必须全绿。

## 未签名/未公证回退

- Windows：SmartScreen 弹窗选择「更多信息 → 仍要运行」。
- macOS：若暂缺 Developer ID，包为 ad-hoc 签名，用户需右键 → 打开；
  一旦证书就绪，重跑构建脚本并在发布说明中改为「已公证」。
