"""Opt-in paid API + desktop audio probe; all player utterances are synthetic.
Run from the repository root with .venv/bin/python. Never reads a user save.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request
import server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', default=os.environ.get('GODOT_BIN') or shutil.which('godot') or '/Applications/Godot-4.6.app/Contents/MacOS/Godot')
    parser.add_argument('--order-text', default="I'll take a taco to go, please.")
    parser.add_argument('--capture-dir', default='')
    args = parser.parse_args()
    with urllib.request.urlopen('http://127.0.0.1:17831/health?refresh=1', timeout=20) as response:
        health = json.load(response)
    if health.get('tts_provider') != 'xai' or health.get('tts_region') != 'us-east-1' or not health.get('dialogue_ready'):
        raise SystemExit('Live probe requires a ready Gemini model and the xAI US speech backend.')
    with tempfile.TemporaryDirectory(prefix='stranger-live-fixture-') as directory:
        path = Path(directory) / 'taco.wav'
        path.write_bytes(server._synthesize_speech(args.order_text, 'eve'))
        command = [args.godot, '--path', str(server.REPO_ROOT / 'game'), 'res://tests/LiveNovelSpeakingTest.tscn', '--quit-after', '12000', '--', '--taco-wav=' + str(path)]
        if args.capture_dir:
            command.append('--order-capture-dir=' + str(Path(args.capture_dir).resolve()))
        result = subprocess.run(command, cwd=server.REPO_ROOT, timeout=180)
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
