# Cloud TTS 接入与凭据创建

> 状态：**已完成并端到端验证**（2026-09-17）。
> 相关：`design/gdd/language-adaptation.md` §5（分级语速与声音）

## 结论摘要

已创建并验证通过。三个原本未知的问题现在都有实测答案：

| 问题 | 实测结果 |
|---|---|
| 服务账号能否认证 | **能**，且不需要任何 IAM 角色 |
| 12 个声音名是否有效 | **全部有效**（`Kore`/`Aoede`/`Charon`/`Fenrir`） |
| 降速是否保持音高 | **保持**，0.75–1.00 全档 F0 漂移 ≤2.4%，不是变调慢放 |
| 比例是否准确 | 准确，0.90→1.12×（请求 1.11×）、0.75→1.39×（请求 1.33×） |
| 0.05 步长能否分辨 | **不能**，噪声底 ≈ 时长的 6–8% |

**对设计的直接影响：`language-adaptation.md` 的 0.05 步长阶梯无法实现，
需要放宽到约 0.15。** 见下文"实测"一节。

## 实际执行记录

项目**没有新建**——账号里已有一个开了结算的 `NativeLingo` 项目
（`<PROJECT_ID>`，结算账户 `<BILLING_ACCOUNT_ID>`；真实 ID 不入库），
现有的 Gemini key 也属于它，因此复用它。实际只需三步：

```bash
# 1. 启用 Cloud Text-to-Speech API
gcloud services enable texttospeech.googleapis.com --project=<PROJECT_ID>

# 2. 创建服务账号
gcloud iam service-accounts create tts-runner \
  --display-name="NativeLingo TTS runner" --project=<PROJECT_ID>

# 3. 下载密钥
gcloud iam service-accounts keys create ~/nativelingo-tts.json \
  --iam-account=tts-runner@<PROJECT_ID>.iam.gserviceaccount.com \
  --project=<PROJECT_ID>
```

**不要尝试授予 `roles/texttospeech.user`**——该角色不存在。项目的角色列表里
只有 `roles/speech.*`（属于 Speech-to-Text，不是 TTS）。Cloud Text-to-Speech
不要求任何 IAM 角色，任何已认证主体启用 API 后即可调用。这一步实测报错：

```
INVALID_ARGUMENT: Role roles/texttospeech.user is not supported for this resource.
```

密钥保存在仓库外（`~/nativelingo-tts.json`，权限 0600）。

## 一、从零开始的完整步骤

如果要在别的账号或项目复现：

```bash
gcloud auth login
gcloud projects create <PROJECT_ID> --name="NativeLingo TTS"
gcloud billing accounts list
gcloud billing projects link <PROJECT_ID> --billing-account=<ACCOUNT_ID>
gcloud services enable texttospeech.googleapis.com --project=<PROJECT_ID>
gcloud iam service-accounts create tts-runner --project=<PROJECT_ID>
gcloud iam service-accounts keys create ~/nativelingo-tts.json \
  --iam-account=tts-runner@<PROJECT_ID>.iam.gserviceaccount.com --project=<PROJECT_ID>
```

结算必须开通（即使只用免费额度）。**不需要授予任何 IAM 角色。**

## 二、启用

```bash
export STRANGER_TTS_PROVIDER=cloud
export GOOGLE_TTS_CREDENTIALS=~/nativelingo-tts.json
```

凭据查找顺序：`GOOGLE_TTS_CREDENTIALS` → `GOOGLE_APPLICATION_CREDENTIALS`
→ 服务目录下的 `CloudTTS.json`/`cloud-tts.json` → 仓库根的 `CloudTTS.json`。

其它可选环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `GOOGLE_TTS_SPEAKING_RATE` | `1.0` | 全局语速，越界自动夹到 0.25–2.0 |
| `GOOGLE_TTS_LOCALE` | `en-US` | 声音区域 |
| `GOOGLE_TTS_PROJECT` | 取服务账号的 `project_id` | 覆盖计费归属项目 |
| `GOOGLE_TTS_ENDPOINT` | v1 `text:synthesize` | 端点覆盖 |
| `GOOGLE_TTS_TIMEOUT_SECONDS` | `30` | 单次合成超时，下限 5 |

## 三、验证

```bash
export STRANGER_TTS_PROVIDER=cloud
export GOOGLE_TTS_CREDENTIALS=~/nativelingo-tts.json
.venv/bin/python game/speech_service/verify_cloud_tts.py --repeat 4
```

脚本做四件事，任一失败返回非零：

1. 服务账号能否换到 access token；
2. 全部 12 个 NPC 的 Chirp 3: HD 声音名是否都存在；
3. 逐档合成，**每档重复多次**，报告实际比例对请求比例的误差，以及相邻档位能否
   从运行间噪声中分辨出来；
4. **音高保持检测** —— 用 Praat 测各档中位 F0，判断降速是"说慢"还是"变调慢放"。

`--repeat` 是关键。单次采样会让这个脚本给出错误结论：我第一次每个档位只跑一遍，
得到"0.90 比 0.85 更慢"这种自相矛盾的结果，因为运行间波动比档位差异还大。
默认 4 次仍偏少，重要决策请用 8 次。

第 4 项是硬门禁。`language-adaptation.md:97` 禁止降低音高冒充慢速。该检测器已用
合成信号自测：拉伸 1.25×（=0.80× 速度）精确测得 −20.0% 漂移，保音高的对照样本
为 0.0%，两者不会混淆（见 `test_cloud_tts.py`）。

