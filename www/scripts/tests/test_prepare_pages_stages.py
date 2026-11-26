"""prepare_github_pages.py, stage by stage: the behaviour a split of the build could break.

STAGE MAP (functions of prepare_github_pages.py; main() runs 1 to 14 in this order)

 1. Copy         _published_files, _copy_published. Reads: git ls-files of www/,
                 scripts/published-files.json and the files it names outside www/. Skip lists
                 SKIP_DIRS, SKIP_FILES, SKIP_GLOBS. Writes: the whole tree in DEST.
 1b. Built pages _build_pages. Writes each of BUILT_PAGES (the pipeline map, ADR-036) from its builder;
                 a failed, empty or already-copied page stops the build (exit 1).
 2. Fill pages   _refresh_tables_page. Reads tables.xml, the repo's file lists and
                 the JMRI additions (build_tables_browser, repo_guide_page, jmri_additions_page, each
                 with its own tests). Rewrites behind/ pages and data/ in DEST. A failed repo guide or JMRI
                 additions refill is a warning; a failed tables browser write stops the build.
 3. site.json     (inline in main). Sets public, empties engDesk, drops tools.
 4. Logos        _vendor_json_logos. Reads ../external/ logos through
                 _source (manifest first). Writes assets/logos/ and rewrites "logo" in
                 data/industries.json and data/*-lineage.json.
 5. Photos       _vendor_fleet_images, _filter_gallery, _gallery_thumbs,
                 _vendor_archive_images, over gallery.json, fleet-gallery.json
                 and archive.json. Reads ../media/ and ../ops/car-cards/ originals. Writes
                 assets/{gallery,fleet,archive}/ and the thumb, width, height and src fields.
                 Every resize goes through _web_jpeg and its cache in .cache/hart/web-jpeg.
                 Order inside the stage: vendor, then filter, then thumbs.
 6. Scrub data   _strip_external_data. Every data/*.json loses fields still
                 pointing at ../external, ../media, ../ops, ../docs. Must follow stages 4 and 5,
                 which read those paths.
 7. Local-only   _strip_local_only_pages. Drops data-local-only elements.
 8. Head tags    _add_head_tags. Icon and share tags (share_cards).
 9. Provenance   _add_provenance. JSON-LD in every page, llms.txt, robots.txt,
                 sitemap.xml. A page provenance.json does not classify stops the build (exit 1).
10. Card thumbs  _card_thumbs. Small share pictures for hub cards; _web_jpeg.
11. WebP         _webp_companions. Reads every page and its JPEGs, so it must
                 follow stages 5 and 10.
12. Leak check   _check_leaks. Reads the finished tree; exit 1 on any hit.
13. Search       build_search_index. Reads the built pages and
                 data/*.json after stages 5 to 7, and the grid thumbs; writes search-index.json and
                 assets/search/ (80 px copies). Fails on a leak or the private name.
14. Cache prune  _prune_jpeg_cache.

Dependencies: 1 feeds everything. 4 and 5 read paths that 6 deletes. 7 to 9 are independent of the
photo stages, apart from both editing page text (8 skips a page that already has icons). 11 needs the
JPEGs of 5 and 10. 12 and 13 need the final tree. Stages 3 to 9, 12 and 13 touch no photo; only
5, 10, 11 and the thumbs part of 13 resize or read photos.

Split point noted while writing these tests: stage 3 is inline in main(), so it is tested through
main() on a fixture tree (FullBuild below); the rest are called directly. The .cache/hart/web-jpeg path and SITE_URL are module state, patched here.

The stages 4, 5, 10 and 11 and the photo cache live in portal_photos.py, 8 and 9 in portal_head.py, 13 in
portal_search_index.py, and PORTAL, SITE_URL and the manifest lookups in portal_common.py; prepare_github_pages.py
re-exports them. A patch goes on the module that holds the name (PORTAL on both prepare_github_pages and
portal_common, which each read it).
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import prepare_github_pages as build  # noqa: E402
import portal_common  # noqa: E402
import portal_photos as photos  # noqa: E402
import portal_search_index as search  # noqa: E402

try:
    from PIL import Image
except ImportError:
    Image = None

# Stands in for the private name in tests: the real check works by fingerprint and the name is never written.
PLANTED = "PLANTED-PRIVATE-MARKER"


def _write(root: Path, rel: str, text: str = "x") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _page(title="Session paperwork — HART", body="<h1>Session paperwork</h1><p>Everything on the clipboard, readable on a phone, with a page for each job.</p>"):
    return f"<!doctype html><html><head><title>{title}</title></head><body><main>{body}</main></body></html>"


def _png(path: Path, colour=(200, 120, 40), size=(300, 200)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(path)
    return path


def _clean_env() -> dict:
    """The environment without any GIT_* variable (a hook or worktree sets GIT_DIR and friends)."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


