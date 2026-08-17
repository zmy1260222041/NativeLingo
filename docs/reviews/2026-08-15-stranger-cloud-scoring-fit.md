# R-18 · Stranger 云评分符合性评审(2026-08-15)

> 需求来源:用户指示「像 NativeLingo 移动端一样在服务器上评分、传回结果,免去单独
> 启动语音服务,降低 Godot 运行时本机负载,改善内测体验」。用户已确认选择
> **全部远程评分(Web 与桌面都走服务器)** 并同意新增音频出站例外。
> 落库为 **FR-29 + NFR-7**(`docs/PRD.md` v0.9)。判据在实现前写死;实现后回填 §7。

## 1. 借鉴对象(已逐文件核读,分支 `feat/android/cloud-speaking` / `ios`)

| 资产 | 内容 | 对 FR-29 的复用 |
|---|---|---|
| `server/README.md` | 云评分部署架构:ONNX Runtime 0.8GB 模型 / 1.5GB 常驻、`124.220.234.178:8756`、systemd、私有 CA + 每设备 token、无录音仓库、PIPL 立场 | 部署与安全基线 |
| `server/backend/main.py` | `/analyze`(multipart ref+learner)、`/register`(激活码→token)、`require_token`、上传/限流/磁盘守卫 | 新端点沿用同一守卫与鉴权 |
| `NativeLingoAndroid/.../CloudClient.kt` | 内置私有 CA 固定 TLS、15/120/300s 超时、Bearer token | Godot `TLSOptions` 等价实现 |
| `NativeLingoIOS/.../CloudClient.swift` | iOS 的 BasicX509 + hostname 手动校验 | 桌面端 TLS 语义对齐 |
| `NativeLingoIOS/README.md` | WebView + 本地 shim + 云端代理的 1:1 架构 | Web Beta 的 nginx 同源反代方案 |

关键事实:**桌面/macOS NativeLingo 是本地 sidecar,并不是远程评分**;真正先例是
Android/iOS 的 cloud-speaking 服务。FR-29 复用其服务端,不改动 Android/iOS 客户端。

## 2. 与既有约束的冲突与解决

| 约束 | 冲突 | 解决 |
|---|---|---|
| NFR-1 录音不出设备 | 云评分必须上传录音 | 新增 NFR-7 极窄例外:仅 FR-29 端点、仅显式激活后、服务器不留存、失败降级手势兜底 |
| NFR-6 出站白名单只含文本 | `/game/evaluate` 上传音频 | NFR-7 作为第二条例外,范围比 NFR-6 更窄;NFR-6 与另两模块表述一字不改 |
| CLAUDE.md:游戏不依赖 Python sidecar、服务不可用时手势兜底完整可玩 | 发布版不能要求用户跑本地服务 | 发布版走远程 HTTP;本地服务降级为开发模式;网络失败→`gesture_fallback` |
| cloud-speaking 服务端不识别 Stranger 意图 | `/analyze` 只有通用跟读评分 | 新增 `POST /game/evaluate`:服务器端槽位判定 + 随包意图参考 WAV + ORT SSL/DTW |

## 3. 架构基线

```text
Godot(Web/桌面)
  V 录音 → SpeechAdapter
           ├─ 未激活/断网/5xx → gesture_fallback(FR-28 保底,主线可通关)
           └─ 已激活 → POST /register(激活码换 token,仅一次)
                       POST /game/evaluate  [Bearer token + X-Stranger-Target + raw WAV]
                            │
        Web: beta 域名 nginx 反代 /game/ → 云服务器(同源,Let's Encrypt)
        桌面: 直连 https://124.220.234.178:8756,内置私有 CA 固定 TLS
                            ▼
             cloud server: faster-whisper(短句 beam=5 + hotwords)
                           + game_judge 槽位 delivery
                           + ORT pipeline.analyze_arrays(随包 refs) pronunciation
                           → FR-28 同构 JSON;录音解码后即弃,零落盘
```

## 4. 门控判据(实现前写死)

- **G1 出站最小化**。未激活时游戏网络请求为 0(抓包级);激活后域名白名单只有
  `/register` 与 `/game/evaluate`;参考音频、游戏进度、设备硬件标识不出设备。
