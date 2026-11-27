"""Share cards drawn as railroad paperwork: the train order, clearance and switching order of the exam and play pages.

Each form is a page of its own in paperwork/<card>.html: its <style> block, then the body that draws the paper.
`{site}` in a body is the address of the site this run serves, for a picture the form shows.

A recipe module of make_share_cards.py, which lists the cards (CARDS) and runs them."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import make_share_cards as kit
from share_card_recipes import CardError

if TYPE_CHECKING:
    from PIL import Image

PAPERWORK = Path(__file__).resolve().parent / "paperwork"
SITE = "{site}"
_PAGE = re.compile(r"<style>\n(.*\n)</style>\n(.*)\n", re.S)


class Form(NamedTuple):
    """A paperwork page as make_share_cards.draw takes it."""
    body: str
    style: str


def form(name: str, site: str) -> Form:
    """The style and body of paperwork/NAME.html, with SITE in place of `{site}`."""
    path = PAPERWORK / f"{name}.html"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CardError(f"{name}: no form at {path}") from exc
    page = _PAGE.fullmatch(text)
    if page is None or "</style>" in page.group(1):
        raise CardError(f"{name}: {path.name} is not one <style> block on its own lines, then the body")
    style, body = page.groups()
    return Form(body.replace(SITE, site), style)


def _drawn(name: str) -> Image.Image:
    return kit.card(kit.draw(name, *form(name, kit._site)))


# ---- Achievement Program, exam and play: drawn paperwork ---------------------------------------

def ap_exam() -> Image.Image:
    """ap-exam: a Form 19 train order on its green flimsy, running Engs C and E extra from the Study Guide to the Exam.

    The order follows Standard Code Form G ("Eng 99 run extra A to F") and a Form S-C wait, the rules the deck teaches."""
    return _drawn("ap-exam")


def ap_exam_run() -> Image.Image:
    """ap-exam-run: a Clearance Form A on the Kestrel Valley, clearing Extra 812 East at Ashby with two orders, stamped Extra East.

    The form follows Standard Code Rule 211: the number of orders and the number of each, then OK, the time and the dispatcher's initials."""
    return _drawn("ap-exam-run")


def play_neville() -> Image.Image:
    """play-neville: the game's switching orders for #105 on the P&OV, with the game's logo, stamped Extra East, on a desk lit like the coke works at dusk.

    Drawn in the manner of ap-exam-run; the P&OV's own form is not known, so the layout is the game's switch list on paper."""
    return _drawn("play-neville")
