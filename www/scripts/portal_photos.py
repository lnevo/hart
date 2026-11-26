"""The photo group of the site build: logos and photos copied in from the gitignored mirrors and resized (stages 4
and 5), hub card thumbnails and WebP companions (stages 10 and 11), the cache of resized JPEGs, and the saved run
of the whole group that a later build reuses when its inputs are unchanged.

Part of the site build, prepare_github_pages.py, which re-exports these names.
"""

from __future__ import annotations

import functools
import hashlib
import html
import inspect
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import portal_common
import share_cards
from portal_common import MIRROR_PREFIXES, PORTAL, PortalBuildError, _manifest, _source

PILLOW_HINT = "Pillow is not installed (python3 -m pip install Pillow)"


class PillowMissing(PortalBuildError):
    """A photo step needs Pillow and it is not installed."""


def have_pillow() -> bool:
    """True when Pillow can be imported."""
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def _require_pillow(step: str) -> None:
    """Raise PillowMissing, naming the step, when Pillow is not installed."""
    if not have_pillow():
        raise PillowMissing(f"{step}: {PILLOW_HINT}")


def _keep_src(src: str, dest_root: Path) -> bool:
    if not src or src.startswith("../"):
        return False
    if src.startswith("http://") or src.startswith("https://"):
        return True
    return (dest_root / src).is_file()


PHOTO_DATA = ("data/gallery.json", "data/fleet-gallery.json", "data/archive.json")


def _missing_mirrors(portal: Path = PORTAL) -> list[str]:
    """Public photo items whose ../ mirror original is not on this machine, plus Pillow if absent.

    The mirrors (media/, ops/car-cards/) are gitignored and live only in the main
    checkout, so a git worktree builds without them and every such photo drops out.
    """
    missing = []
    if not have_pillow():
        missing.append("Pillow (python3 -m pip install Pillow)")
    for rel in PHOTO_DATA:
        path = portal / rel
        if not path.is_file():
            continue
        for item in json.loads(path.read_text(encoding="utf-8")).get("items") or []:
            src = str(item.get("src") or "")
            if item.get("public") is False or item.get("bucket", "curated") != "curated":
                continue
            if src.startswith("../") and not (portal / src).resolve().is_file():
                missing.append(f"{rel}: {src}")
    return missing


def _filter_gallery(path: Path, dest_root: Path) -> None:
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    kept = [
        item
        for item in (data.get("items") or [])
        if _keep_src(str(item.get("src") or ""), dest_root)
    ]
    data["items"] = kept
    albums = []
    for album in data.get("albums") or []:
        count = sum(1 for item in kept if item.get("album") == album.get("id"))
        if count:
            album = dict(album)
            album["count"] = count
            albums.append(album)
    data["albums"] = albums
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _vendor_fleet_images(path: Path, dest_root: Path, max_px: int = 1600, subdir: str = "fleet") -> None:
    """Copy ../external/ gallery photos (rolling stock, layout) into the tree as web-sized JPEGs.

    The originals (~150 MB of 2200 px PNG/JPEG) live in gitignored mirrors, so this
    only fills in when the mirrors are present; otherwise _filter_gallery drops those
    items. Raises PillowMissing without Pillow.
    """
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data.get("items") or []:
        src_rel = str(item.get("src") or "")
        if not src_rel.startswith(MIRROR_PREFIXES):
            continue
        src = _source(src_rel)
        if not src.is_file():
            continue
        album = re.sub(r"[^a-z0-9]+", "-", str(item.get("album") or "misc").lower())
        rel = Path("assets") / subdir / album / f"{src.stem}.jpg"
        _web_jpeg(src, dest_root / rel, max_px)
        item["src"] = rel.as_posix()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# Resized photos are kept in a cache folder between builds: re-encoding the ~530 photos took ~27 s of every build.
# It is <main checkout>/.cache/hart/web-jpeg (HART_CACHE_DIR moves the base), shared by every worktree.
# HART_WEB_JPEG_CACHE=<folder> moves it, HART_WEB_JPEG_CACHE= (empty) turns it off. The key holds the source of
# _render_jpeg, so a change to how photos are drawn never reuses copies drawn the old way.
JPEG_CACHE_ENV = "HART_WEB_JPEG_CACHE"
JPEG_CACHE_KEEP_DAYS = 60
_CACHED_NAME = re.compile(r"^[0-9a-f]{64}(\.jpg|\.\d+\.tmp)$")   # only these are the cache's own files