样例音频写在 `/tmp/cloud-tts-check/`，务必人耳复核一遍再决定。

## 三之二、实测结果（2026-09-17）

`en-US-Chirp3-HD-Fenrir`，27 词句子，每档 8 次：

| 档位 | 平均时长 | 标准差 | 实测比例 | 请求比例 | 误差 |
|---|---:|---:|---:|---:|---:|
| 1.00 | 8.55s | 0.54 | 1.00× | 1.00× | +0.00 |
| 0.90 | 9.58s | 0.68 | 1.12× | 1.11× | +0.01 |
| 0.75 | 11.89s | 0.61 | 1.39× | 1.33× | +0.06 |

**比例准确，噪声底约为时长的 6–8%。** 相邻档位可分辨性：

| 步长 | 时长差 | 2×标准差 | 可分辨 |
|---|---:|---:|---|
| 0.10（1.00 vs 0.90） | 1.03s | 1.22s | **否**（分布重叠：1.00 最大 9.16s，0.90 最小 8.59s） |
| 0.15（0.90 vs 0.75） | 2.30s | 1.29s | **是**（完全不重叠：0.90 最大 10.34s，0.75 最小 11.22s） |

**结论：档位间距需要约 0.15。** 设计文档现在写的是 0.05 步长的
0.80/0.90/0.95/1.00，这个阶梯做不出来——相邻档的时长差落在噪声里，
用户听不出区别。建议改成三档 1.00 / 0.85 / 0.70 之类的间距。

另注意短句更差：在 10 词短句上，运行间波动在每个档位都超过了档位差异本身。
也就是说语速分档只在较长的句子（校园 60–100 词那些）上可感知，
城镇的短对白（"Sure thing."）分档基本无效。

## 四、已实现的代码

`game/speech_service/server.py`：

- `TTS_PROVIDER` 增加 `cloud`；`xai`/`qwen` 行为与缓存键完全不变。
- 服务账号 JWT（RS256）本地自签换 token，只用已有的 `cryptography`，不新增依赖；
  token 按 `expires_in` 缓存，提前 60 秒刷新。
- `_cloud_tts_wav()` 走 `text:synthesize`，`LINEAR16`／24 kHz，上游已带 WAV 头，
  与 xAI 路径的 `_pcm_to_wav` 输出格式一致。
- 声音映射 `CLOUD_TTS_VOICES` 把既有的短声音 id（eve/ara/rex/leo）映到 Chirp 名，
  城镇与校园共用一份 cast。
- **服务端内存缓存键按语速分离**（`@r0.85` 后缀）。这只覆盖 §5
  "音频变体缓存必须区分文本、声音、模型版本、语言、速度"中的文本、声音、速度；
  键里没有模型版本和语言，Godot 端磁盘缓存命名空间也不含供应商与语速。1.0× 与
  非 cloud provider 保持原键，不影响既有缓存与测试。
- **预热只连当前供应商**：cloud 模式的启动预热与 `POST /game/prewarm` 只换取并
  缓存 OAuth token，不会创建 DashScope 连接池、不会连北京 Qwen 端点。`/health`
  的 `tts_region` 在默认端点下报告 `global`。
- 流式接口：Cloud TTS 的流式只在 Chirp 3: HD 的 gRPC 路由上，因此 cloud
  分支整段合成后按既有 chunk 形状回放，客户端无需改动。
- 合成结果的大小上限从 2 MB 提到 8 MB（`_TTS_MAX_WAV_BYTES`）。原 2 MB 是
  流式保护；而 24 kHz 单声道 2 MB 仅 43.7 秒，100 词的校园长句在慢速下会超限。

`game/speech_service/test_cloud_tts.py`：21 个测试，覆盖 JWT 签名（用一次性
RSA 密钥本地验签）、token 缓存与刷新、声音映射、请求体形状与语速字段、
Bearer 与 `x-goog-user-project` 头、语速夹取、空音频与 HTTP 错误、
缓存键分离、cloud 预热不触碰 DashScope，以及上面的音高检测器（未安装 praat-parselmouth 时这 3 项跳过）。

## 五、待办

- [x] 创建服务账号并跑通 `verify_cloud_tts.py` —— 2026-09-17 完成
- [x] 校验 12 个声音映射 —— 全部有效（`Kore`/`Aoede`/`Charon`/`Fenrir`）
- [x] 音高保持实测 —— 通过，不再阻塞语速功能
- [ ] **改设计：把 §3.2 的 0.05 步长放宽到约 0.15**（实测不支持 0.05，见"三之二"）
- [ ] 决定 cast 的声音分配：现有映射下 12 个 NPC 只用了 4 个 Chirp 声音
- [ ] 实现 §6 的"慢一点/换个说法" UI，语速档位按 0.15 间距设计
- [ ] 城镇侧目前没有改档入口（只在校园档案里），§3.1 的"统一交流偏好"入口尚未实现
- [ ] 短句分档无效（10 词句上噪声大于效果），需要决定短对白是否还分档

## 六、免费额度与配额

Chirp 3: HD 每月前 100 万字符免费（项目级、按月重置），超出 $30/百万字符。
流式与非流式同价。配额：Chirp3 每项目 200 请求/分钟，并发流式会话 100，
单请求正文上限 5000 字节（不可提升；最长档 100 词约 600 字符，余量充足）。
