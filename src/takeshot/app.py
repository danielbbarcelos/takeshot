"""Ponto de entrada da CLI — decide o caminho mais barato antes de importar Gtk/Adw.

`import gi.repository.Adw` sozinho custa ~85ms de introspecção GObject
(medido nesta máquina). Pago em toda invocação, isso é o que fazia o atalho
de teclado parecer "tira o print e só depois abre a ferramenta" — quase todo
esse tempo era o processo cliente carregando Gtk/Adw só para encaminhar o
comando a um daemon que já estava rodando. Por isso: se já existe um dono do
bus name, encaminha com um `Gio.Application` puro (a mesma máquina de
registro/encaminhamento do GApplication, sem nada de Gtk/Adw); só importa
`takeshot.gtkapp` (que traz a `TakeshotApplication` de verdade) quando este
processo pode vir a precisar virar o dono.
"""

from __future__ import annotations

import sys

from takeshot import cli
from takeshot.paths import APP_ID


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else [sys.argv[0], *argv]

    # `doctor` e `shortcut` são diagnósticos locais e nunca podem ser
    # encaminhados a uma instância residente já existente — se fossem, a
    # saída iria para o stdout DAQUELE processo (ex.: /dev/null, se ele foi
    # iniciado por `--daemon` em background), não para este terminal.
    try:
        args = cli.parse_args(argv[1:])
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else 0

    if args.command == "doctor":
        from takeshot import doctor

        return doctor.run()
    if args.command == "shortcut":
        from takeshot import shortcuts

        shortcuts.dispatch(args)
        return 0

    if not args.standalone and not args.replace and _daemon_already_running():
        return _forward_lightweight(argv)

    import logging

    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    from takeshot.gtkapp import TakeshotApplication

    app = TakeshotApplication(standalone=args.standalone)

    if args.replace:
        from takeshot import bus

        bus.replace_owner(APP_ID)

    return app.run(argv)


def _daemon_already_running() -> bool:
    from takeshot import bus

    return bus.get_name_owner(bus.session_bus(), APP_ID) is not None


def _forward_lightweight(argv: list[str]) -> int:
    """Encaminha `argv` a uma instância residente sem tocar em Gtk/Adw.

    `Gio.Application` já implementa 100% da lógica de registro/encaminhamento
    de instância única do GApplication — Gtk.Application/Adw.Application só
    adicionam capacidades de janela, que não importam aqui: o processo
    encaminhador nunca chama seu próprio do_command_line/do_activate quando
    já existe um dono do bus name.
    """
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio

    app = Gio.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
    return app.run(argv)
