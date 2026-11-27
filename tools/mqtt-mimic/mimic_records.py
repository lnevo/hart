"""The records of the mimic page's layout JSON (/api/layout, and mimic_layout.json for the JMRI-hosted page).

lcos_mqtt_mimic.load_layout builds them; mimic_bus.Bus and mimic_http.make_handler read them.
"""
from __future__ import annotations

from typing import NotRequired, TypedDict


class Block(TypedDict):
    """An occupancy detector on the page (JSON). A virtual one (main, upper) is set in JMRI directly."""
    addr: str
    label: str
    userName: str
    comment: str
    plant: str
    level: str
    name: str
    virtual: NotRequired[bool]


class Turnout(TypedDict):
    """A switch on the page (JSON): its feedback sensors' addresses when it has two (TWOSENSOR)."""
    addr: str
    label: str
    num: NotRequired[int]       # staging only: the number in its user name
    plant: str
    feedback: str
    n_addr: str | None
    r_addr: str | None
    tip: str
    level: str
    name: str
    virtual: NotRequired[bool]


class Head(TypedDict):
    """A signal head on the page (JSON), by its MQTT topic leaf."""
    id: str
    systemName: str
    mast: str
    plant: str
    level: str


class Layout(TypedDict):
    blocks: list[Block]
    turnouts: list[Turnout]
    heads: list[Head]
