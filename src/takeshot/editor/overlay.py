"""OverlayWindow (uma por monitor) + OverlaySession (coordenador global).

Estado: SELECTING → SELECTED. Eventos são traduzidos para coordenadas
globais lógicas e delegados à OverlaySession, já que a seleção pode cruzar
monitores (CLAUDE.md §3.6). Dentro de SELECTED, um arrasto começado em cima
de um handle redimensiona a seleção; qualquer outro arrasto desenha com a
ferramenta ativa (tools.py).
"""

from __future__ import annotations

import enum
import logging
import math
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from takeshot.editor.canvas import OverlayCanvas
from takeshot.editor.document import AnnotationDocument
from takeshot.editor.items import RenderContext
from takeshot.editor.items import TextAnnotation
from takeshot.editor.textedit import TextEdit, TextStyle
from takeshot.editor.tools import CLICK_TOOLS, TOOL_KEY_BINDINGS, ToolKind, ToolStyle, make_tool
from takeshot.geom import Point, Rect

log = logging.getLogger("takeshot.editor.overlay")

MIN_SELECTION_SIZE = 2.0
NUDGE_STEP = 1.0
NUDGE_STEP_FAST = 10.0
LINE_WIDTH_STEP = 1.0
LINE_WIDTH_RANGE = (1.0, 20.0)
HANDLE_HIT_RADIUS = 14.0

HANDLE_NAMES = ("nw", "n", "ne", "w", "e", "sw", "s", "se")


def handle_positions(rect: Rect) -> dict[str, Point]:
    r = rect.normalized()
    mx, my = r.x + r.width / 2, r.y + r.height / 2
    return {
        "nw": Point(r.x, r.y), "n": Point(mx, r.y), "ne": Point(r.x2, r.y),
        "w": Point(r.x, my), "e": Point(r.x2, my),
        "sw": Point(r.x, r.y2), "s": Point(mx, r.y2), "se": Point(r.x2, r.y2),
    }


def resized_rect(handle: str, anchor: Rect, point: Point) -> Rect:
    """Recalcula `anchor` movendo só os lados que `handle` controla."""
    x, y, x2, y2 = anchor.x, anchor.y, anchor.x2, anchor.y2
    if "n" in handle:
        y = point.y
    if "s" in handle:
        y2 = point.y
    if "w" in handle:
        x = point.x
    if "e" in handle:
        x2 = point.x
    return Rect.from_points(Point(x, y), Point(x2, y2))


def selection_to_fraction(capture, rect: Rect) -> dict:
    """Converte uma seleção (px de imagem) pra fração da tela lógica — robusto a
    mudanças de resolução entre sessões, ao contrário de guardar px absolutos."""
    lb = capture.logical_bounds
    s = rect.normalized()
    lx, ly = capture.logical_from_image(s.x, s.y)
    lx2, ly2 = capture.logical_from_image(s.x + s.width, s.y + s.height)
    return {
        "x": (lx - lb.x) / lb.width,
        "y": (ly - lb.y) / lb.height,
        "w": (lx2 - lx) / lb.width,
        "h": (ly2 - ly) / lb.height,
    }


def fraction_to_selection(capture, fraction: dict) -> "Rect | None":
    lb = capture.logical_bounds
    if lb.width <= 0 or lb.height <= 0:
        return None
    try:
        lx = lb.x + float(fraction["x"]) * lb.width
        ly = lb.y + float(fraction["y"]) * lb.height
        lw = float(fraction["w"]) * lb.width
        lh = float(fraction["h"]) * lb.height
    except (KeyError, TypeError, ValueError):
        return None
    ix, iy = capture.image_from_logical(lx, ly)
    ix2, iy2 = capture.image_from_logical(lx + lw, ly + lh)
    rect = Rect.from_points(Point(ix, iy), Point(ix2, iy2))
    if rect.width < MIN_SELECTION_SIZE or rect.height < MIN_SELECTION_SIZE:
        return None
    return rect


def _text_style_from_config(config) -> TextStyle:
    try:
        background = config.text_background
        return TextStyle(
            color=tuple(config.text_color),
            background=tuple(background) if background else None,
        ).with_font_size(float(config.text_font_size))
    except (TypeError, ValueError):
        return TextStyle()


