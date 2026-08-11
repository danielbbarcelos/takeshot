"""Exportação de window handle para o portal XDG (`parent_window`).

Isto é literalmente o que o Qt5/Flameshot não faz nesta máquina — a causa
raiz do bug que motivou o takeshot. `GdkWayland.WaylandToplevel.export_handle`
é o método real disponível no GTK 4.14 do Ubuntu 24.04 (a API cross-backend
`Gdk.Toplevel.export_handle` só chegou em versões posteriores).

Só importa quando o portal vai desenhar um diálogo (ex.: primeira execução,
pedindo permissão de captura). No caminho quente (permissão já concedida),
ninguém chama nada daqui — usa-se `parent_window = ""`.
"""

from __future__ import annotations

import logging
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

try:
    gi.require_version("GdkWayland", "4.0")
    from gi.repository import GdkWayland
except (ImportError, ValueError):
    GdkWayland = None

try:
    gi.require_version("GdkX11", "4.0")
    from gi.repository import GdkX11
except (ImportError, ValueError):
    GdkX11 = None

log = logging.getLogger("takeshot.portal.window_handle")

OnHandle = Callable[[str], None]


def export_handle(window: Gtk.Window, callback: OnHandle) -> None:
    """Exporta o handle da janela (precisa estar mapeada). Assíncrono."""
    surface = window.get_surface()
    if surface is None:
        log.warning("export_handle chamado antes da janela estar mapeada")
        callback("")
        return

    if GdkWayland is not None and isinstance(surface, GdkWayland.WaylandToplevel):
        ok = surface.export_handle(lambda _toplevel, handle, _data=None: callback(f"wayland:{handle}"), None)
        if not ok:
            log.warning("WaylandToplevel.export_handle recusou")
            callback("")
        return

    if GdkX11 is not None and isinstance(surface, GdkX11.X11Surface):
        callback("x11:%x" % surface.get_xid())
        return

    log.info("nenhum backend Wayland/X11 reconhecido para export_handle")
    callback("")


def unexport_handle(window: Gtk.Window) -> None:
    surface = window.get_surface()
    if surface is None:
        return
    if GdkWayland is not None and isinstance(surface, GdkWayland.WaylandToplevel):
        surface.unexport_handle()
