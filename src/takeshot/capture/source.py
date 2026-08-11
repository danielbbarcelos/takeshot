"""Orquestra a chamada ao portal e monta um `Capture` a partir do PNG devolvido."""

from __future__ import annotations

import logging
import os
from typing import Callable
from urllib.parse import unquote, urlparse

import cairo
import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk  # noqa: E402

from takeshot.bus import session_bus
from takeshot.capture.model import Capture, MonitorInfo
from takeshot.geom import Rect
from takeshot.portal import screenshot as portal_screenshot

log = logging.getLogger("takeshot.capture.source")

OnCaptureResult = Callable[["Capture | None", "str | None"], None]


def _uri_to_path(uri: str) -> str:
    parsed = urlparse(uri)
    return unquote(parsed.path)


def _monitors_info(display: Gdk.Display) -> tuple[Rect, list[MonitorInfo]]:
    monitors_model = display.get_monitors()
    infos: list[MonitorInfo] = []
    rects: list[Rect] = []
    for i in range(monitors_model.get_n_items()):
        monitor: Gdk.Monitor = monitors_model.get_item(i)
        geo = monitor.get_geometry()
        rect = Rect(geo.x, geo.y, geo.width, geo.height)
        infos.append(MonitorInfo(
            name=monitor.get_connector() or f"monitor{i}",
            geometry=rect,
            scale_factor=monitor.get_scale_factor(),
        ))
        rects.append(rect)
    return Rect.union(rects), infos


def capture_screen(
    display: Gdk.Display,
    parent_window: str,
    interactive: bool,
    on_result: OnCaptureResult,
) -> None:
    """Dispara `Screenshot` no portal e entrega um `Capture` pronto (async)."""
    bus = session_bus()

    def on_portal_result(ok: bool, uri: str | None, error: str | None) -> None:
        if not ok:
            on_result(None, error)
            return

        path = _uri_to_path(uri)
        try:
            surface = cairo.ImageSurface.create_from_png(path)
        except Exception as exc:  # noqa: BLE001 — qualquer falha de leitura vira erro reportado
            on_result(None, f"falha ao ler PNG devolvido pelo portal: {exc}")
            return
        finally:
            try:
                os.remove(path)
            except OSError as exc:
                log.warning("não foi possível apagar temporário do portal %s: %s", path, exc)

        logical_bounds, monitors = _monitors_info(display)
        scale = surface.get_width() / logical_bounds.width if logical_bounds.width else 1.0
        on_result(
            Capture(surface=surface, logical_bounds=logical_bounds, scale=scale, monitors=monitors),
            None,
        )

    portal_screenshot.take_screenshot(bus, parent_window, interactive, on_portal_result)
