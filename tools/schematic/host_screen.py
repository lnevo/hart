"""The layout hosts' screen, the one setting the Layout Editor panel's window and the CATS desks' window come from.

preferences.json[main_upper] (the page's preferences) holds `host_screen`: {"size": [width, height], "taskbar": px},
the screen the Pi and the Windows box both drive and the taskbar each keeps along one edge (its `_host_screen` note
records the measurement). The window a maximised panel opens in is that screen less the taskbar:

    host_screen.window(page)                  (width, height - taskbar), checked
    host_screen.apply(opts, sections, page)   opts (the solved page options) with le_window and cats_window set to
                                              the window of sections[page] (sections: every section of
                                              preferences.json as written), the names the schematic-maps plugin
                                              reads (le_prefs.window, cats_prefs.options)

publish_draft.solved_sheet() applies it to the solved sheet's page options, the one way the builders get them, so
build_layout_le.py and build_cats_panel.py both see the same window. Each tool keeps its own frame allowance inside
it, in the plugin: Layout Editor's 18 x 60 px (le_prefs), CATS's frame, title, menu and status lines (cats_prefs
CHROME). No section of preferences.json may set le_window or cats_window itself, and the solved options may hold
neither unless an earlier apply set it: either would be a second source.
"""
from __future__ import annotations

KEY = "host_screen"
DERIVED = ("le_window", "cats_window")

# The options dicts apply() has set, by id, each kept with the window it set (the dict is held, so its id is not
# reused): the plugin's cache can hand back the same solved sheet, whose options then hold this module's own window.
_applied: dict[int, tuple[dict, list[int]]] = {}


class HostScreenError(ValueError):
    """The host_screen setting is missing or malformed, or a window comes from elsewhere; the message says which."""


def _whole(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def window(page: dict) -> tuple[int, int]:
    """(width, height) of the window a panel opens in on the layout hosts: host_screen's size less its taskbar."""
    where = f"preferences.json[main_upper] {KEY}"
    v = (page or {}).get(KEY)
    if v is None:
        raise HostScreenError(f"{where} is not set: it must be {{\"size\": [width, height], \"taskbar\": px}}, the "
                              "layout hosts' screen the panel and desk windows are sized from")
    if not isinstance(v, dict) or set(v) != {"size", "taskbar"}:
        raise HostScreenError(f"{where} must be an object with exactly the keys size and taskbar, not {v!r}")
    size, taskbar = v["size"], v["taskbar"]
    if not (isinstance(size, list) and len(size) == 2 and all(_whole(n) for n in size)):
        raise HostScreenError(f"{where} size must be [width, height], two whole px above zero, not {size!r}")
    if not (isinstance(taskbar, int) and not isinstance(taskbar, bool) and 0 <= taskbar < size[1]):
        raise HostScreenError(f"{where} taskbar must be whole px, 0 or more and less than the height "
                              f"{size[1]}, not {taskbar!r}")
    return size[0], size[1] - taskbar


def apply(opts: dict, sections: dict, page: str) -> dict:
    """`opts` (changed in place, and returned) with le_window and cats_window set to window(sections[page]).
    `sections` is preferences.json as written ({section: its preferences}, notes starting with _ skipped). Stops when
    any section sets either key itself, or when `opts` holds one that this module did not set (a preference merged in
    from somewhere else, such as a sheet.preferences.json)."""
    own = sorted(f"{name}.{k}" for name, body in sections.items() if not name.startswith("_") and isinstance(body, dict)
                 for k in DERIVED if body.get(k) is not None)
    if own:
        raise HostScreenError(f"preferences.json sets {', '.join(own)}: le_window and cats_window come from "
                              f"{page}'s {KEY} (tools/schematic/host_screen.py); remove them there")
    if page not in sections or not isinstance(sections[page], dict):
        raise HostScreenError(f"preferences.json has no section {page!r}, which holds {KEY}")
    w, h = window(sections[page])
    _held, ours = _applied.get(id(opts), (None, None))
    stray = [k for k in DERIVED if opts.get(k) is not None and (_held is not opts or opts[k] != ours)]
    if stray:
        raise HostScreenError(f"the solved page options hold {', '.join(f'{k} {opts[k]!r}' for k in stray)}, which "
                              f"did not come from {KEY}: find where it is set (a merged preferences file) and remove it")
    for k in DERIVED:
        opts[k] = [w, h]
    _applied[id(opts)] = (opts, [w, h])
    return opts
