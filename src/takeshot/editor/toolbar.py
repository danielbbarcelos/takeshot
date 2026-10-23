"""Barra flutuante libadwaita ancorada à seleção.

Dois modos, trocados pela sessão: o menu principal (ferramentas, cor, ações)
e o menu de texto, que ocupa a barra sozinho enquanto um texto está sendo
criado ou editado (tamanho, cor do texto, fundo, confirmar/cancelar/descartar).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, Gtk  # noqa: E402

from takeshot.editor.textedit import FONT_SIZE_STEP, TEXT_BACKGROUNDS, TEXT_COLORS, TextStyle
from takeshot.editor.tools import ToolKind

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


def _install_swatch_css() -> None:
    rules = [f".takeshot-swatch-fg-{i} {{ background: {_css_rgba(c)}; }}" for i, (_n, c) in enumerate(TEXT_COLORS)]
    rules += [
        f".takeshot-swatch-bg-{i} {{ background: {_css_rgba(c)}; }}"
        for i, (_n, c) in enumerate(TEXT_BACKGROUNDS) if c is not None
    ]
    provider = Gtk.CssProvider()
    provider.load_from_string("\n".join(rules))
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1,
    )


_swatch_css_installed = False


def _no_focus(widget: Gtk.Widget) -> Gtk.Widget:
    """Botões do menu de texto não roubam o foco do campo onde se digita."""
    widget.set_focus_on_click(False)
    widget.set_can_focus(False)
    return widget


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

        global _swatch_css_installed
        if not _swatch_css_installed:
            _install_swatch_css()
            _swatch_css_installed = True

        self._main = self._build_main_menu()
        self._text_menu = self._build_text_menu()
        self._text_menu.set_visible(False)
        self.append(self._main)
        self.append(self._text_menu)
        self._syncing = False

    # --- menu principal ---

    def _build_main_menu(self) -> Gtk.Box:
        session = self.session
        box = Gtk.Box(spacing=4)

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
        box.append(tools_box)

        box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        color_btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = session.tool_style.color
        color_btn.set_rgba(rgba)
        color_btn.set_tooltip_text("Cor")
        color_btn.connect("notify::rgba", self._on_color_changed)
        box.append(color_btn)

        width_spin = Gtk.SpinButton.new_with_range(1, 20, 1)
        width_spin.set_value(session.tool_style.line_width)
        width_spin.set_tooltip_text("Espessura do traço / intensidade do pixelizar e desfocar (+/-)")
        width_spin.connect("value-changed", self._on_width_changed)
        box.append(width_spin)

        box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        undo_btn = Gtk.Button(label="↶")
        undo_btn.set_tooltip_text("Desfazer (Ctrl+Z)")
        undo_btn.connect("clicked", self._on_undo)
        box.append(undo_btn)

        redo_btn = Gtk.Button(label="↷")
        redo_btn.set_tooltip_text("Refazer (Ctrl+Shift+Z)")
        redo_btn.connect("clicked", self._on_redo)
        box.append(redo_btn)

        box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        restart_btn = Gtk.Button(label="Nova área")
        restart_btn.set_tooltip_text("Descarta a área e as anotações; o próximo arrasto define a nova área")
        restart_btn.connect("clicked", lambda _b: session.restart_selection())
        box.append(restart_btn)

        cancel_btn = Gtk.Button(label="Cancelar")
        cancel_btn.set_tooltip_text("Esc")
        cancel_btn.connect("clicked", lambda _b: session._cancel())
        box.append(cancel_btn)

        save_btn = Gtk.Button(label="Salvar e copiar")
        save_btn.set_tooltip_text("Ctrl+S — salva no destino escolhido e copia para a área de transferência")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", lambda _b: session._save_as())
        box.append(save_btn)

        copy_btn = Gtk.Button(label="Copiar")
        copy_btn.set_tooltip_text("Ctrl+C — só copia, não salva em disco")
        copy_btn.add_css_class("suggested-action")
        copy_btn.connect("clicked", lambda _b: session._finish(copy_to_clipboard=True, save_to_disk=False))
        box.append(copy_btn)
        return box

    # --- menu de texto ---

    def _build_text_menu(self) -> Gtk.Box:
        session = self.session
        box = Gtk.Box(spacing=6)

        size_box = Gtk.Box(spacing=2)
        size_box.add_css_class("linked")
        smaller = _no_focus(Gtk.Button(label="A−"))
        smaller.set_tooltip_text("Diminuir fonte")
        smaller.connect("clicked", lambda _b: self._change_font_size(-FONT_SIZE_STEP))
        self._size_label = Gtk.Label()
        self._size_label.set_width_chars(3)
        self._size_label.add_css_class("takeshot-text-size")
        bigger = _no_focus(Gtk.Button(label="A+"))
        bigger.set_tooltip_text("Aumentar fonte")
        bigger.connect("clicked", lambda _b: self._change_font_size(FONT_SIZE_STEP))
        size_box.append(smaller)
        size_box.append(self._size_label)
        size_box.append(bigger)
        box.append(size_box)

        box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        box.append(Gtk.Label(label="Texto"))
        self._fg_buttons = self._swatch_row(box, TEXT_COLORS, "fg", self._on_fg_toggled)

        box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        box.append(Gtk.Label(label="Fundo"))
        self._bg_buttons = self._swatch_row(box, TEXT_BACKGROUNDS, "bg", self._on_bg_toggled)

        box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        discard_btn = _no_focus(Gtk.Button(label="Descartar"))
        discard_btn.set_tooltip_text("Esc — desfaz as alterações feitas desde o clique (estilo, posição, conteúdo)")
        discard_btn.connect("clicked", lambda _b: session.text_discard())
        box.append(discard_btn)

        cancel_btn = _no_focus(Gtk.Button(label="Cancelar"))
        cancel_btn.set_tooltip_text("Exclui este texto")
        cancel_btn.add_css_class("destructive-action")
        cancel_btn.connect("clicked", lambda _b: session.text_cancel())
        box.append(cancel_btn)

        confirm_btn = _no_focus(Gtk.Button(label="Confirmar"))
        confirm_btn.set_tooltip_text("Enter — aplica o texto (Shift+Enter quebra linha)")
        confirm_btn.add_css_class("suggested-action")
        confirm_btn.connect("clicked", lambda _b: session.text_confirm())
        box.append(confirm_btn)
        return box

    def _swatch_row(self, parent: Gtk.Box, palette, kind: str, on_toggled) -> list[Gtk.ToggleButton]:
        row = Gtk.Box(spacing=2)
        buttons = []
        for i, (name, color) in enumerate(palette):
            btn = _no_focus(Gtk.ToggleButton())
            btn.add_css_class("takeshot-swatch-button")
            btn.set_tooltip_text(name)
            if color is None:
                btn.set_label("∅")
            else:
                chip = Gtk.Box()
                chip.add_css_class("takeshot-swatch")
                chip.add_css_class(f"takeshot-swatch-{kind}-{i}")
                btn.set_child(chip)
            btn.connect("toggled", on_toggled, i)
            buttons.append(btn)
            row.append(btn)
        parent.append(row)
        return buttons

    def show_text_menu(self, style: TextStyle) -> None:
        self._sync_text_style(style)
        self._main.set_visible(False)
        self._text_menu.set_visible(True)

    def show_main_menu(self) -> None:
        self._text_menu.set_visible(False)
        self._main.set_visible(True)

    def _sync_text_style(self, style: TextStyle) -> None:
        """Marca o tamanho e as amostras do estilo atual (nenhuma, se a cor não é da paleta)."""
        self._syncing = True
        try:
            self._size_label.set_label(f"{style.font_size:g}")
            for btn, (_n, c) in zip(self._fg_buttons, TEXT_COLORS):
                btn.set_active(c == style.color)
            for btn, (_n, c) in zip(self._bg_buttons, TEXT_BACKGROUNDS):
                btn.set_active(c == style.background)
        finally:
            self._syncing = False

    def _apply_text_style(self, style: TextStyle) -> None:
        self._sync_text_style(style)
        self.session.text_set_style(style)
        self.session._refresh()  # largura da toolbar pode mudar

    def _current_text_style(self) -> "TextStyle | None":
        edit = self.session.text_edit
        return edit.style if edit is not None else None

    def _change_font_size(self, delta: float) -> None:
        style = self._current_text_style()
        if style is not None:
            self._apply_text_style(style.with_font_size(style.font_size + delta))

    def _on_fg_toggled(self, button: Gtk.ToggleButton, index: int) -> None:
        self._on_swatch_toggled(button, lambda s: TextStyle(s.font_size, TEXT_COLORS[index][1], s.background))

    def _on_bg_toggled(self, button: Gtk.ToggleButton, index: int) -> None:
        self._on_swatch_toggled(button, lambda s: TextStyle(s.font_size, s.color, TEXT_BACKGROUNDS[index][1]))

    def _on_swatch_toggled(self, button: Gtk.ToggleButton, change) -> None:
        if self._syncing:
            return
        style = self._current_text_style()
        if style is None:
            return
        if button.get_active():
            self._apply_text_style(change(style))
        else:
            self._sync_text_style(style)  # clicar na amostra ativa mantém ela marcada

    # --- ferramentas / estilo de traço ---

    def sync_tool(self, kind: "ToolKind | None") -> None:
        """Reflete troca de ferramenta feita fora da toolbar (atalhos 1..8)."""
        for other_kind, btn in self._tool_buttons.items():
            if btn.get_active() != (other_kind is kind):
                btn.set_active(other_kind is kind)

    def _on_tool_toggled(self, button: Gtk.ToggleButton, kind: ToolKind) -> None:
        if button.get_active():
            for other_kind, other_btn in self._tool_buttons.items():
                if other_kind is not kind:
                    other_btn.set_active(False)
            self.session.set_tool(kind)
        elif self.session.tool_kind is kind:
            # clicou de novo na ferramenta ativa: volta pro modo "arrastar seleção"
            self.session.set_tool(None)

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
