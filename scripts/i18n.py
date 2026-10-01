"""Russian/English UI strings. Locale precedence matches gettext conventions."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = json.loads((Path(__file__).resolve().parent / 'locales/en.json').read_text())


def preference():
    value = os.environ.get('REC_LANG')
    if value in ('ru', 'en', 'auto'):
        return value
    try:
        value = json.loads((ROOT / 'ui-settings.json').read_text()).get('language', 'auto')
    except (OSError, ValueError):
        value = 'auto'
    return value if value in ('ru', 'en', 'auto') else 'auto'


def language():
    selected = preference()
    if selected != 'auto':
        return selected
    locale = (os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or
              os.environ.get('LANG') or 'en').lower()
    return 'ru' if locale.startswith('ru') else 'en'


def set_language(value, persist=False):
    if value not in ('ru', 'en', 'auto'):
        raise ValueError(value)
    os.environ['REC_LANG'] = value
    if persist:
        target = ROOT / 'ui-settings.json'
        temporary = target.with_suffix('.json.part')
        temporary.write_text(json.dumps({'language': value}) + '\n')
        temporary.replace(target)


def t(source, **values):
    text = CATALOG.get(source, source) if language() == 'en' else source
    return text.format(**values) if values else text


if __name__ == '__main__':
    print(language())