- **G2 凭据与传输**。PCK 内不含激活码、token、私有 CA 私钥;桌面端用
  `TLSOptions.client` 固定内置 CA(仅受信 CA,不接受系统/伪造链);Web 走同源
  nginx 反代 + 既有 Let's Encrypt;401/403 → 客户端清除 token 回激活界面。
- **G3 判定一致性**。云端与本地 `game/speech_service` 共用同一意图表与
  `delivery` 判定实现;对同一转写,`delivery`/`band`/`score 合成` 逐位一致;
  `pronunciation` 使用**同一批随包参考 WAV**,ORT 编码器相对 torch 的分数差
  沿用 R-5 既定容差(accuracy ±2.0 / cost ±0.02)。
- **G4 服务器不留存与滥用守卫**。端点内 `soundfile` 解码 → 立即评分 → 请求结束
  即释放;无录音文件/仓库/冷存储;8MB 单条上限、`/game` 限流、磁盘水位检查、
  目标 ID 白名单、`require_token`(SHA-256 哈希 token)。
- **G5 降级完整可玩**。断网、超时、5xx、未激活任一情况下 `gesture_fallback`
  给最低生存档,`test_web_beta_no_voice`/`test_desktop_beta_no_voice` 语义不变,
  三日主线完整通关;普通低分不清除语音可用状态。
- **G6 回归**。服务器端 `game_judge` 单元测试 + 端点契约测试(不加载重模型);
  Godot headless 全部既有套件 + 远程模式解析测试全绿;`python3 -m py_compile`。

## 5. 已知取舍(如实记录)

1. **服务器集中评分把负载从用户设备移到一台 4 核/3.7GB 的盒子上**。首请求与并发
   是新的容量风险:沿用 `/warmup` 预热 + 限流 + 排队;若内测并发超限,需扩容或
   退回桌面本地模式(客户端开关已保留)。
2. **Web 反代层有两个上游**。nginx 需要把 `/game/` 转发到 8756,并保持
   `Authorization`/`X-Stranger-Target` 头;该层不能缓存 POST 响应。
3. **私有 CA 对桌面 Godot 是新增交付物**。CA 证书(PEM)不进 git,由运营者像
   iOS `sync-resources.sh` 一样在构建机注入导出资源;测试/开发可用
   `stranger_cloud/insecure_dev=true` 显式关闭校验(仅本机)。
4. **cloud-speaking 分支与本分支分开演进**。服务器改动在独立 worktree 的
   `feat/stranger-cloud-scoring`(基于 `feat/android/cloud-speaking`),Godot
   改动在 `desktop/stranger-delivery`;两者通过 HTTP 契约与参考 WAV 对齐,
   不互相 import。

## 6. 实现后回填

- 云服务器 worktree(`feat/stranger-cloud-scoring`,基于 `feat/android/cloud-speaking`):
  `server/backend/core/game_judge.py`、`server/backend/main.py` `/game/evaluate`、
  `server/game_refs/*.wav`、`server/tests/test_game_judge.py`、
  `server/tests/test_game_endpoint.py`、`server/README.md`。
- Godot 侧(`desktop/stranger-delivery`):`speech_adapter.gd` 远程模式 +
  `/register` 激活 + token/设备 id 本机存储 + TLSOptions 私有 CA;
  `hud.gd` 激活浮层;`project.godot [stranger_cloud]`;三个
  `Cloud Voice` 导出预设;`CloudVoiceTest.tscn`;本地参考 WAV;nginx 反代块。
- 结论:**代码侧放行,待部署与抓包闭环**(与 R-15/R-16 同一体例):
  服务器部署、CA 注入导出、真实抓包零出站验证、ORT/torch 分数同语料复测
  属于外部操作,不在本机可完成范围。

