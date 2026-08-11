from takeshot.editor.document import AnnotationDocument
from takeshot.editor.items import ArrowAnnotation, CounterAnnotation
from takeshot.geom import Point


def make_arrow():
    return ArrowAnnotation(start=Point(0, 0), end=Point(10, 10))


def test_add_appends_item():
    doc = AnnotationDocument()
    doc.add(make_arrow())
    assert len(doc.items) == 1


def test_undo_restores_previous_state():
    doc = AnnotationDocument()
    doc.add(make_arrow())
    doc.add(make_arrow())
    assert len(doc.items) == 2
    assert doc.undo()
    assert len(doc.items) == 1
    assert doc.undo()
    assert len(doc.items) == 0
    assert not doc.undo()


def test_redo_reapplies_undone_state():
    doc = AnnotationDocument()
    doc.add(make_arrow())
    doc.undo()
    assert doc.redo()
    assert len(doc.items) == 1
    assert not doc.redo()


def test_new_action_clears_redo_stack():
    doc = AnnotationDocument()
    doc.add(make_arrow())
    doc.undo()
    doc.add(make_arrow())
    assert not doc.can_redo


def test_counter_start_default():
    doc = AnnotationDocument(counter_start=1)
    assert doc.next_counter == 1


def test_counter_start_configurable():
    doc = AnnotationDocument(counter_start=5)
    assert doc.next_counter == 5


def test_next_counter_derives_from_max_used():
    doc = AnnotationDocument()
    doc.add(CounterAnnotation(center=Point(0, 0), number=1))
    doc.add(CounterAnnotation(center=Point(10, 10), number=2))
    assert doc.next_counter == 3


def test_undo_of_counter_restores_next_number_automatically():
    doc = AnnotationDocument()
    doc.add(CounterAnnotation(center=Point(0, 0), number=1))
    doc.add(CounterAnnotation(center=Point(10, 10), number=2))
    assert doc.next_counter == 3
    doc.undo()
    assert doc.next_counter == 2


def test_deleting_middle_counter_does_not_renumber_others():
    doc = AnnotationDocument()
    first = CounterAnnotation(center=Point(0, 0), number=1)
    second = CounterAnnotation(center=Point(10, 10), number=2)
    third = CounterAnnotation(center=Point(20, 20), number=3)
    doc.add(first)
    doc.add(second)
    doc.add(third)
    doc.remove(second)
    numbers = [i.number for i in doc.items if isinstance(i, CounterAnnotation)]
    assert numbers == [1, 3]
    # próximo número continua derivado do maior usado, não do count de itens
    assert doc.next_counter == 4


def test_hit_test_returns_topmost_match():
    doc = AnnotationDocument()
    doc.add(ArrowAnnotation(start=Point(0, 0), end=Point(100, 0)))
    doc.add(ArrowAnnotation(start=Point(0, 5), end=Point(100, 5)))
    hit = doc.hit_test(50, 5)
    assert hit is not None
    assert hit.start == Point(0, 5)


def test_clear_resets_everything():
    doc = AnnotationDocument()
    doc.add(make_arrow())
    doc.selection_rect = None
    doc.clear()
    assert doc.items == []
    assert not doc.can_undo
    assert not doc.can_redo