class SelectionState(enum.Enum):
    SELECTING = "selecting"
    SELECTED = "selected"


class OverlayWindow(Gtk.Window):
    def __init__(self, session: "OverlaySession", monitor: Gdk.Monitor, monitor_geometry: Rect):
        super().__init__(application=session.app)
        self.session = session
        self.monitor = monitor
        self.monitor_geometry = monitor_geometry

        self.set_decorated(False)
        self.set_resizable(False)
        self.add_css_class("takeshot-overlay")

        self.canvas = OverlayCanvas(
            session.capture, session.document, monitor_geometry, session.app.config.dim_opacity, session=session,
        )
        self.canvas.set_cursor(Gdk.Cursor.new_from_name("crosshair"))

        self.overlay_root = Gtk.Overlay()
        self.overlay_root.set_child(self.canvas)
        self.overlay_root.connect("get-child-position", self._on_get_child_position)
        self.set_child(self.overlay_root)

        self._floating: dict[Gtk.Widget, Callable[[], "tuple[int, int, int, int] | None"]] = {}

        self._drag_start_local: Point | None = None

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.canvas.add_controller(drag)

        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("pressed", self._on_click_pressed)
        self.canvas.add_controller(click)

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key)

    def present_on_monitor(self) -> None:
        self.fullscreen_on_monitor(self.monitor)
        self.present()

    def contains_global_point(self, p: Point) -> bool:
        mg = self.monitor_geometry
        return mg.x <= p.x <= mg.x2 and mg.y <= p.y <= mg.y2

    def local_from_global(self, p: Point) -> Point:
        return Point(p.x - self.monitor_geometry.x, p.y - self.monitor_geometry.y)

    # --- widgets flutuantes (entrada de texto, toolbar) ---

    def add_floating(self, widget: Gtk.Widget, position_fn: Callable[[], "tuple[int, int, int, int] | None"]) -> None:
        self._floating[widget] = position_fn
        self.overlay_root.add_overlay(widget)

    def remove_floating(self, widget: Gtk.Widget) -> None:
        if widget in self._floating:
            del self._floating[widget]
            self.overlay_root.remove_overlay(widget)

    def reposition_floating(self) -> None:
        for widget in list(self._floating):
            widget.queue_allocate()
        self.overlay_root.queue_allocate()

    def _on_get_child_position(self, _overlay, widget, allocation) -> bool:
        position_fn = self._floating.get(widget)
        if position_fn is None:
            return False
        pos = position_fn()
        if pos is None:
            return False
        allocation.x, allocation.y, allocation.width, allocation.height = pos
        return True

    def _to_global(self, x: float, y: float) -> Point:
        return Point(x + self.monitor_geometry.x, y + self.monitor_geometry.y)

    def _on_drag_begin(self, _gesture, start_x, start_y) -> None:
        self._drag_start_local = Point(start_x, start_y)
        self.session.on_drag_begin(self._to_global(start_x, start_y))

    def _on_drag_update(self, _gesture, offset_x, offset_y) -> None:
        if self._drag_start_local is None:
            return
        p = self._to_global(self._drag_start_local.x + offset_x, self._drag_start_local.y + offset_y)
        self.session.on_drag_update(p)

    def _on_drag_end(self, _gesture, offset_x, offset_y) -> None:
        if self._drag_start_local is None:
            return
        p = self._to_global(self._drag_start_local.x + offset_x, self._drag_start_local.y + offset_y)
        self._drag_start_local = None
        self.session.on_drag_end(p)

    def _on_click_pressed(self, _gesture, n_press, _x, _y) -> None:
        if n_press == 2:
            self.session.on_confirm()

    def _on_key_pressed(self, _controller, keyval, _keycode, state) -> bool:
        return self.session.on_key(keyval, state)