def _jpeg_cache() -> Path | None:
    """The resized-photo cache folder, or None when it is turned off or cannot be made (said once on stderr)."""
    return _jpeg_cache_at(os.environ.get(JPEG_CACHE_ENV))


@functools.lru_cache(maxsize=None)
def _jpeg_cache_at(value: str | None) -> Path | None:
    if value is not None and not value.strip():
        return None
    if value:
        path = Path(value).expanduser()
    else:                         # the shared default, resolved only now (hartlib needs git)
        sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                        if (p / "tools/hartlib/src").is_dir()][:1]
        from hartlib import paths as hart_paths
        path = hart_paths.cache_dir("web-jpeg")
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.chmod(0o700)            # resized copies of mirror-only originals: private to this user
    except OSError as exc:
        print(f"{JPEG_CACHE_ENV}: cannot use {path} ({exc}); resizing every photo", file=sys.stderr)
        return None
    return path


@functools.lru_cache(maxsize=None)
def _render_key() -> bytes:
    """What decides how a photo is drawn: _render_jpeg's own source and Pillow's version."""
    import PIL

    return f"{_RENDER_SOURCE}|{PIL.__version__}".encode()


def _web_jpeg(src: Path, out: Path, max_px: int) -> None:
    """Write a resized JPEG; raises PillowMissing without Pillow. A photo resized before from the same bytes, size
    and drawing code is copied from the cache."""
    _require_pillow(f"resizing {src.name}")
    out.parent.mkdir(parents=True, exist_ok=True)
    cache = _jpeg_cache()
    if cache is None:
        _render_jpeg(src, out, max_px)
        return
    h = hashlib.sha256(_render_key() + f"|{max_px}|".encode())
    with open(src, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    kept = cache / f"{h.hexdigest()}.jpg"
    try:
        shutil.copyfile(kept, out)   # a fresh time stamp on the output, so rsync never passes over a changed photo
        os.utime(kept)               # last use, for pruning
        return
    except FileNotFoundError:        # not cached yet, or pruned by a build running at the same time
        pass
    tmp = kept.with_name(f"{kept.stem}.{os.getpid()}.tmp")
    try:
        _render_jpeg(src, tmp, max_px)
        os.replace(tmp, kept)        # atomic: a parallel build never reads half a file
    finally:
        tmp.unlink(missing_ok=True)
    shutil.copyfile(kept, out)


def _prune_jpeg_cache(keep_days: int = JPEG_CACHE_KEEP_DAYS) -> None:
    """Remove the cache's own files no build has used in keep_days (photos replaced or dropped from the site).
    Other files in the folder are left alone."""
    cache = _jpeg_cache()
    if cache is None:
        return
    cutoff = datetime.now().timestamp() - keep_days * 86400
    for f in cache.iterdir():
        if not _CACHED_NAME.match(f.name):
            continue
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except FileNotFoundError:
            pass


def _render_jpeg(src: Path, out: Path, max_px: int) -> None:
    from PIL import Image

    with Image.open(src) as im:
        im.seek(0)  # first frame of an animated GIF/WebP
        if im.mode in ("RGBA", "LA", "P"):
            rgba = im.convert("RGBA")
            im = Image.new("RGB", rgba.size, (255, 255, 255))
            im.paste(rgba, mask=rgba.getchannel("A"))
        else:
            im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        im.save(out, "JPEG", quality=82, optimize=True, progressive=True)


_RENDER_SOURCE = inspect.getsource(_render_jpeg)   # read once, as written: part of every cache key


def _gallery_thumbs(path: Path, dest_root: Path, subdir: str, thumb_px: int = 640) -> None:
    """Give every local gallery image a grid thumbnail (assets/<subdir>/thumbs/) and its full size.

    Pages show item["thumb"] in the grid and open item["src"]; width/height let them
    reserve space before the image loads. Raises PillowMissing without Pillow.
    """
    if not path.is_file():
        return
    _require_pillow(f"thumbnails for {path.name}")
    from PIL import Image

    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data.get("items") or []:
        src_rel = str(item.get("src") or "")
        src = dest_root / src_rel
        if not src_rel or src_rel.startswith(("http://", "https://", "../")) or not src.is_file():
            continue
        album = re.sub(r"[^a-z0-9]+", "-", str(item.get("album") or "misc").lower())
        thumb = Path("assets") / subdir / "thumbs" / album / f"{src.stem}.jpg"
        try:
            with Image.open(src) as im:
                item["width"], item["height"] = im.size
        except OSError:  # not an image Pillow reads (e.g. SVG)
            continue
        _web_jpeg(src, dest_root / thumb, thumb_px)
        item["thumb"] = thumb.as_posix()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


ARCHIVE_MAX_PX = 6000  # the largest web copy an archive item may ask for


def _archive_px(asked, default: int, name: str = "") -> int:
    """An item's own "max_px", kept between the default and ARCHIVE_MAX_PX; the default when unset.
    A value that is not a whole number, or falls outside those limits, is reported on stderr."""
    if asked is None:
        return default
    try:
        px = int(asked)
    except (TypeError, ValueError):
        px = None
    used = default if px is None else max(default, min(px, ARCHIVE_MAX_PX))
    if px != used:
        print(f"archive: {name or '?'} max_px {asked!r} not usable; using {used}", file=sys.stderr)
    return used


def _vendor_archive_images(
    path: Path, dest_root: Path, max_px: int = 1600, thumb_px: int = 640, resize: bool = True
) -> None:
    """Resize historical-archive images from ../external/ mirrors into assets/archive/.

    Every item gets a small grid thumbnail; mirror-only originals also get a web-sized
    copy, max_px on its long side. An item that sets its own "max_px" (a map or drawing
    meant to be zoomed into) also gets item["full"], a larger copy that only the lightbox's
    open-full link loads, so pages never fetch it on their own. Items marked "public": false or whose original is missing (no mirrors)
    are dropped, and local-only
    fields (PDF paths, where the owner found the file) are stripped. With resize False (no Pillow) mirror-only
    items are dropped and no item gets a thumbnail.
    """
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    kept = []
    for item in data.get("items") or []:
        if item.get("public") is False:  # rights not cleared; local review only
            continue
        if item.get("bucket", "curated") != "curated":  # review/discard stay on the engineering desk
            continue
        src_rel = str(item.get("src") or "")
        src = _source(src_rel)
        if not src_rel or not src.is_file():
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", str(item.get("id") or src.stem).lower()).strip("-")
        size = _archive_px(item.pop("max_px", None), max_px, slug)
        if src_rel.startswith("../"):
            if not resize:
                continue
            rel = Path("assets") / "archive" / f"{slug}.jpg"
            _web_jpeg(src, dest_root / rel, max_px)
            item["src"] = rel.as_posix()
            if size > max_px:
                full = Path("assets") / "archive" / "full" / f"{slug}.jpg"
                _web_jpeg(src, dest_root / full, size)
                item["full"] = full.as_posix()
        if resize:
            thumb = Path("assets") / "archive" / "thumbs" / f"{slug}.jpg"
            _web_jpeg(src, dest_root / thumb, thumb_px)
            item["thumb"] = thumb.as_posix()
        if str(item.get("pdf") or "").startswith("../"):
            item.pop("pdf")
        item.pop("origin", None)
        kept.append(item)
    data["items"] = kept
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _vendor_logo(logo: str, dest_root: Path) -> str:
    """Copy one ../external/ logo into assets/logos/ and return its public path ("" if missing)."""
    src = _source(logo)
    if not src.is_file():
        return ""
    rel = Path("assets") / "logos" / src.name
    out = dest_root / rel
    if out.exists() and out.read_bytes() != src.read_bytes():
        # Same file name from another folder (e.g. operator_logos/ and downloads/).
        rel = Path("assets") / "logos" / f"{src.parent.name}-{src.name}"
        out = dest_root / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, out)
    return rel.as_posix()


