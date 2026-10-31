"""Output folder for the helix fixture scripts: --out DIR, default docs/benchwork/helix/stl/."""
import argparse
from pathlib import Path

STL_DIR = Path(__file__).resolve().parents[1] / "stl"


def out_dir(doc=None):
    """Parse --out and return it as a string ending in "/" (the scripts join names onto it)."""
    parser = argparse.ArgumentParser(description=(doc or "").strip().split("\n", 1)[0] or None)
    parser.add_argument("--out", type=Path, default=STL_DIR, help="output folder (default %(default)s)")
    out = parser.parse_args().out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    return f"{out}/"
