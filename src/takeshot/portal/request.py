"""Helper genérico para o padrão org.freedesktop.portal.Request.

Assina o sinal `Response` ANTES de fazer a chamada do método — senão há uma
race em que o portal pode responder antes de terminarmos de nos inscrever
(request rápida o bastante para isso acontecer na prática).
"""

from __future__ import annotations

import itertools
import os
from typing import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

_counter = itertools.count()

PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"

OnResponse = Callable[[int, dict], None]
BuildArgs = Callable[[str], GLib.Variant]


def make_request(
    bus: Gio.DBusConnection,
    method_iface: str,
    method_name: str,
    build_args: BuildArgs,
    on_response: OnResponse,
    reply_signature: GLib.VariantType = GLib.VariantType.new("(o)"),
) -> None:
    """Executa uma chamada de portal que segue o padrão Request assíncrono.

    `build_args(token)` deve devolver o GLib.Variant de argumentos da
    chamada; suas `options` precisam incluir `handle_token` = token.
    `on_response(code, results)` é chamado quando o sinal Response chega
    (0=sucesso, 1=cancelado, 2=erro) ou, em caso de falha na própria
    chamada D-Bus, com code=-1.
    """
    token = f"takeshot_{os.getpid()}_{next(_counter)}"
    sender = bus.get_unique_name()[1:].replace(".", "_")
    request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

    state = {"subscription_id": None}

    def _unsubscribe() -> None:
        if state["subscription_id"] is not None:
            bus.signal_unsubscribe(state["subscription_id"])
            state["subscription_id"] = None

    def _on_signal(_connection, _sender_name, _object_path, _interface_name, _signal_name, parameters) -> None:
        _unsubscribe()
        code, results = parameters.unpack()
        on_response(code, results)

    state["subscription_id"] = bus.signal_subscribe(
        PORTAL_BUS_NAME, "org.freedesktop.portal.Request", "Response",
        request_path, None, Gio.DBusSignalFlags.NONE, _on_signal,
    )

    def _on_call_done(connection: Gio.DBusConnection, result: Gio.AsyncResult, _user_data=None) -> None:
        try:
            connection.call_finish(result)
        except GLib.Error as exc:
            _unsubscribe()
            on_response(-1, {"error": str(exc)})

    bus.call(
        PORTAL_BUS_NAME, PORTAL_OBJECT_PATH, method_iface, method_name,
        build_args(token), reply_signature, Gio.DBusCallFlags.NONE, -1, None,
        _on_call_done,
    )