def _vendor_logos_in(node: object, dest_root: Path) -> None:
    """Rewrite every "logo" field under node that points into ../external/."""
    if isinstance(node, dict):
        logo = node.get("logo")
        if isinstance(logo, str) and logo.startswith("../"):
            node["logo"] = _vendor_logo(logo, dest_root)
        for value in node.values():
            _vendor_logos_in(value, dest_root)
    elif isinstance(node, list):
        for value in node:
            _vendor_logos_in(value, dest_root)


def _vendor_json_logos(path: Path, dest_root: Path) -> None:
    """Copy ../external/ logos named in a data file into the tree; the public site has no external/ mirror."""
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    _vendor_logos_in(data, dest_root)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _card_thumbs(dest_root: Path) -> None:
    """Hub cards in a grid marked data-card-thumbs show the linked page's share picture.

    The pictures are small copies of the share cards (assets/share/thumbs/). Raises PillowMissing without Pillow.
    """
    _require_pillow("card thumbnails")
    cards, links = share_cards.load(), share_cards.load_links()
    for page in dest_root.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        if "data-card-thumbs" not in text:
            continue
        new, thumbs = share_cards.add_card_thumbs(text, page.relative_to(dest_root), cards, links)
        for thumb, image in thumbs.items():
            if not (dest_root / thumb).is_file():
                _web_jpeg(dest_root / image, dest_root / thumb, share_cards.THUMB_PX)
        if thumbs:
            page.write_text(new, encoding="utf-8")


