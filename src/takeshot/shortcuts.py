"""Atalho de teclado global via `gsettings custom-keybindings` (CLAUDE.md §5).

Não existe portal GlobalShortcuts nesta máquina — este é o único caminho
confirmado. A lógica de merge (indexação por comando, alocação de path,
resolução de conflito) mora em keybinding_merge.py, pura e testável; este
módulo só faz o I/O real via `Gio.Settings`.
"""

from __future__ import annotations

import json

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio  # noqa: E402

from takeshot import keybinding_merge as merge
from takeshot import paths

MEDIA_KEYS_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_KEYBINDING_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
SHELL_KEYBINDINGS_SCHEMA = "org.gnome.shell.keybindings"

TAKESHOT_COMMAND = "takeshot capture --region"
TAKESHOT_NAME = "Captura de região (takeshot)"
DEFAULT_BINDING = "Print"
FALLBACK_BINDING = "<Shift>Print"


def _media_keys_settings() -> Gio.Settings:
    return Gio.Settings.new(MEDIA_KEYS_SCHEMA)


def _custom_settings(path: str) -> Gio.Settings:
    return Gio.Settings.new_with_path(CUSTOM_KEYBINDING_SCHEMA, path)


def _shell_settings() -> "Gio.Settings | None":
    if SHELL_KEYBINDINGS_SCHEMA not in Gio.Settings.list_schemas():
        return None
    return Gio.Settings.new(SHELL_KEYBINDINGS_SCHEMA)


def _read_entries(media: Gio.Settings) -> list[merge.KeybindingEntry]:
    entries = []
    for p in media.get_strv("custom-keybindings"):
        s = _custom_settings(p)
        entries.append(merge.KeybindingEntry(
            path=p, command=s.get_string("command"), binding=s.get_string("binding"), name=s.get_string("name"),
        ))
    return entries


def install(binding: "str | None" = None, force: bool = False) -> dict:
    media = _media_keys_settings()
    entries = _read_entries(media)

    path, created = merge.find_or_alloc_path(entries, TAKESHOT_COMMAND)
    if created:
        media.set_strv("custom-keybindings", [*(e.path for e in entries), path])
        entries.append(merge.KeybindingEntry(path=path, command="", binding="", name=""))

    requested = binding or DEFAULT_BINDING
    conflicting_path = merge.find_conflicting_path(entries, requested, path) if force else None
    used_binding, conflict = merge.resolve_binding(entries, path, requested, FALLBACK_BINDING, force)

    entry = _custom_settings(path)
    entry.set_string("name", TAKESHOT_NAME)
    entry.set_string("command", TAKESHOT_COMMAND)
    entry.set_string("binding", used_binding)

    cleared_from = None
    if conflicting_path:
        other = _custom_settings(conflicting_path)
        cleared_from = other.get_string("name") or conflicting_path
        other.set_string("binding", "")

    _disable_native_screenshot_ui()

    return {
        "path": path,
        "created": created,
        "binding": used_binding,
        "requested_binding": requested,
        "conflict_with": conflict,
        "cleared_from": cleared_from,
    }


def _disable_native_screenshot_ui() -> None:
    """Libera a tecla Print do screenshot-ui nativo do GNOME, guardando o valor anterior."""
    shell = _shell_settings()
    if shell is None:
        return
    state_file = paths.install_state_file()
    if not state_file.exists():
        paths.ensure_dirs()
        current = list(shell.get_strv("show-screenshot-ui"))
        state_file.write_text(json.dumps({"show_screenshot_ui": current}), encoding="utf-8")
    shell.set_strv("show-screenshot-ui", [])


def _restore_native_screenshot_ui() -> None:
    shell = _shell_settings()
    state_file = paths.install_state_file()
    if shell is None or not state_file.exists():
        return
    try:
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        previous = saved.get("show_screenshot_ui")
    except (OSError, json.JSONDecodeError):
        previous = None
    if previous is not None:
        shell.set_strv("show-screenshot-ui", previous)
    state_file.unlink(missing_ok=True)


def remove() -> bool:
    media = _media_keys_settings()
    entries = _read_entries(media)
    remaining_paths, removed = merge.remove_command(entries, TAKESHOT_COMMAND)
    if removed:
        for e in entries:
            if e.command == TAKESHOT_COMMAND:
                s = _custom_settings(e.path)
                s.reset("name")
                s.reset("command")
                s.reset("binding")
        media.set_strv("custom-keybindings", remaining_paths)
        _restore_native_screenshot_ui()
    return removed


def status() -> dict:
    media = _media_keys_settings()
    entries = _read_entries(media)
    ours = next((e for e in entries if e.command == TAKESHOT_COMMAND), None)

    shell = _shell_settings()
    show_ui = str(list(shell.get_strv("show-screenshot-ui"))) if shell is not None else "n/d"
    conflict = merge.binding_owner(entries, ours.binding, ours.path) if ours else None

    return {
        "installed": ours is not None,
        "path": ours.path if ours else None,
        "binding": ours.binding if ours else None,
        "binding_conflict": conflict,
        "show_screenshot_ui": show_ui,
    }


def dispatch(args) -> None:
    if args.action == "install":
        result = install(binding=args.binding, force=args.force)
        verb = "criado" if result["created"] else "atualizado"
        print(f"atalho {verb} em {result['path']} — binding={result['binding']!r}")
        if result["conflict_with"]:
            print(
                f"aviso: {result['requested_binding']!r} já estava em uso por {result['conflict_with']!r}; "
                f"usando {result['binding']!r} (rode com --force para assumir {result['requested_binding']!r})"
            )
        if result["cleared_from"]:
            print(f"'{result['requested_binding']}' foi retirado de {result['cleared_from']!r} para o takeshot poder usá-lo")
    elif args.action == "remove":
        removed = remove()
        print("atalho removido" if removed else "nenhum atalho takeshot encontrado")
    elif args.action == "status":
        st = status()
        if st["installed"]:
            print(f"instalado em {st['path']} — binding={st['binding']!r}")
            if st["binding_conflict"]:
                print(f"conflito: binding também usado por {st['binding_conflict']!r}")
        else:
            print("não instalado")
        print(f"show-screenshot-ui={st['show_screenshot_ui']}")
