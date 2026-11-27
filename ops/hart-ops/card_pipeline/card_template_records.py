"""The records the card builders fill a sticker slot from, keyed as the mail-merge fields are.

``CardRecord`` is an equipment or train card (build_card), ``WaybillCardRecord`` a spot waybill card
(build_waybill_card) and ``CcLabelRecord`` a CC/WB shipment label (build_cc_waybill_label). Every value is text, as
the merge fields and the waybill CSV hold it.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import NotRequired, TypedDict


class CardRecord(TypedDict):
    """An equipment card's four fields; a train card also sets Blank and lists its work orders."""

    Type: str
    RoadName: str
    RoadNumber: str
    Description: str
    Blank: NotRequired[str]
    Orders: NotRequired[list[str]]


class WaybillCardRecord(TypedDict, total=False):
    """The fields of one spot waybill (waybill_deck builds them) that the card prints or reads its kind from.

    A record with no RouteFrom gives the card its Route, and one with no RouteChain its RouteVia.
    """

    Industry: str
    Usage: str
    Commodity: str
    Flow: str
    CardKind: str
    Spots: str
    CarType: str
    LoadSummary: str
    Route: str
    RouteFrom: str
    RouteTo: str
    RouteChain: str
    RouteVia: str


class CcLabelRecord(TypedDict, total=False):
    """One CC/WB shipment label: an empty bill (to the loading spot) or a freight bill (to the unloading spot)."""

    BillKind: str
    ShipmentCode: str
    ToLocation: str
    Station: str
    Track: str
    Spot: str
    Flow: str
    CarCode: str
    Consignment: str
    FromLocation: str
    FromStation: str
    Color: str
    Description: str
    Special: str
    LogoParty: str
    LogoPath: str


# A waybill deck card (waybill_deck) carries more fields than the card prints, so the builders take either.
WaybillSource = WaybillCardRecord | Mapping[str, str]
