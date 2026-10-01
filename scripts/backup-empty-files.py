#!/usr/bin/env python3
"""Preserve unreadable zero-byte Steam placeholders using their metadata."""
import os
from pathlib import Path
import stat
import sys
import tarfile

home = Path.home()
dest = Path(sys.argv[1]).resolve()
with tarfile.open(dest / (sys.argv[2] if len(sys.argv) > 2 else 'home-empty-files.tar'), 'w', format=tarfile.PAX_FORMAT) as archive:
    with open(dest / 'home-excludes.txt', 'a') as excludes:
        for path in (home / '.local/share/Steam/ubuntu12_64/video').glob('libav*.so.*'):
            metadata = path.lstat()
            if stat.S_ISREG(metadata.st_mode) and metadata.st_size == 0 and not os.access(path, os.R_OK):
                relative = str(path.relative_to(home))
                archive.addfile(archive.gettarinfo(str(path), arcname=relative))
                excludes.write(relative + '\n')
