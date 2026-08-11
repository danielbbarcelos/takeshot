"""Helpers de D-Bus: descobrir e substituir o dono de um bus name."""

from __future__ import annotations

import os
import signal
import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402


def session_bus() -> Gio.DBusConnection:
    return Gio.bus_get_sync(Gio.BusType.SESSION, None)


def get_name_owner(bus: Gio.DBusConnection, name: str) -> str | None:
    try:
        result = bus.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "GetNameOwner", GLib.Variant("(s)", (name,)), GLib.VariantType("(s)"),
            Gio.DBusCallFlags.NONE, 2000, None,
        )
        return result.unpack()[0]
    except GLib.Error:
        return None


def get_connection_pid(bus: Gio.DBusConnection, unique_name: str) -> int | None:
    try:
        result = bus.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "GetConnectionUnixProcessID", GLib.Variant("(s)", (unique_name,)), GLib.VariantType("(u)"),
            Gio.DBusCallFlags.NONE, 2000, None,
        )
        return result.unpack()[0]
    except GLib.Error:
        return None


def pid_exe_path(pid: int) -> str | None:
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return None


def describe_owner(name: str) -> dict | None:
    """Retorna {unique_name, pid, exe} do dono atual de `name`, ou None se ninguém o possui."""
    bus = session_bus()
    owner = get_name_owner(bus, name)
    if owner is None:
        return None
    pid = get_connection_pid(bus, owner)
    exe = pid_exe_path(pid) if pid else None
    return {"unique_name": owner, "pid": pid, "exe": exe}


def replace_owner(name: str, timeout: float = 2.0) -> bool:
    """Mata o processo dono atual de `name` (se houver) para liberar o bus name.

    Usado por `--replace`: melhor esforço, não bloqueia se falhar (GApplication
    ainda tentará se registrar normalmente em seguida).
    """
    info = describe_owner(name)
    if info is None or not info.get("pid"):
        return False
    pid = info["pid"]
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False

    deadline = time.monotonic() + timeout
    bus = session_bus()
    while time.monotonic() < deadline:
        if get_name_owner(bus, name) is None:
            return True
        time.sleep(0.05)
    return False
