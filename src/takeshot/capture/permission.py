"""Janela auxiliar 1×1 invisível usada só na primeiríssima execução.

O portal só desenha um diálogo ("permitir captura de tela?") uma vez; depois
a permissão fica no permission store e nenhum diálogo aparece de novo — a
partir daí `parent_window = ""` basta (ver CLAUDE.md §2.4). Esta janela só
existe para ter um handle exportável nesse único momento.
"""

from __future__ import annotations

import logging
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from takeshot.portal import window_handle

log = logging.getLogger("takeshot.capture.permission")

OnHandleReady = Callable[[Gtk.Window, str], None]


def create_and_export_helper_window(app: Gtk.Application, on_ready: OnHandleReady) -> None:
    window = Gtk.Window(application=app)
    window.set_decorated(False)
    window.set_default_size(1, 1)
    window.set_resizable(False)
    window.set_opacity(0.0)
    window.set_can_focus(False)
    window.set_can_target(False)
    window.set_title("takeshot-permission-helper")

    def on_map(_widget) -> None:
        window_handle.export_handle(window, lambda handle: on_ready(window, handle))

    window.connect("map", on_map)
    window.present()


def destroy_helper_window(window: Gtk.Window) -> None:
    window_handle.unexport_handle(window)
    window.destroy()
