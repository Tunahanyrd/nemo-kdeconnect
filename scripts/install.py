#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


def compile_mo(msgfmt_bin: str | None, po_file: Path, mo_file: Path) -> None:
    if not msgfmt_bin:
        return

    subprocess.run(
        [msgfmt_bin, "-f", "-o", str(mo_file), str(po_file)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def install_extension(repo_root: Path, extensions_dir: Path) -> None:
    plugin_src = repo_root / "src" / "nemo-kdeconnect.py"
    locale_src = repo_root / "src" / "nemo-kdeconnect" / "locale"

    if not plugin_src.exists():
        raise FileNotFoundError(f"Plugin file missing: {plugin_src}")

    extensions_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(plugin_src, extensions_dir / "nemo-kdeconnect.py")

    locale_target_root = extensions_dir / "nemo-kdeconnect" / "locale"
    if locale_target_root.parent.exists():
        shutil.rmtree(locale_target_root.parent)
    locale_target_root.mkdir(parents=True, exist_ok=True)

    msgfmt_bin = shutil.which("msgfmt")
    if not msgfmt_bin:
        print("warning: msgfmt not found, .mo files will not be generated (install gettext).")

    for po_file in sorted(locale_src.rglob("*.po")):
        relative = po_file.relative_to(locale_src)
        target_dir = locale_target_root / relative.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        po_target = target_dir / "nemo-kdeconnect.po"
        mo_target = target_dir / "nemo-kdeconnect.mo"

        shutil.copy2(po_file, po_target)
        compile_mo(msgfmt_bin, po_file, mo_target)


def get_paths() -> dict[str, Path]:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return {
        "config_file": config_home / "nemo-kdeconnect" / "config.json",
        "state_file": cache_home / "nemo-kdeconnect" / "sidebar_state.json",
        "bookmarks_file": config_home / "gtk-3.0" / "bookmarks",
        "uri_handler_desktop_file": data_home / "applications" / "nemo-kdeconnect-uri-handler.desktop",
    }


def cleanup_managed_sidebar_bookmarks(state_file: Path, bookmarks_file: Path) -> None:
    if not state_file.exists() or not bookmarks_file.exists():
        return

    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return

    managed_uris = state.get("managed_uris", []) if isinstance(state, dict) else []
    if not isinstance(managed_uris, list):
        return

    managed_uri_set = {uri for uri in managed_uris if isinstance(uri, str)}
    if not managed_uri_set:
        return

    try:
        lines = [line.rstrip("\n") for line in bookmarks_file.read_text(encoding="utf-8").splitlines()]
    except OSError:
        return

    updated_lines = []
    for line in lines:
        if not line.strip():
            continue
        uri = line.split(" ", 1)[0].strip()
        if uri in managed_uri_set:
            continue
        updated_lines.append(line)

    try:
        bookmarks_file.write_text(("\n".join(updated_lines) + "\n") if updated_lines else "", encoding="utf-8")
    except OSError:
        return


def uninstall_extension(extensions_dir: Path) -> None:
    plugin_target = extensions_dir / "nemo-kdeconnect.py"
    uri_handler_target = extensions_dir / "nemo-kdeconnect-uri-handler.py"
    locale_root = extensions_dir / "nemo-kdeconnect"
    pycache_dir = extensions_dir / "__pycache__"

    paths = get_paths()
    config_file = paths["config_file"]
    state_file = paths["state_file"]
    bookmarks_file = paths["bookmarks_file"]
    uri_handler_desktop_file = paths["uri_handler_desktop_file"]

    print(f"Uninstalling nemo-kdeconnect from: {extensions_dir}")

    cleanup_managed_sidebar_bookmarks(state_file, bookmarks_file)

    if plugin_target.exists():
        plugin_target.unlink()
    if uri_handler_target.exists():
        uri_handler_target.unlink()
    if uri_handler_desktop_file.exists():
        uri_handler_desktop_file.unlink()

    if locale_root.exists():
        shutil.rmtree(locale_root)

    if pycache_dir.exists():
        for pyc_file in pycache_dir.glob("nemo-kdeconnect*.pyc"):
            pyc_file.unlink(missing_ok=True)
        try:
            pycache_dir.rmdir()
        except OSError:
            pass

    if state_file.exists():
        state_file.unlink(missing_ok=True)
    if config_file.exists():
        config_file.unlink(missing_ok=True)

    for parent_dir in (state_file.parent, config_file.parent):
        try:
            parent_dir.rmdir()
        except OSError:
            pass

    restore_kdeconnect_handler_if_needed()

    print("Uninstallation completed.")


def configure_kdeconnect_handler(repo_root: Path, extensions_dir: Path, skip_handler_setup: bool) -> None:
    if skip_handler_setup:
        return

    xdg_mime = shutil.which("xdg-mime")
    if not xdg_mime:
        print("warning: xdg-mime is missing, skipping kdeconnect:// handler setup")
        return

    uri_handler_source = repo_root / "scripts" / "kdeconnect_uri_handler.py"
    if not uri_handler_source.exists():
        print(f"warning: URI handler source was not found ({uri_handler_source}), skipping URI handler setup")
        return

    uri_handler_target = extensions_dir / "nemo-kdeconnect-uri-handler.py"
    uri_handler_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(uri_handler_source, uri_handler_target)
    uri_handler_target.chmod(0o755)

    uri_handler_desktop_file = get_paths()["uri_handler_desktop_file"]
    uri_handler_desktop_file.parent.mkdir(parents=True, exist_ok=True)
    escaped_target = str(uri_handler_target).replace("\\", "\\\\").replace(" ", "\\ ")
    desktop_content = (
        "[Desktop Entry]\n"
        "Name=Nemo KDE Connect URI Handler\n"
        f"Exec=python3 {escaped_target} %u\n"
        "Type=Application\n"
        "NoDisplay=true\n"
        "MimeType=x-scheme-handler/kdeconnect;\n"
        "Terminal=false\n"
    )
    uri_handler_desktop_file.write_text(desktop_content, encoding="utf-8")

    desktop_name = uri_handler_desktop_file.name

    subprocess.run(
        [xdg_mime, "default", desktop_name, "x-scheme-handler/kdeconnect"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    query_result = subprocess.run(
        [xdg_mime, "query", "default", "x-scheme-handler/kdeconnect"],
        check=False,
        text=True,
        capture_output=True,
    )
    current_default = query_result.stdout.strip()
    if current_default == desktop_name:
        print(f"Configured kdeconnect:// URI handler: {desktop_name}")
    else:
        display_value = current_default if current_default else "none"
        print(f"warning: failed to set kdeconnect:// handler (current: {display_value})")


def restore_kdeconnect_handler_if_needed() -> None:
    xdg_mime = shutil.which("xdg-mime")
    if not xdg_mime:
        return

    uri_handler_desktop_file = get_paths()["uri_handler_desktop_file"]
    desktop_name = uri_handler_desktop_file.name
    query_result = subprocess.run(
        [xdg_mime, "query", "default", "x-scheme-handler/kdeconnect"],
        check=False,
        text=True,
        capture_output=True,
    )
    current_default = query_result.stdout.strip()
    if current_default != desktop_name:
        return

    app_dirs = [Path.home() / ".local/share/applications", Path("/usr/share/applications")]
    fallback_candidates = ["org.kde.kdeconnect.handler.desktop", "kdeconnect-handler.desktop"]

    for candidate in fallback_candidates:
        for app_dir in app_dirs:
            if (app_dir / candidate).exists():
                subprocess.run(
                    [xdg_mime, "default", candidate, "x-scheme-handler/kdeconnect"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                print(f"Restored kdeconnect:// URI handler to: {candidate}")
                return

    print("No fallback kdeconnect:// handler found; URI association is left unchanged.")


def validate_language(language: str) -> None:
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._@-")
    if not language:
        raise ValueError("--language value cannot be empty")
    if any(char not in allowed_chars for char in language):
        raise ValueError("invalid language value, allowed characters: letters, numbers, dot, underscore, dash, at")


def write_language_config(language: str) -> None:
    validate_language(language)

    config_file = get_paths()["config_file"]
    config_dir = config_file.parent
    config_dir.mkdir(parents=True, exist_ok=True)

    with config_file.open("w", encoding="utf-8") as file_handle:
        json.dump({"language": language}, file_handle, ensure_ascii=False, indent=2)
        file_handle.write("\n")

    print(f"Configured extension language: {language}")


def clear_language_config() -> None:
    config_file = get_paths()["config_file"]
    if config_file.exists():
        config_file.unlink()
    print("Cleared language override (system locale will be used).")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install nemo-kdeconnect into local Nemo extensions")
    parser.add_argument(
        "--extensions-dir",
        default="~/.local/share/nemo-python/extensions",
        help="Target Nemo extension directory",
    )
    parser.add_argument(
        "--restart-nemo",
        action="store_true",
        help="Restart Nemo after installation",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove extension files and managed settings",
    )
    parser.add_argument(
        "--language",
        help="Force extension language (e.g. tr, en, de, tr_TR.UTF-8)",
    )
    parser.add_argument(
        "--clear-language",
        action="store_true",
        help="Remove forced language and use system locale again",
    )
    parser.add_argument(
        "--skip-kdeconnect-handler",
        action="store_true",
        help="Do not set kdeconnect:// URI handler",
    )
    args = parser.parse_args()

    if args.language and args.clear_language:
        parser.error("--language and --clear-language cannot be used together")
    if args.uninstall and (args.language or args.clear_language):
        parser.error("--uninstall cannot be combined with --language or --clear-language")

    repo_root = Path(__file__).resolve().parents[1]
    extensions_dir = Path(args.extensions_dir).expanduser()

    if args.uninstall:
        uninstall_extension(extensions_dir)
    else:
        install_extension(repo_root, extensions_dir)
        configure_kdeconnect_handler(repo_root, extensions_dir, args.skip_kdeconnect_handler)

        if args.language:
            write_language_config(args.language)
        elif args.clear_language:
            clear_language_config()

    if args.restart_nemo:
        subprocess.run(["nemo", "-q"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not args.uninstall:
        print(f"Installed into: {extensions_dir}")
    print("Done. Restart Nemo with: nemo -q && nemo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
