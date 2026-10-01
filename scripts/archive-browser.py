#!/usr/bin/env python3
"""Browse archive metadata with folder sizes; never extract archive contents."""
import sys as _i18n_sys
from pathlib import Path as _I18nPath
_i18n_sys.path.insert(0, str(_I18nPath(__file__).resolve().parent))
from i18n import t
import argparse
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import signal
import subprocess
import sys
import tarfile
import time

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('rec_menu', BASE / 'menu.py')
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)


def human(size):
    for unit in [t('Б'), t('КиБ'), t('МиБ'), t('ГиБ'), t('ТиБ')]:
        if size < 1024 or unit == t('ТиБ'):
            return f'{size:.1f} {unit}'
        size /= 1024


def add_member(nodes, member):
    path = PurePosixPath(member.name)
    if path.is_absolute() or '..' in path.parts:
        return
    name = str(path)
    if name == '.':
        return
    size = member.size if member.isfile() else 0
    old = nodes.get(name, {}).get('own', 0)
    nodes.setdefault(name, {'dir': member.isdir(), 'size': 0, 'own': 0})
    nodes[name]['dir'] = member.isdir() or nodes[name]['dir']
    nodes[name]['own'] = size
    nodes[name]['size'] += size - old
    for parent in path.parents:
        key = str(parent)
        nodes.setdefault(key, {'dir': True, 'size': 0, 'own': 0})
        nodes[key]['size'] += size - old


def index_archive(archive, cache):
    os.umask(0o077)
    nodes = {'.': {'dir': True, 'size': 0, 'own': 0}}
    command = ['cat', '--', str(archive)] if archive.name.endswith('.tar') else ['zstd', '-dc', '--', str(archive)]
    if not os.access(archive, os.R_OK):
        command = ['sudo', '-n', *command]
    child = subprocess.Popen(command, stdout=subprocess.PIPE, start_new_session=True)
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        with tarfile.open(fileobj=child.stdout, mode='r|') as stream:
            for member in stream:
                add_member(nodes, member)
                stream.members.clear()
        child.stdout.close()
        if child.wait() != 0:
            raise RuntimeError(t('Не удалось прочитать сжатый архив'))
        stat = archive.stat()
        temporary = cache.with_suffix('.json.part')
        temporary.write_text(json.dumps({'size': stat.st_size, 'mtime': stat.st_mtime_ns, 'nodes': nodes}))
        temporary.replace(cache)
    finally:
        child.stdout.close()
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()


def browse(archive):
    os.umask(0o077)
    cache = archive.with_name(archive.name + '.index.json')
    nodes = None
    try:
        data = json.loads(cache.read_text())
        stat = archive.stat()
        if data['size'] == stat.st_size and data['mtime'] == stat.st_mtime_ns:
            nodes = data['nodes']
    except (OSError, ValueError, KeyError):
        pass
    if nodes is None:
        if not os.access(archive, os.R_OK) and subprocess.run(['sudo', '-v']).returncode:
            return
        log_path = archive.with_name(archive.name + '.index.log')
        with open(log_path, 'w') as log:
            child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--index', str(archive), str(cache)], stderr=log)
            start = time.monotonic()
            try:
                while child.poll() is None:
                    print(t('\x1b[2J\x1b[H[ DECK / REC ] Индексация архива\n{v0}\nЧитаются заголовки; файлы не распаковываются.\nПрошло {v1} сек.\nB / Esc — отменить', v0=archive.name, v1=int(time.monotonic() - start)), flush=True)
                    if menu.read_key(timeout=0.5) in ('back', 'q', 'Q'):
                        child.terminate()
                        child.wait(timeout=10)
                        return
            except BaseException:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)
                raise
            if child.returncode:
                print(t('Ошибка чтения архива. Журнал: {v0}', v0=log_path))
                menu.pause()
                return
        nodes = json.loads(cache.read_text())['nodes']
    current, cursor = '.', 0
    while True:
        children = sorted((key for key in nodes if key != '.' and str(PurePosixPath(key).parent) == current),
                          key=lambda key: (not nodes[key]['dir'], PurePosixPath(key).name.lower()))
        rows = [t('↩ Назад')] + [f'{"▸" if nodes[key]["dir"] else "·"} {PurePosixPath(key).name}  {human(nodes[key]["size"])}' for key in children]
        menu.draw(t('Просмотр архива'), archive.parent, rows, cursor,
                  note=t('{v0} / {v1}\nРазмер содержимого: {v2} · размер архива: {v3}\nA — открыть папку / сведения · B — назад', v0=archive.name, v1=current, v2=human(nodes.get(current, {}).get('size', 0)), v3=human(archive.stat().st_size)))
        key = menu.read_key()
        if key in ('back', 'q', 'Q') or (key == 'enter' and cursor == 0):
            if current == '.':
                return
            current, cursor = str(PurePosixPath(current).parent), 0
        elif key in ('up', 'w', 'W'):
            cursor = (cursor - 1) % len(rows)
        elif key in ('down', 's', 'S'):
            cursor = (cursor + 1) % len(rows)
        elif key == 'enter':
            chosen = children[cursor - 1]
            if nodes[chosen]['dir']:
                current, cursor = chosen, 0
            else:
                menu.draw(t('Сведения о файле'), archive.parent, [t('↩ Вернуться')], note=t('{v0}\nРазмер: {v1}', v0=chosen, v1=human(nodes[chosen]['size'])))
                while menu.read_key() not in ('enter', 'back', 'q', 'Q'):
                    pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--index', action='store_true')
    parser.add_argument('archive', type=Path)
    parser.add_argument('cache', nargs='?', type=Path)
    args = parser.parse_args()
    if args.index:
        index_archive(args.archive, args.cache)
    else:
        browse(args.archive)
