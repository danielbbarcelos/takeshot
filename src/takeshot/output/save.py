"""Salvar a captura final em disco, direto ou via diálogo salvar-como."""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Callable

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from takeshot import paths

log = logging.getLogger("takeshot.output.save")

FILENAME_TEMPLATE = "takeshot_%Y-%m-%d_%H-%M-%S.png"


def default_path(now: dt.datetime | None = None, directory: Path | None = None) -> Path:
    now = now or dt.datetime.now()
    directory = directory or paths.pictures_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / now.strftime(FILENAME_TEMPLATE)


def save_surface(surface: cairo.ImageSurface, dest: "str | Path | None" = None) -> Path:
    """Salva `surface` como PNG. `dest` pode ser um diretório, um arquivo, ou None (padrão)."""
    if dest:
        path = Path(dest).expanduser()
        if path.is_dir():
            path = default_path(directory=path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
    else:
        path = default_path()
    surface.write_to_png(str(path))
    return path


def save_as_dialog(
    parent: Gtk.Window,
    surface: cairo.ImageSurface,
    initial_dir: "Path | None",
    on_saved: Callable[["Path | None"], None],
) -> None:
    """Abre o diálogo nativo "salvar como" e grava `surface` como PNG no destino escolhido."""
    dialog = Gtk.FileDialog()
    dialog.set_initial_name(default_path().name)
    directory = initial_dir or paths.pictures_dir()
    directory.mkdir(parents=True, exist_ok=True)
    dialog.set_initial_folder(Gio.File.new_for_path(str(directory)))

    png_filter = Gtk.FileFilter()
    png_filter.set_name("PNG")
    png_filter.add_pattern("*.png")
    filters = Gio.ListStore.new(Gtk.FileFilter)
    filters.append(png_filter)
    dialog.set_filters(filters)

    def on_response(dlg: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            gfile = dlg.save_finish(result)
        except GLib.Error as exc:
            if exc.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                log.info("salvar-como cancelado pelo usuário")
            else:
                log.warning("falha no diálogo salvar-como: %s", exc)
            on_saved(None)
            return
        if gfile is None:
            on_saved(None)
            return
        dest = Path(gfile.get_path())
        surface.write_to_png(str(dest))
        on_saved(dest)

    dialog.save(parent, None, on_response)