class OverlaySession:
    def __init__(
        self, app, capture, *,
        initial_selection: "str | None",
        copy: bool, save_path: "str | None", no_edit: bool = False,
        on_finished: Callable[[], None],
    ) -> None:
        self.app = app
        self.capture = capture
        self.copy = copy
        self.save_path = save_path
        self.no_edit = no_edit
        self.on_finished = on_finished

        self.document = AnnotationDocument(counter_start=app.config.counter_start)
        self.state = SelectionState.SELECTING
        self._drag_anchor: Point | None = None
        self.windows: list[OverlayWindow] = []

        self.tool_style = ToolStyle(color=tuple(app.config.tool_color), line_width=float(app.config.tool_line_width))
        self.tool_kind: "ToolKind | None" = None  # nenhuma ferramenta ativa por padrão
        self.text_style = _text_style_from_config(app.config)
        self.tool = None
        self._active_window: "OverlayWindow | None" = None
        self.text_edit: "TextEdit | None" = None
        self._text_box = None  # textbox.FloatingTextBox enquanto text_edit existe
        self._text_drag_anchor: "tuple[Point, Point] | None" = None  # (ponto do clique, origem do texto)
        self.toolbar = None
        self._toolbar_window: "OverlayWindow | None" = None
        self._resize_handle: "str | None" = None
        self._resize_anchor: "Rect | None" = None
        self._move_anchor_point: "Point | None" = None
        self._move_anchor_rect: "Rect | None" = None

        display = Gdk.Display.get_default()
        monitors = display.get_monitors()
        for i in range(monitors.get_n_items()):
            monitor: Gdk.Monitor = monitors.get_item(i)
            geo = monitor.get_geometry()
            self.windows.append(OverlayWindow(self, monitor, Rect(geo.x, geo.y, geo.width, geo.height)))

        if initial_selection == "full":
            self.document.selection_rect = Rect(0, 0, capture.surface.get_width(), capture.surface.get_height())
            self.state = SelectionState.SELECTED
        elif initial_selection is None:
            cached = self._cached_selection_rect()
            if cached is not None:
                self.document.selection_rect = cached
                self.state = SelectionState.SELECTED

    def present(self) -> None:
        for w in self.windows:
            w.present_on_monitor()
        if self.windows:
            self.windows[0].canvas.grab_focus()
        if self.state == SelectionState.SELECTED and not self.no_edit:
            self._ensure_toolbar()

    def present_existing(self) -> None:
        for w in self.windows:
            w.present()

    def _refresh(self) -> None:
        for w in self.windows:
            w.canvas.queue_draw()
        if self.toolbar is not None:
            self._migrate_toolbar_if_needed()
            for w in self.windows:
                w.reposition_floating()

    def _migrate_toolbar_if_needed(self) -> None:
        """Se a seleção foi movida/redimensionada pra outro monitor, a toolbar
        precisa trocar de janela — ela é filha do Gtk.Overlay de uma janela
        específica, não flutua sozinha entre telas."""
        if self.toolbar is None or self.document.selection_rect is None or not self.windows:
            return
        sel = self.document.selection_rect.normalized()
        cx, cy = self.capture.logical_from_image(sel.x + sel.width / 2, sel.y + sel.height / 2)
        target = self._window_at(Point(cx, cy)) or self.windows[0]
        if target is self._toolbar_window:
            return
        if self._toolbar_window is not None:
            self._toolbar_window.remove_floating(self.toolbar)
        self._toolbar_window = target
        target.add_floating(self.toolbar, self._toolbar_position)

    def draw_tool_preview(self, cr, ctx: RenderContext) -> None:
        if self.state == SelectionState.SELECTED and self.tool is not None and self.tool.is_active:
            self.tool.draw_preview(cr, ctx)

    @property
    def is_selected(self) -> bool:
        return self.state == SelectionState.SELECTED

    def _hit_test_handle(self, image_point: Point) -> "str | None":
        if self.document.selection_rect is None:
            return None
        for name, hp in handle_positions(self.document.selection_rect).items():
            if math.hypot(image_point.x - hp.x, image_point.y - hp.y) <= HANDLE_HIT_RADIUS:
                return name
        return None

    # --- seleção / ferramentas ---

    def on_drag_begin(self, global_point: Point) -> None:
        if self.state == SelectionState.SELECTING:
            self._drag_anchor = global_point
            self.document.selection_rect = self._to_image_rect(global_point, global_point)
            self._refresh()
            return

        window = self._window_at(global_point)
        self._active_window = window
        image_point = Point(*self.capture.image_from_logical(global_point.x, global_point.y))

        if self.text_edit is not None:
            # clicar fora do campo confirma o texto em edição e segue com o clique
            self.text_confirm()

        if self.tool_kind in (None, ToolKind.TEXT):
            text_item = self._text_item_at(image_point)
            if text_item is not None:
                # clicar num texto abre ele pra edição; arrastar já move
                self._begin_text_edit(TextEdit.of(text_item), window)
                self._text_drag_anchor = (image_point, text_item.origin)
                return

        handle = self._hit_test_handle(image_point)
        if handle is not None:
            self._resize_handle = handle
            self._resize_anchor = self.document.selection_rect.normalized()
            return

        sel = self.document.selection_rect
        if self.tool_kind is None and sel is not None and sel.normalized().contains(image_point):
            # sem ferramenta ativa e clicou dentro da seleção: arrasta a seleção inteira
            self._move_anchor_point = image_point
            self._move_anchor_rect = sel.normalized()
            return

        if self.tool_kind is None:
            # sem ferramenta ativa e fora da seleção: nada a fazer
            return

        if self.tool_kind is ToolKind.TEXT:
            self._begin_text_edit(TextEdit.new(image_point, self.text_style), window)
            return

        self.tool.on_press(image_point)
        if self.tool_kind in CLICK_TOOLS:
            # ferramentas de clique único agem no press; drag-end apenas confirma
            return
        self._refresh()

    def on_drag_update(self, global_point: Point) -> None:
        if self.state == SelectionState.SELECTING:
            if self._drag_anchor is None:
                return
            self.document.selection_rect = self._to_image_rect(self._drag_anchor, global_point)
            self._refresh()
            return

        image_point = Point(*self.capture.image_from_logical(global_point.x, global_point.y))

        if self._text_drag_anchor is not None and self.text_edit is not None:
            start, origin = self._text_drag_anchor
            self.text_edit.origin = origin.translated(image_point.x - start.x, image_point.y - start.y)
            self._text_box.reposition()
            return

        if self._resize_handle is not None:
            self.document.selection_rect = resized_rect(self._resize_handle, self._resize_anchor, image_point)
            self._refresh()
            return

        if self._move_anchor_point is not None:
            dx = image_point.x - self._move_anchor_point.x
            dy = image_point.y - self._move_anchor_point.y
            self.document.selection_rect = self._move_anchor_rect.translated(dx, dy)
            self._refresh()
            return

        if self.tool_kind is None or self.tool_kind is ToolKind.TEXT or self.tool_kind in CLICK_TOOLS:
            return
        if self.tool is None or not self.tool.is_active:
            return
        self.tool.on_motion(image_point)
        self._refresh()

    def on_drag_end(self, global_point: Point) -> None:
        if self.state == SelectionState.SELECTING:
            if self._drag_anchor is None:
                return
            rect = self._to_image_rect(self._drag_anchor, global_point)
            self._drag_anchor = None
            self.document.selection_rect = rect if (rect.width >= MIN_SELECTION_SIZE and rect.height >= MIN_SELECTION_SIZE) else None
            if self.document.selection_rect is not None:
                self.state = SelectionState.SELECTED
                if not self.no_edit:
                    self._ensure_toolbar()
            self._refresh()
            return

        image_point = Point(*self.capture.image_from_logical(global_point.x, global_point.y))

        if self._text_drag_anchor is not None:
            self._text_drag_anchor = None
            if self._text_box is not None:
                self._text_box.focus()
            return

        if self._resize_handle is not None:
            rect = resized_rect(self._resize_handle, self._resize_anchor, image_point)
            self._resize_handle = None
            self._resize_anchor = None
            if rect.width >= MIN_SELECTION_SIZE and rect.height >= MIN_SELECTION_SIZE:
                self.document.selection_rect = rect
            self._refresh()
            return

        if self._move_anchor_point is not None:
            dx = image_point.x - self._move_anchor_point.x
            dy = image_point.y - self._move_anchor_point.y
            self.document.selection_rect = self._move_anchor_rect.translated(dx, dy)
            self._move_anchor_point = None
            self._move_anchor_rect = None
            self._refresh()
            return

        if self.tool_kind is None or self.tool_kind is ToolKind.TEXT:
            return
        if self.tool is None or not self.tool.is_active:
            return
        item = self.tool.on_release(image_point)
        if item is not None:
            self.document.add(item)
        self._refresh()

    def _window_at(self, global_point: Point) -> "OverlayWindow | None":
        for w in self.windows:
            if w.contains_global_point(global_point):
                return w
        return self.windows[0] if self.windows else None

    def _to_image_rect(self, a_global: Point, b_global: Point) -> Rect:
        ax, ay = self.capture.image_from_logical(a_global.x, a_global.y)
        bx, by = self.capture.image_from_logical(b_global.x, b_global.y)
        return Rect.from_points(Point(ax, ay), Point(bx, by))

    # --- lembrar a última área selecionada entre capturas ---

    def _cached_selection_rect(self) -> "Rect | None":
        cached = self.app.config.last_selection
        if not isinstance(cached, dict):
            return None
        return fraction_to_selection(self.capture, cached)

    def _cache_selection(self) -> None:
        if self.document.selection_rect is None:
            return
        if self.capture.logical_bounds.width <= 0 or self.capture.logical_bounds.height <= 0:
            return
        self.app.config.last_selection = selection_to_fraction(self.capture, self.document.selection_rect)

    # --- edição de texto (campo flutuante + menu de texto na toolbar) ---

    @property
    def editing_item(self) -> "TextAnnotation | None":
        """Texto do documento escondido na tela enquanto o campo o substitui."""
        return self.text_edit.original if self.text_edit is not None else None

    def _text_item_at(self, image_point: Point) -> "TextAnnotation | None":
        for item in reversed(self.document.items):
            if isinstance(item, TextAnnotation) and item.hit_test(image_point.x, image_point.y, tolerance=2.0):
                return item
        return None

    def _begin_text_edit(self, edit: TextEdit, window: "OverlayWindow") -> None:
        from takeshot.editor.textbox import FloatingTextBox

        self.text_edit = edit
        self._text_box = FloatingTextBox(self, window, edit)
        if self.toolbar is not None:
            self.toolbar.show_text_menu(edit.style)
        self._refresh()

    def _end_text_edit(self, outcome: str) -> None:
        edit, box = self.text_edit, self._text_box
        if edit is None:
            return
        # limpa o estado antes de destruir o campo: a remoção mexe no foco
        self.text_edit = None
        self._text_box = None
        self._text_drag_anchor = None
        getattr(edit, outcome)(self.document)
        if box is not None:
            box.destroy()
        if self.toolbar is not None:
            self.toolbar.show_main_menu()
        self._refresh()
        if self.windows:
            (self._active_window or self.windows[0]).canvas.grab_focus()

    def text_confirm(self) -> None:
        """Aplica o texto como está."""
        if self.text_edit is not None:
            self._remember_text_style(self.text_edit.style)
        self._end_text_edit("confirm")

    def text_cancel(self) -> None:
        """Exclui o texto: o novo some, o existente sai do documento (Ctrl+Z traz de volta)."""
        self._end_text_edit("cancel")

    def text_discard(self) -> None:
        """Descarta as alterações desde o clique (estilo, posição, conteúdo)."""
        self._end_text_edit("discard")

    def text_set_style(self, style: TextStyle) -> None:
        if self.text_edit is None or self._text_box is None:
            return
        self.text_edit.style = style
        self._text_box.update_style()
        self._text_box.focus()

    def _remember_text_style(self, style: TextStyle) -> None:
        """O estilo do último texto confirmado vira o padrão do próximo."""
        self.text_style = style
        self.app.config.text_font_size = style.font_size
        self.app.config.text_color = list(style.color)
        self.app.config.text_background = list(style.background) if style.background else None

    # --- toolbar flutuante ---

    def _ensure_toolbar(self) -> None:
        if self.toolbar is not None or not self.windows or self.document.selection_rect is None:
            return
        from takeshot.editor import toolbar as toolbar_mod

        sel = self.document.selection_rect.normalized()
        cx, cy = self.capture.logical_from_image(sel.x + sel.width / 2, sel.y + sel.height / 2)
        window = self._window_at(Point(cx, cy)) or self.windows[0]

        self.toolbar = toolbar_mod.CaptureToolbar(self)
        self._toolbar_window = window
        window.add_floating(self.toolbar, self._toolbar_position)

    def _toolbar_position(self) -> "tuple[int, int, int, int] | None":
        """Ancora a toolbar embaixo da seleção; troca pra cima, e por fim clampa na
        tela, se não couber embaixo — ex.: seleção cobrindo a altura inteira do monitor."""
        window = self._toolbar_window
        if self.toolbar is None or window is None or self.document.selection_rect is None:
            return None

        sel = self.document.selection_rect.normalized()
        _, tb_width, *_ = self.toolbar.measure(Gtk.Orientation.HORIZONTAL, -1)
        _, tb_height, *_ = self.toolbar.measure(Gtk.Orientation.VERTICAL, -1)

        bottom_lx, bottom_ly = self.capture.logical_from_image(sel.x, sel.y + sel.height)
        top_lx, top_ly = self.capture.logical_from_image(sel.x, sel.y)
        local_bottom = window.local_from_global(Point(bottom_lx, bottom_ly))
        local_top = window.local_from_global(Point(top_lx, top_ly))

        margin = 10
        mg_width, mg_height = window.monitor_geometry.width, window.monitor_geometry.height

        if local_bottom.y + margin + tb_height <= mg_height:
            y = local_bottom.y + margin
        elif local_top.y - margin - tb_height >= 0:
            y = local_top.y - margin - tb_height
        else:
            y = max(0, mg_height - tb_height - margin)

        x = max(margin, min(local_bottom.x, mg_width - tb_width - margin))
        return int(x), int(y), tb_width, tb_height

    def _remove_toolbar(self) -> None:
        if self.toolbar is None:
            return
        if self._toolbar_window is not None:
            self._toolbar_window.remove_floating(self.toolbar)
        self.toolbar = None
        self._toolbar_window = None

    def set_tool(self, kind: "ToolKind | None") -> None:
        self.tool_kind = kind
        self.tool = make_tool(kind, self.tool_style, next_counter=lambda: self.document.next_counter) if kind is not None else None
        if self.toolbar is not None:
            self.toolbar.sync_tool(kind)

    def restart_selection(self) -> None:
        """Descarta área e anotações; o próximo arrasto define a nova área."""
        self.text_discard()
        self.document.clear()
        self.state = SelectionState.SELECTING
        self._remove_toolbar()
        self.set_tool(None)
        self._refresh()
        if self.windows:
            (self._active_window or self.windows[0]).canvas.grab_focus()

    def set_color(self, color) -> None:
        self.tool_style.color = color
        self.app.config.tool_color = list(color)

    def set_line_width(self, width: float) -> None:
        width = max(LINE_WIDTH_RANGE[0], min(LINE_WIDTH_RANGE[1], width))
        self.tool_style.line_width = width
        self.app.config.tool_line_width = width

    def on_confirm(self) -> None:
        if self.state == SelectionState.SELECTED and self.document.selection_rect is not None:
            self._finish()

    def on_key(self, keyval: int, state: Gdk.ModifierType) -> bool:
        if self.text_edit is not None:
            # o campo trata o teclado; isto só roda se o foco estiver fora dele
            name = Gdk.keyval_name(keyval) or ""
            if name in ("Return", "KP_Enter"):
                self.text_confirm()
                return True
            if name == "Escape":
                self.text_discard()
                return True
            return False

        name = Gdk.keyval_name(keyval) or ""
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if name == "Escape":
            if self.state == SelectionState.SELECTED:
                self.state = SelectionState.SELECTING
                self.document.selection_rect = None
                self._remove_toolbar()
                self._refresh()
            else:
                self._cancel()
            return True

        if name in ("Return", "KP_Enter") and self.state == SelectionState.SELECTED:
            self._finish()
            return True

        if ctrl and name.lower() == "a":
            self.document.selection_rect = Rect(0, 0, self.capture.surface.get_width(), self.capture.surface.get_height())
            self.state = SelectionState.SELECTED
            if not self.no_edit:
                self._ensure_toolbar()
            self._refresh()
            return True

        if ctrl and name.lower() == "z" and self.state == SelectionState.SELECTED:
            (self.document.redo() if shift else self.document.undo())
            self._refresh()
            return True

        if ctrl and name.lower() == "c" and self.state == SelectionState.SELECTED:
            self._finish(copy_to_clipboard=True, save_to_disk=False)
            return True

        if ctrl and name.lower() == "s" and self.state == SelectionState.SELECTED:
            self._save_as()
            return True

        if self.state == SelectionState.SELECTED and not self.no_edit and not ctrl and name in TOOL_KEY_BINDINGS:
            requested = TOOL_KEY_BINDINGS[name]
            self.set_tool(None if requested is self.tool_kind else requested)
            return True

        if self.state == SelectionState.SELECTED and name in ("plus", "KP_Add", "equal"):
            self.set_line_width(self.tool_style.line_width + LINE_WIDTH_STEP)
            return True
        if self.state == SelectionState.SELECTED and name in ("minus", "KP_Subtract"):
            self.set_line_width(self.tool_style.line_width - LINE_WIDTH_STEP)
            return True

        if self.state == SelectionState.SELECTED and name in ("Up", "Down", "Left", "Right"):
            step = NUDGE_STEP_FAST if shift else NUDGE_STEP
            dx = -step if name == "Left" else step if name == "Right" else 0
            dy = -step if name == "Up" else step if name == "Down" else 0
            if self.document.selection_rect is not None:
                self.document.selection_rect = self.document.selection_rect.translated(dx, dy)
                self._refresh()
            return True

        return False

    def _cancel(self) -> None:
        log.info("captura cancelada pelo usuário")
        self.text_discard()
        self._close_all()
        self.app.overlay_session = None
        self.on_finished()

    def _finish(self, copy_to_clipboard: bool = True, save_to_disk: bool = True) -> None:
        """Confirmação padrão (Enter/duplo clique): salva E copia. Ctrl+C usa
        `save_to_disk=False` pra só copiar, sem tocar em disco."""
        from takeshot.editor import render as render_mod
        from takeshot.output import clipboard as clipboard_out
        from takeshot.output import notify as notify_out
        from takeshot.output import save as save_out

        self.text_confirm()
        final = render_mod.export(self.document, self.capture.surface)

        dest = None
        if copy_to_clipboard:
            clipboard_out.copy_surface(final, self.app)
            log.info("captura copiada para a área de transferência")
        if save_to_disk:
            dest = save_out.save_surface(final, self.save_path or None)
            log.info("captura salva em %s", dest)
        notify_out.notify_capture(self.app, copied=copy_to_clipboard, saved_path=dest)

        self._cache_selection()
        self.app.config.save()
        self._close_all()
        self.app.overlay_session = None
        self.on_finished()

    def _save_as(self) -> None:
        """Salvar-como + copiar: grava no destino escolhido E copia para a área de transferência."""
        from takeshot.editor import render as render_mod
        from takeshot.output import clipboard as clipboard_out
        from takeshot.output import notify as notify_out
        from takeshot.output import save as save_out

        if not self.windows:
            return
        self.text_confirm()
        final = render_mod.export(self.document, self.capture.surface)

        def on_saved(path: "object | None") -> None:
            if path is None:
                return
            clipboard_out.copy_surface(final, self.app)
            log.info("captura salva em %s e copiada para a área de transferência", path)
            notify_out.notify_capture(self.app, copied=True, saved_path=path)
            self._cache_selection()
            self.app.config.save()
            self._close_all()
            self.app.overlay_session = None
            self.on_finished()

        save_out.save_as_dialog(self.windows[0], final, self.app.config.save_dir_path(), on_saved)

    def _close_all(self) -> None:
        for w in self.windows:
            w.destroy()
