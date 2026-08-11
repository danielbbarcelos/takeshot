# takeshot

Ferramenta de captura de tela open source, nativa, para GNOME/Wayland — criada para substituir o
Flameshot, que não funciona neste ambiente (Qt5 não exporta handle de janela via `xdg_foreign` no
Wayland, quebrando a integração com `org.freedesktop.portal.Screenshot`).

**Repositório:** https://github.com/danielbbarcelos/takeshot (público)

## Requisito obrigatório

Antes de considerar qualquer versão pronta para compartilhar: **README.md com instruções de
instalação completas** (`curl | bash` via `install.sh`, pré-requisitos, como desinstalar, como
reportar problemas via `takeshot doctor`). Sem isso o projeto não está "pronto", mesmo que o
código funcione.

## 1. Identidade e decisões de topo

| Item | Decisão |
|---|---|
| App ID | `com.danielbarcelos.Takeshot` |
| Stack | Python 3.12 + PyGObject + GTK4 + libadwaita 1.5 + pycairo |
| Dependências Python de terceiros | zero — só `python3-gi`, `python3-gi-cairo`, `gir1.2-*` do apt |
| Instalação | clone + symlink em `~/.local/bin`. Sem venv, sem pipx, sem wheel |
| Captura | portal XDG `org.freedesktop.portal.Screenshot`, modo **não-interativo** |
| Seleção + anotação | overlay próprio fullscreen sobre a imagem congelada (modelo Flameshot) |
| Instância única | `Adw.Application` com bus name único + rota de escape obrigatória |
| Atalho global | `gsettings custom-keybindings`, registrado idempotentemente pelo `install.sh` |
| Licença | MIT (implementação clean-room, sem código do Flameshot que é GPL-3) |

"Zero dependências de terceiros" cascateia em tudo: sem venv, sem `--system-site-packages`, sem
descasamento entre `gi` do venv e a typelib do sistema. Instalar = copiar arquivos + symlink;
atualizar = `git pull`. pipx é explicitamente rejeitado — existe para isolar deps PyPI, e aqui não
há nenhuma.

## 2. Fluxo de captura no Wayland

### 2.1 Por que não `org.gnome.Shell.Screenshot`
Gateado por `DBusSenderChecker` com allowlist fixa (`org.gnome.SettingsDaemon.MediaKeys`,
`...desktop.gtk`, `...desktop.gnome`). App de terceiro recebe `AccessDenied`. Portal XDG é o único
caminho (confirmado lendo `/usr/lib/gnome-shell/libshell-14.so`, `ui/screenshot.js:2431`).

### 2.2 Não-interativo
**Decisão: `interactive: false`.** O portal devolve a tela inteira já capturada como PNG; o
takeshot faz seleção de região e anotação por conta própria.

Por quê: anotação precisa dos pixels da tela inteira (redimensionar seleção depois de anotar, blur
lendo pixels de origem, expandir seleção). Com `interactive: true` o portal só devolve o crop já
cortado, e a UX vira dupla (seleciona no GNOME → abre outra janela pra anotar) — exatamente o que o
Flameshot evita.

Manter `--portal-interactive` como flag de fallback documentada para compositores onde a permissão
não-interativa é negada (algumas variantes KDE/wlroots) — importa para portabilidade do projeto
open source, não para o caso de uso principal.

### 2.3 A chamada, concretamente

`src/takeshot/portal/request.py` — helper genérico do padrão `org.freedesktop.portal.Request`
(assina o `Response` **antes** de chamar, senão há race):

```python
token = f"takeshot_{os.getpid()}_{next(_counter)}"
sender = bus.get_unique_name()[1:].replace(".", "_")
path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
bus.signal_subscribe(
    "org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request",
    "Response", path, None, Gio.DBusSignalFlags.NONE, on_response)
```

`src/takeshot/portal/screenshot.py`:

