"""Orquestra o fluxo de captura, do atalho até o resultado final.

Ordem de operações (CLAUDE.md §2.5) — nada nosso pode estar mapeado entre o
disparo do portal e o recebimento do PNG, senão o overlay aparece na própria
captura:

    1. se já existe overlay aberto → foca e retorna
    2. portal.screenshot(parent="")            [assíncrono]
    3. recebe uri → cairo.ImageSurface.create_from_png(path) → apaga o temp
    4. monta Capture
    5. AGORA cria e apresenta as janelas de overlay (se houver seleção/edição)
"""

from __future__ import annotations

import logging
from typing import Callable

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk  # noqa: E402

from takeshot.capture import source
from takeshot.capture.model import Capture

log = logging.getLogger("takeshot.capture.controller")

OnFinished = Callable[[], None]


def start_capture(
    app,
    mode: str,
    portal_interactive: bool,
    copy: bool,
    save_path: "str | None",
    no_edit: bool,
    on_finished: OnFinished,
) -> None:
    if getattr(app, "overlay_session", None) is not None:
        app.overlay_session.present_existing()
        on_finished()
        return

    display = Gdk.Display.get_default()
    interactive = portal_interactive or app.config.interactive_portal

    def on_captured(capture: "Capture | None", error: "str | None") -> None:
        if capture is None:
            log.error("captura falhou: %s", error)
            on_finished()
            return

        if not app.config.portal_permission_granted:
            app.config.portal_permission_granted = True
            app.config.save()

        if mode == "screen":
            if no_edit:
                _finish_headless(app, capture, copy, save_path)
                on_finished()
            else:
                _open_editor(app, capture, initial_selection="full", copy=copy, save_path=save_path, on_finished=on_finished)
            return

        # mode == "region": sempre precisa da UI para o usuário desenhar a seleção
        _open_editor(app, capture, initial_selection=None, copy=copy, save_path=save_path, no_edit=no_edit, on_finished=on_finished)

    if app.config.portal_permission_granted:
        # caminho quente: sem janela nossa mapeada, permissão já concedida no portal
        source.capture_screen(display, parent_window="", interactive=interactive, on_result=on_captured)
    else:
        from takeshot.capture import permission

        def on_handle_ready(helper_window, handle: str) -> None:
            def on_captured_and_cleanup(capture: "Capture | None", error: "str | None") -> None:
                permission.destroy_helper_window(helper_window)
                on_captured(capture, error)

            source.capture_screen(display, parent_window=handle, interactive=interactive, on_result=on_captured_and_cleanup)

        permission.create_and_export_helper_window(app, on_handle_ready)


def _finish_headless(app, capture: "Capture", copy: bool, save_path: "str | None") -> None:
    from takeshot.output import clipboard as clipboard_out
    from takeshot.output import save as save_out

    should_copy = copy or (save_path is None and app.config.copy_on_capture)
    should_save = save_path is not None or not should_copy

    if should_copy:
        clipboard_out.copy_surface(capture.surface)
        log.info("captura copiada para a área de transferência")
    if should_save:
        dest = save_out.save_surface(capture.surface, save_path or None)
        log.info("captura salva em %s", dest)


def _open_editor(app, capture: "Capture", *, initial_selection, copy: bool, save_path, no_edit: bool = False, on_finished: OnFinished) -> None:
    from takeshot.editor import overlay as overlay_mod

    session = overlay_mod.OverlaySession(
        app, capture,
        initial_selection=initial_selection,
        copy=copy, save_path=save_path, no_edit=no_edit,
        on_finished=on_finished,
    )
    app.overlay_session = session
    session.present()
