#!/usr/bin/env python3
"""Steam Deck recovery console. Commands remain usable independently."""
import sys as _i18n_sys
from pathlib import Path as _I18nPath
_i18n_sys.path.insert(0, str(_I18nPath(__file__).resolve().parent))
from i18n import t, set_language, preference
import argparse
import os
from pathlib import Path
import select
import shlex
import shutil
import importlib.util
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / 'scripts'
CYAN, GREEN, DIM, RESET = '\033[96m', '\033[92m', '\033[2m', '\033[0m'


def read_key(timeout=None):
    import termios
    import tty
    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd, termios.TCSANOW)
        if timeout is not None and not select.select([fd], [], [], timeout)[0]:
            return 'tick'
        key = os.read(fd, 1)
        if key == b'\x1b':
            if select.select([fd], [], [], 0.06)[0]:
                key += os.read(fd, 1)
                if key[-1:] in (b'[', b'O') and select.select([fd], [], [], 0.06)[0]:
                    key += os.read(fd, 1)
        return {b'\x1b[A': 'up', b'\x1b[B': 'down', b'\n': 'enter',
                b'\r': 'enter', b' ': 'toggle', b'\x1b': 'back'}.get(key, key.decode(errors='ignore'))
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)


def snapshot_status(path):
    packages = t('нет полного снимка')
    try:
        marker = (path / 'COMPLETE').read_text().split()
        if len(marker) == 2 and marker[1] == 'packages':
            packages = t('{v0} пакетов', v0=int(marker[0]))
    except (OSError, ValueError):
        pass
    home = t('есть') if (path / 'home-settings.tar.zst').exists() else t('нет')
    try:
        if (path / 'home-backup-status.txt').read_text().strip() != '0':
            home += t(' · есть предупреждение, см. home-backup-note.txt / home-backup.log')
    except OSError:
        pass
    system = t('есть') if (path / 'system-config.tar.zst').exists() else t('нет')
    return [t('Пакеты: {v0}', v0=packages), f'Home: {home}', t('Системный архив: {v0}', v0=system)]


