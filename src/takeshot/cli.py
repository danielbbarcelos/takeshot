"""Parsing de argv. Sem dependência de gi — testável headless."""

from __future__ import annotations

import argparse

from takeshot import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="takeshot", description="Captura de tela para GNOME/Wayland.")
    parser.add_argument("--version", action="version", version=f"takeshot {__version__}")
    parser.add_argument("--daemon", action="store_true", help="Inicia residente sem capturar (autostart).")
    parser.add_argument("--standalone", action="store_true", help="Roda como instância independente (NON_UNIQUE).")
    parser.add_argument("--replace", action="store_true", help="Substitui a instância atual dona do bus name.")
    parser.add_argument(
        "--portal-interactive", action="store_true",
        help="Usa o portal em modo interativo (fallback para compositores que negam captura não-interativa).",
    )

    sub = parser.add_subparsers(dest="command")

    capture = sub.add_parser("capture", help="Captura tela cheia ou região.")
    mode = capture.add_mutually_exclusive_group()
    mode.add_argument("--region", action="store_true", help="Seleciona uma região (padrão).")
    mode.add_argument("--screen", action="store_true", help="Captura a tela inteira.")
    capture.add_argument("--copy", action="store_true", help="Copia para a área de transferência.")
    capture.add_argument("--save", nargs="?", const="", metavar="PATH", help="Salva em PATH (ou destino padrão).")
    capture.add_argument("--no-edit", action="store_true", help="Pula o editor de anotações (modo headless).")

    shortcut = sub.add_parser("shortcut", help="Gerencia o atalho de teclado global.")
    shortcut.add_argument("action", choices=["install", "remove", "status"])
    shortcut.add_argument("--force", action="store_true", help="Assume o binding mesmo em conflito.")
    shortcut.add_argument("--binding", default=None, help="Binding customizado (padrão: Print).")

    sub.add_parser("doctor", help="Diagnostica o ambiente.")
    sub.add_parser("preferences", help="Abre a janela de preferências.")

    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)