_WEBP_MIN_BYTES = 200_000   # JPEGs over this get a WebP companion
_IMG_TAG = re.compile(r"<img\b[^>]*>")
_IMG_SRC = re.compile(r"""(?<![\w-])src=(["'])([^"']+?\.jpe?g)\1""", re.I)
_IMG_SKIP = re.compile(r"""(?<![\w-])(?:srcset|sizes|data-src)=""", re.I)


def _webp_companions(dest_root: Path) -> int:
    """Serve large JPEGs as WebP where the page names them in a static <img>: write <name>.webp beside the JPEG
    and wrap the tag in <picture> with the JPEG as the fallback. Images a script builds, tags already inside a
    <picture> and photos where WebP is not at least 15% smaller are left alone. Returns the bytes saved.
    Raises PillowMissing without Pillow."""
    _require_pillow("WebP companions")
    from PIL import Image, ImageOps
    made: dict[Path, int] = {}      # JPEG -> bytes saved (0 when WebP did not pay)
    for page in sorted(dest_root.rglob("*.html")):
        text = page.read_text(encoding="utf-8")
        if "<img" not in text:
            continue

        def wrap(m: re.Match, page: Path = page, text: str = text) -> str:
            tag = m.group(0)
            src = _IMG_SRC.search(tag)
            if not src or _IMG_SKIP.search(tag) or "<picture" in text[max(0, m.start() - 200):m.start()].rsplit("</picture>", 1)[-1]:
                return tag
            ref = src.group(2)
            if re.match(r"[a-z][a-z0-9+.-]*:|//|[?#]", ref, re.I) or "'" in ref or "+" in ref:
                return tag
            base = dest_root if ref.startswith("/") else page.parent
            jpg = (base / ref.lstrip("/")).resolve()
            if dest_root.resolve() not in jpg.parents or not jpg.is_file() or jpg.stat().st_size < _WEBP_MIN_BYTES:
                return tag
            webp = jpg.with_suffix(".webp")
            if jpg not in made:
                if webp.exists():   # a WebP already in the tree is the author's: never overwrite or delete it
                    made[jpg] = 0
                    return tag
                with Image.open(jpg) as im:
                    icc = im.info.get("icc_profile")
                    out = ImageOps.exif_transpose(im).convert("RGB")
                    out.save(webp, "WEBP", quality=78, method=6, **({"icc_profile": icc} if icc else {}))
                gain = jpg.stat().st_size - webp.stat().st_size
                if gain < jpg.stat().st_size * 0.15:
                    webp.unlink()
                    gain = 0
                made[jpg] = gain
            if not made[jpg]:
                return tag
            return f'<picture><source srcset="{html.escape(Path(ref).with_suffix(".webp").as_posix())}" type="image/webp">{tag}</picture>'

        new = _IMG_TAG.sub(wrap, text)
        if new != text:
            page.write_text(new, encoding="utf-8")
    return sum(made.values())


def _vendor_logos(dest: Path) -> None:
    """Stage 4: copy the ../external/ logos named in the industry and lineage data into assets/logos/."""
    _vendor_json_logos(dest / "data" / "industries.json", dest)
    for lineage in sorted((dest / "data").glob("*-lineage.json")):  # Who became who charts
        _vendor_json_logos(lineage, dest)


def _vendor_photos(dest: Path, resize: bool = True) -> None:
    """Stage 5: vendor, filter and thumbnail the gallery, fleet and archive photos (in this order per file).

    With resize False (no Pillow) nothing is resized: mirror-only photos drop out and no item gets a thumbnail.
    """
    for name, subdir in (("gallery.json", "gallery"), ("fleet-gallery.json", "fleet")):
        path = dest / "data" / name
        if resize:
            _vendor_fleet_images(path, dest, subdir=subdir)
        _filter_gallery(path, dest)
        if resize:
            _gallery_thumbs(path, dest, subdir)
    _vendor_archive_images(dest / "data" / "archive.json", dest, resize=resize)


