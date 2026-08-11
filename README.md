<p align="center">
  <img src="assets/icon-source.png" alt="Ícone do takeshot" width="128" height="128">
</p>

# takeshot

Ferramenta de captura de tela open source, nativa, para GNOME/Wayland — criada para substituir o
Flameshot, que não funciona em sessões Wayland puras (Qt5 não exporta handle de janela via
`xdg_foreign`, quebrando a integração com `org.freedesktop.portal.Screenshot`).

Seleção de região com anotação (setas, retângulos, elipses, traço livre, texto, pixelização,
desfoque, numeração sequencial), atalho de teclado global, cópia para a área de transferência que
sobrevive ao fechamento da janela, e zero dependências Python de terceiros.

## Plataformas suportadas

**Só Linux com GNOME/Wayland.** Não funciona em macOS nem Windows — a arquitetura inteira é
construída em cima de tecnologias específicas do Linux/GNOME, sem equivalente direto nas outras
plataformas:

- **Captura**: `org.freedesktop.portal.Screenshot` via D-Bus é uma spec do `xdg-desktop-portal`,
  exclusiva de desktops Linux.
- **UI**: GTK4 + libadwaita via PyGObject — toolkit nativo do GNOME.
- **Atalho global**: `gsettings`/dconf, o sistema de configuração do GNOME.
- **Instalador**: `install.sh` assume `apt` (Debian/Ubuntu) e `.desktop` files.
- **Wayland**: a exportação de window handle (`GdkWayland.WaylandToplevel.export_handle`) — a peça
  que resolve o bug do Flameshot que motivou este projeto — é específica do Wayland.

As únicas partes portáveis são a lógica pura do editor (`items.py`, `document.py`, `render.py`,
`geom.py`) — sem dependência de GTK. Um port pra macOS usaria `ScreenCaptureKit`/AppKit; pra
Windows, `Windows.Graphics.Capture`/WinUI — projetos à parte, não um esforço incremental sobre este
código.

## Instalação

```bash
curl -fsSL https://raw.githubusercontent.com/danielbbarcelos/takeshot/main/install.sh | bash
```

O instalador:

1. checa se as dependências do sistema estão presentes e **oferece instalá-las via `apt`** se
   faltarem (nunca instala nada silenciosamente sem confirmação — a menos que você passe `--yes`);
2. clona o takeshot em `~/.local/share/takeshot` e cria um launcher em `~/.local/bin/takeshot`;
3. instala o ícone e o `.desktop` (aparece no menu de aplicativos/dash);
4. registra o daemon residente para iniciar com a sessão (autostart);
5. registra o atalho de teclado global (`Print`, com fallback automático para `<Shift>Print` se
   `Print` já estiver em uso por outro app — nunca sobrescreve atalhos de outros aplicativos).

Rodar o comando de novo **atualiza a instalação existente** (`git pull` + re-render de tudo) e
substitui uma instância residente antiga pela nova, sem precisar sair e entrar na sessão — é seguro
rodar quantas vezes quiser.

### Pré-requisitos

- Linux com uma sessão gráfica ativa (foi desenhado para **Wayland + GNOME**; deve funcionar em
  outros compositores Wayland compatíveis com o portal XDG, mas isso não é testado regularmente —
  veja `--portal-interactive` abaixo se a captura não-interativa for negada).
- `python3 >= 3.10` com `pip`/`apt` disponível.
- Um sistema baseado em `apt` (Debian/Ubuntu) para a instalação automática de dependências. Em
  outras distros, instale manualmente os equivalentes a: `python3-gi`, `python3-gi-cairo`,
  `gir1.2-gtk-4.0`, `gir1.2-adw-1`, `gir1.2-glib-2.0` (GTK4 ≥ 4.10, libadwaita ≥ 1.4).
- `git`, `curl`, `rsync` (usados só pelo instalador).

Não há venv, pipx ou wheel envolvidos — o takeshot não tem nenhuma dependência Python de terceiros,
só bindings do sistema (`gi`, `cairo`). Instalar é copiar arquivos + criar um symlink; atualizar é
`git pull`.

### Opções do instalador

```bash
./install.sh --help
```

| Flag | Efeito |
|---|---|
| `--dev` | instala a partir de um checkout local (symlink), em vez de clonar do GitHub — para desenvolvimento |
| `--no-shortcut` | não instala/atualiza o atalho de teclado global |
| `--no-autostart` | não registra o daemon residente para iniciar com a sessão |
| `--force` | assume o binding `Print` mesmo se outro app já o estiver usando |
| `--yes` | instala dependências via `apt` sem perguntar |
| `--prefix=DIR` | instala em `DIR` em vez de `~/.local` |

## Uso

