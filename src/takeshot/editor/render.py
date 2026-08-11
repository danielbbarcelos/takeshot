"""render(document, cr, ctx) — usado pelo canvas (tela) E pela exportação.

Um único caminho de renderização Cairo evita a classe de bug "o que vejo não
é o que salva" (CLAUDE.md §3.1).
"""

from __future__ import annotations

import cairo

from takeshot.editor.document import AnnotationDocument
from takeshot.editor.items import RenderContext
from takeshot.geom import Rect


def render(document: AnnotationDocument, cr: cairo.Context, ctx: RenderContext) -> None:
    for item in document.items:
        cr.save()
        item.render(cr, ctx)
        cr.restore()


def composite(document: AnnotationDocument, origin: cairo.ImageSurface) -> cairo.ImageSurface:
    """Superfície do tamanho da captura original com as anotações desenhadas por cima."""
    width, height = origin.get_width(), origin.get_height()
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(out)
    cr.set_source_surface(origin, 0, 0)
    cr.paint()
    render(document, cr, RenderContext(origin=origin))
    return out


def crop(surface: cairo.ImageSurface, rect: Rect) -> cairo.ImageSurface:
    r = rect.normalized()
    x, y = round(r.x), round(r.y)
    w, h = max(1, round(r.width)), max(1, round(r.height))
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(out)
    cr.set_source_surface(surface, -x, -y)
    cr.paint()
    return out


def export(document: AnnotationDocument, origin: cairo.ImageSurface) -> cairo.ImageSurface:
    """Composto final pronto para salvar/copiar: anotações + crop na seleção (se houver)."""
    full = composite(document, origin)
    if document.selection_rect is None:
        return full
    return crop(full, document.selection_rect)