```python
bus.call(
    "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
    "org.freedesktop.portal.Screenshot", "Screenshot",
    GLib.Variant("(sa{sv})", (parent_window, {
        "handle_token": GLib.Variant("s", token),
        "interactive":  GLib.Variant("b", False),
        "modal":        GLib.Variant("b", True),
    })),
    GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, -1, None, on_call_done)
```

`Response` chega como `(u a{sv})`: `0` sucesso, `1` cancelado, `2` erro. `results["uri"]` é um
`file://` para arquivo temporário — **apagar depois de carregar**, o portal não limpa. Tudo
assíncrono no main loop GLib, nunca `call_sync` (o portal pode abrir diálogo e bloquear).

### 2.4 `parent_window`: quando importa

Só é usado quando o portal desenha um diálogo. No caminho não-interativo isso acontece **uma única
vez**: "permitir captura de tela?". Depois a permissão fica no permission store
(`~/.local/share/flatpak/db/screenshot`, já existe nesta máquina) e nenhum diálogo aparece de novo
— `parent_window` deixa de importar.

- **Captura por atalho (caminho quente): `parent_window = ""`.** Sem janela nossa mapeada nesse
  momento; permissão já concedida, nenhum diálogo aparece.
- **Primeira execução**: criar janela auxiliar 1×1, `set_decorated(False)`, `set_opacity(0.0)`,
  `set_can_focus(False)`; após `map`, exportar handle e usar. Ao `response == 0`, gravar
  `portal_permission_granted = true` e destruir a janela.
- **Janelas reais** (preferências, salvar-como): sempre exportar handle de verdade.

`src/takeshot/portal/window_handle.py`:

```python
def export_handle(window: Gtk.Window, callback: Callable[[str], None]) -> None:
    surface = window.get_surface()           # precisa estar mapeada
    if GdkWayland and isinstance(surface, GdkWayland.WaylandToplevel):
        ok = surface.export_handle(lambda _tl, h, _d: callback(f"wayland:{h}"), None)
        if not ok:
            callback("")
    elif GdkX11 and isinstance(surface, GdkX11.X11Surface):
        callback("x11:%x" % surface.get_xid())
    else:
        callback("")
```

Notas obrigatórias: `export_handle` exige surface mapeada (conectar em `Gtk.Widget::map` ou usar só
depois de `present()`); é assíncrono; chamar `unexport_handle()` ao terminar a Request; import de
`GdkWayland`/`GdkX11` em `try/except` no topo do módulo.

**Isto é literalmente o que o Qt5 não faz** — a causa raiz do bug do Flameshot nesta máquina.
`GdkWayland.WaylandToplevel.export_handle` é o método real disponível no GTK 4.14 do Ubuntu 24.04
(a API cross-backend `Gdk.Toplevel.export_handle` só chegou em versões posteriores — não existe
aqui, confirmado por introspecção).

### 2.5 Ordem de operações
```
hotkey → Application.activate("capture --region")
  1. se já existe overlay aberto → foca e retorna
  2. portal.screenshot(parent="")            [assíncrono]
  3. recebe uri → cairo.ImageSurface.create_from_png(path) → apaga o temp
  4. monta Capture{surface, logical_bounds, scale, monitors}
  5. AGORA cria e apresenta as janelas de overlay (uma por monitor)
```
Nada nosso pode estar mapeado entre 1 e 3 — regra dura (senão o overlay aparece na própria captura).

### 2.6 Modelo de coordenadas
`Capture` guarda: `surface` (cairo ImageSurface em pixels de dispositivo), `logical_bounds` (união
das geometrias dos monitores via `Gdk.Display.get_monitors()`, coordenadas lógicas), `scale =
surface.get_width() / logical_bounds.width`. Anotações armazenadas em coordenadas de imagem (device
px); o widget converte lógico→imagem na entrada e imagem→lógico no desenho.

`scale` fracionário não testado nesta máquina (monitor único 2560×1080 @ 1.0). Derivar `scale` em
runtime, nunca assumir `get_scale_factor()`. Documentar como limitação conhecida.