```
takeshot                              # = capture --region (padrão)
takeshot capture --region|--screen
takeshot capture --screen --copy --no-edit    # headless, sem editor
takeshot --daemon                     # residente, iniciado pelo autostart
takeshot --standalone | --replace
takeshot shortcut install|remove|status
takeshot preferences
takeshot doctor
```

Depois de instalado, pressione **Print** (ou o binding mostrado pelo instalador, se houve
conflito) para capturar uma região da tela. Com a seleção feita:

| Tecla | Ação |
|---|---|
| `Esc` | cancela / volta para a seleção |
| `Enter` / duplo clique | confirma: salva no destino padrão **e** copia |
| `Ctrl+C` | copia — não salva em disco |
| `Ctrl+S` | abre "salvar como" (escolhe o destino) e copia |
| `Ctrl+Z` / `Ctrl+Shift+Z` | desfazer / refazer |
| `Ctrl+A` | selecionar a tela inteira |
| `1`–`8` | trocar de ferramenta (seta, retângulo, elipse, traço livre, texto, pixelizar, desfocar, numeração) — apertar de novo na ferramenta ativa volta pro modo "arrastar seleção" |
| `+` / `-` | espessura do traço / intensidade do pixelizar e desfocar |
| setas | mover a seleção 1px (`Shift`+seta = 10px) |
| arrastar dentro da seleção (sem ferramenta ativa) | move a seleção inteira, preservando o tamanho |
| arrastar os quadradinhos nas bordas/cantos | redimensiona a seleção |

Por padrão, **nenhuma ferramenta de anotação vem selecionada** — arrastar dentro da seleção move
ela, redimensionar é sempre pelos handles, e desenhar exige escolher uma ferramenta primeiro
(`1`–`8` ou clique na toolbar).

## Desinstalar

```bash
~/.local/share/takeshot/uninstall.sh
```

Remove o atalho de teclado, o daemon residente, o launcher, o ícone e o `.desktop`. Por padrão
preserva as preferências salvas (`~/.config/takeshot`); para remover tudo, incluindo config e
estado:

```bash
~/.local/share/takeshot/uninstall.sh --purge
```

## Reportar problemas

Antes de abrir uma issue, rode:

```bash
takeshot doctor
```

Isso diagnostica: tipo de sessão/desktop, versões do GTK4/libadwaita, presença do portal
`org.freedesktop.portal.Screenshot`, quem é o dono atual do bus name (PID + caminho do binário —
útil se uma instância zumbi estiver travando o atalho), estado do atalho de teclado (incluindo
conflitos de binding), e se o `.desktop`/ícone estão instalados corretamente.

Abra uma issue em <https://github.com/danielbbarcelos/takeshot/issues> incluindo a saída completa
de `takeshot doctor`.

## Limitações conhecidas

- **Scaling fracionário não é testado** — o fator de escala é sempre derivado em runtime a partir
  da captura devolvida pelo portal, mas só foi validado com escala 1.0.
- **Captura de janela ativa não existe no v1** — sem uma extensão do GNOME Shell não há como
  enumerar geometria de janelas no Wayland; só região e tela cheia são suportadas.
- O clipboard no Wayland é servido pelo processo de origem — por isso o takeshot fica residente
  (`--daemon`, autostart). Se o processo residente for encerrado, o conteúdo copiado se perde.
- **A tela pisca (flash) no instante da captura, antes do overlay abrir** — isso é o próprio GNOME
  Shell, não o takeshot. `org.gnome.Shell.Screenshot.Screenshot` (o método interno que o backend
  do portal chama) tem um parâmetro `flash`, mas ele só existe na API interna, restrita à allowlist
  do `DBusSenderChecker` (§2.1) — `org.freedesktop.portal.Screenshot`, a única API que apps de
  terceiros podem usar no Wayland, não expõe esse parâmetro. Não tem como suprimir via API.
  `org.gnome.desktop.interface enable-animations=false` é a única alavanca conhecida que poderia
  afetar isso, mas desliga todas as animações do Shell (não só o flash) — não vale a troca só por
  causa disso, então ficou como está por decisão consciente.

## Desenvolvimento

```bash
git clone https://github.com/danielbbarcelos/takeshot.git
cd takeshot
./install.sh --dev --yes
python3 -m pip install --user pytest
python3 -m pytest
```

`items.py`, `document.py`, `render.py` e `geom.py` não dependem de GTK — são a lógica que mais
importa testar (geometria, undo/redo, numeração) e rodam headless, sem display.

Ícones em `assets/hicolor/` são pré-gerados e commitados; para regenerá-los a partir de
`assets/icon-source.png` (precisa de ImageMagick, só em dev):

```bash
./assets/regen-icons.sh
```

## Licença

MIT — implementação clean-room, sem código do Flameshot (que é GPL-3).
