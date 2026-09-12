"""Launcher route regressions; no processes or network calls are made."""
import unittest
from unittest.mock import patch
from game import run_novel


class LauncherTests(unittest.TestCase):
    @patch.object(run_novel, 'health', return_value={'protocol': 2})
    @patch.object(run_novel.subprocess, 'run')
    @patch.object(run_novel.subprocess, 'Popen')
    def test_checkout_prefers_current_source_over_export(self, spawn, run, health):
        with patch.object(run_novel.shutil, 'which', return_value='/test/godot'), patch.dict(run_novel.os.environ, {'GODOT_BIN': ''}):
            run_novel.main()
        self.assertEqual(spawn.call_args.args[0][0], '/test/godot')
        self.assertIn('res://scenes/Novel.tscn', spawn.call_args.args[0])
        run.assert_not_called()

    @patch.object(run_novel, 'health', return_value={'protocol': 2})
    @patch.object(run_novel.subprocess, 'run')
    @patch.object(run_novel.subprocess, 'Popen')
    def test_export_remains_fallback_without_engine(self, spawn, run, health):
        with patch.object(run_novel.shutil, 'which', return_value=None), patch.dict(run_novel.os.environ, {'GODOT_BIN': ''}), patch.object(run_novel.sys, 'platform', 'darwin'), patch.object(run_novel.Path, 'exists', lambda p: p.name == 'Stranger2D.app'):
            run_novel.main()
        self.assertEqual(run.call_args.args[0][0], 'open')
        spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
