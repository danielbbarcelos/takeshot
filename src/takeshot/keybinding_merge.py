"""Lógica pura de merge do array `custom-keybindings` — sem gi, testável headless.

Isola a lógica que quebra (indexação por comando, alocação do próximo
`customN` livre, resolução de conflito de binding) do I/O real via
`Gio.Settings`, que fica só em shortcuts.py. Indexar pelo `command`, nunca
por nome/posição, é o que garante que rodar `install` dez vezes produza
exatamente uma entrada e nunca sobrescreva as de outros apps (CLAUDE.md §5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

BASE_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"


@dataclass(frozen=True)
class KeybindingEntry:
    path: str
    command: str
    binding: str
    name: str


def next_free_index(paths: list[str]) -> int:
    used = set()
    for p in paths:
        m = re.search(r"custom(\d+)/$", p)
        if m:
            used.add(int(m.group(1)))
    n = 0
    while n in used:
        n += 1
    return n


def find_or_alloc_path(entries: list[KeybindingEntry], command: str) -> tuple[str, bool]:
    """Devolve (path, created). Reusa o path cujo `command` já é o nosso."""
    for e in entries:
        if e.command == command:
            return e.path, False
    idx = next_free_index([e.path for e in entries])
    return f"{BASE_PATH}custom{idx}/", True


def binding_owner(entries: list[KeybindingEntry], binding: str, ignore_path: str) -> "str | None":
    for e in entries:
        if e.path == ignore_path:
            continue
        if e.binding == binding:
            return e.name or e.path
    return None


def find_conflicting_path(entries: list[KeybindingEntry], binding: str, ignore_path: str) -> "str | None":
    """Path da entrada de OUTRO app que já usa `binding` (se houver)."""
    for e in entries:
        if e.path != ignore_path and e.binding == binding:
            return e.path
    return None


def resolve_binding(
    entries: list[KeybindingEntry], our_path: str, requested: str, fallback: str, force: bool,
) -> tuple[str, "str | None"]:
    """Devolve (binding_a_usar, nome_de_quem_causou_conflito_ou_None)."""
    conflict = binding_owner(entries, requested, our_path)
    if not conflict or force:
        return requested, None
    fallback_conflict = binding_owner(entries, fallback, our_path)
    return fallback, (fallback_conflict or conflict)


def remove_command(entries: list[KeybindingEntry], command: str) -> tuple[list[str], bool]:
    """Devolve (paths restantes, houve_remoção)."""
    remaining = [e.path for e in entries if e.command != command]
    removed = len(remaining) != len(entries)
    return remaining, removed