def draw(title, path, entries, cursor=0, checked=None, note=''):
    print('\033[2J\033[H', end='')
    print(f'{CYAN}╔══════════════════════════════════════════════╗\n'
          f'║  DECK / REC      ::      RECOVERY CONSOLE    ║\n'
          f'╚══════════════════════════════════════════════╝{RESET}')
    print(t('\n{v0}{v1}{v2}\n{v3}Снимок: {v4}{v5}', v0=GREEN, v1=title, v2=RESET, v3=DIM, v4=path, v5=RESET))
    for line in snapshot_status(path):
        print(f'  {line}')
    if note:
        print(f'\n{note}')
    print()
    available = max(3, shutil.get_terminal_size().lines - 21 - (note.count('\n') if note else 0))
    begin = max(0, min(cursor - available // 2, len(entries) - available))
    if len(entries) > available:
        print(t('Строки {v0}–{v1} / {v2}', v0=begin + 1, v1=min(begin + available, len(entries)), v2=len(entries)))
    for i in range(begin, min(begin + available, len(entries))):
        entry = entries[i]
        pointer = '▶' if i == cursor else ' '
        checkbox = ('[x] ' if i in checked else '[ ] ') if checked is not None else ''
        color = CYAN if i == cursor else ''
        text = f'{pointer} {i + 1}. {checkbox}' + ''.join(c if c.isprintable() else ' ' for c in entry)
        print(color + ' ' + text[:max(1, shutil.get_terminal_size().columns - 2)] + RESET)
    print(t('\n{v0}Клавиатура: ↑↓ / W,S — выбор  ·  цифры — быстрый выбор', v0=DIM))
    print((t('Пробел — отметить  ·  Enter — запуск  ·  Esc/Q — назад')
           if checked is not None else t('Enter — открыть  ·  Esc/Q — назад')) + RESET)
    print(t('{v0}Steam Deck: крестовина ↑↓ — выбор  ·  A — ', v0=CYAN) +
          (t('запуск  ·  Y — отметить') if checked is not None else t('открыть')) + t('  ·  B — назад') + RESET)
    print(t('{v0}Desktop-раскладка Steam  ·  STEAM+X — экранная клавиатура{v1}', v0=DIM, v1=RESET), flush=True)


def choose(title, path, entries, multiple=False, note=''):
    cursor, checked = 0, set()
    while True:
        draw(title, path, entries, cursor, checked if multiple else None, note)
        key = read_key()
        if key in ('q', 'Q', 'back'):
            return None
        if key in ('up', 'w', 'W'):
            cursor = (cursor - 1) % len(entries)
        elif key in ('down', 's', 'S'):
            cursor = (cursor + 1) % len(entries)
        elif key == 'enter':
            if not multiple:
                return cursor
            if checked:
                return sorted(checked)
        elif multiple and key == 'toggle':
            checked.symmetric_difference_update({cursor})
        elif key.isdigit() and 1 <= int(key) <= len(entries):
            cursor = int(key) - 1
            if multiple:
                checked.symmetric_difference_update({cursor})
            else:
                return cursor


def build_commands(action, selected, path):
    """Pure command planning: no shell interpolation or implicit /etc restore."""
    if action == 'backup':
        options = [[sys.executable, str(SCRIPTS / 'backup-packages.py'), '--output', str(path)],
                   ['bash', str(SCRIPTS / 'backup-settings.sh'), str(path)],
                   ['bash', str(SCRIPTS / 'backup-system.sh'), str(path)]]
    elif action == 'restore':
        options = [['bash', str(SCRIPTS / 'restore-system.sh'), '--backup', str(path), '--yes'],
                   ['bash', str(SCRIPTS / 'restore-settings.sh'), '--backup', str(path)]]
    else:
        raise ValueError(action)
    return [options[index] for index in selected]


def execute(commands, title):
    print('\033[2J\033[H', end='')
    print(t('{v0}[ DECK / REC ] {v1}{v2}\nДождитесь окончания всех этапов.\n', v0=CYAN, v1=title, v2=RESET), flush=True)
    started = time.monotonic()
    warnings = []
    for i, command in enumerate(commands, 1):
        print(t('\n{v0}── Этап {v1}/{v2} ──{v3}', v0=CYAN, v1=i, v2=len(commands), v3=RESET), flush=True)
        print(f"[CMD] {shlex.join(command)}", flush=True)
        result = subprocess.run(command)
        if result.returncode == 3 and Path(command[1]).name == 'backup-settings.sh':
            warnings.append(t('Home: файлы менялись во время чтения; проверьте журнал.'))
        elif result.returncode:
            print(t('\n[!] Работа остановлена: код {v0}. Все этапы не завершены.', v0=result.returncode))
            return False
    elapsed = int(time.monotonic() - started)
    print(t('\n{v0}[OK] Все выбранные этапы завершены · {v1:02d}:{v2:02d}{v3}', v0=GREEN, v1=elapsed // 60, v2=elapsed % 60, v3=RESET))
    for warning in warnings:
        print(f'[!] {warning}')
    print(t('Можно выйти из меню и штатно выключить Steam Deck.'), flush=True)
    return True


def pause():
    print(t('\nEnter / A или B — вернуться в меню… '), flush=True)
    while read_key() not in ('enter', 'back', 'q', 'Q'):
        pass


def configure(snapshot):
    spec = importlib.util.spec_from_file_location('backup_options', SCRIPTS / 'backup-options.py')
    options_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(options_module)
    options = options_module.load()
    while True:
        entries = [f'[{"x" if options["include"][key] else " "}] {label}' for key, label, _, _ in options_module.GROUPS]
        entries += [t('Исключить свои папки home (с размерами)'), t('Сохранить и вернуться')]
        selected = choose(t('Состав бэкапа'), snapshot, entries,
                          note=t('[x] — включено. A переключает пункт. Изменения действуют при следующем бэкапе.'))
        if selected is None:
            return
        if selected < len(options_module.GROUPS):
            key = options_module.GROUPS[selected][0]
            options['include'][key] = not options['include'][key]
        elif selected == len(options_module.GROUPS):
            exclude_browser(options)
        else:
            options_module.save(options)
            return


def exclude_browser(options):
    import concurrent.futures
    base, current, cursor = Path.home(), Path.home(), 0
    sizes = {}
    def size(path):
        try:
            result = subprocess.run(['du', '-sb', '-x', '--', str(path)], capture_output=True, text=True, timeout=5)
            return int(result.stdout.split()[0]) if result.stdout else None
        except subprocess.TimeoutExpired:
            return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        pending = {}
        while True:
            children = sorted((p for p in current.iterdir() if p.is_dir() and not p.is_symlink()), key=lambda p: p.name.lower())
            for p in children:
                if p not in pending:
                    pending[p] = pool.submit(size, p)
                if pending[p].done():
                    sizes[p] = pending[p].result()
            rows = [t('↩ Назад / готово')]
            for p in children:
                relative = str(p.relative_to(base))
                mark = 'x' if relative in options['exclude_home'] else ' '
                amount = (t('{v0:.2f} ГиБ', v0=sizes[p] / 1024 ** 3) if sizes[p] is not None else t('большая папка / оценка >5 сек.')) if p in sizes else t('считаю…')
                rows.append(f'[{mark}] {p.name} · {amount}')
            draw(t('Папки home: исключения'), base, rows, cursor,
                 note=t('{v0}\nY / пробел — исключить папку; A — открыть; B — назад. [x] — исключено.', v0=current))
            key = read_key(timeout=0.5)
            if key in ('back', 'q', 'Q') or (key == 'enter' and cursor == 0):
                if current == base:
                    for future in pending.values(): future.cancel()
                    return
                current, cursor = current.parent, 0
            elif key in ('up', 'w', 'W'):
                cursor = (cursor - 1) % len(rows)
            elif key in ('down', 's', 'S'):
                cursor = (cursor + 1) % len(rows)
            elif cursor and key == 'enter':
                current, cursor = children[cursor - 1], 0
            elif cursor and key == 'toggle':
                relative = str(children[cursor - 1].relative_to(base))
                if relative in options['exclude_home']: options['exclude_home'].remove(relative)
                else: options['exclude_home'].append(relative)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default = ROOT if (ROOT / 'packages.tsv').exists() else ROOT / 'backups/current'
    parser.add_argument('--backup', type=Path, default=default, help=t('каталог снимка'))
    parser.add_argument('--lang', choices=['auto', 'ru', 'en'], help='UI language: auto / ru / en')
    parser.add_argument('--status', action='store_true', help=t('статус снимка без меню'))
    args = parser.parse_args()
    if args.lang:
        set_language(args.lang)
    # Child commands receive the resolved UI language; CLI choices do not overwrite preferences.
    from i18n import language
    os.environ['REC_LANG'] = language()
    spec = importlib.util.spec_from_file_location('backup_options', SCRIPTS / 'backup-options.py')
    options_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(options_module)
    options_module.load()
    path = args.backup.expanduser().resolve()
    if args.status:
        print(t('Снимок: {v0}\n', v0=path) + '\n'.join(snapshot_status(path)))
        return 0
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error(t('Для меню нужен терминал. Используйте --status или отдельные scripts/*.sh.'))
    if os.geteuid() == 0:
        parser.error(t('Запускайте ./rec.sh без sudo; отдельные операции сами запросят пароль.'))
    try:
        while True:
            action = choose(t('Главное меню'), path, [t('Создать / обновить бэкап'), t('Восстановить из снимка'),
                            t('Проверить пакеты без установки'), t('Выбрать каталог снимка'),
                            t('Просмотреть все файлы бэкапа и размеры'), t('Кнопка питания → сон'), t('Настроить состав бэкапа'), t('Язык / Language'), t('Выход')])
            if action is None or action == 8:
                return 0
            if action in (0, 1):
                backup = action == 0
                entries = ([t('Пакеты pacman / AUR'), t('Настройки и данные home'), t('Системные настройки /etc, /usr/local, Flatpak')]
                           if backup else [t('Пакеты pacman / AUR'), t('Только отсутствующие файлы home')])
                note = (t('Выбранные части снимка будут обновлены. Закройте приложения для бэкапа home.')
                        if backup else t('Пакеты: установка без downgrade. Home: существующие файлы сохраняются.\nEnter / A запускает выбранные операции; sudo может запросить пароль.'))
                selected = choose(t('Бэкап') if backup else t('Восстановление'), path, entries, True, note)
                if selected:
                    execute(build_commands('backup' if backup else 'restore', selected, path),
                            t('Создание снимка') if backup else t('Восстановление'))
                    pause()
            elif action == 2:
                execute([['bash', str(SCRIPTS / 'restore-system.sh'), '--backup', str(path), '--dry-run']],
                        t('Проверка снимка; установка не производится'))
                pause()
            elif action == 3:
                print(t('\nНовый каталог (пустой ввод — отмена; STEAM+X — клавиатура):'))
                value = input('> ').strip()
                if value:
                    path = Path(value).expanduser().resolve()
            elif action == 4:
                subprocess.run([sys.executable, str(SCRIPTS / 'file-browser.py'), str(path)])
            elif action == 5:
                option = choose(t('Кнопка питания'), path, [t('Проверить настройку'), t('Установить сон по нажатию'), t('Удалить настройку')])
                if option is not None:
                    result = subprocess.run(['bash', str(SCRIPTS / 'fix-steamdeck-power-button.sh'),
                                             ['status', 'install', 'remove'][option]])
                    if result.returncode and not (option == 0 and result.returncode == 1):
                        print(t('[!] Код завершения: {v0}', v0=result.returncode))
                    pause()
            elif action == 6:
                configure(path)
            elif action == 7:
                selected = choose(t('Язык / Language'), path, ['Auto (locale)', 'Русский', 'English'])
                if selected is not None:
                    set_language(['auto', 'ru', 'en'][selected], persist=True)
    except (KeyboardInterrupt, EOFError):
        print(t('\n[!] Выход. Если операция была прервана, её результат может быть неполным.'))
        return 130


if __name__ == '__main__':
    sys.exit(main())