class _Repo(unittest.TestCase):
    """A throwaway git repo holding a www/ tree; PORTAL points at it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        self.portal = self.repo / "www"
        self.portal.mkdir(parents=True)
        env = mock.patch.dict(os.environ)  # restored on cleanup; the module's own git calls read it
        env.start()
        self.addCleanup(env.stop)
        for key in [k for k in os.environ if k.startswith("GIT_")]:
            del os.environ[key]
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True, env=_clean_env())
        for patch in (
            mock.patch.object(build, "PORTAL", self.portal),
            mock.patch.object(portal_common, "PORTAL", self.portal),
            mock.patch.object(portal_common, "SITE_URL", "https://example.invalid/"),
            mock.patch.dict(os.environ, {build.JPEG_CACHE_ENV: str(Path(self._tmp.name) / "cache")}),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        build._jpeg_cache_at.cache_clear()
        self.addCleanup(build._jpeg_cache_at.cache_clear)
        _write(self.portal, "scripts/published-files.json", "{}")

    def track(self, rel: str, text: str = "x") -> Path:
        path = _write(self.portal, rel, text)
        subprocess.run(["git", "-C", str(self.repo), "add", "-f", f"www/{rel}"], check=True, env=_clean_env())
        return path

    def track_json(self, rel: str, data) -> Path:
        return self.track(rel, json.dumps(data))


class CopyAndSkipLists(_Repo):
    def test_every_skip_list_entry_is_left_out_and_the_rest_is_copied(self):
        kept = ["index.html", "data/site.json", "docs/page.html", "guides/other.html", "assets/media/photo.png"]
        for rel in kept:
            self.track(rel)
        skipped = [str(p) for p in build.SKIP_FILES] + [
            "scripts/build.py", "review/a.html", "review-data/a.json", "tools/t.html", "reference/r.md",
            "docs/note.md", "stale.pyc", "assets/.DS_Store",
        ]
        for rel in skipped:
            self.track(rel)
        self.assertEqual(sorted(p.as_posix() for p in build._published_files()), sorted(kept))

    def test_a_tracked_file_deleted_in_the_working_tree_is_not_published(self):
        gone = self.track("gone.html")
        self.track("here.html")
        gone.unlink()
        self.assertEqual([p.as_posix() for p in build._published_files()], ["here.html"])

    def test_an_untracked_file_is_never_published(self):
        self.track("a.html")
        _write(self.portal, "draft.html")
        self.assertEqual([p.as_posix() for p in build._published_files()], ["a.html"])

    def test_manifest_files_come_from_outside_www_and_a_missing_source_stops(self):
        self.track("index.html")
        _write(self.repo, "docs/shared.json", '{"a": 1}')
        (self.portal / "scripts/published-files.json").write_text(json.dumps({"data/shared.json": "docs/shared.json"}))
        dest = Path(self._tmp.name) / "out"
        build._copy_published(dest)
        self.assertEqual((dest / "data/shared.json").read_text(), '{"a": 1}')
        (self.portal / "scripts/published-files.json").write_text(json.dumps({"data/shared.json": "docs/none.json"}))
        with self.assertRaises(build.PortalBuildError) as raised:
            build._copy_published(Path(self._tmp.name) / "out2")
        self.assertIn("missing source docs/none.json", str(raised.exception))

    def test_a_manifest_entry_on_the_skip_list_is_not_copied(self):
        _write(self.repo, "docs/p.json", "{}")
        (self.portal / "scripts/published-files.json").write_text(json.dumps({"data/invites.json": "docs/p.json"}))
        dest = Path(self._tmp.name) / "out"
        build._copy_published(dest)
        self.assertFalse((dest / "data/invites.json").exists())


class DataScrub(unittest.TestCase):
    def test_fields_pointing_into_the_mirrors_are_removed_at_any_depth(self):
        data = {
            "keep": "assets/a.png",
            "doc": "../external/a.docx",
            "items": [{"id": "x", "pdf": "../ops/car-cards/a.pdf", "src": "../media/a.jpg", "title": "T"}, {"deep": {"note": "../docs/n.md", "ok": "https://example.invalid/"}}],
        }
        build._drop_external_paths(data)
        self.assertEqual(data, {"keep": "assets/a.png", "items": [{"id": "x", "title": "T"}, {"deep": {"ok": "https://example.invalid/"}}]})

    def test_strip_external_data_rewrites_every_data_file_and_only_data_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "data/a.json", json.dumps({"x": "../external/y", "y": "fine"}))
            _write(root, "data/b.json", json.dumps({"items": [{"src": "../media/p.jpg"}]}))
            _write(root, "other/c.json", json.dumps({"x": "../external/y"}))
            build._strip_external_data(root)
            self.assertEqual(json.loads((root / "data/a.json").read_text()), {"y": "fine"})
            self.assertEqual(json.loads((root / "data/b.json").read_text()), {"items": [{}]})
            self.assertEqual(json.loads((root / "other/c.json").read_text()), {"x": "../external/y"})

    def test_local_only_elements_are_dropped_with_their_contents(self):
        text = '<p>a</p><div data-local-only><div>inner</div>tools</div><p>b</p><a data-local-only href="/x">go</a>'
        self.assertEqual(build._strip_local_only(text), "<p>a</p><p>b</p>")


class LeakCheck(unittest.TestCase):
    def test_hits_name_the_file_and_line_and_other_suffixes_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "a/index.html", "fine\nopen http://localhost:8760 now\n")
            _write(root, "b.css", "/* /Users/someone/x */")
            _write(root, "c.png", "localhost")
            _write(root, "data/d.json", '{"p": "../external/x"}')
            _write(root, "e.html", '<a href="../external/x">kept in a page: scripts test for this prefix</a>')
            hits = build._check_leaks(root)
            self.assertEqual(sorted(h.rsplit(":", 1)[0] for h in hits), ["a/index.html:2", "b.css:1", "data/d.json:1"])

    def test_a_clean_tree_has_no_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "a.html", "<p>nothing here</p>")
            self.assertEqual(build._check_leaks(Path(tmp)), [])

    def test_a_planted_private_name_stops_the_search_index_without_echoing_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "a/index.html", _page(body=f"<h1>Crew</h1><p>This paragraph is long enough to be indexed and holds {PLANTED}.</p>"))
            with mock.patch.object(search, "contains_private_name", side_effect=lambda t: PLANTED in t):
                with self.assertRaises(build.PortalBuildError) as raised:
                    build.build_search_index(root)
            self.assertIn("a/index.html", str(raised.exception))
            self.assertNotIn(PLANTED, str(raised.exception))
            self.assertFalse((root / build.INDEX_NAME).exists())


class SearchRecordsFromData(unittest.TestCase):
    def test_fleet_archive_and_photo_records_come_from_the_built_data_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "data/fleet-gallery.json", json.dumps({"items": [{"id": "loco-1", "title": "GP9 1750", "album": "locos", "road": "P&OV", "number": "1750", "caption": "On the ready track"}]}))
            _write(root, "data/archive.json", json.dumps({"kinds": [{"id": "map", "label": "Map"}], "items": [
                {"id": "a1", "title": "Plant map", "bucket": "curated", "kind": "map", "date": "1951", "tags": ["neville-island"], "reason": "private note", "src": "assets/archive/a1.jpg"},
                {"id": "a2", "title": "Hidden", "bucket": "review"},
            ]}))
            _write(root, "data/gallery.json", json.dumps({"items": [{"id": "p1", "title": "Staging", "album": "session-night", "caption": "Night"}]}))
            _write(root, "photos/index.html", _page(body="<h1>Photos</h1>") + ' layout: { subs: { "session-night": "session-night" } }')
            with mock.patch.object(search, "tab_subs", return_value={"s": "session-night"}):
                index = build.build_search_index(root)
            by_url = {r["url"]: r for r in index["records"]}
            self.assertEqual(by_url["photos/index.html#rolling-stock/loco-1"]["kind"], "locomotive")
            self.assertIn("1750", by_url["photos/index.html#rolling-stock/loco-1"]["text"])
            archive = by_url["photos/index.html#historical/a1"]
            self.assertEqual(archive["kind"], "archive")
            self.assertIn("neville island", archive["text"])
            self.assertNotIn("private note", json.dumps(index))
            self.assertNotIn("photos/index.html#historical/a2", by_url)
            self.assertEqual(by_url["photos/index.html#layout/p1"]["kind"], "photo")
            self.assertTrue((root / build.INDEX_NAME).is_file())


@unittest.skipIf(Image is None, "Pillow is not installed")
class PhotoStages(_Repo):
    def test_logo_is_vendored_into_assets_and_the_original_path_is_rewritten(self):
        _write(self.repo, "external/logos/a.png", "logo-bytes")
        dest = Path(self._tmp.name) / "out"
        path = _write(dest, "data/industries.json", json.dumps({"industries": [{"id": "i", "logo": "../external/logos/a.png"}, {"id": "j", "logo": "../external/logos/none.png"}]}))
        build._vendor_json_logos(path, dest)
        logos = [i["logo"] for i in json.loads(path.read_text())["industries"]]
        self.assertEqual(logos, ["assets/logos/a.png", ""])
        self.assertEqual((dest / "assets/logos/a.png").read_text(), "logo-bytes")

    def test_a_second_logo_of_the_same_name_from_another_folder_is_kept_apart(self):
        _write(self.repo, "external/one/a.png", "one")
        _write(self.repo, "external/two/a.png", "two")
        dest = Path(self._tmp.name) / "out"
        self.assertEqual(build._vendor_logo("../external/one/a.png", dest), "assets/logos/a.png")
        self.assertEqual(build._vendor_logo("../external/two/a.png", dest), "assets/logos/two-a.png")

    def gallery(self):
        _png(self.repo / "media/p1.png")
        dest = Path(self._tmp.name) / "out"
        path = _write(dest, "data/gallery.json", json.dumps({
            "albums": [{"id": "night", "label": "Night"}, {"id": "empty", "label": "Empty"}],
            "items": [
                {"id": "p1", "album": "night", "src": "../media/p1.png"},
                {"id": "p2", "album": "night", "src": "../media/missing.png"},
                {"id": "p3", "album": "empty", "src": "assets/not-there.jpg"},
                {"id": "p4", "album": "night", "src": "https://example.invalid/p.jpg"},
            ],
        }))
        return dest, path

    def run_gallery(self, dest, path):
        build._vendor_fleet_images(path, dest, subdir="gallery")
        build._filter_gallery(path, dest)
        build._gallery_thumbs(path, dest, "gallery")
        return json.loads(path.read_text())

    def test_vendor_filter_and_thumbs_keep_only_photos_that_exist(self):
        dest, path = self.gallery()
        data = self.run_gallery(dest, path)
        self.assertEqual([i["id"] for i in data["items"]], ["p1", "p4"])
        first = data["items"][0]
        self.assertEqual(first["src"], "assets/gallery/night/p1.jpg")
        self.assertEqual(first["thumb"], "assets/gallery/thumbs/night/p1.jpg")
        self.assertEqual((first["width"], first["height"]), (300, 200))
        self.assertEqual(data["albums"], [{"id": "night", "label": "Night", "count": 2}])
        self.assertTrue((dest / first["thumb"]).is_file())

    def test_a_second_build_copies_from_the_cache_and_resizes_nothing(self):
        dest, path = self.gallery()
        with mock.patch.object(photos, "_render_jpeg", wraps=build._render_jpeg) as spy:
            self.run_gallery(dest, path)
            first = spy.call_count
        self.assertEqual(first, 2)  # the 1600 px copy and the 640 px thumb
        dest2 = Path(self._tmp.name) / "out2"
        path2 = _write(dest2, "data/gallery.json", json.dumps({"items": [{"id": "p1", "album": "night", "src": "../media/p1.png"}]}))
        with mock.patch.object(photos, "_render_jpeg", wraps=build._render_jpeg) as spy:
            self.run_gallery(dest2, path2)
            self.assertEqual(spy.call_count, 0)
        self.assertTrue((dest2 / "assets/gallery/night/p1.jpg").is_file())

    def test_a_changed_original_misses_the_cache(self):
        dest, path = self.gallery()
        self.run_gallery(dest, path)
        _png(self.repo / "media/p1.png", colour=(1, 2, 3))
        dest2 = Path(self._tmp.name) / "out2"
        path2 = _write(dest2, "data/gallery.json", json.dumps({"items": [{"id": "p1", "album": "night", "src": "../media/p1.png"}]}))
        with mock.patch.object(photos, "_render_jpeg", wraps=build._render_jpeg) as spy:
            self.run_gallery(dest2, path2)
            self.assertEqual(spy.call_count, 2)

    def test_archive_drops_private_and_review_items_and_strips_local_fields(self):
        _png(self.repo / "media/h1.png")
        _png(self.repo / "media/h2.png")
        dest = Path(self._tmp.name) / "out"
        path = _write(dest, "data/archive.json", json.dumps({"items": [
            {"id": "h1", "bucket": "curated", "src": "../media/h1.png", "pdf": "../media/h1.pdf", "origin": "found at home"},
            {"id": "h2", "bucket": "curated", "public": False, "src": "../media/h2.png"},
            {"id": "h3", "bucket": "review", "src": "../media/h2.png"},
            {"id": "h4", "bucket": "curated", "src": "../media/none.png"},
        ]}))
        build._vendor_archive_images(path, dest)
        items = json.loads(path.read_text())["items"]
        self.assertEqual(items, [{"id": "h1", "bucket": "curated", "src": "assets/archive/h1.jpg", "thumb": "assets/archive/thumbs/h1.jpg"}])
        self.assertTrue((dest / "assets/archive/h1.jpg").is_file())
        self.assertFalse((dest / "assets/archive/h2.jpg").exists())


class WithoutPillow(unittest.TestCase):
    """Every photo step raises PillowMissing, naming the step, instead of returning quietly."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dest = Path(self._tmp.name)
        patcher = mock.patch.dict(sys.modules, {"PIL": None, "PIL.Image": None, "PIL.ImageOps": None})
        patcher.start()
        self.addCleanup(patcher.stop)

    def assert_missing(self, step: str, call) -> None:
        with self.assertRaises(build.PillowMissing) as ctx:
            call()
        self.assertIsInstance(ctx.exception, build.PortalBuildError)
        self.assertIn(step, str(ctx.exception))
        self.assertIn("python3 -m pip install Pillow", str(ctx.exception))

    def test_each_step_names_itself(self):
        gallery = _write(self.dest, "data/gallery.json", json.dumps({"items": []}))
        self.assert_missing("resizing a.png", lambda: build._web_jpeg(self.dest / "a.png", self.dest / "a.jpg", 100))
        self.assert_missing("thumbnails for gallery.json", lambda: build._gallery_thumbs(gallery, self.dest, "gallery"))
        self.assert_missing("card thumbnails", lambda: build._card_thumbs(self.dest))
        self.assert_missing("WebP companions", lambda: build._webp_companions(self.dest))

    def test_archive_without_resizing_drops_mirror_items_and_gives_no_thumbs(self):
        _write(self.dest, "assets/archive/local.png")
        _write(self.dest, "media/m.png")
        path = _write(self.dest, "data/archive.json", json.dumps({"items": [
            {"id": "m", "src": "../media/m.png"},
            {"id": "l", "src": "assets/archive/local.png", "origin": "x"},
        ]}))
        with mock.patch.object(photos, "_source", side_effect=lambda rel: self.dest / rel.removeprefix("../")):
            build._vendor_archive_images(path, self.dest, resize=False)
        self.assertEqual(json.loads(path.read_text())["items"], [{"id": "l", "src": "assets/archive/local.png"}])

    def test_the_photo_stages_warn_once_each_and_drop_mirror_photos(self):
        _write(self.dest, "data/gallery.json", json.dumps({"items": [{"id": "m", "album": "a", "src": "../media/m.png"}]}))
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.object(photos, "_jpeg_cache", return_value=None), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            stamp, _, reused = build._photo_early(self.dest, full=False)
            build._photo_late(self.dest, stamp, set(), full=False)
        self.assertFalse(reused)
        self.assertEqual(err.getvalue().count("WARNING: Pillow is not installed"), 2)
        self.assertIn("photo stages: full run (Pillow is missing)", out.getvalue())
        self.assertEqual(json.loads((self.dest / "data/gallery.json").read_text())["items"], [])


