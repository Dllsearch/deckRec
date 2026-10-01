# Deck Recovery

[Русская документация](README.ru.md)

A portable SteamOS backup and recovery kit with a terminal menu, Steam Deck button
hints, progress counters and archive/file browsers.

Run **without sudo**:

```bash
./rec.sh
./rec.sh --lang en
./rec.sh --lang ru
./rec.sh --lang auto
./rec.sh --status
```

Double-click `Deck Recovery.desktop` to open a terminal. Move the **whole kit** to
another SD card or USB drive; the launcher and scripts resolve their own location.
Individual commands are in `scripts/`. The default snapshot is `backups/current`;
a standalone exported snapshot uses its own directory. `--backup DIR` selects
another snapshot. `pacs` is a relative link to the default snapshot's package cache.

## Language and controls

Russian and English are supported. Automatic selection follows `LC_ALL`, then
`LC_MESSAGES`, then `LANG`: Russian locales use Russian; other locales use English.
The Language menu saves `auto`, `ru` or `en` in `ui-settings.json`. A CLI `--lang`
overrides that setting for the current run; `REC_LANG=en` also works for individual
scripts. Output from external programs uses their own locale.

With Steam's standard desktop layout: D-pad up/down navigates, A opens/starts,
Y toggles selections, B goes back, and STEAM+X opens the on-screen keyboard.
Keyboard equivalents are arrows, Enter, Space and Esc/Q.

## Backup and restore

Select packages, home settings/data, or system settings independently.
`backup-options.json` is generated with defaults when absent; existing settings
are preserved. The backup configuration menu controls large categories and
custom home-folder exclusions. By default, games, Steam prefixes/shader cache,
extra Proton, Flatpak installations/runtimes, caches and trash are excluded.
Flatpak app data, `/etc` and `/usr/local` are included.

Archiving estimates uncompressed source size and requires an additional 1 GiB
reserve while retaining the previous archive. Writing stops below 1 GiB free.
Close apps before backing up home. Wait for all stages to complete before shutting
down normally. A `.part` file is incomplete; remove it only after its writer stops.

Package backups preserve exact installed versions, including available AUR binary
archives. `manifest.json`, `missing.json` and checksums are generated during backup.
A COMPLETE marker means the package snapshot is complete. Restore checks checksums,
skips equal/newer installed versions and uses offline pacman transactions without
downgrading or rebuilding AUR packages. Home restore adds missing files only.
The system archive is available for inspection; the kit does not automatically
extract all of `/etc` over a newer SteamOS.

Archive browsers show uncompressed folder/file sizes without extracting data.
The first visit builds a cached metadata index; B cancels indexing. File browsers
show the current folder's total size; Y toggles support scripts, metadata and logs.

Requirements: Bash, Python 3.11+, GNU tar/du/coreutils, zstd, pacman and vercmp;
package backup additionally needs pyalpm and bsdtar. Desktop launching uses Konsole.
Some system operations request sudo.

## Public GitHub repositories

Publish code, translations, tests, desktop launcher and documentation.
The included `.gitignore` excludes snapshots, package caches, logs, incomplete
files and user preferences. Archives may contain passwords, tokens, private keys,
VPN settings and personal app data. Do not upload them. Ignore rules do not remove
files already committed to Git history. No repository is automatically published.

## Tests

```bash
REC_LANG=ru python3 -m unittest discover -s tests -v
bash -n rec.sh scripts/*.sh
```

The existing behavioral tests assert Russian messages; separate localization tests
cover English, automatic language selection and preservation of format fields.
