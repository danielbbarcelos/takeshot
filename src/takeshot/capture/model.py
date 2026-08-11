"""Modelo de uma captura de tela. Só `cairo`/`dataclasses` — sem gi."""

from __future__ import annotations

from dataclasses import dataclass, field

import cairo

from takeshot.geom import Rect


@dataclass
class MonitorInfo:
    name: str
    geometry: Rect  # coordenadas lógicas
    scale_factor: int


@dataclass
class Capture:
    surface: cairo.ImageSurface
    logical_bounds: Rect  # união das geometrias dos monitores, coordenadas lógicas
    scale: float  # surface.get_width() / logical_bounds.width
    monitors: list[MonitorInfo] = field(default_factory=list)

    def image_from_logical(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.logical_bounds.x) * self.scale, (y - self.logical_bounds.y) * self.scale

    def logical_from_image(self, x: float, y: float) -> tuple[float, float]:
        return x / self.scale + self.logical_bounds.x, y / self.scale + self.logical_bounds.y