class BuiltPages(unittest.TestCase):
    """_build_pages (stage 1b): the pages built at deploy instead of committed (ADR-036)."""

    def run_stage(self, pages, existing=()):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in existing:
                _write(root, rel, "committed copy")
            err = io.StringIO()
            with mock.patch.object(build, "BUILT_PAGES", pages), contextlib.redirect_stderr(err), \
                    contextlib.redirect_stdout(io.StringIO()):
                ok = build._build_pages(root)
            written = {rel: (root / rel).read_text() for rel in pages if (root / rel).is_file()}
            return ok, err.getvalue(), written

    def test_the_real_pipeline_map_is_built_into_the_tree(self):
        ok, err, written = self.run_stage(dict(build.BUILT_PAGES))
        self.assertTrue(ok, err)
        page = written["library/pipeline-map.html"]
        data = build.pipeline_map.load(build.pipeline_map.GRAPH)
        self.assertIn(f'{len(data["nodes"])} boxes, {len(data["edges"])} links', page)
        self.assertIn("data-ops-header", page)

    def test_a_failing_builder_stops_with_its_message(self):
        def broken():
            raise build.pipeline_map.GraphError("node 'x' has no links")

        ok, err, written = self.run_stage({"library/map.html": broken})
        self.assertFalse(ok)
        self.assertIn("Cannot build library/map.html", err)
        self.assertIn("node 'x' has no links", err)
        self.assertEqual(written, {})

    def test_an_empty_page_stops(self):
        for empty in ("", "  \n", None):
            with self.subTest(page=empty):
                ok, err, written = self.run_stage({"library/map.html": lambda: empty})
                self.assertFalse(ok)
                self.assertIn("its builder returned no page", err)
                self.assertEqual(written, {})

    def test_a_copied_page_stops_and_the_builder_is_not_run(self):
        builder = mock.Mock(return_value="<p>new</p>")
        ok, err, written = self.run_stage({"library/map.html": builder}, existing=("library/map.html",))
        self.assertFalse(ok)
        self.assertIn("git rm --cached www/library/map.html", err)
        builder.assert_not_called()
        self.assertEqual(written, {"library/map.html": "committed copy"})

    def test_a_write_that_fails_stops_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), "library", "a file where the folder goes")
            err = io.StringIO()
            with mock.patch.object(build, "BUILT_PAGES", {"library/map.html": lambda: "<p>page</p>"}), \
                    contextlib.redirect_stderr(err):
                self.assertFalse(build._build_pages(Path(tmp)))
        self.assertIn("cannot write", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())


