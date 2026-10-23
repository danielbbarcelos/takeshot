from takeshot.editor.document import AnnotationDocument
from takeshot.editor.items import TextAnnotation
from takeshot.editor.textedit import FONT_SIZE_RANGE, TextEdit, TextStyle
from takeshot.geom import Point

STYLE = TextStyle(font_size=14.0, color=(1, 0, 0, 1), background=None)


def doc_with(*items):
    doc = AnnotationDocument()
    for item in items:
        doc.add(item)
    return doc


def test_confirm_new_text_adds_item_with_style():
    doc = AnnotationDocument()
    edit = TextEdit.new(Point(10, 20), STYLE)
    edit.text = "linha 1\nlinha 2"
    edit.confirm(doc)
    (item,) = doc.items
    assert item.text == "linha 1\nlinha 2"
    assert item.origin == Point(10, 20)
    assert item.font_size == 14.0 and item.color == (1, 0, 0, 1) and item.background is None


def test_confirm_empty_new_text_adds_nothing():
    doc = AnnotationDocument()
    TextEdit.new(Point(0, 0), STYLE).confirm(doc)
    assert doc.items == []


def test_confirm_existing_replaces_in_place_and_is_one_undo_step():
    original = TextAnnotation(origin=Point(0, 0), text="oi", font_size=14.0)
    doc = doc_with(original)
    edit = TextEdit.of(original)
    edit.move_by(5, 5)
    edit.style = edit.style.with_font_size(20)
    edit.confirm(doc)
    (item,) = doc.items
    assert item.origin == Point(5, 5) and item.font_size == 20 and item.text == "oi"
    doc.undo()
    assert doc.items == [original]


def test_confirm_existing_emptied_removes_it():
    original = TextAnnotation(origin=Point(0, 0), text="oi")
    doc = doc_with(original)
    edit = TextEdit.of(original)
    edit.text = ""
    edit.confirm(doc)
    assert doc.items == []


def test_cancel_new_text_adds_nothing():
    doc = AnnotationDocument()
    edit = TextEdit.new(Point(0, 0), STYLE)
    edit.text = "rascunho"
    edit.cancel(doc)
    assert doc.items == []


def test_cancel_existing_deletes_it():
    original = TextAnnotation(origin=Point(0, 0), text="oi")
    doc = doc_with(original)
    TextEdit.of(original).cancel(doc)
    assert doc.items == []


def test_discard_existing_keeps_original_untouched():
    original = TextAnnotation(origin=Point(0, 0), text="oi")
    doc = doc_with(original)
    edit = TextEdit.of(original)
    edit.move_by(50, 50)
    edit.text = "mudou"
    edit.discard(doc)
    assert doc.items == [original]


def test_font_size_is_clamped():
    style = STYLE.with_font_size(1000)
    assert style.font_size == FONT_SIZE_RANGE[1]
    assert STYLE.with_font_size(-5).font_size == FONT_SIZE_RANGE[0]


def test_of_existing_copies_its_style():
    original = TextAnnotation(origin=Point(1, 2), text="x", font_size=30, color=(0, 1, 0, 1), background=(0, 0, 0, 1))
    edit = TextEdit.of(original)
    assert edit.style == TextStyle(font_size=30, color=(0, 1, 0, 1), background=(0, 0, 0, 1))
    assert edit.original is original
