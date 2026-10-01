# Deck Recovery

[Русская версия](README.ru.md)

**Deck Recovery helps Steam Deck owners save their customized SteamOS setup and restore it when system changes need to be reapplied after an update or reinstall.** It combines package backups, home settings and selected system directories in a portable toolkit with an interactive terminal menu.

It is useful if you install additional software through pacman or AUR, customize Desktop Mode, or want a reusable snapshot instead of remembering which packages and settings to restore manually. You can keep the toolkit and snapshots on an SD card or USB drive and use them from another mount point.

Package backup saves **exact installed versions**, including available AUR binary archives. Recovery installs those local archives without downloading or rebuilding packages. Home recovery adds missing files while preserving existing ones. System configuration archives are available for inspection and selective manual recovery.

This is not a full disk image or a complete game/save backup. Games, Proton prefixes and several large software directories are excluded by default. Existing home files are not rolled back to their previous state, and an older package snapshot is not guaranteed to remain compatible with a newer SteamOS release.

## Features

- Interactive backup and recovery menu with Steam Deck button hints.
- Independent selection of packages, home data and system settings.
- Configurable exclusions for large folders, with size estimates and space checks.
- Offline package recovery with checksum verification and version comparison.
- Command display, live activity, progress counters, elapsed time and approximate stage ETA where measurable.
- File and archive browsers with folder/file sizes and controller-friendly navigation.
- Russian and English interfaces, automatic language selection and manual overrides.
- Portable desktop launcher, toolkit and exported package snapshots.

## Quick start

Use SteamOS **Desktop Mode** and run the toolkit as your regular user, without sudo:

```bash
./rec.sh
```

You can also double-click `Deck Recovery.desktop`. If KDE asks whether to trust the launcher, allow execution for your own copy. Running `rec.sh` without a terminal opens Konsole automatically when a graphical session is available. Operations requiring elevated privileges request sudo themselves.

In the menu, choose what to back up or restore, mark the required components, then start them. Before backing up or restoring home data, close the affected applications. Wait for all selected stages to finish before closing the terminal or shutting down normally.

Useful options:

```bash
./rec.sh --status
./rec.sh --backup backups/another-snapshot
./rec.sh --lang en
./rec.sh --lang ru
./rec.sh --lang auto
```

Requirements: SteamOS on Steam Deck, Bash, Python 3.11+, GNU tar/du/coreutils, zstd and the native pacman toolchain. Package backup additionally needs pyalpm and bsdtar. Package recovery uses `vercmp`; desktop launching uses Konsole. System backup and package installation need sudo access.

## Controls and language

| Action | Keyboard | Steam Deck, standard Steam desktop layout |
| --- | --- | --- |
| Navigate | ↑ / ↓ or W / S | D-pad ↑ / ↓ |
| Open or start | Enter | A |
| Toggle a selection | Space | Y |
| Back or exit a browser | Esc / Q | B |
| Enter a path or sudo password | Keyboard input | STEAM + X opens the on-screen keyboard |

Number keys provide quick selection where shown. On a browser's support-files checkbox, A also toggles the setting. Custom Steam Input layouts may map the buttons differently.

The Language menu saves `auto`, `ru` or `en` in `ui-settings.json`. Automatic selection follows `LC_ALL`, then `LC_MESSAGES`, then `LANG`: Russian locales use Russian; other locales use English. `--lang` overrides the language for one run. For individual scripts, use `REC_LANG=en` or `REC_LANG=ru`. Output from external programs uses their own locale.

## What gets backed up

| Component | Contents | Recovery behavior |
| --- | --- | --- |
| Packages | Exact installed pacman package versions, including available AUR/foreign binary archives | Offline installation of missing or older installed versions; no downgrade |
| Home | Top-level hidden files and directories, including settings, authorizations, app data and Steam configuration/userdata, subject to exclusions | Missing files only; existing files are preserved |
| System | `/etc` plus selected `/usr/local` and system Flatpak directories | Browse the archive and recover selected files manually; no automatic whole-system extraction |

Ordinary non-hidden folders such as Documents, Downloads and Desktop are outside the home archive. Downloaded games and save data inside excluded Proton prefixes are outside the default backup too. Symbolic links are stored as links; external targets are not copied.

The **Configure backup contents** menu controls these categories:

| Category | Default |
| --- | --- |
| Steam games, prefixes and shader cache | Excluded |
| Extra Proton / compatibility tools | Excluded |
| User Flatpak installations and runtimes, including Proton-GE | Excluded |
| Flatpak app data in `.var/app` | Included, subject to other exclusions |
| Caches and trash | Excluded |
| `/usr/local` | Included |
| System Flatpak installations and runtimes | Excluded |

`/etc` is included in system backup. You can add custom home-folder exclusions through the folder browser: A opens a folder, Y marks it as excluded, B goes back. Sizes are calculated in the background; scans exceeding five seconds are labeled instead of showing an invented value. Choose **Save and return** to apply your configuration.

`backup-options.json` is generated with defaults when absent; existing settings are preserved. You can also edit relative paths in `exclude_home` and `exclude_system` (`etc/...` or `usr/local/...` for the system). Each archive run records the selected input paths and exclusions in `home-*` or `system-*` files beside the snapshot.

### Space and interrupted backups

Before archiving, the toolkit estimates uncompressed source size after exclusions. It requires that amount plus a 1 GiB reserve while the previous archive remains on disk. This is conservative because the final compression ratio is unknown. Writing stops if free space drops below 1 GiB.

A `.part` file is unfinished, not a ready snapshot. Remove it only after the associated backup/tar/zstd processes have stopped. A successful archive is finalized and flushed to storage before completion is reported. A home-backup warning means files changed during reading; check the log before relying on that snapshot. Copying live application files does not guarantee consistent databases.

