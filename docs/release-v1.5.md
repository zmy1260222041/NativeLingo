# NativeLingo v1.5.0 — 首个可分发版

英语跟读发音评估,**全本地推理**(macOS Apple Silicon)。录音不出设备。

## 下载

`NativeLingo_1.5.0_aarch64.dmg`(约 380MB)

## 安装

1. 打开 `.dmg`,把 NativeLingo 拖入「应用程序」。
2. **首次打开**:访达里**右键 NativeLingo → 打开 → 确认**(应用未公证,Gatekeeper 提示仅一次)。
   或终端:`xattr -dr com.apple.quarantine /Applications/NativeLingo.app`
3. **首次跟读**会按需下载模型(wav2vec2 / faster-whisper / MMS 强制对齐 / 音素 CTC,共约 1.7GB),之后**完全离线**。应用启动后端冷加载约 1 分钟,属正常。

## 系统要求

macOS 13+ · Apple Silicon(Intel Mac 暂不支持)· 麦克风权限(首次录音时授权)

## 用法

把你的英语视频(新闻播报、演讲、访谈等)放入:
```
~/Library/Application Support/com.nativelingo.app/videos/
```
应用内选片 → 听原声、看字幕 → 按句/段跟读录音 → 立即看到**准确度/流畅度分数、问题词、每个问题词的改法** → 任意词/句 **A/B 回放**对比原声 → 重练。

## 本版亮点

- **可分发 .dmg**:PyInstaller 冻结全栈后端(torch/torchaudio/transformers/faster-whisper),开箱即用,~380MB。
- 音素级诊断:对读错的词给出"/θ/ 读成了 /s/"式替换诊断 + 发音部位指导(v1.4)。
- 真实新闻播报域验证 + 长句自动二级切分(v1.3)。
- 中层 SSL 编码(6–9 层)+ speechocean762 真人评分校准(v1.2)。

## 已知限制

- 首次启动约 1 分钟加载模型(后续启动同样,因冻结态导入);功能正常,请稍候。
- 仅 Apple Silicon;暂无 Intel Mac 构建。
- 模型首次使用时联网下载(~1.7GB),之后离线。
- 未公证:首次打开需右键绕过(见上)。

技术细节见 [CHANGELOG.md](../CHANGELOG.md) 的 v1.5 条目。
