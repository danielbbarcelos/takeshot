"""Geometria pura: sem gi, sem cairo. Compartilhada por capture/editor/overlay."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def translated(self, dx: float, dy: float) -> Point:
        return Point(self.x + dx, self.y + dy)


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def x2(self) -> float:
        return self.x + self.width

    @property
    def y2(self) -> float:
        return self.y + self.height

    def normalized(self) -> Rect:
        """Largura/altura sempre positivas, independente da direção do arrasto."""
        x = min(self.x, self.x2)
        y = min(self.y, self.y2)
        return Rect(x, y, abs(self.width), abs(self.height))

    def contains(self, p: Point) -> bool:
        return self.x <= p.x <= self.x2 and self.y <= p.y <= self.y2

    def scaled(self, factor: float) -> Rect:
        return Rect(self.x * factor, self.y * factor, self.width * factor, self.height * factor)

    def translated(self, dx: float, dy: float) -> Rect:
        return Rect(self.x + dx, self.y + dy, self.width, self.height)

    def inset(self, amount: float) -> Rect:
        return Rect(self.x + amount, self.y + amount, self.width - 2 * amount, self.height - 2 * amount)

    @staticmethod
    def from_points(a: Point, b: Point) -> Rect:
        return Rect(a.x, a.y, b.x - a.x, b.y - a.y).normalized()

    @staticmethod
    def union(rects: list[Rect]) -> Rect:
        if not rects:
            return Rect(0, 0, 0, 0)
        min_x = min(r.x for r in rects)
        min_y = min(r.y for r in rects)
        max_x = max(r.x2 for r in rects)
        max_y = max(r.y2 for r in rects)
        return Rect(min_x, min_y, max_x - min_x, max_y - min_y)
