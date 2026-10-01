#!/usr/bin/env python3
"""Terminal progress, command display and a live summary of command output."""
import sys as _i18n_sys
from pathlib import Path as _I18nPath
_i18n_sys.path.insert(0, str(_I18nPath(__file__).resolve().parent))
from i18n import t
import argparse
from collections import deque
import os
from pathlib import Path
import re
import shlex
import signal
import shutil
import subprocess
import sys
import threading
import time


def duration(seconds):
    seconds = max(0, int(seconds))
    return f'{seconds // 60:02d}:{seconds % 60:02d}'


def clean(text):
    # File names and external output must not inject terminal control sequences.
    return ''.join(c if c.isprintable() else ' ' for c in str(text)).strip()


def show_command(command):
    print(f'[CMD] {clean(shlex.join(command))}', file=sys.stderr, flush=True)


class Progress:
    def __init__(self, title, total=None):
        self.title, self.total = title, total
        self.start = time.monotonic()
        self.last = 0
        self.tty = sys.stderr.isatty()
        self.done, self.detail = 0, t('Команда выполняется…')
        self.stopped = threading.Event()
        self.lock = threading.RLock()
        self.drawn = False
        self.rendered_detail = None
        print(f'\n[ DECK / REC ] {title}', file=sys.stderr, flush=True)
        self.worker = threading.Thread(target=self.heartbeat, daemon=True)
        self.worker.start()

    def heartbeat(self):
        while not self.stopped.wait(1):
            with self.lock:
                self._render()

    def update(self, done=0, detail='', force=False):
        with self.lock:
            self.done, self.detail = done, clean(detail)
            self._render(force)

    def _clear(self):
        if self.tty and self.drawn:
            print('\r\033[2K\033[1A\r\033[2K', end='', file=sys.stderr)
            self.drawn = False

    def _render(self, force=False):
        now = time.monotonic()
        interval = 0.2 if self.tty else (1 if self.detail != self.rendered_detail else 15)
        if not force and now - self.last < interval:
            return
        self.last = now
        self.rendered_detail = self.detail
        elapsed = now - self.start
        if self.total is not None:
            fraction = min(self.done / self.total, 1) if self.total else 1
            cells = int(fraction * 20)
            bar = '[' + '#' * cells + '.' * (20 - cells) + ']'
            eta = duration(elapsed * max(self.total - self.done, 0) / self.done) if self.done else '--:--'
            status = t('{v0} {v1:4.0%} {v2}/{v3} | {v4} | ~осталось {v5}', v0=bar, v1=fraction, v2=self.done, v3=self.total, v4=duration(elapsed), v5=eta)
        else:
            spinner = '|/-' + chr(92)
            status = t('[{v0}] {v1} | осталось: неизвестно', v0=spinner[int(elapsed) % 4], v1=duration(elapsed))
        if self.tty:
            self._clear()
            width = max(1, shutil.get_terminal_size().columns - 1)
            print(status[:width] + '\n' + ('[>] ' + self.detail)[:width], end='', file=sys.stderr, flush=True)
            self.drawn = True
        else:
            print(f'{status} | {self.detail}', file=sys.stderr, flush=True)

    def activity(self, detail):
        with self.lock:
            self.detail = clean(detail)
            self._render()

    def message(self, text):
        with self.lock:
            self._clear()
            print(clean(text), file=sys.stderr, flush=True)

    def finish(self, message=t('Этап завершён'), state='OK'):
        self.stopped.set()
        self.worker.join()
        with self.lock:
            self._render(force=True)
            if self.tty:
                print(file=sys.stderr)
                self.drawn = False
            print(f'[{state}] {message} · {duration(time.monotonic() - self.start)}', file=sys.stderr, flush=True)


