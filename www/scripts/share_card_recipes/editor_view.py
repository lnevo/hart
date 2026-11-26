"""The ai-electronics share card: lines of the LCOS bridge source drawn as an editor view.

A recipe module of make_share_cards.py, which lists the cards (CARDS) and runs them."""

from __future__ import annotations

import html
import re

import make_share_cards as kit
from make_share_cards import REPO
from share_card_recipes import CardError


# ---- Editor view of the bridge code -----------------------------------------------------------

_KEYWORDS = r"\b(static|bool|const|char|byte|if|return|true|false|NULL|void|uint16_t)\b"
_TOKEN = re.compile(r'"[^"]*"|\'[^\']*\'|\b[A-Z][A-Z0-9_]{3,}\b|\b[A-Za-z_]\w*(?=\()|' + _KEYWORDS + r"|\b\d+\b")


def _highlight(line: str) -> str:
    if re.match(r"\s*(/\*\*|\*/)|^ \*( |$)", line):  # doc comment lines; "  *aspect_out = …" is code
        return f"<span class=c>{html.escape(line)}</span>"
    out, i = [], 0
    for m in _TOKEN.finditer(line):
        token = m.group(0)
        cls = ("s" if token[0] in "\"'" else "k" if re.fullmatch(_KEYWORDS, token)
               else "n" if token.isdigit() else "K" if token.isupper() else "f")
        out += [html.escape(line[i:m.start()]), f"<span class={cls}>{html.escape(token)}</span>"]
        i = m.end()
    return "".join(out) + html.escape(line[i:])


BRIDGE_SOURCE = "external/lcos-bridge/lcos_mqtt_bridge.cpp"
SHOWN_FUNCTION = "appearanceToLcosAspect"  # the signal colour to aspect function
CODE_ROWS = 25  # rows the code area holds: (630 - 46 - 24) px at 22 px a row


def function_lines(src: list[str], name: str) -> tuple[int, int]:
    """The 1-based first and last line of C function `name` in `src`: from the doc comment just above its definition
    to the brace that closes it at the start of a line. Raises CardError when the function is not there once."""
    heads = [i for i, line in enumerate(src) if re.match(rf"\s*(?:static\s+)?[\w\s\*]+\b{name}\s*\(", line)
             and not line.rstrip().endswith(";")]
    if len(heads) != 1:
        raise CardError(f"ai-electronics: {BRIDGE_SOURCE} defines {name}() {len(heads)} times, not once; "
                        "name another function in SHOWN_FUNCTION")
    first = heads[0]
    if first > 0 and src[first - 1].strip() == "*/":
        while first > 0 and not src[first].lstrip().startswith("/**"):
            first -= 1
    end = next((i for i in range(heads[0], len(src)) if src[i].startswith("}")), None)
    if end is None:
        raise CardError(f"ai-electronics: {name}() in {BRIDGE_SOURCE} has no closing brace at the start of a line")
    return first + 1, end + 1


def shown_lines(src: list[str], name: str, rows: int = CODE_ROWS) -> tuple[int, int]:
    """function_lines of `name`, cut to the `rows` the code area holds: a longer function runs off the bottom edge,
    as it would in an editor, instead of drawing under the status bar."""
    first, last = function_lines(src, name)
    return first, min(last, first + rows - 1)


def ai_electronics():
    """ai-electronics: lines of external/lcos-bridge/lcos_mqtt_bridge.cpp (the signal colour to
    aspect function) drawn as an editor view. Needs the lcos-bridge submodule."""
    path = REPO / BRIDGE_SOURCE
    if not path.is_file():
        raise CardError(f"ai-electronics: {BRIDGE_SOURCE} is missing; run git submodule update --init external/lcos-bridge")
    src = path.read_text(encoding="utf-8").splitlines()
    first, last = shown_lines(src, SHOWN_FUNCTION)
    at = next(n for n in range(first, last + 1) if SHOWN_FUNCTION in src[n - 1])  # the cursor, on the definition
    rows = "".join(f"<div class=l><span class=g>{n}</span>{_highlight(src[n - 1]) or ' '}</div>" for n in range(first, last + 1))
    files = ["lcos-bridge.ino", "lcos_mqtt_bridge.cpp", "lcos_mqtt_bridge.h", "mqtt_serial.cpp", "mqtt_serial.h",
             "gateways.h", "serial_to_mqtt.py", "README.md"]
    side = "".join(f'<div class="fi{" on" if f == "lcos_mqtt_bridge.cpp" else ""}">{f}</div>' for f in files)
    style = (
        'body{background:#1e1e1e;color:#d4d4d4;font:13px -apple-system,"Segoe UI",sans-serif}'
        ".side{position:absolute;left:0;top:0;width:205px;height:630px;background:#252526;border-right:1px solid #111}"
        ".side h4{margin:0;padding:13px 16px 9px;font-size:11px;letter-spacing:.09em;color:#bbb;font-weight:600}"
        ".rp{padding:4px 16px 8px;font-weight:700;font-size:12px;color:#ccc}"
        ".fi{padding:5px 16px 5px 28px;color:#c5c5c5;font-size:13.5px}.fi.on{background:#094771;color:#fff}"
        ".tabs{position:absolute;left:206px;top:0;right:0;height:38px;background:#2d2d2d}"
        ".tab{display:inline-block;height:38px;line-height:38px;padding:0 18px;background:#1e1e1e;"
        "border-top:2px solid #0a84c1;box-sizing:border-box;color:#fff;font-size:13.5px}"
        ".code{position:absolute;left:206px;top:46px;right:0;bottom:24px;font:16px/22px Menlo,Monaco,Consolas,monospace;white-space:pre}"
        ".l{height:22px}.g{display:inline-block;width:52px;padding-right:18px;text-align:right;color:#858585}"
        ".c{color:#6a9955}.s{color:#ce9178}.k{color:#569cd6}.K{color:#4fc1ff}.f{color:#dcdcaa}.n{color:#b5cea8}"
        ".st{position:absolute;left:0;right:0;bottom:0;height:24px;background:#0a6aa1;color:#fff;font-size:12px;line-height:24px;padding:0 14px}"
    )
    body = (f"<div class=side><h4>EXPLORER</h4><div class=rp>LCOS-BRIDGE</div>{side}</div>"
            f"<div class=tabs><span class=tab>lcos_mqtt_bridge.cpp</span></div><div class=code>{rows}</div>"
            f"<div class=st>C++ &nbsp;·&nbsp; UTF-8 &nbsp;·&nbsp; Ln {at}, Col 1</div>")
    return kit.card(kit.draw("ide", body, style, ()))
