#!/usr/bin/env bash
# NativeLingo 一键启动脚本
# 用法: ./start.sh
#
# 通过 Tauri 开发模式运行应用，同时启动 Vite 并拉起 Python 后端。

set -e
cd "$(dirname "$0")"

# 清理可能残留的旧进程,避免端口占用
pkill -f "target/debug/nativelingo" 2>/dev/null || true
pkill -f "backend.main" 2>/dev/null || true

echo "启动 NativeLingo 开发工作台…"
source "$HOME/.cargo/env" 2>/dev/null || true
exec npm run tauri -- dev
