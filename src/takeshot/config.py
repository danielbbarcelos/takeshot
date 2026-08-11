"""Configuração persistente em JSON (~/.config/takeshot/config.json)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from takeshot import paths

DEFAULTS: dict[str, Any] = {
    "portal_permission_granted": False,
    "interactive_portal": False,
    "copy_on_capture": True,
    "edit_on_capture": True,
    "save_dir": None,  # None => paths.pictures_dir()
    "dim_opacity": 0.45,
    "counter_start": 1,
    "tool_color": [1.0, 0.13, 0.13, 1.0],
    "tool_line_width": 3.0,
    "last_selection": None,  # {"x","y","w","h"} como fração 0..1 da tela lógica, ou None
}


@dataclass
class Config:
    data: dict[str, Any] = field(default_factory=lambda: dict(DEFAULTS))

    def __getattr__(self, name: str) -> Any:
        try:
            return self.data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "data":
            super().__setattr__(name, value)
        else:
            self.data[name] = value

    def save_dir_path(self) -> Path:
        raw = self.data.get("save_dir")
        return paths.pictures_dir() if raw is None else Path(raw)

    def save(self) -> None:
        paths.ensure_dirs()
        path = paths.config_file()
        path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @classmethod
    def load(cls) -> "Config":
        path = paths.config_file()
        merged = dict(DEFAULTS)
        if path.exists():
            try:
                on_disk = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(on_disk, dict):
                    merged.update(on_disk)
            except (OSError, json.JSONDecodeError):
                pass
        return cls(data=merged)
