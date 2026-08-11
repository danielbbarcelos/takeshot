import cairo

from takeshot.capture.model import Capture
from takeshot.editor.overlay import fraction_to_selection, selection_to_fraction
from takeshot.geom import Rect


def make_capture(logical_bounds=Rect(0, 0, 1920, 1080), scale=1.0):
    surface = cairo.ImageSurface(
        cairo.FORMAT_ARGB32, round(logical_bounds.width * scale), round(logical_bounds.height * scale),
    )
    return Capture(surface=surface, logical_bounds=logical_bounds, scale=scale)


def test_round_trip_preserves_rect_at_scale_one():
    cap = make_capture(scale=1.0)
    original = Rect(100, 200, 300, 150)
    fraction = selection_to_fraction(cap, original)
    restored = fraction_to_selection(cap, fraction)
    assert restored is not None
    assert round(restored.x, 3) == original.x
    assert round(restored.y, 3) == original.y
    assert round(restored.width, 3) == original.width
    assert round(restored.height, 3) == original.height


def test_round_trip_preserves_rect_at_scale_two():
    cap = make_capture(scale=2.0)
    original = Rect(40, 60, 200, 100)
    fraction = selection_to_fraction(cap, original)
    restored = fraction_to_selection(cap, fraction)
    assert round(restored.width, 3) == original.width
    assert round(restored.height, 3) == original.height


def test_fraction_survives_different_resolution():
    """Guardado numa tela 1920x1080, restaurado numa 3840x2160 — deve escalar proporcionalmente."""
    small = make_capture(logical_bounds=Rect(0, 0, 1920, 1080))
    original = Rect(0, 0, 960, 540)  # metade da tela
    fraction = selection_to_fraction(small, original)

    big = make_capture(logical_bounds=Rect(0, 0, 3840, 2160))
    restored = fraction_to_selection(big, fraction)
    assert restored is not None
    assert round(restored.width, 3) == 1920.0
    assert round(restored.height, 3) == 1080.0


def test_fraction_to_selection_none_when_no_cache():
    cap = make_capture()
    assert fraction_to_selection(cap, {}) is None


def test_fraction_to_selection_none_for_degenerate_rect():
    cap = make_capture()
    assert fraction_to_selection(cap, {"x": 0, "y": 0, "w": 0, "h": 0}) is None


def test_fraction_to_selection_none_for_malformed_dict():
    cap = make_capture()
    assert fraction_to_selection(cap, {"x": "nao-numero", "y": 0, "w": 0.1, "h": 0.1}) is None
