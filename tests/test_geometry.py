from takeshot.geom import Point, Rect


def test_rect_normalized_handles_negative_drag():
    r = Rect(100, 100, -50, -30)
    n = r.normalized()
    assert n == Rect(50, 70, 50, 30)


def test_rect_from_points():
    r = Rect.from_points(Point(10, 10), Point(2, 30))
    assert r == Rect(2, 10, 8, 20)


def test_rect_contains():
    r = Rect(0, 0, 10, 10)
    assert r.contains(Point(5, 5))
    assert not r.contains(Point(11, 5))


def test_rect_union_single():
    r = Rect(0, 0, 10, 10)
    assert Rect.union([r]) == r


def test_rect_union_multiple_monitors():
    a = Rect(0, 0, 1920, 1080)
    b = Rect(1920, 0, 1920, 1080)
    assert Rect.union([a, b]) == Rect(0, 0, 3840, 1080)


def test_rect_union_empty():
    assert Rect.union([]) == Rect(0, 0, 0, 0)


def test_rect_inset_grows_with_negative_amount():
    r = Rect(10, 10, 20, 20)
    grown = r.inset(-5)
    assert grown == Rect(5, 5, 30, 30)


def test_point_translated():
    p = Point(1, 2)
    assert p.translated(3, -1) == Point(4, 1)
