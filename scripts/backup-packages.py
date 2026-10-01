#!/usr/bin/env python3
"""Back up exact installed versions, including AUR, without changing the system."""
import sys as _i18n_sys
from pathlib import Path as _I18nPath
_i18n_sys.path.insert(0, str(_I18nPath(__file__).resolve().parent))
from i18n import t
import argparse
import concurrent.futures
import hashlib
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import pyalpm
from launcher import write_launcher
import importlib.util
_ui_spec = importlib.util.spec_from_file_location("terminal_ui", Path(__file__).resolve().parent / "terminal-ui.py")
_ui = importlib.util.module_from_spec(_ui_spec)
_ui_spec.loader.exec_module(_ui)
Progress = _ui.Progress

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent if BASE.name == "scripts" else BASE

def output(*args):
    return subprocess.check_output(args, text=True).strip()

def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT if (ROOT / 'packages.tsv').exists() else ROOT / 'backups/current')
    parser.add_argument('--cache-only', action='store_true')
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise SystemExit("Run without sudo to use your own AUR caches and Downloads.")
    dest = args.output.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    os.chmod(dest, 0o700)
    lock = open(dest / '.packages.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    (dest / 'COMPLETE').unlink(missing_ok=True)
    handle = pyalpm.Handle('/', output('pacman-conf', 'DBPath'))
    repos = []
    for name in output('pacman-conf', '--repo-list').splitlines():
        db = handle.register_syncdb(name, 0)
        db.servers = output('pacman-conf', '--repo', name, 'Server').splitlines()
        repos.append(db)
    installed = {p.name: p for p in handle.get_localdb().pkgcache}
    foreign = {n for n in installed if not any(d.get_pkg(n) for d in repos)}
    for group in ('repo', 'foreign'):
        (dest / 'packages' / group).mkdir(parents=True, exist_ok=True)
    (dest / 'installed.txt').write_text(output('pacman', '-Q') + '\n')
    (dest / 'explicit.txt').write_text(output('pacman', '-Qqe') + '\n')
    (dest / 'foreign.txt').write_text('\n'.join(sorted(foreign)) + '\n')
    shutil.copy2('/etc/os-release', dest / 'os-release')
    cache = {}
    progress = Progress(t('Поиск готовых архивов в кэшах'))
    scanned = 0
    prefixes = tuple(f'{p.name}-{v}-' for p in installed.values()
                     for v in {p.version, p.version.split(':', 1)[-1]})
    roots = [dest / 'packages', ROOT / 'packages', ROOT / 'pacs', ROOT / 'incoming', Path('/var/cache/pacman/pkg'),
             Path.home() / '.cache/yay', Path.home() / '.cache/paru', Path.home() / 'Downloads']
    seen_paths = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob('*.pkg.tar*'):
            if not path.is_file() or path.name.endswith(('.sig', '.part')):
                continue
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            if 'older_vers' in path.parts:
                if not path.name.startswith(prefixes):
                    continue
            try:
                scanned += 1
                progress.update(detail=t('Проверено {v0} архивов · bsdtar -xqOf {v1} .PKGINFO', v0=scanned, v1=path.name))
                info = output('bsdtar', '-xqOf', str(path), '.PKGINFO')
                fields = dict(line.split(' = ', 1) for line in info.splitlines() if ' = ' in line)
                name, version = fields['pkgname'], fields['pkgver']
                if name in installed and version == installed[name].version:
                    cache.setdefault(name, path)
            except (subprocess.CalledProcessError, KeyError):
                progress.message(f'Invalid archive: {path}')

    progress.finish(t('Найдено {v0} точных версий', v0=len(cache)))

    # Resolve libalpm objects on the main thread; download plain immutable specs.
    jobs = []
    if not args.cache_only:
        for name, pkg in installed.items():
            repo_pkg = next((d.get_pkg(name) for d in repos if d.get_pkg(name)), None)
            if name not in cache and repo_pkg and repo_pkg.version == pkg.version:
                jobs.append((name, repo_pkg.filename, repo_pkg.sha256sum, list(repo_pkg.db.servers)))

    def download(spec):
        name, filename, checksum, servers = spec
        target = dest / 'packages/repo' / filename
        errors = []
        for server in servers * 3:
            try:
                temporary = target.with_name(target.name + '.part')
                url = server.rstrip('/') + '/' + urllib.parse.quote(filename)
                progress.activity(t('HTTP GET: {v0} · до 4 загрузок одновременно', v0=name))
                with urllib.request.urlopen(url, timeout=45) as response, open(temporary, 'wb') as stream:
                    shutil.copyfileobj(response, stream)
                if not checksum or digest(temporary) != checksum:
                    raise RuntimeError('repository SHA256 mismatch')
                temporary.replace(target)
                return name, target, None
            except Exception as exc:
                errors.append(str(exc))
        return name, None, '; '.join(errors)

    download_errors = {}
    progress = Progress(t('Скачивание недостающих архивов'), len(jobs))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(download, job) for job in jobs]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            name, path, error = future.result()
            if path:
                cache[name] = path
            else:
                download_errors[name] = error
                progress.message(f'Download failed: {name}: {error}')
            progress.update(index, t('Получен ответ: {v0} · ошибок {v1}', v0=name, v1=len(download_errors)), force=index == len(jobs))
    progress.finish(t('Загрузка завершена; ошибок {v0}', v0=len(download_errors)))

    def collect(name):
        pkg = installed[name]
        if name in download_errors:
            raise RuntimeError(download_errors[name])
        group = 'foreign' if name in foreign else 'repo'
        repo_pkg = next((d.get_pkg(name) for d in repos if d.get_pkg(name)), None)
        source = cache.get(name)
        if source:
            target = dest / 'packages' / group / source.name
            if source.resolve() != target.resolve():
                temporary = target.with_name(target.name + '.part')
                shutil.copy2(source, temporary)
                temporary.replace(target)
        else:
            raise RuntimeError('no archive for installed version ' + pkg.version)
        checksum = digest(target)
        if repo_pkg and repo_pkg.version == pkg.version and repo_pkg.sha256sum:
            if checksum != repo_pkg.sha256sum:
                if args.cache_only:
                    raise RuntimeError('cached package differs from repository SHA256')
                _, replacement, error = download((name, repo_pkg.filename, repo_pkg.sha256sum, list(repo_pkg.db.servers)))
                if error:
                    raise RuntimeError(error)
                target = replacement
                checksum = digest(target)
        check = handle.load_pkg(str(target))
        if check.name != name or check.version != pkg.version:
            raise RuntimeError('package metadata mismatch')
        return {'name': name, 'version': pkg.version, 'group': group,
                'file': str(target.relative_to(dest)), 'sha256': checksum, 'reason': pkg.reason}

    records, missing = [], []
    progress = Progress(t('Сохранение и проверка пакетов'), len(installed))
    for index, name in enumerate(sorted(installed), 1):
        progress.update(index - 1, t('Сохранение и SHA256: {v0} {v1}', v0=name, v1=installed[name].version))
        try:
            records.append(collect(name))
        except Exception as exc:
            missing.append({'name': name, 'version': installed[name].version, 'error': str(exc)})
            progress.message(f'MISSING {name}: {exc}')
        progress.update(index, t('Обработан {v0} · не хватает {v1}', v0=name, v1=len(missing)), force=index == len(installed))
    progress.finish(t('Сохранено {v0}; не хватает {v1}', v0=len(records), v1=len(missing)))
    (dest / 'manifest.json').write_text(json.dumps(records, indent=2) + '\n')
    (dest / 'missing.json').write_text(json.dumps(missing, indent=2) + '\n')
    (dest / 'packages.tsv').write_text(''.join(
        f"{p['name']}\t{p['version']}\t{p['reason']}\t{p['file']}\n" for p in records))
    (dest / 'SHA256SUMS').write_text(''.join(f"{p['sha256']}  {p['file']}\n" for p in records))
    if BASE.resolve() != (dest / 'scripts').resolve():
        shutil.copytree(BASE, dest / 'scripts', dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__'))
    for filename in ('rec.sh', 'README.md', 'README.ru.md', '.gitignore', 'backup-options.json', 'ui-settings.json'):
        if (ROOT / filename).exists() and (ROOT / filename).resolve() != (dest / filename).resolve():
            shutil.copy2(ROOT / filename, dest / filename)
    if (ROOT / 'tests').is_dir() and (ROOT / 'tests').resolve() != (dest / 'tests').resolve():
        shutil.copytree(ROOT / 'tests', dest / 'tests', dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__'))
    write_launcher(dest)
    progress = Progress(t('Сохранение снимка на накопитель'))
    progress.message("[CMD] " + __import__("shlex").join(["sync", "-f", str(dest)]))
    subprocess.run(["sync", "-f", str(dest)], check=True)
    progress.finish()
    if missing:
        print(f'INCOMPLETE: {len(missing)} missing; see {dest}/missing.json')
        return 1
    (dest / 'COMPLETE').write_text(f'{len(records)} packages\n')
    _ui.show_command(["sync", "-f", str(dest)])
    subprocess.run(["sync", "-f", str(dest)], check=True)
    print(t('[OK] Снимок готов: {v0} ({v1} пакетов). Скрипт закончил работу.', v0=dest, v1=len(records)))
    return 0

if __name__ == '__main__':
    sys.exit(main())