### 2.7 Escopo: janela ativa fica de fora do v1
Sem extensão do GNOME Shell não há como enumerar geometria de janelas no Wayland. v1 entrega apenas
região e tela cheia — documentado, sem heurística de detecção de bordas.

## 3. Arquitetura de anotação

### 3.1 Um único caminho de renderização: Cairo
Tudo renderiza via Cairo, inclusive na tela (`snapshot.append_cairo(rect)` chamando a mesma
`render(document, cr, ctx)` que a exportação usa). Evita a classe de bug "o que vejo não é o que
salva". Se blur incomodar depois, otimiza-se com cache de superfície por anotação — não com um
segundo renderer (GSK).

### 3.2 Camadas
```
src/takeshot/editor/
  items.py       Annotation dataclasses: render(cr, ctx) / bounds() / hit_test(p) / translate(d)
  document.py    AnnotationDocument: itens, selection_rect, undo/redo, next_counter
  render.py      render(document, cr, ctx) — usada por canvas E export. Sem gi.
  tools.py       máquina de estados por ferramenta (press/motion/release/key + preview)
  canvas.py      Gtk.Widget subclass, do_snapshot → append_cairo → render.render()
  overlay.py     Gtk.Window fullscreen por monitor + OverlaySession (coordenador global)
  toolbar.py     barra flutuante libadwaita ancorada à seleção
```
`items.py`, `document.py`, `render.py` **não importam `gi`** — só `cairo`/`dataclasses`. Testáveis
headless com pytest puro (é onde mora a lógica que quebra: undo, geometria, numeração).

### 3.3 Itens
```python
@dataclass
class Annotation:
    color: tuple[float, float, float, float]
    line_width: float
    def render(self, cr: cairo.Context, ctx: RenderContext) -> None: ...
    def bounds(self) -> Rect: ...
    def hit_test(self, x: float, y: float) -> bool: ...

ArrowAnnotation(start, end)
RectAnnotation(rect, filled=False)
EllipseAnnotation(rect)
FreehandAnnotation(points)
TextAnnotation(origin, text, font_size)       # PangoCairo, não cr.show_text
PixelateAnnotation(rect, block=12)
BlurAnnotation(rect, radius=8)
CounterAnnotation(center, radius, number)     # numeração sequencial
```
`RenderContext` carrega a superfície de origem (`Capture.surface`). **Blur/pixelate sempre lê a
origem**, nunca o composto — borrar uma área e desenhar uma seta por cima não borra a seta.

Pixelate em Cairo puro (down-scale + up-scale `FILTER_NEAREST`); blur via cadeia de down/up-scale
`FILTER_BILINEAR` (3 passes ≈ gaussiano visual). Zero numpy, zero Pillow.

### 3.4 Numeração sequencial
Número **derivado, não armazenado como estado mutável**:
```python
@property
def next_counter(self) -> int:
    used = [i.number for i in self._items if isinstance(i, CounterAnnotation)]
    return (max(used) + 1) if used else self.counter_start
```
Undo de um contador volta o próximo ao número certo automaticamente; apagar o nº 2 do meio não
renumera os outros (comportamento Flameshot). `counter_start` configurável na toolbar.

### 3.5 Undo/redo
**Snapshot da lista de itens**, não command pattern:
```python
def _commit(self) -> None:
    self._undo.append(list(self._items))     # dataclasses imutáveis por convenção
    self._redo.clear()
    if len(self._undo) > 100: self._undo.pop(0)
```
Command pattern adicionaria superfície de bug sem necessidade real (payload é sempre pequeno).
`_commit()` só no `on_release` da ferramenta — durante o arrasto, `tool.draw_preview(cr)` fora do
documento.

