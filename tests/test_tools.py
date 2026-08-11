from takeshot.editor.items import ArrowAnnotation, CounterAnnotation, FreehandAnnotation, RectAnnotation
from takeshot.editor.tools import ArrowTool, CounterTool, FreehandTool, RectTool, ToolStyle, make_tool, ToolKind
from takeshot.geom import Point


def test_arrow_tool_produces_annotation_on_release():
    tool = ArrowTool(ToolStyle())
    tool.on_press(Point(0, 0))
    tool.on_motion(Point(10, 10))
    item = tool.on_release(Point(20, 20))
    assert isinstance(item, ArrowAnnotation)
    assert item.start == Point(0, 0)
    assert item.end == Point(20, 20)


def test_arrow_tool_ignores_zero_length_drag():
    tool = ArrowTool(ToolStyle())
    tool.on_press(Point(5, 5))
    item = tool.on_release(Point(5, 5))
    assert item is None


def test_rect_tool_ignores_tiny_drag():
    tool = RectTool(ToolStyle())
    tool.on_press(Point(0, 0))
    item = tool.on_release(Point(1, 1))
    assert item is None


def test_rect_tool_produces_normalized_rect():
    tool = RectTool(ToolStyle())
    tool.on_press(Point(50, 50))
    item = tool.on_release(Point(10, 10))
    assert isinstance(item, RectAnnotation)
    assert item.rect.x == 10 and item.rect.y == 10


def test_freehand_tool_collects_motion_points():
    tool = FreehandTool(ToolStyle())
    tool.on_press(Point(0, 0))
    tool.on_motion(Point(1, 1))
    tool.on_motion(Point(2, 2))
    item = tool.on_release(Point(3, 3))
    assert isinstance(item, FreehandAnnotation)
    assert len(item.points) == 4


def test_counter_tool_uses_next_number_callback():
    calls = iter([1, 2])
    tool = CounterTool(ToolStyle(), next_number=lambda: next(calls))
    a = tool.on_release(Point(0, 0))
    b = tool.on_release(Point(10, 10))
    assert isinstance(a, CounterAnnotation) and a.number == 1
    assert isinstance(b, CounterAnnotation) and b.number == 2


def test_make_tool_returns_matching_kind():
    tool = make_tool(ToolKind.BLUR, ToolStyle(), next_counter=lambda: 1)
    assert tool.kind is ToolKind.BLUR
