"""Anotações: dataclasses imutáveis com render(cr, ctx) / bounds() / hit_test(p).

Só `cairo`/`gi.repository.Pango*`/`dataclasses` — sem `Gtk`, sem display.
Pango/PangoCairo não precisam de conexão com um servidor gráfico, então isto
continua testável headless (ver tests/).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

from takeshot.geom import Point, Rect

Color = tuple[float, float, float, float]

DEFAULT_COLOR: Color = (1.0, 0.13, 0.13, 1.0)
FONT_FAMILY = "Ubuntu"


@dataclass
class RenderContext:
    """Carrega a superfície de origem da captura, em coordenadas de imagem.

    Blur/pixelate sempre leem `origin`, nunca o composto: borrar uma área e
    desenhar uma seta por cima não deve borrar a seta.
    """

    origin: cairo.ImageSurface


@dataclass(kw_only=True, frozen=True)
class Annotation:
    color: Color = DEFAULT_COLOR
    line_width: float = 3.0

    def render(self, cr: cairo.Context, ctx: RenderContext) -> None:
        raise NotImplementedError

    def bounds(self) -> Rect:
        raise NotImplementedError

    def hit_test(self, x: float, y: float, tolerance: float = 6.0) -> bool:
        return self.bounds().inset(-tolerance).contains(Point(x, y))

    def translated(self, dx: float, dy: float) -> Annotation:
        raise NotImplementedError


def _set_source(cr: cairo.Context, color: Color) -> None:
    cr.set_source_rgba(*color)


def _pango_layout(cr: cairo.Context, text: str, font_size: float, bold: bool = False) -> Pango.Layout:
    layout = PangoCairo.create_layout(cr)
    layout.set_text(text, -1)
    font_desc = Pango.FontDescription()
    font_desc.set_family(FONT_FAMILY)
    font_desc.set_size(max(1, int(font_size * Pango.SCALE)))
    if bold:
        font_desc.set_weight(Pango.Weight.BOLD)
    layout.set_font_description(font_desc)
    return layout


# ---------------------------------------------------------------------------
# Seta


@dataclass(kw_only=True, frozen=True)
class ArrowAnnotation(Annotation):
    start: Point
    end: Point

    def bounds(self) -> Rect:
        return Rect.from_points(self.start, self.end).inset(-max(self.line_width, 10.0))

    def translated(self, dx: float, dy: float) -> ArrowAnnotation:
        return replace(self, start=self.start.translated(dx, dy), end=self.end.translated(dx, dy))

    def render(self, cr: cairo.Context, ctx: RenderContext) -> None:
        _set_source(cr, self.color)
        cr.set_line_width(self.line_width)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.move_to(self.start.x, self.start.y)
        cr.line_to(self.end.x, self.end.y)
        cr.stroke()

        angle = math.atan2(self.end.y - self.start.y, self.end.x - self.start.x)
        head_len = max(12.0, self.line_width * 4)
        head_angle = math.radians(28)
        for sign in (1, -1):
            hx = self.end.x - head_len * math.cos(angle - sign * head_angle)
            hy = self.end.y - head_len * math.sin(angle - sign * head_angle)
            cr.move_to(self.end.x, self.end.y)
            cr.line_to(hx, hy)
        cr.stroke()

    def hit_test(self, x: float, y: float, tolerance: float = 6.0) -> bool:
        return _segment_distance(x, y, self.start, self.end) <= tolerance + self.line_width / 2


def _segment_distance(x: float, y: float, a: Point, b: Point) -> float:
    px, py = x - a.x, y - a.y
    dx, dy = b.x - a.x, b.y - a.y
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, (px * dx + py * dy) / length_sq))
    cx, cy = a.x + t * dx, a.y + t * dy
    return math.hypot(x - cx, y - cy)


# ---------------------------------------------------------------------------
# Retângulo


@dataclass(kw_only=True, frozen=True)
class RectAnnotation(Annotation):
    rect: Rect
    filled: bool = False

    def bounds(self) -> Rect:
        return self.rect.normalized().inset(-self.line_width)

    def translated(self, dx: float, dy: float) -> RectAnnotation:
        return replace(self, rect=self.rect.translated(dx, dy))

    def render(self, cr: cairo.Context, ctx: RenderContext) -> None:
        r = self.rect.normalized()
        _set_source(cr, self.color)
        cr.rectangle(r.x, r.y, r.width, r.height)
        if self.filled:
            cr.fill()
        else:
            cr.set_line_width(self.line_width)
            cr.stroke()


# ---------------------------------------------------------------------------
# Elipse


@dataclass(kw_only=True, frozen=True)
class EllipseAnnotation(Annotation):
    rect: Rect
    filled: bool = False

    def bounds(self) -> Rect:
        return self.rect.normalized().inset(-self.line_width)

    def translated(self, dx: float, dy: float) -> EllipseAnnotation:
        return replace(self, rect=self.rect.translated(dx, dy))

    def render(self, cr: cairo.Context, ctx: RenderContext) -> None:
        r = self.rect.normalized()
        if r.width <= 0 or r.height <= 0:
            return
        cx, cy = r.x + r.width / 2, r.y + r.height / 2
        cr.save()
        cr.translate(cx, cy)
        cr.scale(r.width / 2, r.height / 2)
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()
        _set_source(cr, self.color)
        if self.filled:
            cr.fill()
        else:
            cr.set_line_width(self.line_width)
            cr.stroke()


# ---------------------------------------------------------------------------
# Traço livre


@dataclass(kw_only=True, frozen=True)
class FreehandAnnotation(Annotation):
    points: tuple[Point, ...] = ()

    def bounds(self) -> Rect:
        if not self.points:
            return Rect(0, 0, 0, 0)
        xs = [p.x for p in self.points]
        ys = [p.y for p in self.points]
        return Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)).inset(-self.line_width)

    def translated(self, dx: float, dy: float) -> FreehandAnnotation:
        return replace(self, points=tuple(p.translated(dx, dy) for p in self.points))

    def render(self, cr: cairo.Context, ctx: RenderContext) -> None:
        if len(self.points) < 2:
            return
        _set_source(cr, self.color)
        cr.set_line_width(self.line_width)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.move_to(self.points[0].x, self.points[0].y)
        for p in self.points[1:]:
            cr.line_to(p.x, p.y)
        cr.stroke()

    def hit_test(self, x: float, y: float, tolerance: float = 6.0) -> bool:
        r = tolerance + self.line_width / 2
        return any(
            _segment_distance(x, y, a, b) <= r
            for a, b in zip(self.points, self.points[1:])
        )


# ---------------------------------------------------------------------------
# Texto


@dataclass(kw_only=True, frozen=True)
class TextAnnotation(Annotation):
    origin: Point
    text: str = ""
    font_size: float = 24.0

    def bounds(self) -> Rect:
        width = max(len(self.text), 1) * self.font_size * 0.6
        height = self.font_size * 1.4
        return Rect(self.origin.x, self.origin.y, width, height)

    def translated(self, dx: float, dy: float) -> TextAnnotation:
        return replace(self, origin=self.origin.translated(dx, dy))

    def render(self, cr: cairo.Context, ctx: RenderContext) -> None:
        if not self.text:
            return
        layout = _pango_layout(cr, self.text, self.font_size)
        cr.move_to(self.origin.x, self.origin.y)
        _set_source(cr, self.color)
        PangoCairo.show_layout(cr, layout)


# ---------------------------------------------------------------------------
# Pixelate / Blur — sempre lêem RenderContext.origin, nunca o composto


def _scale_surface(surface: cairo.ImageSurface, dst_w: int, dst_h: int, filter_: int) -> cairo.ImageSurface:
    dst_w, dst_h = max(1, dst_w), max(1, dst_h)
    dst = cairo.ImageSurface(cairo.FORMAT_ARGB32, dst_w, dst_h)
    dst_cr = cairo.Context(dst)
    dst_cr.scale(dst_w / surface.get_width(), dst_h / surface.get_height())
    pattern = cairo.SurfacePattern(surface)
    pattern.set_filter(filter_)
    dst_cr.set_source(pattern)
    dst_cr.paint()
    return dst


def _crop_origin(origin: cairo.ImageSurface, r: Rect) -> cairo.ImageSurface | None:
    x, y = round(r.x), round(r.y)
    w, h = max(1, round(r.width)), max(1, round(r.height))
    if w < 1 or h < 1:
        return None
    crop = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    crop_cr = cairo.Context(crop)
    crop_cr.set_source_surface(origin, -x, -y)
    crop_cr.paint()
    return crop


@dataclass(kw_only=True, frozen=True)
class PixelateAnnotation(Annotation):
    """Reaproveita `line_width` como tamanho do bloco em px — dá controle ao vivo
    pelo mesmo +/- da toolbar, em vez de um tamanho fixo que nunca agrada todo mundo."""

    rect: Rect

    def bounds(self) -> Rect:
        return self.rect.normalized()

    def translated(self, dx: float, dy: float) -> PixelateAnnotation:
        return replace(self, rect=self.rect.translated(dx, dy))

    def render(self, cr: cairo.Context, ctx: RenderContext) -> None:
        r = self.rect.normalized()
        crop = _crop_origin(ctx.origin, r)
        if crop is None:
            return
        block = max(2, round(self.line_width * 1.5))
        # arredonda (não trunca) e garante um mínimo de blocos, senão uma
        # região pequena vira 1-2 quadrados gigantes em vez de pixelizada
        small_w = max(6, round(crop.get_width() / block))
        small_h = max(6, round(crop.get_height() / block))
        small = _scale_surface(crop, small_w, small_h, cairo.FILTER_NEAREST)

        cr.save()
        cr.rectangle(r.x, r.y, r.width, r.height)
        cr.clip()
        cr.translate(r.x, r.y)
        cr.scale(r.width / small_w, r.height / small_h)
        pattern = cairo.SurfacePattern(small)
        pattern.set_filter(cairo.FILTER_NEAREST)
        cr.set_source(pattern)
        cr.paint()
        cr.restore()


@dataclass(kw_only=True, frozen=True)
class BlurAnnotation(Annotation):
    """Forte o bastante pra realmente ocultar, não só suavizar. Reaproveita
    `line_width` como intensidade — mesmo +/- da toolbar controla ao vivo."""

    rect: Rect

    def bounds(self) -> Rect:
        return self.rect.normalized()

    def translated(self, dx: float, dy: float) -> BlurAnnotation:
        return replace(self, rect=self.rect.translated(dx, dy))

    def render(self, cr: cairo.Context, ctx: RenderContext) -> None:
        r = self.rect.normalized()
        crop = _crop_origin(ctx.origin, r)
        if crop is None:
            return
        cur = crop
        w, h = crop.get_width(), crop.get_height()
        radius = max(4, round(self.line_width * 6))
        factor = max(2, radius // 2)
        for _ in range(5):
            small = _scale_surface(cur, w // factor, h // factor, cairo.FILTER_BILINEAR)
            cur = _scale_surface(small, w, h, cairo.FILTER_BILINEAR)

        cr.save()
        cr.rectangle(r.x, r.y, r.width, r.height)
        cr.clip()
        pattern = cairo.SurfacePattern(cur)
        pattern.set_filter(cairo.FILTER_BILINEAR)
        matrix = cairo.Matrix()
        matrix.translate(-r.x, -r.y)
        pattern.set_matrix(matrix)
        cr.set_source(pattern)
        cr.paint()
        cr.restore()


# ---------------------------------------------------------------------------
# Numeração sequencial


@dataclass(kw_only=True, frozen=True)
class CounterAnnotation(Annotation):
    center: Point
    radius: float = 16.0
    number: int = 1
    text_color: Color = (1.0, 1.0, 1.0, 1.0)

    def bounds(self) -> Rect:
        return Rect(self.center.x - self.radius, self.center.y - self.radius, self.radius * 2, self.radius * 2)

    def translated(self, dx: float, dy: float) -> CounterAnnotation:
        return replace(self, center=self.center.translated(dx, dy))

    def hit_test(self, x: float, y: float, tolerance: float = 4.0) -> bool:
        return math.hypot(x - self.center.x, y - self.center.y) <= self.radius + tolerance

    def render(self, cr: cairo.Context, ctx: RenderContext) -> None:
        _set_source(cr, self.color)
        cr.arc(self.center.x, self.center.y, self.radius, 0, 2 * math.pi)
        cr.fill()

        layout = _pango_layout(cr, str(self.number), self.radius, bold=True)
        _, log_rect = layout.get_pixel_extents()
        cr.move_to(self.center.x - log_rect.width / 2, self.center.y - log_rect.height / 2)
        _set_source(cr, self.text_color)
        PangoCairo.show_layout(cr, layout)
