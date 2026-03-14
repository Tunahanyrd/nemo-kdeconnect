# KDEConnect Nemo Extension

This extension for the Nemo file manager integrates KDE Connect directly into Nemo.

## Features

- Send selected files to paired KDE Connect devices
- Mount phone storage over KDE Connect SFTP
- Browse mounted phone storage from Nemo
- Show mounted phone storage in Nemo sidebar via managed bookmarks
- Auto-recover attempt when `kdeconnectd` is not running
- Installer auto-configures `kdeconnect://` URI handler when possible

# Usage

Right-click in Nemo and use the `KDE Connect` menu:

- On selected files: `Send selected files`
- On files or folder background: `Browse phone storage`, `Mount phone storage`, `Unmount phone storage`

When a phone storage is mounted, it is added to the Nemo sidebar (Places) and can be accessed like a disk.

## Requirements

- `kdeconnectd` running in the user session
- Phone paired and reachable in KDE Connect
- KDE Connect SFTP plugin enabled for the device
- `msgfmt` (from gettext) for compiling `.mo` localization files during local installs

# Installation

## Automatic install (sh)

```sh
sh scripts/install.sh --restart-nemo
```

This installer also tries to configure `kdeconnect://` URI handling via `xdg-mime`.

Optional target path:

```sh
NEMO_EXTENSIONS_DIR="$HOME/.local/share/nemo-python/extensions" sh scripts/install.sh --restart-nemo
```

## Automatic install (uv)

```sh
uv run scripts/install.py --restart-nemo
```

This installer also tries to configure `kdeconnect://` URI handling via `xdg-mime`.

Optional target path:

```sh
uv run scripts/install.py --extensions-dir ~/.local/share/nemo-python/extensions --restart-nemo
```

## Installer options

### Language override

Default behavior is system locale. If you want to force extension UI language:

```sh
sh scripts/install.sh --language tr --restart-nemo
uv run scripts/install.py --language tr --restart-nemo
```

To remove forced language and return to system locale:

```sh
sh scripts/install.sh --clear-language --restart-nemo
uv run scripts/install.py --clear-language --restart-nemo
```

### URI handler control

If you do not want installer to touch `kdeconnect://` association:

```sh
sh scripts/install.sh --skip-kdeconnect-handler
uv run scripts/install.py --skip-kdeconnect-handler
```

## Uninstall

Remove extension files, managed Nemo sidebar entries, and extension config/state:

```sh
sh scripts/install.sh --uninstall --restart-nemo
uv run scripts/install.py --uninstall --restart-nemo
```

Note: uninstall leaves your global `kdeconnect://` URI handler association unchanged.

## Debian based Distributions (e.g. Ubuntu, Linux Mint, ...)

 Install the `.deb` file from the [releases section](https://github.com/JoeJoeTV/nemo-extension-kdeconnect/releases)

## Other Distributions

 Download the `.tar.gz` or `.zip` file from the [releases section](https://github.com/JoeJoeTV/nemo-extension-kdeconnect/releases) and extract the contents of the `src/` folder in the archive into the nemo-python extensions folder (`~/.local/share/nemo-python/extensions`)

After install, restart Nemo:

```sh
nemo -q && nemo
```

# Translations

If anyone wants to translate this extension, you can just open a pull request with the added `.po` file

# Credits

- Original project: [JoeJoeTV](https://github.com/JoeJoeTV) / [nemo-extension-kdeconnect](https://github.com/JoeJoeTV/nemo-extension-kdeconnect)
- Fork maintenance and production hardening: [Tunahanyrd](https://github.com/Tunahanyrd)
- `v1.3.0` maintenance/update set was generated with GitHub Copilot using GPT-5.3-Codex based on maintainer requirements; manual line-by-line coding was not used for this update set.

# Bugs & Issues

If you find any bugs or issues, please head over to the "Issues" tab and open a new issue there.