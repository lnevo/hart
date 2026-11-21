"""The layout hosts' screen, the one setting the Layout Editor panel's window and the CATS desks' window come from.

preferences.json[main_upper] (the page's preferences) holds `host_screen`: {"size": [width, height], "taskbar": px},
the screen the Pi and the Windows box both drive and the taskbar each keeps along one edge (its `_host_screen` note
records the measurement). The window a maximised panel opens in is that screen less the taskbar:

    host_screen.window(page)        (width, height - taskbar), checked
    host_screen.apply(opts, prefs)  opts (the solved page options) with le_window and cats_window set to the window
                                    of prefs (the preferences section as written), the names the schematic-maps
                                    plugin reads (le_prefs.window, cats_prefs.options)

publish_draft.solved_sheet() applies it to the solved sheet's page options, the one way the builders get them, so
build_layout_le.py and build_cats_panel.py both see the same window. Each tool keeps its own frame allowance inside
it, in the plugin: Layout Editor's 18 x 60 px (le_prefs), CATS's frame, title, menu and status lines (cats_prefs
CHROME). The page's preferences must not set le_window or cats_window themselves: they would be a second source.
"""
from __future__ import annotations

KEY = "host_screen"
DERIVED = ("le_window", "cats_window")


class HostScreenError(ValueError):
    """The host_screen setting is missing or malformed; the message names it and what it must be."""


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


def apply(opts: dict, prefs: dict) -> dict:
    """`opts` (changed in place, and returned) with le_window and cats_window set to window(prefs). `prefs` is the
    page's preferences section as written: it stops when that sets either key itself. `opts` may already hold them
    from an earlier apply (the plugin's cache can hand back the same sheet), so they are set, not checked."""
    own = [k for k in DERIVED if (prefs or {}).get(k) is not None]
    if own:
        raise HostScreenError(f"preferences.json[main_upper] sets {', '.join(own)}: they come from {KEY} "
                              "(tools/schematic/host_screen.py); remove them there")
    w, h = window(prefs)
    for k in DERIVED:
        opts[k] = [w, h]
    return opts
