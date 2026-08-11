"""Janela de preferências (Adw.PreferencesWindow)."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402


class PreferencesWindow(Adw.PreferencesWindow):
    def __init__(self, app) -> None:
        super().__init__(application=app, title="Preferências do takeshot")
        self.app = app
        self.config = app.config

        page = Adw.PreferencesPage()
        self.add(page)

        quick_group = Adw.PreferencesGroup(title="Captura rápida")
        page.add(quick_group)
        quick_row = Adw.ActionRow(title="Nova captura", subtitle="Também disponível pelo atalho de teclado")

        screen_btn = Gtk.Button(label="Tela inteira")
        screen_btn.set_valign(Gtk.Align.CENTER)
        screen_btn.connect("clicked", lambda _b: self._start_quick_capture("screen"))
        quick_row.add_suffix(screen_btn)

        region_btn = Gtk.Button(label="Capturar região")
        region_btn.add_css_class("suggested-action")
        region_btn.set_valign(Gtk.Align.CENTER)
        region_btn.connect("clicked", lambda _b: self._start_quick_capture("region"))
        quick_row.add_suffix(region_btn)

        quick_group.add(quick_row)

        capture_group = Adw.PreferencesGroup(title="Captura")
        page.add(capture_group)

        copy_row = Adw.SwitchRow(title="Copiar para a área de transferência", subtitle="Ao confirmar uma captura")
        copy_row.set_active(self.config.copy_on_capture)
        copy_row.connect("notify::active", self._on_switch, "copy_on_capture")
        capture_group.add(copy_row)

        edit_row = Adw.SwitchRow(title="Abrir o editor de anotações", subtitle="Ao capturar a tela inteira (--screen)")
        edit_row.set_active(self.config.edit_on_capture)
        edit_row.connect("notify::active", self._on_switch, "edit_on_capture")
        capture_group.add(edit_row)

        interactive_row = Adw.SwitchRow(
            title="Portal interativo",
            subtitle="Fallback para compositores que negam captura não-interativa",
        )
        interactive_row.set_active(self.config.interactive_portal)
        interactive_row.connect("notify::active", self._on_switch, "interactive_portal")
        capture_group.add(interactive_row)

        appearance_group = Adw.PreferencesGroup(title="Aparência")
        page.add(appearance_group)

        dim_row = Adw.SpinRow.new_with_range(0.0, 0.9, 0.05)
        dim_row.set_title("Escurecimento fora da seleção")
        dim_row.set_value(self.config.dim_opacity)
        dim_row.connect("notify::value", self._on_spin_float, "dim_opacity")
        appearance_group.add(dim_row)

        counter_row = Adw.SpinRow.new_with_range(1, 999, 1)
        counter_row.set_title("Número inicial da numeração sequencial")
        counter_row.set_value(self.config.counter_start)
        counter_row.connect("notify::value", self._on_spin_int, "counter_start")
        appearance_group.add(counter_row)

        save_group = Adw.PreferencesGroup(title="Salvar")
        page.add(save_group)
        save_dir_row = Adw.ActionRow(title="Pasta de destino", subtitle=GLib.markup_escape_text(str(self.config.save_dir_path())))
        save_group.add(save_dir_row)

        shortcut_group = Adw.PreferencesGroup(title="Atalho de teclado global")
        page.add(shortcut_group)
        self._shortcut_row = Adw.ActionRow(title="Status")
        reinstall_btn = Gtk.Button(label="Reinstalar")
        reinstall_btn.set_valign(Gtk.Align.CENTER)
        reinstall_btn.add_css_class("flat")
        reinstall_btn.connect("clicked", self._on_reinstall_shortcut)
        self._shortcut_row.add_suffix(reinstall_btn)
        shortcut_group.add(self._shortcut_row)
        self._refresh_shortcut_status()

    def _start_quick_capture(self, mode: str) -> None:
        """Fecha a janela e SÓ DEPOIS dispara a captura — `close()` não é
        síncrono no Wayland (o compositor precisa processar o unmap antes do
        próximo frame); disparar o portal logo em seguida arrisca pegar esta
        janela ainda visível na captura."""
        app = self.app

        def begin_capture() -> bool:
            from takeshot.capture import controller

            app.hold()

            def on_finished() -> None:
                app.release()

            controller.start_capture(
                app, mode=mode, portal_interactive=False,
                copy=False, save_path=None, no_edit=False, on_finished=on_finished,
            )
            return False

        def on_unmap(_widget) -> None:
            # unmap do GTK só garante que ESTE processo marcou a janela como
            # escondida; o compositor ainda precisa processar isso e repintar
            # a tela sem ela — um idle_add só não é suficiente (confirmado:
            # sem essa espera, a janela aparecia na própria captura).
            GLib.timeout_add(200, begin_capture)

        self.connect("unmap", on_unmap)
        self.close()

    def _refresh_shortcut_status(self) -> None:
        from takeshot import shortcuts

        st = shortcuts.status()
        if st["installed"]:
            note = f" (conflito com {st['binding_conflict']})" if st["binding_conflict"] else ""
            subtitle = f"binding: {st['binding']}{note}"
        else:
            subtitle = "não instalado"
        self._shortcut_row.set_subtitle(GLib.markup_escape_text(subtitle))

    def _on_reinstall_shortcut(self, _button: Gtk.Button) -> None:
        from takeshot import shortcuts

        shortcuts.install()
        self._refresh_shortcut_status()

    def _on_switch(self, row: "Adw.SwitchRow", _pspec, key: str) -> None:
        setattr(self.config, key, row.get_active())
        self.config.save()

    def _on_spin_float(self, row: "Adw.SpinRow", _pspec, key: str) -> None:
        setattr(self.config, key, row.get_value())
        self.config.save()

    def _on_spin_int(self, row: "Adw.SpinRow", _pspec, key: str) -> None:
        setattr(self.config, key, int(row.get_value()))
        self.config.save()
