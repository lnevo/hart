#!/usr/bin/env python3
"""Screenshot a page at desktop and phone width, so visual work can be checked.

    python3 tools/ops/screenshot.py www/index.html
    python3 tools/ops/screenshot.py https://www.hartrailroad.com/ --out /tmp/shots

A repo path is served locally, because portal pages fetch JSON and fail on
file:// URLs. A www/ page is built first, so it shows what a deploy would publish.
Uses headless Google Chrome and writes <name>-desktop.png and
<name>-phone.png. Read them back to check the result.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIZES = {"desktop": "1440,1000", "phone": "390,844"}
MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


def find_chrome() -> str:
    for name in (MAC_CHROME, "google-chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("Google Chrome not found")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("page", help="repo-relative path or http(s) URL")
    parser.add_argument("--out", default=tempfile.gettempdir(), help="folder for the images")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome()
    server = None
    url = args.page
    if "://" not in url:
        if not (ROOT / url).exists():
            raise SystemExit(f"no such page: {url}")
        site = ROOT
        if args.page.startswith("www/"):
            # Published images exist only in the build, as on the live site.
            build = tempfile.TemporaryDirectory()
            site = Path(build.name) / "dist"
            subprocess.run([sys.executable, str(ROOT / "www/scripts/prepare_github_pages.py"), str(site)],
                           check=True, capture_output=True)
        handler = functools.partial(Quiet, directory=str(site))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        path = args.page.removeprefix("www/")
        url = f"http://127.0.0.1:{server.server_address[1]}/{path}"

    name = Path(args.page.rstrip("/")).stem or "page"
    failed = 0
    with tempfile.TemporaryDirectory() as profile:
        for label, size in SIZES.items():
            target = out / f"{name}-{label}.png"
            subprocess.run(
                [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                 f"--user-data-dir={profile}", f"--window-size={size}",
                 "--virtual-time-budget=5000", f"--screenshot={target}", url],
                capture_output=True, timeout=60,
            )
            if target.is_file():
                print(target)
            else:
                print(f"no screenshot for {label}", file=sys.stderr)
                failed = 1
    if server:
        server.shutdown()
    return failed


if __name__ == "__main__":
    sys.exit(main())
