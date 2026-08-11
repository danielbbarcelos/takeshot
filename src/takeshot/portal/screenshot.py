"""org.freedesktop.portal.Screenshot — captura de tela via portal XDG."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from takeshot.portal import request

OnScreenshotResult = Callable[[bool, str | None, str | None], None]
"""on_result(ok, uri_ou_None, mensagem_de_erro_ou_None)."""


def take_screenshot(
    bus: Gio.DBusConnection,
    parent_window: str,
    interactive: bool,
    on_result: OnScreenshotResult,
) -> None:
    def build_args(token: str) -> GLib.Variant:
        return GLib.Variant(
            "(sa{sv})",
            (
                parent_window,
                {
                    "handle_token": GLib.Variant("s", token),
                    "interactive": GLib.Variant("b", interactive),
                    "modal": GLib.Variant("b", True),
                },
            ),
        )

    def on_response(code: int, results: dict) -> None:
        if code == 0:
            uri = results.get("uri")
            if not uri:
                on_result(False, None, "portal retornou sucesso sem 'uri'")
                return
            on_result(True, uri, None)
        elif code == 1:
            on_result(False, None, "captura cancelada pelo usuário")
        else:
            on_result(False, None, results.get("error") or f"erro do portal (code={code})")

    request.make_request(
        bus, "org.freedesktop.portal.Screenshot", "Screenshot", build_args, on_response,
    )