## Package collection and recovery

The package collector searches the snapshot cache, `pacs`, `incoming`, pacman's cache, yay/paru caches and Downloads. Missing repository archives are downloaded from configured mirrors only when the exact installed version is available, and checked against the repository SHA256. AUR archives come from local caches: a PKGBUILD alone is not a binary package, and the collector does not build it automatically as root.

Missing exact versions are reported in `missing.json`, without substituting other versions. `COMPLETE` is written only when every installed package has been collected. It confirms **package completeness**, not completeness or consistency of home/system archives.

Recovery verifies package checksums and metadata, compares versions with `vercmp` including epoch and pkgrel, and skips equal or newer installed versions. It uses one offline `pacman -U` transaction with `--needed --overwrite '*'`, and retains dependency checks. It does not run `pacman -Syu`, yay, network downloads or AUR builds. Before installation, the script enables SteamOS devmode when available, disables read-only mode when available, and resizes `/` only if it is Btrfs. Dependency status is restored for newly installed dependency packages.

`--overwrite` handles file conflicts, not incompatible dependencies or file-versus-directory conflicts. After a SteamOS change, foreign packages may need rebuilding against newer libraries. The script reports transaction failures rather than disabling dependency checks.

Dropping a new archive into `pacs` or `incoming` does **not** update the snapshot index. If its version is installed on the source system, rerun the package collector to regenerate the manifests and checksums.

## Individual scripts

All working scripts are in `scripts/`; the menu calls the same commands.

| Script | Purpose |
| --- | --- |
| `backup-packages.py` | Collect exact package archives and generate manifests/checksums |
| `backup-settings.sh` | Archive selected hidden home files and app data |
| `backup-system.sh` | Archive selected system directories using sudo |
| `restore-all.sh` | Restore packages; optionally add missing home files with `--with-settings` |
| `restore-system.sh` | Verify and restore packages; `--dry-run` checks without installation |
| `restore-settings.sh` | Restore missing home files as their owner, without sudo |
| `fix-steamdeck-power-button.sh` | Configure suspend on a short power-button press; `status` checks and `remove` undoes it; reboot after changes |

Other files implement configuration, translation, progress, browsing and preservation of unreadable zero-byte Steam placeholders. They are helpers, not separate backup components.

Examples, from the toolkit directory:

```bash
# Create or update the default snapshot
./scripts/backup-packages.py
./scripts/backup-settings.sh
./scripts/backup-system.sh

# Keep a separate snapshot
./scripts/backup-packages.py --output backups/another-snapshot
./scripts/backup-settings.sh backups/another-snapshot
./scripts/backup-system.sh backups/another-snapshot

# Verify without changing the system
./scripts/restore-system.sh --dry-run

# Restore packages, optionally adding missing home files
./scripts/restore-all.sh --yes
./scripts/restore-all.sh --yes --with-settings
```

Restore commands accept `--backup DIR`. Package collection also supports `--cache-only` to avoid downloading missing repository archives. Reusing an output directory updates its package index.

## Browsing and progress

**Browse backup files and sizes** shows the current folder's total size, including hidden support files. Scripts, metadata and logs are hidden by default; Y/Space or A on **Show support files** reveals them. Text preview supports scrolling and reads at most the first 64 KiB.

Opening a tar archive shows its directory tree and uncompressed file/folder sizes without extracting contents. The first visit reads the archive to build `*.index.json`; B cancels indexing or returns through folders and exits at the root. The index is reused while the archive's size and modification time match. The archive's displayed file size is compressed; tree sizes are uncompressed.

`[CMD]` displays the command being run. The UI shows current activity, package/checksum counters, errors and elapsed time. Approximate ETA applies to measurable stages; archive compression and pacman installation do not have a reliable countdown. Full archive output is saved to `home-backup.log` or `system-backup.log`; restore logs use `/tmp/rec-*`.

## Layout and portability

```text
Deck Recovery.desktop    Desktop launcher
rec.sh                   Main entry point
scripts/                 Commands, UI helpers and translations
tests/                   Automated checks
backup-options.json      Generated backup configuration
ui-settings.json         Generated language preference
backups/current/         Default private snapshot
incoming/                Extra package archives outside the snapshot index
pacs -> backups/current/packages
```

Code-only checkouts may not contain snapshots, caches or preferences yet. Backup operations create their destinations and generated metadata as needed. The default snapshot is `backups/current`; an exported snapshot containing `packages.tsv` uses its own directory.

Move or rename the **whole toolkit directory** after active operations finish. Keep internal names and structure unchanged. The scripts resolve their own location; the desktop launcher uses its location through `%k`; `pacs` is a relative symlink. An exported package snapshot includes its own launcher, scripts, documentation and available preferences, updated by the package collector. Move those files together with its archives and manifests to use the snapshot independently.

## Privacy and GitHub

Home and system archives can contain authorizations, tokens, private keys, VPN configuration and other personal data. File lists, archive indices and logs may expose personal paths too.

Public repositories should contain code, translations, tests, the desktop launcher and documentation. The included `.gitignore` excludes snapshots, package caches, archives, logs, unfinished files and user preferences, including metadata at the root of an exported snapshot. Ignore rules do not remove files already committed to Git history. The toolkit does not publish or upload backups automatically.

## Validation

```bash
REC_LANG=ru python3 -m unittest discover -s tests -v
bash -n rec.sh scripts/*.sh
```

Tests cover package version selection and checksum failures, preservation of existing home files, backup exclusions, space checks, archive metadata sizes, portability, menu control handling and language selection. Behavioral tests use Russian messages; localization checks also cover English. Tests do not perform a real package installation.
