import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

UI = Path(__file__).resolve().parents[1] / 'scripts' / 'terminal-ui.py'


class TerminalUITests(unittest.TestCase):
    def run_command(self, code, *options):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'command.log'
            result = subprocess.run(
                [sys.executable, str(UI), '--title', 'Тест', '--log', str(log),
                 *options, '--', sys.executable, '-c', code],
                capture_output=True, text=True)
            return result, log.read_text()

    def test_success_captures_noise_without_ansi(self):
        result, log = self.run_command('print("package noise")')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('package noise', log)
        self.assertIn('[CMD]', result.stderr)
        self.assertIn('package noise', result.stderr)
        self.assertNotIn('\x1b', result.stderr)
        self.assertIn('[OK]', result.stderr)

    def test_failure_keeps_status_and_displays_error(self):
        result, log = self.run_command('import sys; print("broken archive"); sys.exit(2)')
        self.assertEqual(result.returncode, 2)
        self.assertIn('broken archive', result.stderr)
        self.assertIn('ОШИБКА', result.stderr)

    def test_changed_archive_is_warning_with_original_status(self):
        result, log = self.run_command('import sys; sys.exit(1)', '--allow-changed')
        self.assertEqual(result.returncode, 1)
        self.assertIn('файлы менялись', result.stderr)
        self.assertNotIn('ОШИБКА', result.stderr)

    def test_checksum_counts_real_results_and_preserves_failure(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = [root / 'one package', root / 'two']
            for path in paths:
                path.write_bytes(b'good')
            manifest = root / 'SHA256SUMS'
            manifest.write_text(''.join(f'{hashlib.sha256(b"good").hexdigest()}  {path.name}\n' for path in paths))
            def run():
                return subprocess.run([sys.executable, str(UI), '--title', 'SHA256',
                    '--log', str(root / 'check.log'), '--checksums', '--total', '2',
                    '--', 'sha256sum', '--check', 'SHA256SUMS'], cwd=root, text=True, capture_output=True)
            result = run()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('2/2', result.stderr)
            self.assertIn('100%', result.stderr)
            self.assertIn('two: OK', result.stderr)
            paths[0].write_bytes(b'bad')
            result = run()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('ошибок 1', result.stderr)
            self.assertIn('FAILED', result.stderr)
            self.assertIn('[ERROR]', result.stderr)
            paths[0].unlink()
            result = run()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('2/2', result.stderr)
            self.assertIn('FAILED open or read', result.stderr)

    def test_hash_output_is_valid_and_stderr_never_enters_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'present').write_bytes(b'good')
            manifest = root / 'SUMS'
            result = subprocess.run([sys.executable, str(UI), '--title', 'Create hashes',
                '--log', str(root / 'hash.log'), '--hashes', '--total', '2',
                '--stdout-file', str(manifest), '--', 'sha256sum', 'present', 'missing'],
                cwd=root, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('1/2', result.stderr)
            self.assertNotIn('No such file', manifest.read_text())
            check = subprocess.run(['sha256sum', '--check', str(manifest)], cwd=root, capture_output=True)
            self.assertEqual(check.returncode, 0)

    def test_live_output_appears_before_command_exits(self):
        import selectors
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.Popen([sys.executable, str(UI), '--title', 'Live',
                '--log', str(Path(temp) / 'live.log'), '--', sys.executable, '-c',
                'import time; print("LIVE-MESSAGE", flush=True); time.sleep(20)'],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            # Binary nonblocking reads avoid TextIO buffering in select().
            selector = selectors.DefaultSelector()
            selector.register(result.stderr, selectors.EVENT_READ)
            seen = b''
            try:
                import time
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if selector.select(0.2):
                        seen += os.read(result.stderr.fileno(), 4096)
                    # Look for a rendered output line, not the quoted command header.
                    if b'| LIVE-MESSAGE' in seen:
                        break
                self.assertIn(b'| LIVE-MESSAGE', seen)
                self.assertIsNone(result.poll())
            finally:
                import signal
                result.send_signal(signal.SIGINT)
                result.wait(timeout=5)
                result.stderr.close()
                selector.close()


if __name__ == '__main__':
    unittest.main()
