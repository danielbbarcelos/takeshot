import cairo
import pytest

from takeshot.editor.items import (
    ArrowAnnotation,
    BlurAnnotation,
    CounterAnnotation,
    EllipseAnnotation,
    FreehandAnnotation,
    PixelateAnnotation,
    RectAnnotation,
    RenderContext,
    TextAnnotation,
)
from takeshot.geom import Point, Rect


@pytest.fixture
def origin_surface() -> cairo.ImageSurface:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 200)
    cr = cairo.Context(surface)
    cr.set_source_rgba(0.2, 0.4, 0.6, 1.0)
    cr.paint()
    return surface


@pytest.fixture
def ctx(origin_surface) -> RenderContext:
    return RenderContext(origin=origin_surface)


def render_alone(item, ctx) -> cairo.ImageSurface:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 200)
    cr = cairo.Context(surface)
    item.render(cr, ctx)
    return surface


def test_rect_annotation_bounds_normalizes_negative_size():
    item = RectAnnotation(rect=Rect(50, 50, -20, -20))
    b = item.bounds()
    assert b.x < 50 and b.y < 50


def test_arrow_hit_test_near_line():
    item = ArrowAnnotation(start=Point(0, 0), end=Point(100, 0), line_width=4)
    assert item.hit_test(50, 1)
    assert not item.hit_test(50, 50)


def test_freehand_hit_test_along_path():
    item = FreehandAnnotation(points=(Point(0, 0), Point(10, 0), Point(10, 10)))
    assert item.hit_test(5, 0)
    assert item.hit_test(10, 5)
    assert not item.hit_test(100, 100)


def test_freehand_translated_moves_all_points():
    item = FreehandAnnotation(points=(Point(0, 0), Point(1, 1)))
    moved = item.translated(5, 5)
    assert moved.points == (Point(5, 5), Point(6, 6))


def test_counter_annotation_hit_test_is_circular():
    item = CounterAnnotation(center=Point(50, 50), radius=10, number=3)
    assert item.hit_test(55, 50)
    assert not item.hit_test(70, 50)


def test_items_render_without_raising(ctx):
    items = [
        ArrowAnnotation(start=Point(0, 0), end=Point(50, 50)),
        RectAnnotation(rect=Rect(10, 10, 30, 30)),
        EllipseAnnotation(rect=Rect(10, 10, 30, 30), filled=True),
        FreehandAnnotation(points=(Point(0, 0), Point(5, 5), Point(10, 0))),
        TextAnnotation(origin=Point(5, 5), text="oi"),
        PixelateAnnotation(rect=Rect(20, 20, 40, 40), line_width=8),
        BlurAnnotation(rect=Rect(20, 20, 40, 40), line_width=6),
        CounterAnnotation(center=Point(100, 100), number=1),
    ]
    for item in items:
        render_alone(item, ctx)  # não deve lançar


def test_pixelate_reads_origin_not_transparent(ctx):
    item = PixelateAnnotation(rect=Rect(20, 20, 40, 40), line_width=8)
    surface = render_alone(item, ctx)
    surface.flush()
    data = surface.get_data()
    stride = surface.get_stride()
    # pixel no meio da região pixelizada deve ter alpha > 0 (algo foi desenhado)
    px, py = 40, 40
    offset = py * stride + px * 4
    assert data[offset + 3] > 0


def test_text_annotation_bounds_scale_with_length():
    short = TextAnnotation(origin=Point(0, 0), text="a")
    long = TextAnnotation(origin=Point(0, 0), text="a longer string")
    assert long.bounds().width > short.bounds().width
