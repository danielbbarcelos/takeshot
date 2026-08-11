"""TakeshotApplication: a Adw.Application de verdade, com janelas e captura.

Só é importado quando este processo pode vir a ser o dono do bus name
(nenhum dono existe ainda, ou `--standalone`/`--replace`) — carregar `Adw`
sozinho custa ~85ms de introspecção GObject, então o caminho quente
(comando encaminhado a um daemon já residente) nunca importa este módulo;
ver `_forward_lightweight` em app.py.
"""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk  # noqa: E402

from takeshot import cli  # noqa: E402
from takeshot import config as config_mod  # noqa: E402
from takeshot.paths import APP_ID  # noqa: E402

log = logging.getLogger("takeshot.app")


class TakeshotApplication(Adw.Application):
    def __init__(self, standalone: bool = False) -> None:
        flags = Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        if standalone:
            flags |= Gio.ApplicationFlags.NON_UNIQUE
        super().__init__(application_id=APP_ID, flags=flags)
        self.config = config_mod.Config.load()
        self.overlay_session = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._load_css()

    def _load_css(self) -> None:
        from pathlib import Path

        from gi.repository import Gdk

        css_path = Path(__file__).parent / "ui" / "style.css"
        if not css_path.exists():
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(css_path))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        argv = command_line.get_arguments()[1:]
        try:
            args = cli.parse_args(argv)
        except SystemExit as exc:
            code = exc.code
            return code if isinstance(code, int) else 0

        self._dispatch(args)
        return 0

    def _dispatch(self, args) -> None:
        if args.command == "preferences":
            self._open_preferences()
            return
        if args.daemon:
            log.info("residente iniciado (--daemon)")
            self.hold()
            return

        self._start_capture(args)

    def _open_preferences(self) -> None:
        from takeshot.ui.preferences import PreferencesWindow

        window = PreferencesWindow(self)
        self.hold()

        def on_close(_window) -> bool:
            self.release()
            return False

        window.connect("close-request", on_close)
        window.present()

    def _start_capture(self, args) -> None:
        from takeshot.capture import controller

        mode = "screen" if getattr(args, "screen", False) else "region"
        portal_interactive = bool(getattr(args, "portal_interactive", False))
        copy = getattr(args, "copy", False)
        save_path = getattr(args, "save", None)
        no_edit = getattr(args, "no_edit", False)

        self.hold()

        def on_finished() -> None:
            self.release()

        controller.start_capture(
            self,
            mode=mode,
            portal_interactive=portal_interactive,
            copy=copy,
            save_path=save_path,
            no_edit=no_edit,
            on_finished=on_finished,
        )

    def do_activate(self) -> None:
        Adw.Application.do_activate(self)
