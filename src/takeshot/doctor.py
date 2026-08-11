"""`takeshot doctor` — diagnóstico do ambiente Wayland/GNOME/portal.

Desenhado a partir das dores da sessão de debug que motivou este projeto
(ver CLAUDE.md §6). Cada checagem é isolada e nunca lança: erros viram uma
linha de resultado "ERRO", nunca uma exceção não tratada.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from takeshot import bus as bus_mod
from takeshot.paths import APP_ID

OK = "OK"
WARN = "AVISO"
ERR = "ERRO"
INFO = "INFO"


@dataclass
class Check:
    level: str
    label: str
    detail: str = ""


def _check_session() -> list[Check]:
    session_type = os.environ.get("XDG_SESSION_TYPE", "?")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "?")
    checks = []
    level = OK if session_type == "wayland" else WARN
    checks.append(Check(level, "Tipo de sessão", session_type))
    level = OK if "GNOME" in desktop.upper() else WARN
    checks.append(Check(level, "Desktop atual", desktop))
    return checks


def _check_versions() -> list[Check]:
    checks = [Check(INFO, "Python", sys.version.split()[0])]
    try:
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gtk

        checks.append(Check(OK, "GTK", f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"))
        checks.append(Check(OK, "libadwaita", f"{Adw.get_major_version()}.{Adw.get_minor_version()}.{Adw.get_micro_version()}"))
    except (ImportError, ValueError) as exc:
        checks.append(Check(ERR, "GTK4/libadwaita", str(exc)))
    try:
        import cairo  # noqa: F401

        checks.append(Check(OK, "pycairo", "presente"))
    except ImportError as exc:
        checks.append(Check(ERR, "pycairo", str(exc)))
    return checks


def _portal_call(bus: Gio.DBusConnection, iface: str, method: str, args=None, timeout=2000):
    return bus.call_sync(
        "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop", iface, method,
        args, None, Gio.DBusCallFlags.NONE, timeout, None,
    )


def _portal_property(bus: Gio.DBusConnection, iface: str, prop: str):
    result = bus.call_sync(
        "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
        "org.freedesktop.DBus.Properties", "Get",
        GLib.Variant("(ss)", (iface, prop)), GLib.VariantType("(v)"),
        Gio.DBusCallFlags.NONE, 2000, None,
    )
    return result.unpack()[0]


def _check_portal() -> list[Check]:
    checks: list[Check] = []
    try:
        bus = bus_mod.session_bus()
    except GLib.Error as exc:
        return [Check(ERR, "Session bus", str(exc))]

    try:
        version = _portal_property(bus, "org.freedesktop.portal.Screenshot", "version")
        checks.append(Check(OK, "portal Screenshot", f"presente, versão {version}"))
    except GLib.Error as exc:
        checks.append(Check(ERR, "portal Screenshot", f"ausente: {exc}"))

    try:
        _portal_property(bus, "org.freedesktop.portal.GlobalShortcuts", "version")
        checks.append(Check(WARN, "portal GlobalShortcuts", "presente — atalho via gsettings pode ser desnecessário"))
    except GLib.Error:
        checks.append(Check(INFO, "portal GlobalShortcuts", "ausente (esperado nesta máquina — atalho via gsettings custom-keybindings)"))

    for backend_name in ("org.freedesktop.impl.portal.desktop.gnome", "org.freedesktop.impl.portal.desktop.gtk"):
        owner = bus_mod.get_name_owner(bus, backend_name)
        checks.append(Check(OK if owner else INFO, f"backend {backend_name}", owner or "não ativo"))

    try:
        bus.call_sync(
            "org.gnome.Shell", "/org/gnome/Shell/Screenshot", "org.gnome.Shell.Screenshot",
            "Screenshot", GLib.Variant("(bbs)", (False, False, "/tmp/takeshot-doctor-probe.png")),
            None, Gio.DBusCallFlags.NONE, 2000, None,
        )
        checks.append(Check(WARN, "org.gnome.Shell.Screenshot", "chamada direta funcionou — inesperado, allowlist pode ter mudado"))
    except GLib.Error as exc:
        msg = str(exc)
        if "AccessDenied" in msg or "not allowed" in msg.lower():
            checks.append(Check(OK, "org.gnome.Shell.Screenshot", "AccessDenied (esperado — confirma necessidade do portal XDG)"))
        else:
            checks.append(Check(INFO, "org.gnome.Shell.Screenshot", msg))

    return checks


def _check_bus_owner() -> list[Check]:
    info = bus_mod.describe_owner(APP_ID)
    if info is None:
        return [Check(INFO, f"dono de {APP_ID}", "nenhuma instância rodando")]
    pid = info.get("pid")
    exe = info.get("exe")
    return [Check(OK, f"dono de {APP_ID}", f"pid={pid} exe={exe} unique_name={info.get('unique_name')}")]


def _check_keybinding() -> list[Check]:
    checks = []
    try:
        from takeshot import shortcuts

        state = shortcuts.status()
    except Exception as exc:  # noqa: BLE001 — diagnóstico não pode lançar
        return [Check(ERR, "keybinding", str(exc))]

    if state["installed"]:
        checks.append(Check(OK, "atalho takeshot", f"path={state['path']} binding={state['binding']!r}"))
        if state["binding_conflict"]:
            checks.append(Check(WARN, "conflito de binding", f"binding {state['binding']!r} também usado por: {state['binding_conflict']}"))
    else:
        checks.append(Check(WARN, "atalho takeshot", "não instalado — rode `takeshot shortcut install`"))

    show_ui = state["show_screenshot_ui"]
    level = OK if show_ui == "[]" else WARN
    detail = show_ui if show_ui == "[]" else f"{show_ui} — tecla Print pode ter voltado a abrir o screenshot-ui nativo"
    checks.append(Check(level, "show-screenshot-ui", detail))
    return checks


def _check_path_and_desktop() -> list[Check]:
    checks = []
    local_bin = str(Path.home() / ".local" / "bin")
    in_path = local_bin in os.environ.get("PATH", "").split(":")
    checks.append(Check(OK if in_path else WARN, "~/.local/bin no PATH", "sim" if in_path else "não — adicione ao seu shell rc"))

    desktop_file = Path.home() / ".local" / "share" / "applications" / f"{APP_ID}.desktop"
    checks.append(Check(OK if desktop_file.exists() else WARN, ".desktop instalado", str(desktop_file) if desktop_file.exists() else "ausente"))

    icon_found = False
    for size_dir in (Path.home() / ".local" / "share" / "icons" / "hicolor").glob("*/apps"):
        if (size_dir / f"{APP_ID}.png").exists() or (size_dir / f"{APP_ID}.svg").exists():
            icon_found = True
            break
    checks.append(Check(OK if icon_found else WARN, "ícone instalado", "sim" if icon_found else "ausente"))

    for tool in ("gsettings", "xdg-user-dir", "gtk-update-icon-cache", "update-desktop-database"):
        checks.append(Check(OK if shutil.which(tool) else WARN, f"binário {tool}", shutil.which(tool) or "não encontrado no PATH"))

    return checks


def collect() -> list[Check]:
    checks: list[Check] = []
    checks += _check_session()
    checks += _check_versions()
    checks += _check_portal()
    checks += _check_bus_owner()
    checks += _check_keybinding()
    checks += _check_path_and_desktop()
    return checks


def run(as_json: bool = False) -> int:
    checks = collect()
    if as_json:
        print(json.dumps([{"level": c.level, "label": c.label, "detail": c.detail} for c in checks], ensure_ascii=False, indent=2))
    else:
        width = max((len(c.label) for c in checks), default=0)
        for c in checks:
            print(f"[{c.level:5}] {c.label.ljust(width)}  {c.detail}")
    return 1 if any(c.level == ERR for c in checks) else 0


if __name__ == "__main__":
    sys.exit(run())
