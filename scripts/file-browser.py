#!/usr/bin/env python3
"""Browse every snapshot file; preview text and inspect archives without extraction."""
import sys as _i18n_sys
from pathlib import Path as _I18nPath
_i18n_sys.path.insert(0, str(_I18nPath(__file__).resolve().parent))
from i18n import t
import concurrent.futures
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('rec_menu', BASE / 'menu.py')
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)


def human(size):
    if size is None:
        return t('размер пока неизвестен')
    for unit in [t('Б'), t('КиБ'), t('МиБ'), t('ГиБ'), t('ТиБ')]:
        if size < 1024 or unit == t('ТиБ'):
            return f'{size:.1f} {unit}'
        size /= 1024


def folder_size(path):
    try:
        result = subprocess.run(['du', '-sb', '-x', '--', str(path)], capture_output=True, text=True, timeout=5)
        return int(result.stdout.split()[0]) if result.returncode == 0 and result.stdout else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def is_service(path):
    return (path.name.startswith('.') or path.name in {
        'scripts', 'tests', '__pycache__', 'COMPLETE', 'SHA256SUMS',
        'HOME-SHA256SUMS', 'SYSTEM-SHA256SUMS', 'os-release',
    } or path.name.endswith(('.json', '.log', '.txt', '.tsv', '.list0',
                            '.lock', '.py', '.sh', '.md', '.desktop', '-estimated-bytes')))


def list_entries(directory, show_service=False):
    return sorted((p for p in directory.iterdir() if show_service or not is_service(p)), key=lambda p: (not (p.is_dir() and not p.is_symlink()), p.name.lower()))


def preview(path):
    try:
        if path.is_symlink():
            lines = [t('Символическая ссылка → ') + os.readlink(path)]
        else:
            with open(path, 'rb') as stream:
                data = stream.read(65537)
            if b'\0' in data[:8192]:
                lines = [t('Двоичный файл. Содержимое не выводится.')]
            else:
                lines = data[:65536].decode('utf-8', errors='replace').splitlines() or [t('Пустой файл.')]
                if len(data) > 65536:
                    lines.append(t('… Показаны только первые 64 КиБ.'))
    except OSError as exc:
        lines = [t('Не удалось прочитать файл: {v0}', v0=exc)]
    offset = 0
    while True:
        terminal = shutil.get_terminal_size()
        height = max(1, terminal.lines - 7)
        print(t('\x1b[2J\x1b[H[ DECK / REC ] Просмотр файла'))
        print(str(path))
        print(t('Размер: {v0} · строки {v1}–{v2}/{v3}\n', v0=human(path.lstat().st_size), v1=offset + 1, v2=min(offset + height, len(lines)), v3=len(lines)))
        for line in lines[offset:offset+height]:
            print(''.join(c if c.isprintable() else ' ' for c in line)[:max(1, terminal.columns-1)])
        print(t('\nКрестовина ↑↓ — прокрутка · A / B / Enter / Esc — назад'), flush=True)
        key = menu.read_key()
        if key in ('enter', 'back', 'q', 'Q'):
            return
        if key in ('down', 's', 'S'):
            offset = min(max(0, len(lines)-height), offset+1)
        elif key in ('up', 'w', 'W'):
            offset = max(0, offset-1)


def browse(root):
    root = Path(root).resolve()
    if not root.is_dir():
        print(t('Каталог снимка отсутствует: {v0}', v0=root)); menu.pause(); return
    current, cursor = root, 0
    pending = {}
    show_service = False
    previous_view = None
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    try:
        while True:
            try:
                children = list_entries(current, show_service)
            except OSError as exc:
                print(exc); menu.pause(); current, cursor = root, 0; continue
            if current not in pending:
                pending[current] = pool.submit(folder_size, current)
            total = human(pending[current].result()) if pending[current].done() else t('считаю…')
            rows = [t('↩ Назад / выход'), t('[{v0}] Показать служебные файлы · Y / пробел', v0='x' if show_service else ' ')]
            for p in children:
                if p.is_symlink():
                    kind, amount = '↗', t('ссылка')
                elif p.is_dir():
                    if p not in pending:
                        pending[p] = pool.submit(folder_size, p)
                    kind = '▸'
                    amount = human(pending[p].result()) if pending[p].done() else t('считаю…')
                else:
                    kind, amount = '·', human(p.stat().st_size)
                rows.append(f'{kind} {p.name} · {amount}')
            cursor = min(cursor, len(rows)-1)
            view = (current, cursor, total, tuple(rows))
            if view != previous_view:
                menu.draw(t('Содержимое снимка'), root, rows, cursor,
                          note=t('Каталог: {v0} · всего {v1} (включая служебные)\nA — открыть · B — назад / выход · Y — служебные файлы', v0=current.relative_to(root), v1=total))
                previous_view = view
            key = menu.read_key(timeout=0.5)
            if key.isdigit() and 1 <= int(key) <= len(rows):
                cursor, key = int(key)-1, 'enter'
            if key == 'toggle' or (key == 'enter' and cursor == 1):
                show_service = not show_service
                cursor = 1
                continue
            if key in ('back', 'q', 'Q') or (key == 'enter' and cursor == 0):
                if current == root:
                    return
                current, cursor = current.parent, 0
            elif key in ('up', 'w', 'W'):
                cursor = (cursor-1) % len(rows)
            elif key in ('down', 's', 'S'):
                cursor = (cursor+1) % len(rows)
            elif key == 'enter' and cursor >= 2:
                chosen = children[cursor-2]
                if chosen.is_symlink():
                    preview(chosen)
                    previous_view = None
                elif chosen.is_dir():
                    current, cursor = chosen, 0
                elif chosen.name.endswith(('.tar', '.tar.zst')):
                    subprocess.run([sys.executable, str(BASE / 'archive-browser.py'), str(chosen)])
                    previous_view = None
                else:
                    preview(chosen)
                    previous_view = None
    finally:
        for future in pending.values():
            future.cancel()
        pool.shutdown(wait=True, cancel_futures=True)


if __name__ == '__main__':
    try:
        browse(Path(sys.argv[1]))
    except (KeyboardInterrupt, EOFError):
        pass
