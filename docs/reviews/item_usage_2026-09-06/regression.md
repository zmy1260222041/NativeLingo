# 2026-09-06 最终回归摘要

Godot 4.6.3，macOS，当前工作树。每套件均匹配 PASS 且无 SCRIPT ERROR/ERROR/FAIL。

| 套件 | 结果 |
|---|---|
| items | PASS — PASS: Item usage 180 checks, 0 failures |
| game-state | PASS — PASS: Stranger game-state smoke suite |
| onboarding | PASS — PASS: Stranger onboarding suite |
| migration | PASS — PASS: Stranger save migration suite |
| voice-rewards | PASS — PASS: Stranger voice-gated reward suite |
| dialogue | PASS — PASS: Godot NPC dialogue asset suite |
| VocabularyTest | PASS — PASS: Stranger vocabulary suite |
| WordAcquisitionTest | PASS — PASS: Stranger word acquisition suite |
| WordPracticeTest | PASS — PASS: Stranger word practice adapter suite |
| GuidedWordPracticeTest | PASS — PASS: Stranger guided word-practice suite |
| WebBetaNoVoiceTest | PASS — PASS: Stranger web-beta no-voice suite |
| DesktopBetaNoVoiceTest | PASS — PASS: Stranger desktop-beta no-voice suite |
| HudTest | PASS — PASS: Stranger HUD smoke suite |
| VoiceTargetCancelTest | PASS — PASS: Stranger voice target-cancel suite |
| Main 场景渲染集成 | PASS: Item runtime 26 checks, 0 failures |

主场景渲染证据：counter.png / counter-objects.png / home.png / home-object.png / inventory-150.png。

说明：Node 类型测试按对应 .tscn 运行；首次误用 --script 的编译错误不计为通过，改用 README 指定场景后重新运行。测试途中暴露的布局与手柄映射缺陷已修复，上表为最后一次重跑结果。
