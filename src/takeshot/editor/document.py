"""AnnotationDocument: itens, seleção, undo/redo, numeração sequencial.

Undo/redo por snapshot da lista de itens, não command pattern (CLAUDE.md
§3.5) — os itens são imutáveis por convenção, o payload é sempre pequeno, e
um command pattern adicionaria superfície de bug sem necessidade real.
`_commit()` só deve ser chamado no fim de uma ação da ferramenta (on_release);
durante o arrasto, a ferramenta desenha um preview fora do documento.
"""

from __future__ import annotations

from takeshot.editor.items import Annotation, CounterAnnotation
from takeshot.geom import Rect

MAX_UNDO_DEPTH = 100


class AnnotationDocument:
    def __init__(self, counter_start: int = 1) -> None:
        self._items: list[Annotation] = []
        self._undo: list[list[Annotation]] = []
        self._redo: list[list[Annotation]] = []
        self.selection_rect: Rect | None = None
        self.counter_start = counter_start

    @property
    def items(self) -> list[Annotation]:
        return list(self._items)

    @property
    def next_counter(self) -> int:
        """Número derivado, nunca armazenado como estado mutável.

        Undo de um contador volta o próximo ao número certo automaticamente;
        apagar o nº 2 do meio não renumera os outros (comportamento Flameshot).
        """
        used = [i.number for i in self._items if isinstance(i, CounterAnnotation)]
        return (max(used) + 1) if used else self.counter_start

    def add(self, item: Annotation) -> None:
        self._commit(self._items + [item])

    def remove(self, item: Annotation) -> None:
        if item in self._items:
            self._commit([i for i in self._items if i is not item])

    def replace_items(self, items: list[Annotation]) -> None:
        self._commit(list(items))

    def hit_test(self, x: float, y: float) -> Annotation | None:
        for item in reversed(self._items):
            if item.hit_test(x, y):
                return item
        return None

    def _commit(self, new_items: list[Annotation]) -> None:
        self._undo.append(list(self._items))
        self._items = new_items
        self._redo.clear()
        if len(self._undo) > MAX_UNDO_DEPTH:
            self._undo.pop(0)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(list(self._items))
        self._items = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(list(self._items))
        self._items = self._redo.pop()
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def clear(self) -> None:
        self._items = []
        self._undo.clear()
        self._redo.clear()
        self.selection_rect = None
