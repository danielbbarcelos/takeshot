"""Barra flutuante libadwaita ancorada à seleção: ferramentas, cor, ações."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, Gtk  # noqa: E402

from takeshot.editor.tools import TEXT_PRESETS, ToolKind

TOOL_LABELS: dict[ToolKind, tuple[str, str]] = {
    ToolKind.ARROW: ("↗", "Seta (1)"),
    ToolKind.RECT: ("▭", "Retângulo (2)"),
    ToolKind.ELLIPSE: ("◯", "Elipse (3)"),
    ToolKind.FREEHAND: ("✎", "Traço livre (4)"),
    ToolKind.TEXT: ("T", "Texto (5)"),
    ToolKind.PIXELATE: ("▦", "Pixelizar (6)"),
    ToolKind.BLUR: ("◑", "Desfocar (7)"),
    ToolKind.COUNTER: ("①", "Numeração (8)"),
}


def _css_rgba(color) -> str:
    r, g, b, a = color
    return f"rgba({round(r * 255)}, {round(g * 255)}, {round(b * 255)}, {a:.2f})"


def _install_text_preset_css() -> None:
    """Uma classe por preset, usada no botão do preset e no Gtk.Entry enquanto
    se digita — o texto já aparece com as cores que vão para a imagem."""
    rules = []
    for i, preset in enumerate(TEXT_PRESETS):
        if preset.foreground is None:
            continue
        rules.append(
            f".takeshot-text-preset-{i} {{ color: {_css_rgba(preset.foreground)}; "
            f"background: {_css_rgba(preset.background)}; font-weight: bold; }}"
        )
    provider = Gtk.CssProvider()
    provider.load_from_string("\n".join(rules))
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1,
    )


_text_preset_css_installed = False


class CaptureToolbar(Gtk.Box):
    __gtype_name__ = "TakeshotCaptureToolbar"

    def __init__(self, session) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.session = session
        self.add_css_class("toolbar")
        self.add_css_class("osd")
        self.add_css_class("takeshot-toolbar")
        self.set_margin_top(4)
        self.set_margin_bottom(4)
        self.set_margin_start(6)
        self.set_margin_end(6)

        self._tool_buttons: dict[ToolKind, Gtk.ToggleButton] = {}
        tools_box = Gtk.Box(spacing=2)
        tools_box.add_css_class("linked")
        for kind, (symbol, tooltip) in TOOL_LABELS.items():
            btn = Gtk.ToggleButton(label=symbol)
            btn.set_tooltip_text(tooltip)
            btn.set_active(kind == session.tool_kind)
            btn.connect("toggled", self._on_tool_toggled, kind)
            self._tool_buttons[kind] = btn
            tools_box.append(btn)
        self.append(tools_box)

        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        color_btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = session.tool_style.color
        color_btn.set_rgba(rgba)
        color_btn.set_tooltip_text("Cor")
        color_btn.connect("notify::rgba", self._on_color_changed)
        self.append(color_btn)

        global _text_preset_css_installed
        if not _text_preset_css_installed:
            _install_text_preset_css()
            _text_preset_css_installed = True

        # estilos do texto: só aparecem com a ferramenta T ativa
        self._preset_buttons: list[Gtk.ToggleButton] = []
        self._presets_box = Gtk.Box(spacing=2)
        self._presets_box.add_css_class("linked")
        for i, preset in enumerate(TEXT_PRESETS):
            btn = Gtk.ToggleButton(label="Aa")
            btn.set_tooltip_text(f"Texto: {preset.label}")
            btn.add_css_class("takeshot-text-preset")
            btn.add_css_class(f"takeshot-text-preset-{i}")
            btn.set_active(i == session.text_preset)
            btn.connect("toggled", self._on_preset_toggled, i)
            self._preset_buttons.append(btn)
            self._presets_box.append(btn)
        self._presets_box.set_visible(session.tool_kind is ToolKind.TEXT)
        self.append(self._presets_box)

        width_spin = Gtk.SpinButton.new_with_range(1, 20, 1)
        width_spin.set_value(session.tool_style.line_width)
        width_spin.set_tooltip_text("Espessura do traço / intensidade do pixelizar e desfocar (+/-)")
        width_spin.connect("value-changed", self._on_width_changed)
        self.append(width_spin)

        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        undo_btn = Gtk.Button(label="↶")
        undo_btn.set_tooltip_text("Desfazer (Ctrl+Z)")
        undo_btn.connect("clicked", self._on_undo)
        self.append(undo_btn)

        redo_btn = Gtk.Button(label="↷")
        redo_btn.set_tooltip_text("Refazer (Ctrl+Shift+Z)")
        redo_btn.connect("clicked", self._on_redo)
        self.append(redo_btn)

        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        restart_btn = Gtk.Button(label="Nova área")
        restart_btn.set_tooltip_text("Descarta a área e as anotações; o próximo arrasto define a nova área")
        restart_btn.connect("clicked", lambda _b: session.restart_selection())
        self.append(restart_btn)

        cancel_btn = Gtk.Button(label="Cancelar")
        cancel_btn.set_tooltip_text("Esc")
        cancel_btn.connect("clicked", lambda _b: session._cancel())
        self.append(cancel_btn)

        save_btn = Gtk.Button(label="Salvar e copiar")
        save_btn.set_tooltip_text("Ctrl+S — salva no destino escolhido e copia para a área de transferência")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", lambda _b: session._save_as())
        self.append(save_btn)

        copy_btn = Gtk.Button(label="Copiar")
        copy_btn.set_tooltip_text("Ctrl+C — só copia, não salva em disco")
        copy_btn.add_css_class("suggested-action")
        copy_btn.connect("clicked", lambda _b: session._finish(copy_to_clipboard=True, save_to_disk=False))
        self.append(copy_btn)

    def _on_tool_toggled(self, button: Gtk.ToggleButton, kind: ToolKind) -> None:
        if button.get_active():
            for other_kind, other_btn in self._tool_buttons.items():
                if other_kind is not kind:
                    other_btn.set_active(False)
            self.session.set_tool(kind)
        elif self.session.tool_kind is kind:
            # clicou de novo na ferramenta ativa: volta pro modo "arrastar seleção"
            self.session.set_tool(None)

    def sync_tool(self, kind: "ToolKind | None") -> None:
        """Reflete troca de ferramenta feita fora da toolbar (atalhos 1..8)."""
        for other_kind, btn in self._tool_buttons.items():
            if btn.get_active() != (other_kind is kind):
                btn.set_active(other_kind is kind)
        self._presets_box.set_visible(kind is ToolKind.TEXT)
        self.session._refresh()  # largura da toolbar mudou: reposiciona

    def _on_preset_toggled(self, button: Gtk.ToggleButton, index: int) -> None:
        if button.get_active():
            for i, other in enumerate(self._preset_buttons):
                if i != index:
                    other.set_active(False)
            self.session.set_text_preset(index)
        elif self.session.text_preset == index:
            button.set_active(True)  # sempre há um preset escolhido

    def _on_color_changed(self, button: Gtk.ColorDialogButton, _pspec) -> None:
        rgba = button.get_rgba()
        self.session.set_color((rgba.red, rgba.green, rgba.blue, rgba.alpha))

    def _on_width_changed(self, spin: Gtk.SpinButton) -> None:
        self.session.set_line_width(spin.get_value())

    def _on_undo(self, _button: Gtk.Button) -> None:
        self.session.document.undo()
        self.session._refresh()

    def _on_redo(self, _button: Gtk.Button) -> None:
        self.session.document.redo()
        self.session._refresh()
