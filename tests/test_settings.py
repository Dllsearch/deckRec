#!/usr/bin/env python3
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import stat
import tarfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'restore-settings.sh'

class SettingsTests(unittest.TestCase):
    @unittest.skipIf(os.geteuid() == 0, 'settings restore intentionally requires regular user')
    def test_existing_settings_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, home, backup = (root / p for p in ('source', 'home', 'backup'))
            for p in (source / '.config', home / '.config', backup):
                p.mkdir(parents=True)
            (source / '.config/existing').write_text('old account')
            (source / '.config/missing').write_text('saved setting')
            (home / '.config/existing').write_text('current account')
            archive = backup / 'home-settings.tar.zst'
            subprocess.run(['tar', '--zstd', '-cpf', str(archive), '-C', str(source), '.config'], check=True)
            checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
            (backup / 'HOME-SHA256SUMS').write_text(f'{checksum}  {archive.name}\n')
            supplemental = backup / 'home-empty-files.tar'
            with tarfile.open(supplemental, 'w') as out:
                info = tarfile.TarInfo('.config/empty-placeholder')
                info.mode = 0
                out.addfile(info)
            with open(backup / 'HOME-SHA256SUMS', 'a') as sums:
                sums.write(f'{hashlib.sha256(supplemental.read_bytes()).hexdigest()}  {supplemental.name}\n')
            result = subprocess.run(['bash', str(SCRIPT), '--backup', str(backup)],
                                    env=dict(os.environ, HOME=str(home)), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((home / '.config/existing').read_text(), 'current account')
            self.assertEqual((home / '.config/missing').read_text(), 'saved setting')
            placeholder = home / '.config/empty-placeholder'
            self.assertEqual(placeholder.stat().st_size, 0)
            self.assertEqual(stat.S_IMODE(placeholder.stat().st_mode), 0)

if __name__ == '__main__':
    unittest.main()