### 3.6 Overlay e máquina de estados
```
OverlaySession
 ├── OverlayWindow(monitor A)  ─┐
 ├── OverlayWindow(monitor B)  ─┴─ compartilham o mesmo AnnotationDocument
 └── estado: SELECTING → SELECTED
```
`Gtk.Window`, `set_decorated(False)`, `fullscreen_on_monitor(monitor)`, CSS transparente, cursor
`crosshair`. Cada janela desenha seu recorte do `Capture.surface`, escurecido (`dim_opacity` default
0.45) exceto na região selecionada. Eventos via `Gtk.GestureDrag` + `Gtk.EventControllerKey` +
`Gtk.EventControllerMotion`, traduzidos para coordenadas globais lógicas e delegados à
`OverlaySession` (seleção pode cruzar monitores).

Teclado:

| Tecla | Ação |
|---|---|
| `Esc` | cancela / volta de SELECTED para SELECTING |
| `Enter` / duplo clique | confirma → copy/save conforme config |
| `Ctrl+C` / `Ctrl+S` | copiar / salvar-como |
| `Ctrl+Z` / `Ctrl+Shift+Z` | undo / redo |
| `Ctrl+A` | selecionar tela inteira |
| `1`..`8` | trocar ferramenta |
| `+` / `-` | espessura |
| setas | nudge 1px (`Shift`=10px) |

### 3.7 Saída
```python
value = GObject.Value(Gdk.Texture, texture_from_surface(final_surface))
display.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(value))
```
`Gdk.Clipboard.set_texture` **não é introspectável** no PyGObject — confirmado, usar
`ContentProvider`. No Wayland quem serve o clipboard é o processo de origem: **o app precisa ficar
residente** (ver §4), senão a imagem some ao sair — a dor conhecida do Flameshot/ksnip.

`output/save.py`: default `xdg-user-dir PICTURES` + `/Takeshot` (ex.: `~/Imagens/Takeshot`), template
`takeshot_%Y-%m-%d_%H-%M-%S.png` via `surface.write_to_png()`.

## 4. Instância única, residência

`Adw.Application(application_id="com.danielbarcelos.Takeshot", flags=HANDLES_COMMAND_LINE)`. GApplication resolve unicidade nativamente — segunda invocação encaminha argv pro processo vivo (~300ms de boot Python/GTK viram ~5ms), e é o que mantém o clipboard vivo.

O desastre do Flameshot não foi o singleton em si — foi **dois builds disputando o mesmo bus name
sem forma de diagnosticar quem venceu**. Três mitigações são requisito de v1:

1. `--standalone` → `NON_UNIQUE`, rota de escape sempre disponível.
2. `--replace` → mata o dono atual do bus name e assume.
3. `takeshot doctor` reporta o dono do bus name via `GetConnectionUnixProcessID` →
   `/proc/<pid>/exe` → caminho real do binário.

Residência: `keep_running: true` (default). `hold()` enquanto houver overlay aberto ou for dono do
clipboard. `--daemon` inicia residente sem capturar (autostart).

## 5. Atalho de teclado global

`gsettings custom-keybindings` é o único caminho confirmado: **não existe portal GlobalShortcuts**
nesta máquina (0 ocorrências, verificado por introspecção em `org.freedesktop.portal.Desktop` e no
impl do GNOME). O caminho por ícone/`.desktop`/cache do Shell já se mostrou não confiável nesta
sessão.

Estado atual da máquina que o instalador precisa respeitar: já existe `custom0` ocupado por
`ksnip -r`, e `org.gnome.shell.keybindings show-screenshot-ui` já está `[]` (tecla `Print`
liberada). **O instalador não pode sobrescrever o array.**

Algoritmo idempotente em `install.sh` (helper Python inline pra parsear GVariant — nada de `sed`):
```
1. lê array atual de custom-keybindings
2. para cada path, lê `command`
   - se command == "takeshot capture --region" → reusa esse path (UPDATE)
3. senão: escolhe menor customN livre, faz APPEND ao array
4. set name/command/binding="Print" no path escolhido
5. checa conflito de binding: sem --force cai para "<Shift>Print"; com --force assume
6. salva valor anterior de show-screenshot-ui em ~/.local/state/takeshot/install-state.json,
   depois seta "[]"
```
Indexar pelo **command**, não pelo nome/posição — rodar `install.sh` dez vezes produz exatamente uma
entrada. `uninstall.sh` faz o inverso. `takeshot shortcut install|remove|status` expõe a mesma
lógica em runtime.