class RefillFailures(unittest.TestCase):
    """_refresh_tables_page: which failed refills are warnings and which stop the build."""

    PAGES = (build.build_tables_browser.PAGE_REL, build.repo_guide_page.PAGE_REL, build.jmri_additions_page.PAGE_REL)

    def run_refresh(self, **failing):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in self.PAGES:
                _write(root, str(rel))
            targets = {
                "tables": (build.build_tables_browser, "write_page"),
                "guide": (build.repo_guide_page, "write"),
                "jmri": (build.jmri_additions_page, "write"),
            }
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.ExitStack() as stack:
                for name, (mod, fn) in targets.items():
                    stack.enter_context(mock.patch.object(mod, fn, side_effect=failing.get(name)))
                build._refresh_tables_page(root)
            return out.getvalue()

    def test_all_refills_succeeding_prints_nothing(self):
        self.assertEqual(self.run_refresh(), "")

    def test_repo_guide_failures_are_warnings(self):
        for exc in (build.repo_guide_page.PageError("stale"), subprocess.CalledProcessError(1, "git"), OSError("disk")):
            with self.subTest(exc=type(exc).__name__):
                self.assertIn("WARNING: repository guide not refilled", self.run_refresh(guide=exc))

    def test_jmri_additions_failures_are_warnings(self):
        for exc in (build.jmri_additions_page.PageError("stale"), OSError("disk"), ValueError("bad")):
            with self.subTest(exc=type(exc).__name__):
                self.assertIn("WARNING: JMRI additions page not refilled", self.run_refresh(jmri=exc))

    def test_a_tables_browser_failure_stops_the_build(self):
        with self.assertRaises(OSError):
            self.run_refresh(tables=OSError("no tables.xml"))

    def test_other_errors_in_the_guide_or_additions_stop_the_build(self):
        with self.assertRaises(KeyError):
            self.run_refresh(guide=KeyError("x"))
        with self.assertRaises(KeyError):
            self.run_refresh(jmri=KeyError("x"))


