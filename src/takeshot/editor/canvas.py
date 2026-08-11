"""OverlayCanvas: Gtk.Widget que desenha o recorte de um monitor + anotações.

Único caminho de renderização (CLAUDE.md §3.1): do_snapshot -> append_cairo
-> render.render(), a MESMA função usada pela exportação final. Evita a
classe de bug "o que vejo não é o que salva".
"""

from __future__ import annotations

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Graphene, Gtk  # noqa: E402

from takeshot.capture.model import Capture
from takeshot.editor import render as render_mod
from takeshot.editor.document import AnnotationDocument
from takeshot.editor.items import RenderContext
from takeshot.geom import Rect

SELECTION_BORDER_COLOR = (0.20, 0.55, 1.0, 0.95)
SELECTION_BORDER_WIDTH = 1.5
HANDLE_SIZE = 9.0


class OverlayCanvas(Gtk.Widget):
    __gtype_name__ = "TakeshotOverlayCanvas"

    def __init__(self, capture: Capture, document: AnnotationDocument, monitor_geometry: Rect, dim_opacity: float = 0.45, session=None):
        super().__init__()
        self.capture = capture
        self.document = document
        self.monitor_geometry = monitor_geometry
        self.dim_opacity = dim_opacity
        self.session = session
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_can_target(True)
        self.set_focusable(True)

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            size = int(self.monitor_geometry.width)
        else:
            size = int(self.monitor_geometry.height)
        return size, size, -1, -1

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width = self.get_width()
        height = self.get_height()
        if width <= 0 or height <= 0:
            return
        rect = Graphene.Rect()
        rect.init(0, 0, width, height)
        cr = snapshot.append_cairo(rect)
        self._draw(cr)

    def _image_bounds_for_monitor(self) -> Rect:
        mg = self.monitor_geometry
        ix, iy = self.capture.image_from_logical(mg.x, mg.y)
        return Rect(ix, iy, mg.width * self.capture.scale, mg.height * self.capture.scale)

    def _apply_image_to_widget_transform(self, cr: cairo.Context) -> None:
        """Faz `cr` aceitar coordenadas em px de imagem (absolutas) e desenhar em px lógicos do widget."""
        scale = self.capture.scale
        lb = self.capture.logical_bounds
        mg = self.monitor_geometry
        cr.scale(1 / scale, 1 / scale)
        cr.translate((lb.x - mg.x) * scale, (lb.y - mg.y) * scale)

    def _draw(self, cr: cairo.Context) -> None:
        cr.save()
        self._apply_image_to_widget_transform(cr)

        # 1. fundo: recorte da captura original
        cr.set_source_surface(self.capture.surface, 0, 0)
        cr.paint()

        # 2. spotlight: escurece tudo exceto a seleção (fill-rule even-odd = "buraco")
        monitor_bounds = self._image_bounds_for_monitor()
        selection = self.document.selection_rect
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        cr.set_source_rgba(0, 0, 0, self.dim_opacity)
        cr.rectangle(monitor_bounds.x, monitor_bounds.y, monitor_bounds.width, monitor_bounds.height)
        if selection is not None:
            s = selection.normalized()
            cr.rectangle(s.x, s.y, s.width, s.height)
        cr.fill()

        # 3. borda da seleção
        if selection is not None:
            s = selection.normalized()
            cr.set_source_rgba(*SELECTION_BORDER_COLOR)
            cr.set_line_width(SELECTION_BORDER_WIDTH * self.capture.scale)
            cr.rectangle(s.x, s.y, s.width, s.height)
            cr.stroke()

        # 3b. handles de redimensionar — só quando a seleção já foi confirmada
        if selection is not None and self.session is not None and self.session.is_selected:
            self._draw_handles(cr, selection)

        # 4. anotações — mesmo render() usado na exportação
        ctx = RenderContext(origin=self.capture.surface)
        render_mod.render(self.document, cr, ctx)

        # 5. preview da ferramenta ativa (fora do documento, só nesta janela)
        if self.session is not None:
            self.session.draw_tool_preview(cr, ctx)

        cr.restore()

    def _draw_handles(self, cr: cairo.Context, selection: Rect) -> None:
        from takeshot.editor.overlay import handle_positions

        size = HANDLE_SIZE * self.capture.scale
        for hp in handle_positions(selection).values():
            cr.rectangle(hp.x - size / 2, hp.y - size / 2, size, size)
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.fill_preserve()
            cr.set_source_rgba(*SELECTION_BORDER_COLOR)
            cr.set_line_width(1.2 * self.capture.scale)
            cr.stroke()
