#!/usr/bin/python3

# Name: KDE Connect Nemo Extension
# Description: KDE Connect Integration for the Nemo file manager
# by JoeJoeTV
# maintained by Tunahanyrd
# implementation support: GitHub Copilot (GPT-5.3-Codex)
# https://github.com/JoeJoeTV/nemo-extension-kdeconnect

EXTENSION_VERSION = "1.3.0"

import gettext
import json
import os
import shutil
import subprocess
import time

import gi

gi.require_version('Notify', '0.7')
from gi.repository import GObject, Nemo, Gio, GLib, Notify  # type: ignore

KDECONNECT_DBUS_NAME = "org.kde.kdeconnect"
KDECONNECT_DAEMON_PATH = "/modules/kdeconnect"
KDECONNECT_DAEMON_INTERFACE = "org.kde.kdeconnect.daemon"
SIDEBAR_REFRESH_SECONDS = 12
BOOKMARKS_PATH = os.path.expanduser("~/.config/gtk-3.0/bookmarks")
SIDEBAR_STATE_PATH = os.path.expanduser("~/.cache/nemo-kdeconnect/sidebar_state.json")
CONFIG_PATH = os.path.expanduser("~/.config/nemo-kdeconnect/config.json")
KDECONNECT_DAEMON_START_COOLDOWN_SECONDS = 10
KDECONNECT_DAEMON_COMMANDS = (
    "kdeconnectd",
    "/usr/lib/kdeconnectd",
    "/usr/libexec/kdeconnectd",
)

def read_extension_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as config_file:
            config = json.load(config_file)
            if isinstance(config, dict):
                return config
    except (OSError, ValueError, TypeError):
        pass

    return {}


def get_language_override():
    config = read_extension_config()
    language = config.get("language")
    if not isinstance(language, str):
        return None

    language = language.strip()
    if not language:
        return None

    return language


def try_load_translation(localedir, languages=None):
    options = {"fallback": False}
    if languages:
        options["languages"] = languages

    try:
        return gettext.translation("nemo-kdeconnect", localedir, **options)
    except OSError:
        return None


def load_translation():
    extension_locale_dir = os.path.dirname(os.path.realpath(__file__)) + "/nemo-kdeconnect/locale"
    system_locale_dir = "/usr/share/locale"

    language_override = get_language_override()
    if language_override:
        forced_languages = [language_override]
        for locale_dir in (extension_locale_dir, system_locale_dir):
            translation = try_load_translation(locale_dir, forced_languages)
            if translation is not None:
                print(f"[KDEConnectMenu] Using forced language: {language_override}")
                return translation

        print(f"[KDEConnectMenu] Forced language '{language_override}' not found, falling back to system locale.")

    for locale_dir in (extension_locale_dir, system_locale_dir):
        translation = try_load_translation(locale_dir)
        if translation is not None:
            return translation

    return gettext.translation("nemo-kdeconnect", system_locale_dir, fallback=True)


# Setup localization
t = load_translation()

# Install _() function into namespace
t.install()
_ = t.gettext


def get_device_icon(device_type):
    """ Given a device type, returns the fitting icon for the device or a fallback icon """
    if device_type == "desktop":
        return "computer-symbolic"
    elif device_type == "laptop":
        return "laptop-symbolic"
    elif device_type == "smartphone":
        return "smartphone-symbolic"
    elif device_type == "tablet":
        return "tablet-symbolic"
    elif device_type == "tv":
        return "tv-symbolic"
    else:
        return "dialog-question-symbolic"


