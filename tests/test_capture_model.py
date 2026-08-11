import cairo

from takeshot.capture.model import Capture
from takeshot.geom import Rect


def make_capture(scale: float = 2.0) -> Capture:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 100)
    return Capture(surface=surface, logical_bounds=Rect(0, 0, 100, 50), scale=scale)


def test_image_from_logical_applies_scale():
    cap = make_capture(scale=2.0)
    assert cap.image_from_logical(10, 5) == (20.0, 10.0)


def test_logical_from_image_is_inverse_of_image_from_logical():
    cap = make_capture(scale=2.0)
    ix, iy = cap.image_from_logical(37, 12)
    lx, ly = cap.logical_from_image(ix, iy)
    assert round(lx, 6) == 37.0
    assert round(ly, 6) == 12.0


def test_logical_bounds_offset_is_respected():
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 100, 100)
    cap = Capture(surface=surface, logical_bounds=Rect(1920, 0, 100, 100), scale=1.0)
    assert cap.image_from_logical(1920, 0) == (0.0, 0.0)
    assert cap.image_from_logical(1970, 50) == (50.0, 50.0)
