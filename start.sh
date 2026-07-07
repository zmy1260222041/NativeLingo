#!/usr/bin/env bash
# NativeLingo 一键启动脚本
# 用法: ./start.sh
#
# 直接运行已编译好的 Tauri 应用(会自动拉起 Python 后端)。
# 若二进制不存在,会先编译。

set -e
cd "$(dirname "$0")"

BIN="src-tauri/target/debug/nativelingo"

# 清理可能残留的旧进程,避免端口占用
pkill -f "target/debug/nativelingo" 2>/dev/null || true
pkill -f "backend.main" 2>/dev/null || true
sleep 1

# 总是重新编译:Tauri 会在编译时把前端(src/)嵌入二进制,
# 只改前端文件而不重编,运行的仍是旧界面。重编在无改动时几乎瞬时完成。
echo "编译应用(嵌入最新前端)…"
source "$HOME/.cargo/env" 2>/dev/null || true
(cd src-tauri && cargo build 2>&1 | tail -2)

echo "启动 NativeLingo… (关闭窗口即退出,后端会自动关闭)"
exec "$BIN"
