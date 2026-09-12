#!/usr/bin/env python3
"""Start the local speech companion, then the exported 2D game (or Godot)."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def health():
    try:
        with urllib.request.urlopen('http://127.0.0.1:17831/health', timeout=1) as response:
            data = json.load(response)
            return data if data.get('protocol') == 2 else None
    except (OSError, ValueError):
        return None


def main():
    app = ROOT / 'build/novel/Stranger2D.app'
    engine = os.environ.get('GODOT_BIN') or shutil.which('godot')
    bundled = Path('/Applications/Godot-4.6.app/Contents/MacOS/Godot')
    if not engine and bundled.exists():
        engine = str(bundled)
    if not app.exists() and not engine:
        raise SystemExit('请先导出 macOS 2D Novel，或通过 GODOT_BIN 指定 Godot 4.6.3。')
    if not health():
        python = ROOT / '.venv/bin/python'
        if not python.exists():
            raise SystemExit('缺少 .venv。请按 game/speech_service/README.md 安装语音依赖。')
        log_path = Path(tempfile.gettempdir()) / 'stranger-novel-speech.log'
        with log_path.open('a') as log:
            child = subprocess.Popen([str(python), str(ROOT / 'game/speech_service/server.py')], cwd=ROOT, stdout=log, stderr=log, start_new_session=True)
        deadline = time.monotonic() + 25
        while not health() and time.monotonic() < deadline and child.poll() is None:
            time.sleep(.25)
        if not health():
            raise SystemExit(f'语音服务未启动，请查看 {log_path}')
    print('本地语音已连接。游戏设置中会单独检查在线交谈模型。')
    # In a development checkout use the installed engine and current sources.
    # This also avoids silently launching a stale exported bundle.
    if engine:
        subprocess.Popen([engine, '--path', str(ROOT / 'game'), 'res://scenes/Novel.tscn'], cwd=ROOT, start_new_session=True)
    elif app.exists() and sys.platform == 'darwin':
        subprocess.run(['open', str(app)], check=True)
    else:
        raise SystemExit('当前平台没有可用的 Godot 引擎。')


if __name__ == '__main__':
    main()
