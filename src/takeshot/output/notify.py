"""Notificação nativa do SO ao concluir uma captura (Gio.Notification)."""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio  # noqa: E402


def notify_capture(app: Gio.Application, *, copied: bool, saved_path: "Path | None" = None) -> None:
    """Dispara a notificação de "captura concluída" — resumo do que aconteceu com o resultado."""
    if copied and saved_path is not None:
        body = f"Copiada para a área de transferência e salva em {saved_path}"
    elif saved_path is not None:
        body = f"Salva em {saved_path}"
    elif copied:
        body = "Copiada para a área de transferência"
    else:
        return

    notification = Gio.Notification.new("Captura de tela")
    notification.set_body(body)
    notification.set_priority(Gio.NotificationPriority.NORMAL)
    app.send_notification("takeshot-capture", notification)