class KDEConnectMenu(GObject.GObject, Nemo.MenuProvider, Nemo.NameAndDescProvider):
    def __init__(self):
        GObject.GObject.__init__(self)

        self.dbus_daemon = None
        self.notify_ready = False
        self.dbus_warning_printed = False
        self.last_daemon_start_attempt = 0.0

        self.ensure_dbus_proxy()
        self.refresh_sidebar_bookmarks()
        GLib.timeout_add_seconds(SIDEBAR_REFRESH_SECONDS, self.on_sidebar_refresh_timer)

        print(f"[KDEConnectMenu] KDE Connect Nemo Extension v{EXTENSION_VERSION} initialized.")

    def ensure_dbus_proxy(self):
        if self.dbus_daemon is not None:
            return True

        for try_number in (1, 2):
            try:
                self.dbus_daemon = Gio.DBusProxy.new_for_bus_sync(
                    Gio.BusType.SESSION,
                    Gio.DBusProxyFlags.NONE,
                    None,
                    KDECONNECT_DBUS_NAME,
                    KDECONNECT_DAEMON_PATH,
                    KDECONNECT_DAEMON_INTERFACE,
                    None
                )
                self.dbus_daemon.connect("g-signal", self.on_daemon_signal)
                self.dbus_warning_printed = False
                return True
            except GLib.Error as error:
                self.dbus_daemon = None

                if try_number == 1:
                    self.try_start_kdeconnect_daemon()
                    continue

                if not self.dbus_warning_printed:
                    print(f"[KDEConnectMenu] KDE Connect daemon is not reachable: {error.message}")
                    self.dbus_warning_printed = True
                return False

        return False

    def try_start_kdeconnect_daemon(self):
        now = time.monotonic()
        if now - self.last_daemon_start_attempt < KDECONNECT_DAEMON_START_COOLDOWN_SECONDS:
            return

        self.last_daemon_start_attempt = now

        for daemon_cmd in KDECONNECT_DAEMON_COMMANDS:
            executable = daemon_cmd if daemon_cmd.startswith("/") else shutil.which(daemon_cmd)
            if not executable:
                continue

            try:
                subprocess.Popen(
                    [executable],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
            except OSError:
                continue

        # Allow daemon a short time to appear on DBus before the second connect attempt
        time.sleep(0.3)

    def on_daemon_signal(self, proxy, sender_name, signal_name, parameters):
        if signal_name in ("deviceAdded", "deviceRemoved", "deviceVisibilityChanged", "deviceListChanged"):
            self.refresh_sidebar_bookmarks()

    def on_sidebar_refresh_timer(self):
        if self.dbus_daemon is None:
            self.ensure_dbus_proxy()

        self.refresh_sidebar_bookmarks()
        return True

    def dbus_call(self, proxy, method_name, parameters=None):
        if parameters is None:
            parameters = GLib.Variant("()", ())
        return proxy.call_sync(method_name, parameters, Gio.DBusCallFlags.NONE, 5000, None).unpack()

    def make_proxy(self, object_path, interface_name):
        return Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            None,
            KDECONNECT_DBUS_NAME,
            object_path,
            interface_name,
            None
        )

    def get_device_proxy(self, device_id):
        return self.make_proxy(
            f"{KDECONNECT_DAEMON_PATH}/devices/{device_id}",
            "org.kde.kdeconnect.device"
        )

    def get_share_proxy(self, device_id):
        return self.make_proxy(
            f"{KDECONNECT_DAEMON_PATH}/devices/{device_id}/share",
            "org.kde.kdeconnect.device.share"
        )

    def get_sftp_proxy(self, device_id):
        return self.make_proxy(
            f"{KDECONNECT_DAEMON_PATH}/devices/{device_id}/sftp",
            "org.kde.kdeconnect.device.sftp"
        )

    def get_proxy_property(self, proxy, property_name, fallback=None):
        variant = proxy.get_cached_property(property_name)
        if variant is None:
            return fallback
        return variant.unpack()

    def show_notification(self, title, text, icon="kdeconnect", urgency=Notify.Urgency.NORMAL):
        try:
            if not self.notify_ready:
                Notify.init("KDEConnectMenu")
                self.notify_ready = True

            notification = Notify.Notification.new(title, text, icon)
            notification.set_urgency(urgency)
            notification.show()
        except GLib.Error as error:
            print(f"[KDEConnectMenu] Failed to show notification: {error.message}")

    def is_valid_send_selection(self, files):
        if not files:
            return False

        for file in files:
            if (file.get_uri_scheme() != 'file') or file.is_directory():
                return False
        return True

    def get_mount_error(self, device_id):
        try:
            sftp_proxy = self.get_sftp_proxy(device_id)
            return self.dbus_call(sftp_proxy, "getMountError")[0]
        except GLib.Error:
            return ""

    def is_device_mounted(self, device_id):
        try:
            sftp_proxy = self.get_sftp_proxy(device_id)
            return bool(self.dbus_call(sftp_proxy, "isMounted")[0])
        except GLib.Error:
            return False

    def get_device_mount_point(self, device_id):
        try:
            sftp_proxy = self.get_sftp_proxy(device_id)
            mount_point = self.dbus_call(sftp_proxy, "mountPoint")[0]
            if mount_point and os.path.isdir(mount_point):
                return mount_point
        except GLib.Error:
            return None

        return None

    def unpack_variant_value(self, value):
        if isinstance(value, GLib.Variant):
            return value.unpack()
        return value

    def get_device_storage_directories(self, device_id):
        try:
            sftp_proxy = self.get_sftp_proxy(device_id)
            directory_map = self.dbus_call(sftp_proxy, "getDirectories")[0]
        except GLib.Error:
            return []

        if not isinstance(directory_map, dict):
            return []

        storage_directories = []
        for path_value, label_value in directory_map.items():
            storage_path = self.unpack_variant_value(path_value)
            storage_label = self.unpack_variant_value(label_value)

            if not isinstance(storage_path, str) or not storage_path:
                continue

            if not os.path.isdir(storage_path):
                continue

            if not isinstance(storage_label, str):
                storage_label = ""

            storage_directories.append((storage_path, storage_label))

        storage_directories.sort(key=lambda item: ((item[1] or item[0]).casefold(), item[0]))
        return storage_directories

    def get_device_browsable_paths(self, device_id):
        storage_directories = self.get_device_storage_directories(device_id)
        if storage_directories:
            return storage_directories

        mount_point = self.get_device_mount_point(device_id)
        if mount_point:
            return [(mount_point, "")]

        return []

    def choose_primary_browsable_path(self, browsable_paths, fallback_path):
        for storage_path, storage_label in browsable_paths:
            if isinstance(storage_label, str) and "internal" in storage_label.casefold():
                return storage_path

        if browsable_paths:
            return browsable_paths[0][0]

        return fallback_path

    def ensure_device_mounted(self, device):
        sftp_proxy = self.get_sftp_proxy(device["id"])

        if not bool(self.dbus_call(sftp_proxy, "isMounted")[0]):
            mount_success = bool(self.dbus_call(sftp_proxy, "mountAndWait")[0])
            if not mount_success:
                return None

        mount_point = self.dbus_call(sftp_proxy, "mountPoint")[0]
        if mount_point and os.path.isdir(mount_point):
            return mount_point

        return None

    def open_path_in_file_manager(self, path):
        uri = Gio.File.new_for_path(path).get_uri()
        Gio.AppInfo.launch_default_for_uri(uri, None)

    def sidebar_label(self, device_name):
        return _("KDE Connect: {device_name}").format(device_name=device_name)

    def split_bookmark_line(self, line):
        if " " not in line:
            return line.strip(), ""

        uri, label = line.split(" ", 1)
        return uri.strip(), label.strip()

    def load_sidebar_state(self):
        try:
            with open(SIDEBAR_STATE_PATH, "r", encoding="utf-8") as state_file:
                state = json.load(state_file)
                if isinstance(state, dict) and isinstance(state.get("managed_uris", []), list):
                    return state
        except (OSError, ValueError, TypeError):
            pass

        return {"managed_uris": []}

    def save_sidebar_state(self, state):
        try:
            os.makedirs(os.path.dirname(SIDEBAR_STATE_PATH), exist_ok=True)
            temp_path = SIDEBAR_STATE_PATH + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as state_file:
                json.dump(state, state_file)
            os.replace(temp_path, SIDEBAR_STATE_PATH)
        except OSError as error:
            print(f"[KDEConnectMenu] Failed to persist sidebar state: {error}")

    def read_bookmarks(self):
        try:
            with open(BOOKMARKS_PATH, "r", encoding="utf-8") as bookmarks_file:
                return [line.rstrip("\n") for line in bookmarks_file]
        except FileNotFoundError:
            return []
        except OSError as error:
            print(f"[KDEConnectMenu] Failed to read bookmarks file: {error}")
            return []

    def write_bookmarks(self, lines):
        try:
            os.makedirs(os.path.dirname(BOOKMARKS_PATH), exist_ok=True)
            with open(BOOKMARKS_PATH, "w", encoding="utf-8") as bookmarks_file:
                bookmarks_file.write("\n".join(lines))
                if lines:
                    bookmarks_file.write("\n")
        except OSError as error:
            print(f"[KDEConnectMenu] Failed to write bookmarks file: {error}")

    def refresh_sidebar_bookmarks(self):
        if not self.ensure_dbus_proxy():
            return True

        mounted_entries = []
        for device in self.get_connected_devices():
            if not device["supports_sftp"]:
                continue

            browsable_paths = self.get_device_browsable_paths(device["id"])
            if not browsable_paths:
                continue

            sidebar_base_label = self.sidebar_label(device["name"])
            add_storage_suffix = len(browsable_paths) > 1

            for storage_path, storage_label in browsable_paths:
                entry_label = sidebar_base_label
                if add_storage_suffix:
                    suffix = storage_label if storage_label else os.path.basename(storage_path)
                    if suffix:
                        entry_label = f"{sidebar_base_label} — {suffix}"

                uri = Gio.File.new_for_path(storage_path).get_uri()
                mounted_entries.append((uri, entry_label))

        previous_state = self.load_sidebar_state()
        managed_uris = set(previous_state.get("managed_uris", []))
        existing_lines = self.read_bookmarks()

        preserved_lines = []
        preserved_uris = set()
        for line in existing_lines:
            if not line.strip():
                continue

            uri, _ = self.split_bookmark_line(line)
            if uri in managed_uris:
                continue

            preserved_lines.append(line)
            preserved_uris.add(uri)

        updated_lines = list(preserved_lines)
        updated_managed_uris = []

        for uri, label in sorted(mounted_entries, key=lambda item: item[1].casefold()):
            if uri in preserved_uris:
                continue

            updated_lines.append(f"{uri} {label}")
            preserved_uris.add(uri)
            updated_managed_uris.append(uri)

        if updated_lines != existing_lines:
            self.write_bookmarks(updated_lines)

        previous_managed_uris = previous_state.get("managed_uris", [])
        if previous_managed_uris != updated_managed_uris:
            self.save_sidebar_state({"managed_uris": updated_managed_uris})

        return True
    
    def send_files(self, menu, files, device):
        """ Tells KDE Connect to send the specified files to the specified device and notifies the user """

        # Get list of file URIs
        uri_list = [file.get_uri() for file in files]

        try:
            # Create DBus proxy for specific device path
            dbus_share = self.get_share_proxy(device["id"])

            # Convert URI list to GVariant and call DBus function
            variant_uris = GLib.Variant("(as)", (uri_list,))
            self.dbus_call(dbus_share, "shareUrls", variant_uris)

            print(f"[KDEConnectMenu] Sending {len(files)} files to {device['name']}({device['id']})")

            # Send notification informing the user that the files are being sent
            self.show_notification(
                _("Sending to {device_name}...").format(device_name=device["name"]),
                _("Sending {num_files} file(s) to device").format(num_files=len(files)),
                "kdeconnect"
            )
        except GLib.Error as error:
            self.show_notification(
                _("Could not send files"),
                _("KDE Connect reported: {error_message}").format(error_message=error.message),
                "dialog-warning",
                Notify.Urgency.CRITICAL
            )

    def browse_device_storage(self, menu, device):
        """ Mounts and opens phone storage in Nemo """

        try:
            mount_point = self.ensure_device_mounted(device)
            if not mount_point:
                mount_error = self.get_mount_error(device["id"])
                error_text = mount_error if mount_error else _("Unknown SFTP mount error")
                self.show_notification(
                    _("Could not mount {device_name}").format(device_name=device["name"]),
                    error_text,
                    "dialog-warning",
                    Notify.Urgency.CRITICAL
                )
                return

            browsable_paths = self.get_device_browsable_paths(device["id"])
            browse_path = self.choose_primary_browsable_path(browsable_paths, mount_point)

            self.refresh_sidebar_bookmarks()
            self.open_path_in_file_manager(browse_path)
            self.show_notification(
                _("Phone storage opened"),
                _("{device_name} is available like a disk in Nemo").format(device_name=device["name"]),
                "folder-remote"
            )
        except GLib.Error as error:
            self.show_notification(
                _("Could not open phone storage"),
                _("KDE Connect reported: {error_message}").format(error_message=error.message),
                "dialog-warning",
                Notify.Urgency.CRITICAL
            )

    def mount_device(self, menu, device):
        """ Mounts phone storage without opening a new window """

        try:
            mount_point = self.ensure_device_mounted(device)
            if not mount_point:
                mount_error = self.get_mount_error(device["id"])
                error_text = mount_error if mount_error else _("Unknown SFTP mount error")
                self.show_notification(
                    _("Could not mount {device_name}").format(device_name=device["name"]),
                    error_text,
                    "dialog-warning",
                    Notify.Urgency.CRITICAL
                )
                return

            self.refresh_sidebar_bookmarks()
            self.show_notification(
                _("Phone storage mounted"),
                _("{device_name} is now available in Nemo sidebar").format(device_name=device["name"]),
                "drive-removable-media-symbolic"
            )
        except GLib.Error as error:
            self.show_notification(
                _("Could not mount phone storage"),
                _("KDE Connect reported: {error_message}").format(error_message=error.message),
                "dialog-warning",
                Notify.Urgency.CRITICAL
            )

    def unmount_device(self, menu, device):
        """ Unmounts phone storage and removes managed sidebar bookmark """

        try:
            sftp_proxy = self.get_sftp_proxy(device["id"])
            self.dbus_call(sftp_proxy, "unmount")
            self.refresh_sidebar_bookmarks()
            self.show_notification(
                _("Phone storage unmounted"),
                _("{device_name} is no longer mounted").format(device_name=device["name"]),
                "media-eject-symbolic"
            )
        except GLib.Error as error:
            self.show_notification(
                _("Could not unmount phone storage"),
                _("KDE Connect reported: {error_message}").format(error_message=error.message),
                "dialog-warning",
                Notify.Urgency.CRITICAL
            )
    
    def get_connected_devices(self):
        """ Gets a list of connected devices from the KDE Connect daemon using DBus """

        if not self.ensure_dbus_proxy():
            return []

        devices = []

        # Get list of available devices from DBus
        params_variant = GLib.Variant("(bb)", (True, True))
        try:
            device_ids = self.dbus_call(self.dbus_daemon, "devices", params_variant)[0]
            device_names = self.dbus_call(self.dbus_daemon, "deviceNames", params_variant)[0]
        except GLib.Error as error:
            print(f"[KDEConnectMenu] Could not fetch device list: {error.message}")
            return []

        for device_id in device_ids:
            try:
                dbus_device = self.get_device_proxy(device_id)

                device_type = self.get_proxy_property(dbus_device, "type", "smartphone")
                supported_plugins = self.get_proxy_property(dbus_device, "supportedPlugins", []) or []
                if not isinstance(supported_plugins, (list, tuple)):
                    supported_plugins = []

                supports_share = "kdeconnect_share" in supported_plugins
                supports_sftp = "kdeconnect_sftp" in supported_plugins

                if not (supports_share or supports_sftp):
                    continue

                devices.append({
                    "id": device_id,
                    "name": device_names.get(device_id, device_id),
                    "type": device_type,
                    "supports_share": supports_share,
                    "supports_sftp": supports_sftp
                })
            except GLib.Error:
                continue
        
        return devices

    def build_main_menu(self, menu_name, menu_label, menu_tip, icon, files=None):
        devices = self.get_connected_devices()

        # If there are zero available devices, return greyed-out menu item
        if len(devices) == 0:
            return [
                Nemo.MenuItem(
                    name=f"KDEConnectMenu::{menu_name}::NoDevices",
                    label=menu_label,
                    tip=_("No compatible KDE Connect devices are currently available"),
                    icon=icon,
                    sensitive=False)
            ]

        can_send_files = self.is_valid_send_selection(files)
        has_any_action = False

        # Main Menu Item
        main_menuitem = Nemo.MenuItem(
            name=f"KDEConnectMenu::{menu_name}",
            label=menu_label,
            tip=menu_tip,
            icon=icon
        )

        sub_device_menu = Nemo.Menu()
        main_menuitem.set_submenu(sub_device_menu)

        # Add Menu Items for each device
        for device in devices:
            supports_send_action = can_send_files and device["supports_share"]
            supports_storage_action = device["supports_sftp"]

            if not (supports_send_action or supports_storage_action):
                continue

            has_any_action = True

            device_item = Nemo.MenuItem(
                name="KDEConnectMenu::Device" + device["id"],
                label=device["name"],
                tip=_("Actions for {device_name}").format(device_name=device["name"]),
                icon=get_device_icon(device["type"])
            )

            device_actions_menu = Nemo.Menu()
            device_item.set_submenu(device_actions_menu)

            if supports_send_action:
                send_item = Nemo.MenuItem(
                    name="KDEConnectMenu::SendTo" + device["id"],
                    label=_("Send selected files"),
                    tip=_("Send selected files to {device_name}").format(device_name=device["name"]),
                    icon="mail-send-symbolic"
                )
                send_item.connect('activate', self.send_files, files, device)
                device_actions_menu.append_item(send_item)

            if supports_storage_action:
                browse_item = Nemo.MenuItem(
                    name="KDEConnectMenu::Browse" + device["id"],
                    label=_("Browse phone storage"),
                    tip=_("Mount and open {device_name} storage").format(device_name=device["name"]),
                    icon="folder-remote-symbolic"
                )
                browse_item.connect('activate', self.browse_device_storage, device)
                device_actions_menu.append_item(browse_item)

                if self.is_device_mounted(device["id"]):
                    mount_toggle_item = Nemo.MenuItem(
                        name="KDEConnectMenu::Unmount" + device["id"],
                        label=_("Unmount phone storage"),
                        tip=_("Unmount {device_name} storage").format(device_name=device["name"]),
                        icon="media-eject-symbolic"
                    )
                    mount_toggle_item.connect('activate', self.unmount_device, device)
                else:
                    mount_toggle_item = Nemo.MenuItem(
                        name="KDEConnectMenu::Mount" + device["id"],
                        label=_("Mount phone storage"),
                        tip=_("Mount {device_name} storage for disk-like access").format(device_name=device["name"]),
                        icon="drive-removable-media-symbolic"
                    )
                    mount_toggle_item.connect('activate', self.mount_device, device)

                device_actions_menu.append_item(mount_toggle_item)

            sub_device_menu.append_item(device_item)

        if not has_any_action:
            return [
                Nemo.MenuItem(
                    name=f"KDEConnectMenu::{menu_name}::NoActions",
                    label=menu_label,
                    tip=_("No matching KDE Connect actions are available for this selection"),
                    icon=icon,
                    sensitive=False)
            ]

        return [main_menuitem]
        
    def get_file_items(self, window, files):
        return self.build_main_menu(
            menu_name="FileActions",
            menu_label=_("KDE Connect"),
            menu_tip=_("Share files and browse phone storage via KDE Connect"),
            icon="kdeconnect",
            files=files
        )

    def get_background_items(self, window, current_folder):
        return self.build_main_menu(
            menu_name="BackgroundActions",
            menu_label=_("KDE Connect"),
            menu_tip=_("Browse and mount phone storage via KDE Connect"),
            icon="kdeconnect",
            files=None
        )
    
    def get_name_and_desc(self):
        return [("Nemo KDE Connect:::"+_("Share files and browse mounted phone storage via KDE Connect directly from within Nemo."))]