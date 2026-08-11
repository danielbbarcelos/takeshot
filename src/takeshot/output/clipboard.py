"""Cópia da captura final para a área de transferência.

`Gdk.Clipboard.set_texture` não é introspectável no PyGObject (confirmado) —
por isso construímos um `Gdk.ContentProvider` manualmente via `GObject.Value`.
"""

from __future__ import annotations

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, GObject  # noqa: E402


def texture_from_surface(surface: cairo.ImageSurface) -> Gdk.Texture:
    surface.flush()
    data = bytes(surface.get_data())
    gbytes = GLib.Bytes.new(data)
    return Gdk.MemoryTexture.new(
        surface.get_width(),
        surface.get_height(),
        Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED,
        gbytes,
        surface.get_stride(),
    )


def copy_surface(surface: cairo.ImageSurface, display: "Gdk.Display | None" = None) -> None:
    display = display or Gdk.Display.get_default()
    texture = texture_from_surface(surface)
    value = GObject.Value(Gdk.Texture, texture)
    provider = Gdk.ContentProvider.new_for_value(value)
    display.get_clipboard().set_content(provider)
