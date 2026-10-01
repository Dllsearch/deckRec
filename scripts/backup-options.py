#!/usr/bin/env python3
"""Portable backup exclusions and preflight sizing."""
import sys as _i18n_sys
from pathlib import Path as _I18nPath
_i18n_sys.path.insert(0, str(_I18nPath(__file__).resolve().parent))
from i18n import t
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
GROUPS = [
 ('games', t('Игры, префиксы и shadercache Steam'), 'home', ['.local/share/Steam/steamapps', '.var/app/com.valvesoftware.Steam/data/Steam/steamapps']),
 ('proton', t('Дополнительные Proton / compatibilitytools'), 'home', ['.local/share/Steam/compatibilitytools.d', '.var/app/com.valvesoftware.Steam/data/Steam/compatibilitytools.d']),
 ('user_flatpak', t('Пользовательские Flatpak и рантаймы (включая Proton-GE)'), 'home', ['.local/share/flatpak']),
 ('app_data', t('Данные приложений Flatpak'), 'home', ['.var/app']),
 ('cache', t('Кэши и корзина'), 'home', ['.cache', '.local/share/Trash', '.npm/_cacache', '.var/app/*/cache', '.local/share/Steam/appcache', '.local/share/Steam/depotcache', '.local/share/Steam/package', '.local/share/Steam/logs']),
 ('local', t('/usr/local: вручную установленные программы'), 'system', ['usr/local']),
 ('system_flatpak', t('Системные Flatpak и рантаймы'), 'system', ['var/lib/flatpak']),
]
DEFAULT = {key: key in ('app_data', 'local') for key, *_ in GROUPS}


def load():
    path = ROOT / 'backup-options.json'
    value = json.loads(path.read_text()) if path.exists() else {}
    options = {'include': {**DEFAULT, **value.get('include', {})},
               'exclude_home': value.get('exclude_home', []), 'exclude_system': value.get('exclude_system', [])}
    if not path.exists():
        # Exclusive create: never replace settings another process has just written.
        try:
            with path.open('x') as out:
                json.dump(options, out, ensure_ascii=False, indent=2)
                out.write('\n')
        except FileExistsError:
            return load()
    return options


def save(options):
    target = ROOT / 'backup-options.json'
    temporary = target.with_suffix('.json.part')
    temporary.write_text(json.dumps(options, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(target)


def exclusions(scope, options=None):
    options = options or load()
    result = []
    for key, label, group_scope, paths in GROUPS:
        if scope == group_scope and not options['include'][key]:
            result.extend(paths)
    result.extend(options['exclude_' + scope])
    # Back up neither the kit itself nor its destination if kept inside HOME.
    if scope == 'home':
        try:
            result.append(str(ROOT.relative_to(Path.home())))
        except ValueError:
            pass
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('scope', choices=['home', 'system'])
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    dest = args.destination.resolve()
    excludes = exclusions(args.scope)
    base = Path.home() if args.scope == 'home' else Path('/')
    try:
        excludes.append(str(dest.relative_to(base)))
    except ValueError:
        pass
    (dest / (args.scope + '-excludes.txt')).write_text('\n'.join(excludes) + '\n')
    if args.scope == 'home':
        paths = sorted(p.name for p in base.iterdir() if p.name.startswith('.'))
    else:
        paths = ['etc'] + [p for key, _, scope, items in GROUPS if scope == 'system' and load()['include'][key] for p in items if (base / p).exists()]
    with open(dest / (args.scope + '-files.list0'), 'wb') as out:
        for path in paths:
            out.write(os.fsencode(path) + b'\0')
    # GNU du uses the same exclusion patterns as tar; count apparent bytes conservatively.
    command = ['du', '--apparent-size', '--block-size=1', '--summarize',
               '--exclude-from=' + str(dest / (args.scope + '-excludes.txt')), '--', *paths]
    result = subprocess.run(command, cwd=base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    size = sum(int(line.split('\t')[0]) for line in result.stdout.splitlines())
    (dest / (args.scope + '-estimated-bytes')).write_text(str(size) + '\n')
    print(t('Оценка несжатых данных: {v0:.2f} ГиБ; исключений: {v1}', v0=size / 1024 ** 3, v1=len(excludes)))
    if result.returncode:
        print(t('Некоторые файлы недоступны для оценки; объём может быть неполным.'))
    free = __import__('shutil').disk_usage(dest).free
    reserve = 1024**3
    # Require space for an uncompressed snapshot plus reserve; existing archive stays intact until success.
    if size + reserve > free:
        raise SystemExit(t('Недостаточно свободного места: нужно до {v0:.2f} ГиБ, доступно {v1:.2f} ГиБ. Отключите большие папки в настройках.', v0=(size + reserve) / 1024 ** 3, v1=free / 1024 ** 3))


if __name__ == '__main__':
    main()
