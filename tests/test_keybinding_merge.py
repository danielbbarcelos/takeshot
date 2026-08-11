from takeshot.keybinding_merge import (
    KeybindingEntry,
    binding_owner,
    find_conflicting_path,
    find_or_alloc_path,
    next_free_index,
    remove_command,
    resolve_binding,
)

TAKESHOT = "takeshot capture --region"


def ksnip_entry(path="/.../custom0/"):
    return KeybindingEntry(path=path, command="ksnip -r", binding="Print", name="Captura de tela (ksnip)")


def test_next_free_index_skips_used_slots():
    paths = ["/.../custom0/", "/.../custom2/"]
    assert next_free_index(paths) == 1


def test_next_free_index_empty():
    assert next_free_index([]) == 0


def test_find_or_alloc_path_creates_new_when_absent():
    entries = [ksnip_entry()]
    path, created = find_or_alloc_path(entries, TAKESHOT)
    assert created
    assert path.endswith("custom1/")


def test_find_or_alloc_path_reuses_existing_entry_indexed_by_command():
    entries = [ksnip_entry(), KeybindingEntry(path="/.../custom1/", command=TAKESHOT, binding="<Shift>Print", name="takeshot")]
    path, created = find_or_alloc_path(entries, TAKESHOT)
    assert not created
    assert path == "/.../custom1/"


def test_running_install_ten_times_produces_exactly_one_entry():
    entries = [ksnip_entry()]
    for _ in range(10):
        path, created = find_or_alloc_path(entries, TAKESHOT)
        if created:
            entries.append(KeybindingEntry(path=path, command=TAKESHOT, binding="Print", name="takeshot"))
    takeshot_entries = [e for e in entries if e.command == TAKESHOT]
    assert len(takeshot_entries) == 1


def test_binding_owner_finds_conflicting_command():
    entries = [ksnip_entry()]
    owner = binding_owner(entries, "Print", ignore_path="/.../custom1/")
    assert owner == "Captura de tela (ksnip)"


def test_binding_owner_ignores_self():
    entries = [KeybindingEntry(path="/.../custom1/", command=TAKESHOT, binding="Print", name="takeshot")]
    assert binding_owner(entries, "Print", ignore_path="/.../custom1/") is None


def test_resolve_binding_falls_back_on_conflict():
    entries = [ksnip_entry()]
    binding, conflict = resolve_binding(entries, "/.../custom1/", "Print", "<Shift>Print", force=False)
    assert binding == "<Shift>Print"
    assert conflict == "Captura de tela (ksnip)"


def test_resolve_binding_force_keeps_requested():
    entries = [ksnip_entry()]
    binding, conflict = resolve_binding(entries, "/.../custom1/", "Print", "<Shift>Print", force=True)
    assert binding == "Print"
    assert conflict is None


def test_resolve_binding_no_conflict_keeps_requested():
    entries = []
    binding, conflict = resolve_binding(entries, "/.../custom1/", "Print", "<Shift>Print", force=False)
    assert binding == "Print"
    assert conflict is None


def test_remove_command_drops_matching_entry_keeps_others():
    entries = [ksnip_entry(), KeybindingEntry(path="/.../custom1/", command=TAKESHOT, binding="<Shift>Print", name="takeshot")]
    remaining, removed = remove_command(entries, TAKESHOT)
    assert removed
    assert remaining == [ksnip_entry().path]


def test_find_conflicting_path_returns_other_entrys_path():
    entries = [ksnip_entry(path="/.../custom0/")]
    assert find_conflicting_path(entries, "Print", ignore_path="/.../custom1/") == "/.../custom0/"


def test_find_conflicting_path_ignores_self():
    entries = [KeybindingEntry(path="/.../custom1/", command=TAKESHOT, binding="Print", name="takeshot")]
    assert find_conflicting_path(entries, "Print", ignore_path="/.../custom1/") is None


def test_find_conflicting_path_none_when_no_conflict():
    entries = [ksnip_entry()]
    assert find_conflicting_path(entries, "<Shift>Print", ignore_path="/.../custom1/") is None


def test_remove_command_noop_when_absent():
    entries = [ksnip_entry()]
    remaining, removed = remove_command(entries, TAKESHOT)
    assert not removed
    assert remaining == [ksnip_entry().path]
