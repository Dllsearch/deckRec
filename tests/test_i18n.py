import importlib.util
import json
import os
from pathlib import Path
import string
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import i18n


class I18nTests(unittest.TestCase):
    def test_locale_precedence_and_english_fallback(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(i18n, 'ROOT', Path(temp)):
            for environment, expected in [({'LANG':'ru_RU.UTF-8'}, 'ru'),
                                          ({'LANG':'de_DE.UTF-8'}, 'en'),
                                          ({'LANG':'ru_RU.UTF-8', 'LC_MESSAGES':'en_US.UTF-8'}, 'en'),
                                          ({'LC_ALL':'ru_RU.UTF-8', 'LANG':'en_US.UTF-8'}, 'ru'),
                                          ({'REC_LANG':'en', 'LANG':'ru_RU.UTF-8'}, 'en')]:
                with patch.dict(os.environ, environment, clear=True):
                    self.assertEqual(i18n.language(), expected)

    def test_saved_language_and_auto_choice(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(i18n, 'ROOT', Path(temp)), patch.dict(os.environ, {'LANG':'ru_RU.UTF-8'}, clear=True):
            i18n.set_language('en', persist=True)
            os.environ.pop('REC_LANG')
            self.assertEqual(i18n.language(), 'en')
            i18n.set_language('auto', persist=True)
            self.assertEqual(i18n.language(), 'ru')
            self.assertEqual(json.loads((Path(temp)/'ui-settings.json').read_text())['language'], 'auto')

    def test_translations_preserve_format_fields(self):
        formatter = string.Formatter()
        for source, english in i18n.CATALOG.items():
            original = [(field, spec, conversion) for _, field, spec, conversion in formatter.parse(source) if field is not None]
            translated = [(field, spec, conversion) for _, field, spec, conversion in formatter.parse(english) if field is not None]
            self.assertEqual(original, translated, source)
            english.format(**{field: 2 for field, _, _ in original})

    def test_english_status_via_launcher_override(self):
        result = subprocess.run(['bash', str(ROOT/'rec.sh'), '--lang', 'en', '--status'], capture_output=True, text=True,
                                env=dict(os.environ, REC_LANG='ru'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Snapshot:', result.stdout)
        self.assertIn('Packages:', result.stdout)
        self.assertNotIn('Снимок:', result.stdout)

    def test_missing_backup_options_created_once(self):
        spec = importlib.util.spec_from_file_location('defaults', ROOT/'scripts/backup-options.py')
        options = importlib.util.module_from_spec(spec); spec.loader.exec_module(options)
        with tempfile.TemporaryDirectory() as temp, patch.object(options, 'ROOT', Path(temp)):
            settings = options.load()
            target = Path(temp)/'backup-options.json'
            self.assertEqual(json.loads(target.read_text()), settings)
            settings['include']['games'] = True
            options.save(settings)
            before = target.read_bytes()
            self.assertTrue(options.load()['include']['games'])
            self.assertEqual(target.read_bytes(), before)
