import contextlib
import importlib.util
import io
import os
import pty
import sys
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rec_menu', ROOT / 'scripts/menu.py')
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)


class MenuTests(unittest.TestCase):
    def test_arrow_does_not_consume_following_space(self):
        master, slave = pty.openpty()
        code = "import importlib.util; s=importlib.util.spec_from_file_location('m', __import__('sys').argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print('READY', flush=True); print(m.read_key(), m.read_key(), flush=True)"
        child = subprocess.Popen([sys.executable, '-c', code, str(ROOT / 'scripts/menu.py')],
                                 stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'READY')
            os.write(master, b'\x1b[B ')
            output, error = child.communicate(timeout=5)
            self.assertEqual(child.returncode, 0, error)
            self.assertEqual(output.strip(), 'down toggle')
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            child.stdout.close()
            child.stderr.close()
            os.close(master)
            os.close(slave)

    def test_plans_components_and_keeps_path_as_one_argument(self):
        path = Path('/tmp/snapshot with spaces')
        backup = menu.build_commands('backup', [0, 2], path)
        self.assertEqual(len(backup), 2)
        self.assertEqual(backup[0][-2:], ['--output', str(path)])
        restore = menu.build_commands('restore', [0, 1], path)
        self.assertEqual(restore[0][-3:], ['--backup', str(path), '--yes'])
        self.assertEqual(Path(restore[1][1]).name, 'restore-settings.sh')
        self.assertNotIn('backup-system.sh', str(restore))

    def test_error_stops_next_component_and_never_reports_success(self):
        commands = menu.build_commands('backup', [1, 2], Path('/tmp/example'))
        # Code 1 may mean checksum/sync failure; it must not be treated as tar's warning.
        with patch.object(menu.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)) as run:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertFalse(menu.execute(commands, 'test'))
            self.assertEqual(run.call_count, 1)
            self.assertNotIn('[OK]', output.getvalue())

    def test_home_warning_continues_and_is_reported(self):
        commands = menu.build_commands('backup', [1, 2], Path('/tmp/example'))
        with patch.object(menu.subprocess, 'run', side_effect=[subprocess.CompletedProcess([], 3), subprocess.CompletedProcess([], 0)]):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertTrue(menu.execute(commands, 'test'))
            self.assertIn('файлы менялись', output.getvalue())

    def test_empty_snapshot_status_is_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertIn('Пакеты: нет полного снимка', menu.snapshot_status(Path(temp)))
            self.assertEqual(list(Path(temp).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
