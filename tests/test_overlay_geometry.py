from takeshot.editor.overlay import HANDLE_NAMES, handle_positions, resized_rect
from takeshot.geom import Point, Rect


def test_handle_positions_covers_all_eight_handles():
    r = Rect(10, 10, 100, 50)
    positions = handle_positions(r)
    assert set(positions.keys()) == set(HANDLE_NAMES)
    assert positions["nw"] == Point(10, 10)
    assert positions["se"] == Point(110, 60)
    assert positions["n"] == Point(60, 10)
    assert positions["e"] == Point(110, 35)


def test_resized_rect_corner_moves_two_edges():
    anchor = Rect(10, 10, 100, 50)  # x2=110, y2=60
    result = resized_rect("nw", anchor, Point(0, 0))
    assert result == Rect(0, 0, 110, 60)


def test_resized_rect_edge_moves_one_side_only():
    anchor = Rect(10, 10, 100, 50)
    result = resized_rect("e", anchor, Point(200, 999))  # y não deveria importar
    assert result == Rect(10, 10, 190, 50)


def test_resized_rect_south_edge():
    anchor = Rect(10, 10, 100, 50)
    result = resized_rect("s", anchor, Point(999, 100))
    assert result == Rect(10, 10, 100, 90)


def test_resized_rect_handles_drag_past_opposite_edge():
    """Arrastar o handle 'e' pra esquerda do lado 'w' original deve inverter, não quebrar."""
    anchor = Rect(10, 10, 100, 50)
    result = resized_rect("e", anchor, Point(-50, 10))
    assert result == Rect(-50, 10, 60, 50)


def test_resized_rect_se_corner():
    anchor = Rect(0, 0, 50, 50)
    result = resized_rect("se", anchor, Point(80, 80))
    assert result == Rect(0, 0, 80, 80)