## 6. Estrutura de diretórios

```
takeshot/
├── CLAUDE.md
├── README.md                 OBRIGATÓRIO — instruções de instalação (ver topo deste arquivo)
├── LICENSE                   MIT
├── install.sh
├── uninstall.sh
├── pyproject.toml            metadados + ruff/pytest — NÃO é o caminho de instalação
├── bin/takeshot               shell wrapper: PYTHONPATH=$INSTALL/src exec python3 -m takeshot "$@"
├── data/
│   ├── com.danielbarcelos.Takeshot.desktop.in
│   └── com.danielbarcelos.Takeshot.Daemon.desktop.in     autostart
├── assets/
│   ├── icon-source.png                                    256x256 original (já copiado)
│   └── hicolor/{16,24,32,48,64,128,256}x*/apps/com.danielbarcelos.Takeshot.png
│       + scalable/apps/com.danielbarcelos.Takeshot.svg
├── tests/                    pytest headless: document, geometry, items, naming, gsettings merge
└── src/takeshot/
    ├── __main__.py            python3 -m takeshot
    ├── cli.py / app.py / config.py / paths.py / doctor.py / shortcuts.py
    ├── portal/{request,screenshot,window_handle}.py
    ├── capture/{model,source}.py
    ├── editor/{items,document,render,tools,canvas,overlay,toolbar}.py
    ├── output/{clipboard,save}.py
    └── ui/{style.css,preferences.py}
```

CLI alvo:
```
takeshot                              # = capture --region (default)
takeshot capture --region|--screen
takeshot capture --screen --copy --no-edit    # headless
takeshot --daemon                     # residente, autostart
takeshot --standalone | --replace
takeshot shortcut install|remove|status
takeshot doctor
```
`takeshot doctor` — desenhado a partir das dores desta sessão de debug: tipo de sessão/desktop,
versões gi/Gtk4/Adw, presença/versão da interface Screenshot no portal, qual backend está no bus,
`org.gnome.Shell.Screenshot` (espera `AccessDenied`), ausência do GlobalShortcuts, dono do bus name
com PID+exe, estado do keybinding (conflito em `Print`? `show-screenshot-ui` voltou?), `~/.local/bin`
no PATH, `.desktop`/cache de ícones.

## 7. `install.sh`

Bash, `set -euo pipefail`, sem root, suporta `curl -fsSL .../install.sh | bash`.
```
1. guards: Linux, bash, não-root, python3 >= 3.10
2. detecta sessão; avisa (não aborta) se não for Wayland+GNOME
3. checa deps (import gi/cairo/Gtk4/Adw); faltando → oferece
   sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-glib-2.0
   (--yes roda sem perguntar; nunca silencioso por default)
4. destino ~/.local/share/takeshot: rsync/symlink (--dev) se local, git clone/pull se via curl
5. launcher ~/.local/bin/takeshot, chmod +x; avisa se não está no PATH
6. ícones → ~/.local/share/icons/hicolor/**; gtk-update-icon-cache -f -t ... || true
7. .desktop renderizado de data/*.desktop.in → ~/.local/share/applications/...
   update-desktop-database ... || true
8. autostart (default sim, --no-autostart desliga)
9. keybinding idempotente (§5), a menos que --no-shortcut
10. resumo: "pressione Print"; nota sobre cache do GNOME Shell se ícone não abrir (logout/login)
```
Flags: `--dev`, `--no-shortcut`, `--no-autostart`, `--force`, `--yes`, `--prefix`. Todo passo
idempotente.

`application_id` do `Adw.Application` **tem que ser idêntico** ao basename do `.desktop` — é o que
faz o GNOME Shell associar janela↔ícone no Wayland sem `StartupWMClass` (categoria de problema que
já apareceu com o ícone do ksnip nesta sessão). Desktop Actions para região/tela no botão direito da
dock.

