# Stranger Web Beta 上线手册

> 首轮范围：无语音、三日完整流程、G 手势完成 NPC 交互。
> 受众：中国大陆 ≤20 人 / ≤5 并发，桌面 Chrome/Edge（Windows/macOS）。
> 发布地址：`https://beta.<注册域名>/`。

## 0. 状态与术语

- 构建标签：`web-beta.1`
- 构建脚本：`scripts/build_stranger_web_beta.sh`
- 浏览器冒烟：`node production/web-beta/browser_smoke.mjs`（`WEB_BETA_HEADED=1` 额外断言指针锁定）
- 发布目录（服务器）：`/srv/nativelingo/releases/<build-id>`，`current` 软链接原子切换，`previous` 用于回滚
- 账号文件：`/srv/nativelingo/accounts.htpasswd`（bcrypt，仅服务器本地）
- 构建产物：`build/web/`（已被根 `.gitignore` 忽略，不入库）
- HTML shell 补丁：`production/web-beta/web_shell_patch.js`（导出后由构建脚本注入，
  在真实点击手势中获取指针锁定，吞掉 Chrome 的 `WrongDocumentError` 未处理 Promise）

## 1. 上线顺序（关键路径）

1. **注册域名**（备案主体实名认证的品牌域名）。
2. **购买腾讯云上海轻量应用服务器**：Ubuntu LTS、≥2 vCPU/2 GB/50 GB、
   200 Mbps 大陆套餐，包年包月 ≥3 个月。
3. **ICP 备案**（腾讯云备案控制台）：
   - 域名先完成实名认证（通常需超过 2 个工作日）；
   - 云服务器作为备案接入资源；
   - 填写主体信息、网站信息、上传证件/核验照；
   - 腾讯云初审 → 工信部短信核验 → 管局审核（约 7–20 个工作日，因省份而异）；
   - 通过后在页面底部展示备案号。
4. DNS：`beta.<域名>` A 记录解析到服务器公网 IP。
5. 服务器初始化：`production/web-beta/setup_server.sh`。
6. 生成内测账号：把 `accounts.sh` 上传到服务器（`scp`）后执行
   `sudo /srv/nativelingo/accounts.sh add tester01`。
7. 构建、浏览器冒烟、部署：
   ```sh
   scripts/build_stranger_web_beta.sh
   node production/web-beta/browser_smoke.mjs
   WEB_BETA_HEADED=1 node production/web-beta/browser_smoke.mjs   # 断言指针锁定
   WEB_BETA_HOST=admin@<ip> production/web-beta/deploy.sh
   ```
8. 冒烟验证：
   ```sh
   WEB_BETA_DOMAIN=<域名> \
   WEB_BETA_TEST_USER=tester01 \
   WEB_BETA_TEST_PASSWORD=<密码> \
   production/web-beta/validate.sh
   ```
9. 创建腾讯问卷，把问卷链接填入 `game/project.godot` 的
   `[web_beta] survey_url`，重新构建发布。问卷在暂停菜单与通关页打开。
10. 备案号：备案通过后按工信部要求将备案号加到页面底部（当前 `index.html`
    由 Godot 生成，建议在 Nginx `sub_filter` 或自定义 HTML shell 中注入；
    未备案通过前域名站点不得正式对外提供）。

## 2. 账号操作

```sh
# 服务器上执行（先把 accounts.sh 上传到 /srv/nativelingo/）
sudo /srv/nativelingo/accounts.sh add tester01     # 生成并显示一次性密码
sudo /srv/nativelingo/accounts.sh revoke tester01  # 撤销立即生效
sudo /srv/nativelingo/accounts.sh list
```

密码只显示一次；凭据与服务器密钥不进入仓库。撤销后 Nginx 会重新加载配置。

## 3. 回滚

```sh
WEB_BETA_HOST=admin@<ip> production/web-beta/rollback.sh
```

## 4. 问卷内容（待创建，腾讯问卷）

| 问题 | 类型 | 选项/说明 |
|---|---|---|
| 账号别名 | 填空 | 与 Basic Auth 账号一致，仅用于关联反馈 |
| 系统与浏览器 | 单选/多选 | Windows/macOS × Chrome/Edge 及版本 |
| 完成进度 | 单选 | 未完成 / 第1天 / 第2天 / 通关 |
| 加载时间与帧率感受 | 单选 | 明显卡顿 / 可用 / 流畅 |
| 操作与画面问题 | 多选+填空 | 镜头/移动/交互/贴图/崩溃等 |
| 开放反馈 | 填空 | |

不收集录音、不收集设备标识以外的信息（问卷平台自身字段除外）。

## 5. 外部交接清单（需要用户完成）

- [ ] 注册域名并完成域名实名认证
- [ ] 购买腾讯云上海轻量服务器（包年包月 ≥3 个月）
- [ ] 提交 ICP 备案并完成短信核验、管局审核
- [ ] 确定腾讯问卷链接并回填 `game/project.godot [web_beta] survey_url`
- [ ] 提供服务器 IP / SSH 账号 / 管理员固定 IP（用于 SSH 白名单）
- [ ] 提供 certbot 通知邮箱
- [ ] 提供备案号（上线前显示在页面底部）

## 6. 验收门槛（发布前全绿）

- [ ] HTTPS 证书评级 A（SSL Labs 或等效工具）
- [ ] WASM MIME 为 `application/wasm`
- [ ] gzip 预压缩首包 ≤70 MiB（当前构建约 35 MiB）
- [ ] 典型大陆 20 Mbps 网络冷启动 ≤30 s
- [ ] 5 个并发冷启动无 5xx
- [ ] 未登录 / 错误密码返回 401；有效账号可加载；撤销立即失效
- [ ] Chrome/Edge、Windows/macOS、1366×768 与 1440×900 可完整通关
- [ ] 浏览器不请求麦克风；网络面板无 localhost / 语音请求
- [ ] 控制台无 TCP、WASM、资源或 shader 错误
- [ ] 首次点击后指针锁定生效（`WEB_BETA_HEADED=1 node production/web-beta/browser_smoke.mjs` 已在本机 Chrome 验证）
- [ ] 刷新后存档保留；清除站点数据后重置
- [ ] 问卷在新标签页打开
