#!/usr/bin/env python3
"""Copy the Operations Pro showcase walkthrough into the site.

    python3 www/scripts/build_opspro_guide.py          # write
    python3 www/scripts/build_opspro_guide.py --check  # exit 1 if stale

The master is GUIDE.md in the plugin (model-railroad-skills). The copy is
byte for byte, so the text is never edited here; www/library/opspro-showcase-guide.html
fetches it and draws it with js/md-view.js. Rerun after the plugin submodule moves.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "external/model-railroad-skills/plugins/operations-pro/examples/showcase/GUIDE.md"
OUT = ROOT / "www/library/opspro-showcase-guide.md"


def main():
    data = SRC.read_bytes()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_bytes() != data:
            sys.exit("www/library/opspro-showcase-guide.md is stale; run python3 www/scripts/build_opspro_guide.py")
        print("opspro-showcase-guide.md is current")
        return
    OUT.write_bytes(data)
    print("wrote %s (%d bytes)" % (OUT.relative_to(ROOT), len(data)))


if __name__ == "__main__":
    main()