## 8. Empacotamento do ícone

Fonte: `assets/icon-source.png` (cópia de `~/Downloads/crop.png`, 256×256 RGBA, confirmado). Convenção hicolor com PNGs **pré-gerados e commitados** (install.sh não depende de ImageMagick no
destino): `16/24/32/48/64/128/256` + `scalable/apps/....svg`. Nome do arquivo = App ID sempre
(`Icon=com.danielbarcelos.Takeshot` no `.desktop` resolve assim, mesmo nome serve para
`Gtk.Window.set_icon_name()`).

Geração via `assets/regen-icons.sh` (só no dev, nunca no install), downscale Lanczos a partir do
256. Nos tamanhos ≤32 simplificar manualmente (só o frame de crop, sem a miniatura interna).
`scalable/*.svg` v1: SVG com o PNG 256 embutido em base64 — suficiente e honesto; vetorizar de
verdade fica para depois. Ícone `-symbolic.svg` fora do v1.

## 9. Riscos conhecidos e mitigações

| Risco | Mitigação |
|---|---|
| Overlay aparecer na própria captura | Nenhuma janela nossa mapeada entre chamada do portal e retorno |
| Janela 1×1 de handle visível na captura | Só na primeiríssima execução; opacity 0, 1×1, can_focus false |
| Clipboard morre ao sair | Processo residente + `keep_running: true` + autostart |
| Scaling fracionário | `scale` derivado em runtime, não testado — limitação documentada |
| Cache de app do GNOME Shell (ícone não abre) | Atalho não depende dele; install.sh avisa sobre logout |
| Tecla `Print` roubada de volta por update do GNOME | `doctor` detecta, `shortcut install` reconserta |
| `custom0` do ksnip sobrescrito | Merge no array indexado por `command`, nunca `set` direto |
| Bus name preso por instância zumbi | `--standalone`, `--replace`, `doctor` mostrando PID+exe do dono |
| Divergência tela vs. arquivo salvo | Um único `render()` Cairo compartilhado entre tela e export |
| Flash de tela antes do overlay abrir | Não mitigável — é o GNOME Shell reagindo ao `Screenshot()` do portal; `flash` só existe na API interna (allowlist), o portal público não expõe essa opção. Confirmado nesta máquina: `gdbus introspect ...org.gnome.Shell/Screenshot` mostra `flash` só em `Screenshot`/`ScreenshotArea`/`ScreenshotWindow` (interno), nunca em `org.freedesktop.portal.Screenshot`. `enable-animations=false` é a única alavanca, mas desliga todas as animações do Shell — decisão consciente de não aplicar |

## 10. Ordem de implementação sugerida

1. `paths.py`, `config.py`, `cli.py`, `app.py` — esqueleto que sobe e responde `--version`
2. `doctor.py` — primeiro, dá visibilidade em tudo que vier depois
3. `portal/request.py` + `portal/screenshot.py` + `capture/` → `takeshot capture --screen --copy
   --no-edit` funcionando ponta a ponta. **Marco de valor real.**
4. `portal/window_handle.py` + fluxo de primeira permissão
5. `editor/items.py` + `document.py` + `render.py` + testes headless (sem GTK ainda)
6. `editor/canvas.py` + `overlay.py` → seleção de região funcionando
7. `editor/tools.py` + `toolbar.py` → ferramentas incluindo numeração sequencial
8. `output/save.py` + diálogo salvar-como
9. `install.sh` + `uninstall.sh` + ícones + `.desktop`
10. `ui/preferences.py`

Passo 3 é o corte crítico: se funciona, o risco arquitetural principal (Wayland/portal) está
eliminado e o resto é UI.

---

Referências verificadas nesta máquina que sustentam este documento:
`/usr/lib/gnome-shell/libshell-14.so` (`ui/screenshot.js:2431-2434`, allowlist do
`DBusSenderChecker`) e `/home/daniel/.local/share/flatpak/db/screenshot` (permission store da
concessão do portal).
