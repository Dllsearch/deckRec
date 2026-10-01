import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class BackupOptionsTests(unittest.TestCase):
    def test_default_exclusions_and_custom_choices(self):
        options = module('options', 'backup-options.py')
        with tempfile.TemporaryDirectory() as tmp, patch.object(options, 'ROOT', Path(tmp)):
            data = options.load()
            self.assertIn('.local/share/flatpak', options.exclusions('home', data))
            self.assertIn('var/lib/flatpak', options.exclusions('system', data))
            data['include']['user_flatpak'] = True
            data['exclude_home'].append('.local/share/large-custom-folder')
            options.save(data)
            self.assertNotIn('.local/share/flatpak', options.exclusions('home'))
            self.assertIn('.local/share/large-custom-folder', options.exclusions('home'))

    def test_preflight_refuses_low_space_without_touching_old_archive(self):
        options = module('options', 'backup-options.py')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home, dest = root / 'home', root / 'backup'
            home.mkdir(); dest.mkdir()
            (home / '.config').mkdir()
            archive = dest / 'home-settings.tar.zst'
            archive.write_bytes(b'previous snapshot')
            result = subprocess.CompletedProcess([], 0, '100\t.config\n', '')
            with patch.object(options, 'ROOT', root), patch.object(Path, 'home', return_value=home), \
                 patch.object(options.subprocess, 'run', return_value=result), \
                 patch('shutil.disk_usage', return_value=shutil._ntuple_diskusage(1000, 1000, 0)), \
                 patch.object(sys, 'argv', ['options', 'home', str(dest)]):
                with self.assertRaisesRegex(SystemExit, 'Недостаточно свободного места'):
                    options.main()
            self.assertEqual(archive.read_bytes(), b'previous snapshot')

    def test_home_backup_omits_proton_flatpak_and_games(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home, dest, bins = root / 'home', root / 'backup', root / 'bin'
            for p in (home, dest, bins): p.mkdir()
            for name in ['.config/keep', '.local/share/flatpak/runtime/Proton-GE/file', '.local/share/Steam/compatibilitytools.d/Proton/file', '.local/share/Steam/steamapps/common/game/file']:
                path = home / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture')
            (bins / 'flatpak').write_text('#!/bin/sh\nexit 0\n')
            (bins / 'flatpak').chmod(0o755)
            result = subprocess.run(['bash', str(ROOT / 'scripts/backup-settings.sh'), str(dest)],
                env=dict(os.environ, HOME=str(home), PATH=str(bins)+':'+os.environ['PATH']), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            listing = subprocess.check_output(['tar', '--zstd', '-tf', str(dest / 'home-settings.tar.zst')], text=True)
            self.assertIn('.config/keep', listing)
            self.assertNotIn('Proton', listing)
            self.assertNotIn('game/file', listing)
            self.assertFalse((dest / 'home-empty-files.tar.part').exists())

    def test_archive_tree_counts_sizes_without_following_links(self):
        browser = module('browser', 'archive-browser.py')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'sample.tar'
            with tarfile.open(archive, 'w') as out:
                info = tarfile.TarInfo('etc/folder/file')
                info.size = 7
                out.addfile(info, io.BytesIO(b'content'))
                link = tarfile.TarInfo('etc/link')
                link.type = tarfile.SYMTYPE
                link.linkname = '/huge/folder'
                out.addfile(link)
            for compressed in (False, True):
                target = archive
                if compressed:
                    target = root / 'sample.tar.zst'
                    subprocess.run(['zstd', '-q', str(archive), '-o', str(target)], check=True)
                cache = root / 'index.json'
                # Indexing is a subprocess: signal handlers must not leak into the test runner.
                result = subprocess.run([sys.executable, str(ROOT / 'scripts/archive-browser.py'), '--index', str(target), str(cache)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                nodes = json.loads(cache.read_text())['nodes']
                self.assertEqual(nodes['etc']['size'], 7)
                self.assertEqual(nodes['etc/folder/file']['size'], 7)
                self.assertEqual(nodes['etc/link']['size'], 0)

    def test_launcher_and_script_find_moved_kit(self):
        launcher = module('launcher', 'launcher.py')
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp) / 'moved kit with spaces'
            kit.mkdir()
            shutil.copytree(ROOT / 'scripts', kit / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copy2(ROOT / 'rec.sh', kit / 'rec.sh')
            desktop = launcher.write_launcher(kit)
            line = next(x for x in desktop.read_text().splitlines() if x.startswith('Exec='))
            self.assertNotIn(str(ROOT), line)
            args = shlex.split(line[5:])
            with patch('os.execv') as execute:
                with patch.object(sys, 'argv', ['-c', str(desktop)]):
                    exec(args[2])
                self.assertEqual(execute.call_args.args[1][-1], str(kit / 'rec.sh'))
            result = subprocess.run(['bash', str(kit / 'rec.sh'), '--status'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(kit / 'backups/current'), result.stdout)