NO_PILLOW_EARLY = (
    f"WARNING: {PILLOW_HINT}, so this build has no gallery, fleet or archive thumbnails and no photo from the "
    "mirrors (a deploy, --require-mirrors, stops on this)"
)
NO_PILLOW_LATE = f"WARNING: {PILLOW_HINT}, so no card thumbnails or WebP companions were made"


# The photo group (logos, photo vendor/filter/thumbs/archive, card thumbs, WebP) reads every original and re-encodes
# the large JPEGs, which is most of a build. Its outputs are saved under the JPEG cache after a full run, with a stamp
# of its inputs; a later build whose stamp matches copies them back and reads no original. The text group (copy,
# page fills, scrubs, head tags, provenance, leak check, search) always runs. Any doubt runs the photo group in full.
# PHOTO_CODE_VERSION: bump it when the group's output changes in a way its source text does not show.
PHOTO_CODE_VERSION = "1"
PHOTO_STORE = "photo-group"
_PHOTO_JSON = ("data/industries.json", "data/gallery.json", "data/fleet-gallery.json", "data/archive.json")
# The code the photo group runs, whole files: this one (every stage and helper of the group), portal_common.py (the
# manifest lookups and mirror prefixes it resolves sources with) and share_cards.py (the card thumbs). An edit to any
# of them misses the stamp, helpers included, so a saved run is never reused under changed code.
PHOTO_CODE_FILES = (Path(__file__), Path(portal_common.__file__), Path(share_cards.__file__))


@functools.lru_cache(maxsize=None)
def _photo_code_key() -> str:
    """The version constant, the bytes of PHOTO_CODE_FILES and the drawing key, so editing any of that code misses the
    stamp."""
    h = hashlib.sha256(PHOTO_CODE_VERSION.encode())
    for path in PHOTO_CODE_FILES:
        h.update(f"|{path.name}|".encode())
        h.update(path.read_bytes())
    if have_pillow():
        h.update(_render_key())
    else:                    # no Pillow: _photo_load says so and the photo stages run without resizing
        h.update(b"no-pillow")
    return h.hexdigest()