| 门 | 判据 | 实现后结果 | 备注 |
|---|---|---|---|
| G1 | 未激活零出站,仅两个端点 | ✅ PASS(代码级) | `finish_recording` 在无 token 时不发请求;仅 `/register` 与 `/game/evaluate` 两个 URL 拼接点;抓包验证待部署后执行 |
| G2 | 无内置凭据,TLS/CA/401 处理 | ✅ PASS(代码级) | PCK 无激活码;token/设备 id 仅 `user://`;桌面 `TLSOptions.client(CA)`;Web 同源反代;401/403 清 token 并回 `CLOUD_UNAUTHORIZED` |
| G3 | delivery/band 逐位一致,pronunciation 同参考 | ✅ PASS(可测部分) | 11 条语料云端/本地 `delivery` 与 `band` 逐位一致,INTENTS 字典全等;两侧使用同一批 `reference_audio` WAV;ORT 分数复测留待服务器部署后 |
| G4 | 服务器不留存 + 守卫 | ✅ PASS(代码级) | 端点 raw body 解码即弃、无录音仓库;8MB 上限、`/game` 限流 20/min、target 白名单、`require_token` |
| G5 | 断网/未激活手势兜底通关 | ✅ PASS | `CloudVoiceTest` 断言未激活→fallback 武装、激活→解除;既有 Web/Desktop no-voice 套件仍全绿 |
| G6 | Python + Godot 回归全绿 | ✅ PASS | 云端 13 个 unittest 全绿;Godot 10 套 headless 全绿(新增 `CloudVoiceTest` 16 断言);`py_compile` 通过 |

## 7. 遗留外部闭环(部署时执行)

1. 把 `server/game_refs/` 与 `game_judge.py` rsync 到 `124.220.234.178:/opt/nativelingo/`,
   重启 `nativelingo.service`,用激活码设备实测 `/game/evaluate`。
2. 把私有 CA `ca.pem` 注入 `game/certs/nl_ca.pem`(不入库)后导出桌面
   Cloud Voice 预设;Web 上线时使用单独的 nginx site(`microphone=(self)` +
   `/game/` 反代)。
3. 抓包验证:未激活零出站;激活后仅 `/register` 与 `/game/evaluate`;
   服务器数据目录无录音文件。
4. ORT 与 torch 对同一批 WAV 复测 accuracy 差 ±2.0 / cost ±0.02(R-5 容差)。

## 8. 部署闭环进展(2026-08-17)

§7 清单的实际执行情况(操作者为本机 agent,均留有服务器日志):

1. **rsync + 重启:完成**。`server/`(含 FR-32 TTS 的 DashScope WebSocket
   修复、42 条台词目录、`requirements-server.txt` 增 `dashscope`)已同步到
   `124.220.234.178:/opt/nativelingo/`,venv 安装 `dashscope`,放置
   `TTS.csv`(权限 600),`nativelingo.service` 重启后 `/health` 正常
   (`{"status":"ok","model_loaded":true}`,常驻 1.2G)。
2. **CA 注入导出:完成,并顺带修复两个导出构建专属缺陷**。
   `game/certs/nl_ca.pem` 与服务器 `tls/ca.pem` 指纹一致;Cloud Voice 预设
   `include_filter` 增加 `*.pem`(`.pem` 非 Godot 资源类型,否则不入 PCK)。
   其一:`SpeechAdapter._configure_cloud_tls` 以 `ResourceLoader.exists`
   检查证书——该函数对非资源文件在导出构建中恒为 false(开发环境为 true,
   故历史测试与 `CloudVoiceTest` 全绿而未暴露),CA 从未加载,激活必报
   「网络不可用」;改为 `FileAccess.file_exists` + `X509Certificate.load`。
   其二:`NpcVoice` 自有 HTTPRequest 从未配置固定 CA,云端 TTS 请求 TLS
   握手必败;已补同构配置。
3. **设备级实测:完成**。真实一次性激活码经 Godot 客户端(固定 TLS、无
   insecure 开关)`POST /register` 成功、token 落盘 `user://`;
   `/game/tts` 返回 WAV 并播放;`/game/evaluate` 对同一合成 WAV 云端与本地
   均返回 `score 96 / band generous / reference_dtw`(G3 单样本逐位一致)。
   `/game/score_word` 对非候选词正确返回 clarify、零惩罚。
   新增 `game/tests/CloudActivationLiveTest.tscn` 固化该链路。
4. **正式抓包零出站验证、ORT/torch 批量分数复测:仍待**。G3 目前只有单样本
   逐位一致,批量复测(≥ 每意图多条语料)与 tcpdump 级零出站证据未做。
