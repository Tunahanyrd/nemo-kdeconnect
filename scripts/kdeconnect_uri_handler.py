#!/usr/bin/env python3

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from urllib.parse import urlparse

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

KDECONNECT_DBUS_NAME = "org.kde.kdeconnect"
KDECONNECT_DAEMON_PATH = "/modules/kdeconnect"
KDECONNECT_SFTP_INTERFACE = "org.kde.kdeconnect.device.sftp"


def parse_device_id(uri: str) -> str | None:
    parsed = urlparse(uri)
    if parsed.scheme != "kdeconnect":
        return None

    if parsed.netloc:
        return parsed.netloc

    path = parsed.path.lstrip("/")
    if path:
        return path.split("/", 1)[0]

    return None


def dbus_call(proxy: Gio.DBusProxy, method_name: str, parameters: GLib.Variant | None = None):
    if parameters is None:
        parameters = GLib.Variant("()", ())
    return proxy.call_sync(method_name, parameters, Gio.DBusCallFlags.NONE, 7000, None).unpack()


def unpack_variant(value):
    if isinstance(value, GLib.Variant):
        return value.unpack()
    return value


def get_sftp_proxy(device_id: str) -> Gio.DBusProxy:
    return Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SESSION,
        Gio.DBusProxyFlags.NONE,
        None,
        KDECONNECT_DBUS_NAME,
        f"{KDECONNECT_DAEMON_PATH}/devices/{device_id}/sftp",
        KDECONNECT_SFTP_INTERFACE,
        None,
    )


def ensure_mounted(sftp_proxy: Gio.DBusProxy) -> None:
    is_mounted = bool(dbus_call(sftp_proxy, "isMounted")[0])
    if is_mounted:
        return

    mount_success = bool(dbus_call(sftp_proxy, "mountAndWait")[0])
    if mount_success:
        return

    mount_error = dbus_call(sftp_proxy, "getMountError")[0]
    if isinstance(mount_error, str) and mount_error:
        raise RuntimeError(mount_error)
    raise RuntimeError("Unknown SFTP mount error")


def get_browsable_paths(sftp_proxy: Gio.DBusProxy):
    browsable_paths = []

    directories_result = dbus_call(sftp_proxy, "getDirectories")[0]
    if isinstance(directories_result, dict):
        for path_value, label_value in directories_result.items():
            storage_path = unpack_variant(path_value)
            storage_label = unpack_variant(label_value)

            if not isinstance(storage_path, str) or not storage_path:
                continue
            if not os.path.isdir(storage_path):
                continue

            if not isinstance(storage_label, str):
                storage_label = ""

            browsable_paths.append((storage_path, storage_label))

    if not browsable_paths:
        mount_point = dbus_call(sftp_proxy, "mountPoint")[0]
        if isinstance(mount_point, str) and mount_point and os.path.isdir(mount_point):
            browsable_paths.append((mount_point, ""))

    browsable_paths.sort(key=lambda item: ((item[1] or item[0]).casefold(), item[0]))
    return browsable_paths


def choose_primary_path(browsable_paths):
    for storage_path, storage_label in browsable_paths:
        if isinstance(storage_label, str) and "internal" in storage_label.casefold():
            return storage_path
    return browsable_paths[0][0]


def open_in_nemo(path: str) -> None:
    nemo_bin = shutil.which("nemo")
    if nemo_bin:
        subprocess.Popen(
            [nemo_bin, path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return

    uri = Gio.File.new_for_path(path).get_uri()
    Gio.AppInfo.launch_default_for_uri(uri, None)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: kdeconnect_uri_handler.py kdeconnect://<device-id>", file=sys.stderr)
        return 1

    device_id = parse_device_id(sys.argv[1])
    if not device_id:
        print("Invalid URI. Expected kdeconnect://<device-id>", file=sys.stderr)
        return 1

    try:
        sftp_proxy = get_sftp_proxy(device_id)
        ensure_mounted(sftp_proxy)
        browsable_paths = get_browsable_paths(sftp_proxy)

        if not browsable_paths:
            print("No browsable storage path was exposed by KDE Connect.", file=sys.stderr)
            return 1

        target_path = choose_primary_path(browsable_paths)
        open_in_nemo(target_path)
        return 0
    except GLib.Error as error:
        print(f"DBus error: {error.message}", file=sys.stderr)
        return 1
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
