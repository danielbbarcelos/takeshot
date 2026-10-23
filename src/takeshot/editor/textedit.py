"""Edição de um texto (novo ou existente) antes de ir para o documento. Sem gi.

O rascunho vive fora do documento enquanto se edita; o original, se houver,
continua no documento e só é escondido na tela (render(exclude=...)). Assim
os três desfechos da toolbar de texto são triviais e cada um custa no máximo
um passo de undo:

    confirm  aplica o rascunho (add, replace ou remove se ficou vazio)
    cancel   exclui o texto: o novo some, o existente é removido do documento
    discard  descarta só as alterações: o documento fica como estava
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from takeshot.editor.document import AnnotationDocument
from takeshot.editor.items import Color, TextAnnotation
from takeshot.geom import Point, Rect

FONT_SIZE_DEFAULT = 14.0
FONT_SIZE_STEP = 2.0
FONT_SIZE_RANGE = (8.0, 96.0)

TEXT_COLORS: list[tuple[str, Color]] = [
    ("Vermelho", (0.90, 0.11, 0.14, 1.0)),
    ("Laranja", (1.00, 0.47, 0.00, 1.0)),
    ("Amarelo", (1.00, 0.84, 0.00, 1.0)),
    ("Verde", (0.18, 0.76, 0.49, 1.0)),
    ("Azul", (0.21, 0.52, 0.89, 1.0)),
    ("Branco", (1.0, 1.0, 1.0, 1.0)),
    ("Preto", (0.0, 0.0, 0.0, 1.0)),
]

TEXT_BACKGROUNDS: list[tuple[str, "Color | None"]] = [
    ("Sem fundo", None),
    ("Preto", (0.0, 0.0, 0.0, 0.85)),
    ("Branco", (1.0, 1.0, 1.0, 0.95)),
    ("Amarelo", (1.00, 0.84, 0.00, 1.0)),
    ("Vermelho", (0.90, 0.11, 0.14, 1.0)),
    ("Azul", (0.21, 0.52, 0.89, 1.0)),
]


@dataclass(frozen=True)
class TextStyle:
    font_size: float = FONT_SIZE_DEFAULT
    color: Color = TEXT_COLORS[0][1]
    background: "Color | None" = None

    def with_font_size(self, size: float) -> TextStyle:
        return replace(self, font_size=max(FONT_SIZE_RANGE[0], min(FONT_SIZE_RANGE[1], size)))


@dataclass
class TextEdit:
    origin: Point
    style: TextStyle
    text: str = ""
    original: "TextAnnotation | None" = None

    @classmethod
    def new(cls, origin: Point, style: TextStyle) -> TextEdit:
        return cls(origin=origin, style=style)

    @classmethod
    def of(cls, item: TextAnnotation) -> TextEdit:
        style = TextStyle(font_size=item.font_size, color=item.color, background=item.background)
        return cls(origin=item.origin, style=style, text=item.text, original=item)

    @property
    def is_new(self) -> bool:
        return self.original is None

    def move_by(self, dx: float, dy: float) -> None:
        self.origin = self.origin.translated(dx, dy)

    def draft(self) -> TextAnnotation:
        return TextAnnotation(
            origin=self.origin, text=self.text, font_size=self.style.font_size,
            color=self.style.color, background=self.style.background,
        )

    def bounds(self) -> Rect:
        """Caixa do rascunho; com texto vazio, mede uma linha de um caractere."""
        return replace(self.draft(), text=self.text or " ").bounds()

    def confirm(self, document: AnnotationDocument) -> None:
        if self.original is None:
            if self.text:
                document.add(self.draft())
            return
        if not self.text:
            document.remove(self.original)
        elif self.draft() != self.original:
            document.replace(self.original, self.draft())

    def cancel(self, document: AnnotationDocument) -> None:
        if self.original is not None:
            document.remove(self.original)

    def discard(self, document: AnnotationDocument) -> None:
        pass
