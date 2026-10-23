"""Campo flutuante de edição de texto: Gtk.TextView multilinha + alça de mover.

O TextView é estilizado (fonte, tamanho, cor, fundo, padding) para coincidir
com o que `TextAnnotation.render` vai desenhar, e o canvas esconde o original
enquanto se edita — o campo É a pré-visualização. Enter confirma, Shift+Enter
quebra linha, Esc descarta.
"""

from __future__ import annotations

import math
from dataclasses import replace

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, GLib, Graphene, Gtk  # noqa: E402

from takeshot.editor.items import FONT_FAMILY, TEXT_BACKGROUND_PADDING
from takeshot.editor.textedit import TextEdit
from takeshot.geom import Point

PANGO_PX_PER_PT = 96 / 72  # PangoCairo usa 96 dpi: é assim que font_size vira px na imagem
MIN_MARGIN = 3  # px lógicos: espaço pro cursor e pro contorno quando não há fundo
GRIP_GAP = 4
CARET_SLACK = 4  # px lógicos além do texto, pro cursor no fim da linha não cortar

_provider: "Gtk.CssProvider | None" = None


def _css_rgba(color) -> str:
    r, g, b, a = color
    return f"rgba({round(r * 255)}, {round(g * 255)}, {round(b * 255)}, {a:.2f})"


def _provider_for_display() -> Gtk.CssProvider:
    global _provider
    if _provider is None:
        _provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), _provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2,
        )
    return _provider


class FloatingTextBox:
    def __init__(self, session, window, edit: TextEdit) -> None:
        self.session = session
        self.window = window
        self.edit = edit

        self.view = Gtk.TextView()
        self.view.set_name("takeshot-text-edit")
        self.view.set_wrap_mode(Gtk.WrapMode.NONE)
        self.view.set_accepts_tab(False)
        self.view.get_buffer().set_text(edit.text)
        self.view.get_buffer().connect("changed", self._on_changed)

        key = Gtk.EventControllerKey()
        key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed", self._on_key)
        self.view.add_controller(key)

        self.grip = Gtk.Label(label="✥")
        self.grip.add_css_class("takeshot-text-grip")
        self.grip.set_tooltip_text("Arraste para mover o texto")
        self.grip.set_cursor(Gdk.Cursor.new_from_name("move"))
        # A alça anda junto com o arrasto, então os offsets do GestureDrag
        # (relativos ao widget) oscilariam: mede tudo em coordenadas da janela.
        self._grip_anchor: "tuple[Point, Point] | None" = None
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_grip_begin)
        drag.connect("drag-update", self._on_grip_update)
        drag.connect("drag-end", lambda *_a: setattr(self, "_grip_anchor", None))
        self.grip.add_controller(drag)

        self.update_style()
        window.add_floating(self.view, self._view_position)
        window.add_floating(self.grip, self._grip_position)
        self.focus()

    # --- estilo e posição ---

    def _margin(self) -> float:
        """Distância (px lógicos) da borda do campo até o texto = padding do fundo."""
        pad_image = self.edit.style.font_size * TEXT_BACKGROUND_PADDING if self.edit.style.background else 0
        return max(MIN_MARGIN, pad_image / self.session.capture.scale)

    def update_style(self) -> None:
        style = self.edit.style
        scale = self.session.capture.scale
        font_px = style.font_size * PANGO_PX_PER_PT / scale
        margin = self._margin()
        background = _css_rgba(style.background) if style.background else "transparent"
        outline = "none" if style.background else "1px dashed rgba(255, 255, 255, 0.85)"
        _provider_for_display().load_from_string(
            f"""
            textview#takeshot-text-edit > text {{
              background: transparent;
            }}
            textview#takeshot-text-edit, textview#takeshot-text-edit > text {{
              color: {_css_rgba(style.color)};
              caret-color: {_css_rgba(style.color)};
              font-family: "{FONT_FAMILY}";
              font-size: {font_px:.2f}px;
            }}
            textview#takeshot-text-edit {{
              background: {background};
              border-radius: {margin:.1f}px;
              outline: {outline};
              outline-offset: 0;
            }}
            """
        )
        m = round(margin)
        self.view.set_left_margin(m)
        self.view.set_right_margin(m)
        self.view.set_top_margin(m)
        self.view.set_bottom_margin(m)
        self.reposition()

    def reposition(self) -> None:
        self.window.reposition_floating()

    def _text_origin_local(self) -> Point:
        lx, ly = self.session.capture.logical_from_image(self.edit.origin.x, self.edit.origin.y)
        return self.window.local_from_global(Point(lx, ly))

    def _view_position(self) -> "tuple[int, int, int, int]":
        """Tamanho pelas extents Pango do próprio rascunho (o TextView não informa
        uma largura natural que acompanhe o conteúdo)."""
        origin = self._text_origin_local()
        m = round(self._margin())
        scale = self.session.capture.scale
        text = self.edit.text or " "
        extents = replace(self.edit.draft(), text=text, background=None).bounds()
        width = math.ceil(extents.width / scale) + 2 * m + CARET_SLACK
        height = math.ceil(extents.height / scale) + 2 * m
        return int(origin.x) - m, int(origin.y) - m, width, height

    def _grip_position(self) -> "tuple[int, int, int, int]":
        x, y, _, _ = self._view_position()
        _, gw, *_ = self.grip.measure(Gtk.Orientation.HORIZONTAL, -1)
        _, gh, *_ = self.grip.measure(Gtk.Orientation.VERTICAL, -1)
        return x - gw - GRIP_GAP, y, gw, gh

    # --- eventos ---

    def _on_changed(self, buffer: Gtk.TextBuffer) -> None:
        self.edit.text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        self.reposition()

    def _on_key(self, _controller, keyval, _keycode, state) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        if name in ("Return", "KP_Enter"):
            if state & Gdk.ModifierType.SHIFT_MASK:
                self.view.get_buffer().insert_at_cursor("\n")
            else:
                self.session.text_confirm()
            return True
        if name == "Escape":
            self.session.text_discard()
            return True
        return False

    def _grip_point_in_window(self, x: float, y: float) -> Point:
        ok, p = self.grip.compute_point(self.window, Graphene.Point().init(x, y))
        return Point(p.x, p.y) if ok else Point(x, y)

    def _on_grip_begin(self, _gesture, x: float, y: float) -> None:
        self._grip_anchor = (self._grip_point_in_window(x, y), self.edit.origin)

    def _on_grip_update(self, gesture, _dx: float, _dy: float) -> None:
        if self._grip_anchor is None:
            return
        ok, x, y = gesture.get_point(None)
        if not ok:
            return
        start, origin = self._grip_anchor
        now = self._grip_point_in_window(x, y)
        scale = self.session.capture.scale
        self.edit.origin = origin.translated((now.x - start.x) * scale, (now.y - start.y) * scale)
        self.reposition()

    def focus(self) -> None:
        self.view.grab_focus()

    def destroy(self) -> None:
        # pode ser chamado de dentro de um evento do próprio TextView (Enter/Esc);
        # remover o widget ali mesmo já travou o GTK uma vez (ver histórico do
        # foco em overlay.py), então esconde agora e remove no idle.
        self.view.set_visible(False)
        self.grip.set_visible(False)

        def remove() -> bool:
            self.window.remove_floating(self.grip)
            self.window.remove_floating(self.view)
            return False

        GLib.idle_add(remove)