class OutputSummary:
    def __init__(self, checksums=False, hashes=False):
        self.checksums = checksums
        self.hashes = hashes
        self.done = 0
        self.failed = 0
        self.latest = ''
        self.tail = deque(maxlen=12)
        self.partial = {}

    def feed(self, text, final=False, source='log'):
        pending = self.partial.get(source, '') + text
        lines = pending.split('\n')
        self.partial[source] = lines.pop()
        if final and self.partial[source]:
            lines.append(self.partial[source])
            self.partial[source] = ''
        for line in lines:
            line = clean(line)
            if not line:
                continue
            self.latest = line
            self.tail.append(line)
            if self.checksums and re.search(r': (OK|FAILED(?: open or read)?)$', line):
                self.done += 1
                self.failed += not line.endswith(': OK')
            elif self.hashes and re.match(r'^\\?[0-9a-f]{64} [ *]', line):
                self.done += 1
                self.latest = t('SHA256 готов: ') + line.split(' ', 2)[-1].lstrip('*')


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--title', required=True)
    parser.add_argument('--log', required=True)
    parser.add_argument('--watch', type=Path)
    parser.add_argument('--allow-changed', action='store_true')
    parser.add_argument('--checksums', action='store_true', help='count sha256sum --check results')
    parser.add_argument('--hashes', action='store_true', help='count sha256sum creation results')
    parser.add_argument('--stdout-file', type=Path, help='save stdout separately (e.g. SHA256SUMS)')
    parser.add_argument('--total', type=int)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('command is required')
    if args.total is not None and args.total < 0:
        parser.error('total must be nonnegative')
    if command[0] in ('tar', 'sha256sum') and shutil.which('stdbuf'):
        command = ['stdbuf', '-oL', '-eL', *command]
    show_command(command)
    print(t('[i] Каталог: {v0}\n[i] Полный журнал: {v1}', v0=Path.cwd(), v1=args.log), file=sys.stderr, flush=True)
    if args.stdout_file:
        print(t('[i] Результат команды: {v0}', v0=args.stdout_file), file=sys.stderr, flush=True)
    progress = Progress(args.title, args.total)
    summary = OutputSummary(args.checksums, args.hashes)
    child = None
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        env = dict(os.environ)
        if args.checksums:
            env['LC_ALL'] = 'C'
        from contextlib import ExitStack
        with ExitStack() as stack:
            log = stack.enter_context(open(args.log, 'w', opener=lambda path, flags: os.open(path, flags, 0o600)))
            reader = stack.enter_context(open(args.log, errors='replace'))
            output = stack.enter_context(open(args.stdout_file, 'w')) if args.stdout_file else log
            output_reader = stack.enter_context(open(args.stdout_file, errors='replace')) if args.stdout_file else None
            child = subprocess.Popen(command, stdout=output, stderr=log, env=env, start_new_session=True)
            try:
                while True:
                    finished = child.poll() is not None
                    summary.feed(reader.read(), final=finished)
                    if output_reader:
                        summary.feed(output_reader.read(), final=finished, source='stdout')
                    detail = summary.latest or t('Команда работает; новых сообщений пока нет')
                    if args.watch and args.watch.exists():
                        if not finished and shutil.disk_usage(args.watch.parent).free < 1024**3:
                            raise OSError(t('Осталось меньше 1 ГиБ: запись остановлена, недописанный архив можно удалить'))
                        detail = t('Записано {v0:.1f} МиБ · {v1}', v0=args.watch.stat().st_size / 1024 ** 2, v1=detail)
                    if args.checksums or args.hashes:
                        detail = t('Проверено {v0}; ошибок {v1} · {v2}', v0=summary.done, v1=summary.failed, v2=detail)
                    progress.update(summary.done, detail, force=finished)
                    if finished:
                        break
                    time.sleep(0.25)
            except BaseException:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
                raise
        if child.returncode == 1 and args.allow_changed:
            progress.finish(t('Архив записан; файлы менялись при чтении. Журнал: {v0}', v0=args.log), state='WARN')
        elif child.returncode:
            progress.finish(t('ОШИБКА (код {v0}); журнал: {v1}', v0=child.returncode, v1=args.log), state='ERROR')
            for line in summary.tail:
                print(line, file=sys.stderr)
        else:
            progress.finish(t('Команда завершилась (код 0); журнал: {v0}', v0=args.log))
        return child.returncode if child.returncode >= 0 else 128 - child.returncode
    except KeyboardInterrupt:
        progress.finish(t('Прервано; работа не завершена'), state='STOP')
        return 130
    except OSError as exc:
        progress.finish(t('Не удалось выполнить команду: {v0}', v0=exc), state='ERROR')
        return 1


if __name__ == '__main__':
    sys.exit(run())