def _named_sources(node: object):
    """Every source file a data file names: src, thumb and pdf (mirror or site-local, not a URL) and logo ("../")."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and value:
                if key == "logo" and value.startswith("../"):
                    yield value
                elif key in ("src", "thumb", "pdf") and not value.startswith(("http://", "https://")):
                    yield value
            else:
                yield from _named_sources(value)
    elif isinstance(node, list):
        for value in node:
            yield from _named_sources(value)


def _early_stamp(dest: Path) -> str:
    """Hash of what the logo and photo stages read: the data files as copied into dest, the manifest, the code, and
    the path, size, mtime, inode and ctime of every file those data files name (missing ones too)."""
    h = hashlib.sha256(_photo_code_key().encode())
    files = [dest / rel for rel in _PHOTO_JSON] + sorted((dest / "data").glob("*-lineage.json"))
    named: set[str] = set()
    for f in files:
        h.update(f.name.encode())
        if f.is_file():
            raw = f.read_bytes()
            h.update(raw)
            named.update(_named_sources(json.loads(raw)))
    h.update(json.dumps(_manifest(), sort_keys=True).encode())
    for rel in sorted(named):
        try:
            src = _source(rel)
            st = src.stat()
            h.update(f"|{rel}:{src}:{st.st_size}:{st.st_mtime_ns}:{st.st_ino}:{st.st_ctime_ns}".encode())
        except OSError:
            h.update(f"|{rel}:missing".encode())
    return h.hexdigest()


def _tree_state(dest: Path) -> dict[str, tuple[int, int]]:
    state = {}
    for p in dest.rglob("*"):
        if p.is_file():
            st = p.stat()
            state[p.relative_to(dest).as_posix()] = (st.st_size, st.st_mtime_ns)
    return state


def _photo_store(part: str) -> Path | None:
    cache = _jpeg_cache()
    return cache / PHOTO_STORE / part if cache is not None else None


def _photo_load(part: str, stamp: str, full: bool) -> tuple[Path, dict] | str:
    """The saved output of one part when its stamp matches, else the reason it cannot be reused."""
    if not have_pillow():
        return "Pillow is missing"
    if full:
        return "--full"
    store = _photo_store(part)
    if store is None:
        return "the photo cache is off"
    try:
        meta = json.loads((store / "stamp.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "no saved run"
    except (OSError, ValueError):
        return "saved stamp unreadable"
    if not isinstance(meta, dict) or meta.get("stamp") != stamp:
        return "inputs changed"
    files = meta.get("files")
    if not isinstance(files, dict) or any(
        not (store / "files" / rel).is_file() or (store / "files" / rel).stat().st_size != size for rel, size in files.items()
    ):
        return "saved files incomplete"
    return store, meta


def _photo_restore(store: Path, meta: dict, dest: Path) -> None:
    for rel in meta["files"]:
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(store / "files" / rel, out)   # fresh time stamp, as _web_jpeg does


def _photo_save(part: str, stamp: str, dest: Path, before: dict, extra: dict | None = None) -> None:
    """Keep the files a part added or rewrote in dest, with the stamp, replacing the last saved run."""
    store = _photo_store(part)
    if store is None or not have_pillow():   # a run without Pillow is never saved for reuse
        return
    after = _tree_state(dest)
    changed = sorted(rel for rel, st in after.items() if before.get(rel) != st)
    tmp = store.with_name(f"{store.name}.{os.getpid()}.tmp")
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        for rel in changed:
            out = tmp / "files" / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(dest / rel, out)
        meta = {"stamp": stamp, "files": {rel: after[rel][0] for rel in changed}, **(extra or {})}
        (tmp / "stamp.json").write_text(json.dumps(meta), encoding="utf-8")
        store.parent.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(store, ignore_errors=True)
        os.replace(tmp, store)
    except OSError as exc:
        print(f"photo stages: could not save this run for reuse ({exc})", file=sys.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _photo_early(dest: Path, full: bool) -> tuple[str, set[str], bool]:
    """Logos and photos (stages 4 and 5), reused when the stamp matches. Returns the stamp, the files it wrote and
    whether the saved run was reused."""
    stamp = _early_stamp(dest)
    got = _photo_load("early", stamp, full)
    if isinstance(got, tuple):
        store, meta = got
        _photo_restore(store, meta, dest)
        print(f"photo stages: reused the saved run ({len(meta['files'])} files), no original read")
        return stamp, set(meta["files"]), True
    print(f"photo stages: full run ({got})")
    before = _tree_state(dest)
    _vendor_logos(dest)
    resize = have_pillow()
    if not resize:
        print(NO_PILLOW_EARLY, file=sys.stderr)
    _vendor_photos(dest, resize)
    _photo_save("early", stamp, dest, before)
    after = _tree_state(dest)
    return stamp, {rel for rel, st in after.items() if before.get(rel) != st}, False


def _late_stamp(dest: Path, early_stamp: str, early_files: set[str]) -> str:
    """Card thumbs and WebP read the finished pages and the JPEGs: hash every file but the photos the early stamp covers."""
    h = hashlib.sha256(_photo_code_key().encode())
    h.update(f"|{early_stamp}|{portal_common.SITE_URL}|".encode())
    if share_cards.CARDS.is_file():
        h.update(share_cards.CARDS.read_bytes())   # the cards and links _card_thumbs reads
    for p in sorted(dest.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(dest).as_posix()
        if rel in early_files and p.suffix.lower() != ".json":
            continue
        h.update(f"|{rel}|".encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def _photo_late(dest: Path, early_stamp: str, early_files: set[str], full: bool) -> None:
    """Card thumbs and WebP (stages 10 and 11), reused when the pages and photos they read are unchanged."""
    stamp = _late_stamp(dest, early_stamp, early_files)
    got = _photo_load("late", stamp, full)
    if isinstance(got, tuple):
        store, meta = got
        _photo_restore(store, meta, dest)
        print(f"WebP companions: {meta['saved'] // 1024} KB smaller than the JPEGs they stand beside")
        return
    print(f"photo stages, card thumbs and WebP: full run ({got})")
    before = _tree_state(dest)
    if have_pillow():
        _card_thumbs(dest)
        saved = _webp_companions(dest)
        print(f"WebP companions: {saved // 1024} KB smaller than the JPEGs they stand beside")
    else:
        print(NO_PILLOW_LATE, file=sys.stderr)
        saved = 0
    _photo_save("late", stamp, dest, before, {"saved": saved})
