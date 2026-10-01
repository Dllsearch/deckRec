#!/usr/bin/env python3
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'restore-system.sh'

class RestoreTests(unittest.TestCase):
    def test_version_selection_and_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bins = root / 'bin'
            bins.mkdir()
            mock = bins / 'pacman'
            mock.write_text('''#!/usr/bin/env bash
case "$1" in
-Q) cat "$MOCK_INSTALLED" ;;
-Qp) cat "${@: -1}" ;;
*) echo "UNEXPECTED MUTATION" >&2; exit 99 ;;
esac
''')
            mock.chmod(0o755)
            backup = root / 'backup with spaces'
            (backup / 'packages/repo').mkdir(parents=True)
            versions = {'equal': '2-1', 'newer': '2-1', 'older': '2-1',
                        'missing': '2-1', 'epoch': '1:9-1', 'release': '2-2'}
            rows, sums = [], []
            for name, version in versions.items():
                relative = f'packages/repo/{name}.pkg.tar.zst'
                data = f'{name} {version}\n'.encode()
                (backup / relative).write_bytes(data)
                rows.append(f'{name}\t{version}\t0\t{relative}\n')
                sums.append(f'{hashlib.sha256(data).hexdigest()}  {relative}\n')
            (backup / 'packages.tsv').write_text(''.join(rows))
            (backup / 'SHA256SUMS').write_text(''.join(sums))
            (backup / 'COMPLETE').write_text('6 packages\n')
            installed = root / 'installed'
            installed.write_text('equal 2-1\nnewer 3-1\nolder 1-1\nepoch 2:1-1\nrelease 2-1\n')
            env = dict(os.environ, PATH=f'{bins}:{os.environ["PATH"]}', MOCK_INSTALLED=str(installed))
            def run():
                return subprocess.run(['bash', str(SCRIPT), '--backup', str(backup), '--dry-run'],
                                      env=env, text=True, capture_output=True)
            result = run()
            self.assertEqual(result.returncode, 0, result.stderr)
            for name in ('equal', 'newer', 'epoch'):
                self.assertIn(f'SKIP {name} ', result.stdout)
            for name in ('older', 'missing', 'release'):
                self.assertIn(f'INSTALL {name} ', result.stdout)
            self.assertIn('Packages to install: 3', result.stdout)
            target = backup / 'packages/repo/missing.pkg.tar.zst'
            target.write_text('corrupted')
            self.assertNotEqual(run().returncode, 0)
            (backup / 'COMPLETE').unlink()
            self.assertNotEqual(run().returncode, 0)

if __name__ == '__main__':
    unittest.main()
