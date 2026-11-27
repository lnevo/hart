"""Naming-layers step 14: a main or upper device is swapped to a physical name by its owner row alone (ADR-028).

A copy of the device master gets two field rows, as the owner would add them, and nothing else changes:
- main's Switch 107 (switch:107): assignment field, jmri_name and system_name its planned turnout M2T3308;
- main's detector BS 107 Loop 1 (det:block:107B-107C#1): assignment field, jmri_name and system_name M2S3305.
Then, over the copy: the device map (build_device_map.master_outputs, written to the copy), the beans
(hartlib.tables_build.base, written to a temporary tables file), the railroad check (every invariant up to tables),
the device-master check of the rows against those tables (check_device_master.check_tables) and the CATS desks
(build_cats_panel.generate, to temporary files). The swapped devices bind their physical names everywhere: the
turnout with TWOSENSOR feedback on its two planned feedback pins (the alias and feedback rows follow the turnout,
device_map_rows.follow_swaps), the detector as a wired M2S sensor; every other row, bean and desk binding is as
committed. Runs over the committed drawing (needs the plugin; skipped without it, failing with SCHEMATIC_REQUIRED=1).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import build_device_map as bdm  # noqa: E402
from repo_read_only import RepoReadOnly  # noqa: E402
from hartlib import devices, railroad, tables, tables_build  # noqa: E402

TURNOUT = ("2", "switch:107")
DETECTOR = ("2", "det:block:107B-107C#1")
SWAP = {TURNOUT: "M2T3308", DETECTOR: "M2S3305"}
# the rows the swap reaches: the two swapped, the turnout's LCC alias and feedback (follow_swaps), and the block
# whose bean comment names its detector's sensor
REACHED = {TURNOUT, DETECTOR, ("2", "dcc:107"), ("2", "fb:107:N"), ("2", "fb:107:R"), ("2", "block:107B-107C#1")}


def skip_or_fail(exc: Exception) -> None:
    if os.environ.get("SCHEMATIC_REQUIRED") == "1":
        raise AssertionError(f"the plugin is required: {exc}")
    raise unittest.SkipTest(str(exc))


def swap_rows(rows: list[dict]) -> list[dict]:
    """The field rows with the two swap rows added, as the owner adds them: key, layer, assignment and the two
    names only."""
    layer = {TURNOUT: "turnout", DETECTOR: "occupancy"}
    out = [dict(r) for r in rows]
    for (level, ident), name in SWAP.items():
        row = dict.fromkeys(devices.COLUMNS, "")
        row.update(level=level, id=ident, layer=layer[(level, ident)], assignment="field", system_name=name,
                   jmri_name=name)
        out.append(row)
    return sorted(out, key=devices._rank)


class SwapByRow(RepoReadOnly, unittest.TestCase):
    """The whole build over a copy of the device master with the two swap rows in its field file."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        # registered before the guard: class cleanups run last first, so the guard is off when it runs (rmtree's
        # relative unlinks look like repo writes)
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        super().setUpClass()
        import build_layout_le as bl
        try:
            cls.bands, cls.joined, runs, corners = bdm.solve()
        except bl.BuildError as exc:
            skip_or_fail(exc)
        cls.runs = staticmethod(runs)
        rr = railroad.Railroad(bdm.sources(), upto="inputs")
        _cp, main_rows, parts = bdm.build(cls.bands, cls.joined, runs, bdm.MapInputs.of(rr), corners)
        cls.before = {devices.key_of(r): dict(r) for r in devices.load()}
        cls.files = devices.pair_copy(cls.tmp / "data")
        cls.files.field.write_text(devices.master_text(swap_rows(list(devices.field_rows(cls.files)))),
                                   encoding="utf-8")
        devices.write_all(cls.files, bdm.master_outputs(cls.bands, cls.joined, runs, main_rows, parts, cls.files,
                                                        warn=lambda line: None))
        cls.rows = list(devices.load(cls.files))
        cls.after = {devices.key_of(r): dict(r) for r in cls.rows}
        cls.tables_path = cls.tmp / "swapped_tables.xml"
        cls.tables_path.write_bytes(tables_build.base(cls.rows).tobytes())
        cls.committed_tables = tables_build.base(list(devices.load()))
        cls.rr = railroad.Railroad(railroad.Sources.under().but(devices=cls.files.master, tables=cls.tables_path))

    # ---- the device master

    def test_only_the_rows_the_swap_reaches_change(self):
        self.assertEqual(set(self.before), set(self.after))
        changed = {k for k in self.before if self.before[k] != self.after[k]}
        self.assertEqual(changed, REACHED)

    def test_the_swapped_rows_are_field_devices(self):
        t, d = self.after[TURNOUT], self.after[DETECTOR]
        self.assertEqual((t["assignment"], t["jmri_name"], t["start"]), ("field", "M2T3308", ""))
        self.assertEqual((d["assignment"], d["jmri_name"], d["detector"], d["start"]),
                         ("field", "M2S3305", "wired", ""))

    def test_the_alias_and_feedback_follow_the_turnout(self):
        alias = self.after[("2", "dcc:107")]
        self.assertEqual((alias["assignment"], alias["jmri_name"]), ("field", alias["system_name"]))
        for nr in "NR":
            fb = self.after[("2", f"fb:107:{nr}")]
            self.assertEqual((fb["assignment"], fb["jmri_name"]), ("field", fb["system_name"]))
            self.assertTrue(fb["jmri_name"].startswith("M2S"))

    def test_the_railroad_check_passes(self):
        self.assertEqual([str(p) for p in self.rr.check()], [])

    # ---- the beans

    def beans(self, root) -> dict[tuple[str, str], tuple[str, dict]]:
        """{(kind, system name): (user name, attributes)} of the turnouts and sensors."""
        out = {}
        for kind, els in (("turnout", tables.turnouts(root)), ("sensor", tables.sensors(root))):
            for el in els:
                out[(kind, tables.system_name(el))] = (tables.user_name(el), dict(el.attrib))
        return out

    def test_the_swapped_beans_bind_the_physical_names(self):
        got = self.beans(tables.read(self.tables_path))
        was = self.beans(self.committed_tables.root)
        alias = self.after[("2", "dcc:107")]["system_name"]
        fbs = {self.after[("2", f"fb:107:{nr}")]["system_name"] for nr in "NR"}
        gone = set(was) - set(got)
        new = set(got) - set(was)
        self.assertEqual(gone, {("turnout", "IT:HART:C3:107"), ("sensor", "IS:HART:C3:B:107_Loop_1")})
        self.assertEqual(new, {("turnout", "M2T3308"), ("turnout", alias), ("sensor", "M2S3305")}
                         | {("sensor", s) for s in fbs})
        self.assertEqual(got[("turnout", "M2T3308")][0], "Switch 107")
        self.assertEqual(got[("turnout", "M2T3308")][1]["feedback"], "TWOSENSOR")
        self.assertEqual(got[("sensor", "M2S3305")][0], "BS 107 Loop 1")
        # every other turnout and sensor as committed
        self.assertEqual({k: v for k, v in got.items() if k not in new}, {k: v for k, v in was.items() if k not in gone})

    def test_the_panelpro_smoke_check_takes_the_swapped_detector(self):
        """The smoke test's block check (Jython; its plain functions run here) on the copy's tables, as
        run_panelpro_smoke_test.sh passes them: the swapped block on M2S3305 passes, every other main and upper block
        on its virtual sensor; the committed tables have no field-detected block."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "jmri/layouts/hart/scripts/tests"))
        from test_panelpro_smoke_blocks import plain_parts
        from hartlib import level_devices
        smoke = plain_parts()
        root = tables.read(self.tables_path)
        field = level_devices.field_detected(root)
        sensors = tables.by_any_name(tables.sensors(root))
        block = self.after[("2", "block:107B-107C#1")]
        self.assertEqual(field, {block["jmri_name"]: "M2S3305"})
        self.assertEqual(level_devices.field_detected(self.committed_tables.root), {})
        blocks = [(tables.user_name(b), tables.system_name(b),
                   tables.system_name(sensors[tables.text(b, "occupancysensor")])
                   if tables.text(b, "occupancysensor") else None)
                  for b in tables.blocks(root) if tables.system_name(b).startswith(level_devices.BLOCK_PREFIX)]
        text = "".join(f"{b} {s};" for b, s in sorted(field.items()))     # what the wrapper exports
        self.assertEqual(smoke["block_sensor_errors"](blocks, smoke["field_detected"](text)), [])
        self.assertEqual(smoke["block_sensor_errors"](blocks, {}),     # the old check: the swapped block fails
                         [f"main and upper blocks with no virtual occupancy sensor: {block['user_name']}"])

    def test_the_device_master_check_passes_on_the_copy(self):
        import check_device_master as cdm
        lines = [dict(r) for r in self.rows if r["role"] not in devices.OUT_OF_MAPS and not devices.is_unplaced(r)]
        self.assertEqual(cdm.check_tables(lines, self.rr), [])
        self.assertEqual(cdm.check_bean_cells([dict(r) for r in self.rows], self.rr.tables.root), [])

    # ---- the desks

    def test_the_desks_bind_the_physical_names(self):
        import build_cats_panel as bcp
        import cats_panel_facts as cpf
        import publish_draft as pd
        out = self.tmp / "desks"
        out.mkdir()
        paths_ = {"ctc": out / "ctc.xml", "abs": out / "abs.xml", "bindings": out / "bindings.json"}
        with unittest.mock.patch.object(bcp, "load_facts", lambda: cpf.load_facts(self.rr)):
            bcp.generate(pd.plugin(), paths_["ctc"], paths_["bindings"], paths_["abs"])
        got = json.loads(paths_["bindings"].read_text(encoding="utf-8"))
        was = json.loads(bcp.BINDINGS.read_text(encoding="utf-8"))
        changed = {(part, k) for part in ("switches", "blocks", "masts")
                   for k in set(got[part]) | set(was[part]) if got[part].get(k) != was[part].get(k)}
        self.assertEqual({part for part, _k in changed}, {"switches", "blocks"})
        text = json.dumps({f"{p}/{k}": got[p][k] for p, k in changed})
        self.assertNotIn("HART:C3:107", text)
        self.assertNotIn("107_Loop_1", text)
        self.assertIn('"JMRIPREFIX": "M2T"', text)
        self.assertIn('"DECADDR": "3308"', text)
        self.assertIn('"DECADDR": "3305"', text)
        # the desks differ from the committed ones only in those IOSPECs
        for key, path in (("ctc", bcp.OUT), ("abs", bcp.OUT_ABS)):
            old = path.read_text(encoding="utf-8").splitlines()
            new = paths_[key].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(old), len(new))
            diff = [(a, b) for a, b in zip(old, new) if a != b]
            self.assertTrue(diff)
            self.assertTrue(all("IOSPEC" in a and "IOSPEC" in b for a, b in diff), diff[:3])


if __name__ == "__main__":
    unittest.main()
