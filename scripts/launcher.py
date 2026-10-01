#!/usr/bin/env python3
"""Create a desktop launcher for a kit, including an exported snapshot."""
from pathlib import Path


def write_launcher(root):
    root = Path(root).resolve()
    # %k is the clicked launcher's location, so moving the complete kit keeps it usable.
    executable = "import os,pathlib,sys,urllib.parse; p=sys.argv[1]; p=urllib.parse.unquote(urllib.parse.urlparse(p).path) if p.startswith('file:') else p; os.execv('/bin/bash',['bash',str(pathlib.Path(p).resolve().parent/'rec.sh')])"
    launcher = root / 'Deck Recovery.desktop'
    launcher.write_text(
        '[Desktop Entry]\nType=Application\nVersion=1.0\n'
        'Name=Deck Recovery\nName[ru]=Deck Recovery — бэкап и восстановление\n'
        'Comment=Steam Deck backup and recovery console\n'
        'Comment[ru]=Меню резервного копирования и восстановления Steam Deck\n'
        f'Exec=python3 -c "{executable}" %k\n'
        'Icon=utilities-terminal\nTerminal=true\nCategories=System;\n')
    launcher.chmod(0o755)
    return launcher


if __name__ == '__main__':
    write_launcher(Path(__file__).resolve().parent.parent)
