"""Caminhos de configuração, estado e dados do takeshot (XDG base dirs)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

APP_ID = "com.danielbarcelos.Takeshot"


def _xdg(env_var: str, default: str) -> Path:
    value = os.environ.get(env_var)
    return Path(value) if value else Path.home() / default


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / "takeshot"


def state_dir() -> Path:
    return _xdg("XDG_STATE_HOME", ".local/state") / "takeshot"


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share") / "takeshot"


def config_file() -> Path:
    return config_dir() / "config.json"


def install_state_file() -> Path:
    return state_dir() / "install-state.json"


def pictures_dir() -> Path:
    """Diretório padrão para salvar capturas: xdg-user-dir PICTURES + /Takeshot (ex.: ~/Imagens/Takeshot)."""
    try:
        out = subprocess.run(
            ["xdg-user-dir", "PICTURES"],
            capture_output=True, text=True, timeout=2, check=True,
        ).stdout.strip()
        base = Path(out) if out else Path.home() / "Pictures"
    except (OSError, subprocess.SubprocessError):
        base = Path.home() / "Pictures"
    return base / "Takeshot"


def ensure_dirs() -> None:
    for d in (config_dir(), state_dir(), data_dir()):
        d.mkdir(parents=True, exist_ok=True)
