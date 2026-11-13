"""layers.py: read one level's input files, split by kind (see wiki/projects/schematic-maps-handoff.md).

    <level>.plan_overrides.json   layer 1  facts about the railroad (always read)
    <level>.hints.json            layer 2  TEMPORARY hand hints that stand in for generation rules not written yet
    <level>.preferences.json      layer 3  the owner's look for this sheet
    <level>.signals.json          layer 1  masts, generated from the Layout Editor panel (signal_reader.py)

Merged in that order: a dict merges key by key, a list is added to (edits keep their order), anything else is
replaced. Keys that start with "_" are notes and are dropped.
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[3] / "jmri" / "layouts" / "hart" / "data" / "schematic"


def merge(a, b):
    out = dict(a)
    for k, v in b.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        elif isinstance(v, list) and isinstance(out.get(k), list):
            out[k] = out[k] + v
        else:
            out[k] = v
    return out


def load(level, preferences=True, hints=True, data=DATA):
    """The options of one level (staging, main_upper) with the layers asked for."""
    opts = {}
    for kind, on in (("plan_overrides", True), ("hints", hints), ("preferences", preferences)):
        path = Path(data) / f"{level}.{kind}.json"
        if on and path.exists():
            opts = merge(opts, json.load(open(path)))
    sig = Path(data) / f"{level}.signals.json"      # layer 1 too, generated from the panel by signal_reader.py
    if sig.exists():
        opts["signals"] = json.load(open(sig))["signals"]
    return opts
