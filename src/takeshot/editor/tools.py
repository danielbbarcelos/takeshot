"""Máquina de estados por ferramenta: on_press/on_motion/on_release + preview.

Cada ferramenta devolve, no release, um `Annotation` imutável pronto para
`document.add()`. Durante o arrasto a ferramenta desenha um preview
diretamente no `cr` do canvas — fora do documento (CLAUDE.md §3.5):
`_commit()` só acontece no fim, via `document.add()`.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Callable

import cairo

from takeshot.editor.items import (
    Annotation,
    ArrowAnnotation,
    BlurAnnotation,
    Color,
    CounterAnnotation,
    EllipseAnnotation,
    FreehandAnnotation,
    PixelateAnnotation,
    RectAnnotation,
    RenderContext,
    TextAnnotation,
)
from takeshot.geom import Point, Rect

MIN_DRAG_SIZE = 2.0


class ToolKind(enum.Enum):
    ARROW = "arrow"
    RECT = "rect"
    ELLIPSE = "ellipse"
    FREEHAND = "freehand"
    TEXT = "text"
    PIXELATE = "pixelate"
    BLUR = "blur"
    COUNTER = "counter"


TOOL_KEY_BINDINGS: dict[str, ToolKind] = {
    "1": ToolKind.ARROW,
    "2": ToolKind.RECT,
    "3": ToolKind.ELLIPSE,
    "4": ToolKind.FREEHAND,
    "5": ToolKind.TEXT,
    "6": ToolKind.PIXELATE,
    "7": ToolKind.BLUR,
    "8": ToolKind.COUNTER,
}

CLICK_TOOLS = {ToolKind.TEXT, ToolKind.COUNTER}
"""Ferramentas que agem no clique/press, não no arrasto de um retângulo."""


@dataclass
class ToolStyle:
    color: Color = (1.0, 0.13, 0.13, 1.0)
    line_width: float = 3.0


class Tool:
    kind: ToolKind

    def __init__(self, style: ToolStyle) -> None:
        self.style = style
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    def on_press(self, p: Point) -> None:
        self._active = True

    def on_motion(self, p: Point) -> None:
        raise NotImplementedError

    def on_release(self, p: Point) -> "Annotation | None":
        self._active = False
        raise NotImplementedError

    def draw_preview(self, cr: cairo.Context, ctx: RenderContext) -> None:
        pass


class ArrowTool(Tool):
    kind = ToolKind.ARROW

    def __init__(self, style: ToolStyle) -> None:
        super().__init__(style)
        self._start: Point | None = None
        self._end: Point | None = None

    def on_press(self, p: Point) -> None:
        super().on_press(p)
        self._start = p
        self._end = p

    def on_motion(self, p: Point) -> None:
        self._end = p

    def _annotation(self) -> "Annotation | None":
        if self._start is None or self._end is None or self._start == self._end:
            return None
        return ArrowAnnotation(start=self._start, end=self._end, color=self.style.color, line_width=self.style.line_width)

    def on_release(self, p: Point) -> "Annotation | None":
        self._end = p
        item = self._annotation()
        self._active = False
        self._start = self._end = None
        return item

    def draw_preview(self, cr: cairo.Context, ctx: RenderContext) -> None:
        item = self._annotation()
        if item:
            item.render(cr, ctx)


class _RectDragTool(Tool):
    """Base para ferramentas que definem um Rect por arrasto (rect/ellipse/pixelate/blur)."""

    annotation_cls: type

    def __init__(self, style: ToolStyle, **extra_kwargs) -> None:
        super().__init__(style)
        self._start: Point | None = None
        self._end: Point | None = None
        self._extra_kwargs = extra_kwargs

    def on_press(self, p: Point) -> None:
        super().on_press(p)
        self._start = p
        self._end = p

    def on_motion(self, p: Point) -> None:
        self._end = p

    def _annotation(self) -> "Annotation | None":
        if self._start is None or self._end is None:
            return None
        rect = Rect.from_points(self._start, self._end)
        if rect.width < MIN_DRAG_SIZE or rect.height < MIN_DRAG_SIZE:
            return None
        return self.annotation_cls(rect=rect, color=self.style.color, line_width=self.style.line_width, **self._extra_kwargs)

    def on_release(self, p: Point) -> "Annotation | None":
        self._end = p
        item = self._annotation()
        self._active = False
        self._start = self._end = None
        return item

    def draw_preview(self, cr: cairo.Context, ctx: RenderContext) -> None:
        item = self._annotation()
        if item:
            item.render(cr, ctx)


class RectTool(_RectDragTool):
    kind = ToolKind.RECT
    annotation_cls = RectAnnotation


class EllipseTool(_RectDragTool):
    kind = ToolKind.ELLIPSE
    annotation_cls = EllipseAnnotation


class PixelateTool(_RectDragTool):
    kind = ToolKind.PIXELATE
    annotation_cls = PixelateAnnotation


class BlurTool(_RectDragTool):
    kind = ToolKind.BLUR
    annotation_cls = BlurAnnotation


class FreehandTool(Tool):
    kind = ToolKind.FREEHAND

    def __init__(self, style: ToolStyle) -> None:
        super().__init__(style)
        self._points: list[Point] = []

    def on_press(self, p: Point) -> None:
        super().on_press(p)
        self._points = [p]

    def on_motion(self, p: Point) -> None:
        self._points.append(p)

    def on_release(self, p: Point) -> "Annotation | None":
        self._points.append(p)
        self._active = False
        points, self._points = self._points, []
        if len(points) < 2:
            return None
        return FreehandAnnotation(points=tuple(points), color=self.style.color, line_width=self.style.line_width)

    def draw_preview(self, cr: cairo.Context, ctx: RenderContext) -> None:
        if len(self._points) >= 2:
            FreehandAnnotation(points=tuple(self._points), color=self.style.color, line_width=self.style.line_width).render(cr, ctx)


class CounterTool(Tool):
    """Ferramenta de clique único: numeração sequencial derivada do documento."""

    kind = ToolKind.COUNTER

    def __init__(self, style: ToolStyle, next_number: Callable[[], int]) -> None:
        super().__init__(style)
        self._next_number = next_number

    def on_motion(self, p: Point) -> None:
        pass

    def on_release(self, p: Point) -> "Annotation | None":
        self._active = False
        return CounterAnnotation(center=p, number=self._next_number(), color=self.style.color)


class TextTool(Tool):
    """Ferramenta de clique único: a UI de entrada de texto é responsabilidade do overlay."""

    kind = ToolKind.TEXT

    def on_motion(self, p: Point) -> None:
        pass

    def on_release(self, p: Point) -> "Annotation | None":
        self._active = False
        return None  # overlay.py trata TEXT à parte (abre um Gtk.Entry flutuante)


def make_tool(kind: ToolKind, style: ToolStyle, next_counter: Callable[[], int]) -> Tool:
    if kind is ToolKind.ARROW:
        return ArrowTool(style)
    if kind is ToolKind.RECT:
        return RectTool(style)
    if kind is ToolKind.ELLIPSE:
        return EllipseTool(style)
    if kind is ToolKind.FREEHAND:
        return FreehandTool(style)
    if kind is ToolKind.PIXELATE:
        return PixelateTool(style)
    if kind is ToolKind.BLUR:
        return BlurTool(style)
    if kind is ToolKind.COUNTER:
        return CounterTool(style, next_counter)
    if kind is ToolKind.TEXT:
        return TextTool(style)
    raise ValueError(f"ferramenta desconhecida: {kind}")


def make_text_annotation(origin: Point, text: str, style: ToolStyle, font_size: float = 24.0) -> "Annotation | None":
    if not text:
        return None
    return TextAnnotation(origin=origin, text=text, font_size=font_size, color=style.color)