@unittest.skipIf(Image is None, "Pillow is not installed")
class FullBuild(_Repo):
    """main() on a small fixture site: the output list must stay the same however the stages are split."""

    EXPECTED = [
        "404.html", "about/index.html", "assets/archive/h1.jpg", "assets/archive/thumbs/h1.jpg",
        "assets/gallery/night/p1.jpg", "assets/gallery/thumbs/night/p1.jpg", "assets/logos/a.png",
        "assets/search/assets-archive-thumbs-h1.jpg",
        "data/archive.json", "data/fleet-gallery.json", "data/gallery.json", "data/industries.json", "data/site.json",
        "docs/page.html", "index.html", "library/map.html", "llms.txt", "robots.txt", "search-index.json",
        "sitemap.xml",
    ]

    def setUp(self):
        super().setUp()
        self.out = Path(self._tmp.name) / "out"
        # Small fixtures, so the real provenance.json and share-cards.json can change without touching this test.
        prov = _write(Path(self._tmp.name), "prov/provenance.json", json.dumps({
            "site": {"name": "Test Railroad", "summary": "A test site.", "notes": ["Everything here is a fixture."], "setting": "Nowhere"},
            "classes": {c: f"{c} pages" for c in ("prototype", "fiction", "hobby", "mixed")},
            "rules": {"index.html": {"class": "hobby"}, "about/": {"class": "hobby"}, "docs/": {"class": "hobby"},
                      "library/": {"class": "hobby"}},
        }))
        original_load = build.provenance.load
        for patch in (
            mock.patch.object(build.provenance, "load", lambda path=prov: original_load(path)),
            mock.patch.object(build.share_cards, "load", return_value={"about/index.html": {"image": "assets/share/about.jpg", "alt": "About card"}}),
            mock.patch.object(build.share_cards, "load_links", return_value={}),
            mock.patch.object(build, "BUILT_PAGES", {"library/map.html": lambda: _page("Map — HART", "<h1>Map</h1>")}),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        _png(self.repo / "media/p1.png")
        _png(self.repo / "media/h1.png")
        _write(self.repo, "external/logos/a.png", "logo")
        self.track("index.html", _page("Home — HART", '<h1>Home</h1><p>The layout, the crews and the plants of Neville Island, in one place.</p><div data-local-only><p>Engineering desk</p></div>'))
        self.track("about/index.html", _page("About — HART", "<h1>About</h1><p>What the layout is and who runs the sessions, in plain words for visitors.</p>"))
        self.track("404.html", _page("Not found — HART", "<h1>Not found</h1>"))
        self.track("docs/page.html", _page("Doc — HART", "<h1>Doc</h1><p>A document published from the docs folder for the public site to show.</p>"))
        for rel in ("README.md", "docs/note.md", "scripts/tool.py", "review/a.html", "data/invites.json"):
            self.track(rel, f"skip me {PLANTED}")
        self.track_json("data/site.json", {"engDesk": "http://localhost:8760", "tools": {"sts": "http://localhost:8980"}, "name": "HART"})
        self.track_json("data/industries.json", {"industries": [{"id": "i", "logo": "../external/logos/a.png", "source": "../external/x.docx"}]})
        self.track_json("data/gallery.json", {"albums": [{"id": "night", "label": "Night"}], "items": [{"id": "p1", "album": "night", "src": "../media/p1.png"}, {"id": "p2", "album": "night", "src": "../media/gone.png"}]})
        self.track_json("data/fleet-gallery.json", {"items": []})
        self.track_json("data/archive.json", {"items": [{"id": "h1", "title": "Plant", "bucket": "curated", "src": "../media/h1.png", "pdf": "../media/h1.pdf", "origin": "home"}]})

    def run_main(self):
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["prepare", str(self.out)]), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = build.main()
        return code, out.getvalue(), err.getvalue()

    def tree(self):
        return sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob("*") if p.is_file())

    def test_output_file_list_is_fixed_for_a_fixed_tree(self):
        code, _, err = self.run_main()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.tree(), self.EXPECTED)

    def test_a_built_page_that_fails_stops_the_build(self):
        def broken():
            raise build.pipeline_map.GraphError("the graph has problems")

        with mock.patch.object(build, "BUILT_PAGES", {"library/map.html": broken}):
            code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("Cannot build library/map.html", err)
        self.assertNotIn("Traceback", err)

    def test_a_second_run_gives_the_same_files_and_resizes_nothing(self):
        self.assertEqual(self.run_main()[0], 0)
        with mock.patch.object(photos, "_render_jpeg", wraps=build._render_jpeg) as spy:
            self.assertEqual(self.run_main()[0], 0)
            self.assertEqual(spy.call_count, 0)
        self.assertEqual(self.tree(), self.EXPECTED)

    def test_public_data_and_pages_are_scrubbed(self):
        code, _, err = self.run_main()
        self.assertEqual(code, 0, err)
        site = json.loads((self.out / "data/site.json").read_text())
        self.assertEqual(site, {"engDesk": "", "name": "HART", "public": True})
        industries = json.loads((self.out / "data/industries.json").read_text())
        self.assertEqual(industries, {"industries": [{"id": "i", "logo": "assets/logos/a.png"}]})
        archive = json.loads((self.out / "data/archive.json").read_text())["items"][0]
        self.assertNotIn("pdf", archive)
        self.assertNotIn("origin", archive)
        gallery = json.loads((self.out / "data/gallery.json").read_text())
        self.assertEqual([i["id"] for i in gallery["items"]], ["p1"])
        home = (self.out / "index.html").read_text()
        self.assertNotIn("Engineering desk", home)
        self.assertIn('rel="icon"', home)
        self.assertIn("application/ld+json", home)
        about = (self.out / "about/index.html").read_text()
        self.assertIn("https://example.invalid/assets/share/about.jpg", about)
        self.assertIn("Test Railroad", about)
        for skipped in ("README.md", "docs/note.md", "scripts/tool.py", "review/a.html"):
            self.assertFalse((self.out / skipped).exists(), skipped)

    def test_search_index_holds_the_pages_and_the_archive_item(self):
        code, _, err = self.run_main()
        self.assertEqual(code, 0, err)
        index = json.loads((self.out / build.INDEX_NAME).read_text())
        urls = sorted(r["url"] for r in index["records"])
        self.assertEqual(urls, ["about/index.html", "docs/page.html", "index.html", "library/map.html",
                                "photos/index.html#historical/h1"])
        self.assertNotIn("Engineering desk", json.dumps(index))

    def test_a_leak_in_a_page_fails_the_build_before_the_index_is_written(self):
        self.track("about/index.html", _page("About — HART", "<h1>About</h1><p>Open the tool at http://localhost:8760 on the layout PC for the desk.</p>"))
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("about/index.html", err)
        self.assertIn("Local hosts or paths", err)
        self.assertFalse((self.out / build.INDEX_NAME).exists())

    def test_a_planted_private_name_in_a_page_stops_the_build(self):
        self.track("about/index.html", _page("About — HART", f"<h1>About</h1><p>This paragraph is long enough to be indexed and holds {PLANTED} in it.</p>"))
        with mock.patch.object(search, "contains_private_name", side_effect=lambda t: PLANTED in t):
            with self.assertRaises(SystemExit) as raised:
                self.run_main()
        self.assertIn("search index holds text that must not publish", str(raised.exception))
        self.assertNotIn(PLANTED, str(raised.exception))
        self.assertFalse((self.out / build.INDEX_NAME).exists())

    def test_a_page_with_no_provenance_rule_stops_the_build(self):
        self.track("zz-unclassified/index.html", _page("Other — HART", "<h1>Other</h1><p>A page that provenance.json does not classify at all, so it stops.</p>"))
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("zz-unclassified/index.html", err)

    def test_a_dest_that_holds_the_repo_is_refused_and_left_alone(self):
        marker = _write(self.repo, "keep.txt")
        with mock.patch.object(sys, "argv", ["prepare", str(self.repo)]), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(build.main(), 2)
        self.assertTrue(marker.is_file())


if __name__ == "__main__":
    unittest.main()
