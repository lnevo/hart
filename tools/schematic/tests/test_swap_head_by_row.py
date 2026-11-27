"""A main or upper signal head is swapped to its physical LCOS head by its owner row alone (ADR-028; the naming-layers
follow-up after step 14), as test_swap_by_row.py does for a turnout and a detector.

A copy of the device master gets two field rows, as the owner would add them, and nothing else changes: main's Mast
108LA's heads, Head 108LA Top (mast:107:B:west:top) and Head 108LA Bottom (mast:107:B:west:bottom), each with
assignment field and jmri_name and system_name its planned head (IH3332, IH3333). Then, over the copy: the device map
(build_device_map.master_outputs), masts.csv (build_masts.build, to a temporary file), the beans
(hartlib.tables_build.base, to a temporary tables file), the railroad check, the device-master check, the Digicon
heads (hartlib.wiring.digicon_rows, hartlib.tables_build.digicon_masts) and the CATS desks. The mast follows its
heads (device_map_rows.mast_on_heads) onto IH3332 and IH3333, masts.csv's check takes the swapped heads by the row
(level_masts.read), and the heads are Digicon heads by their rows' assignment; every other row, bean and desk is as
committed. Runs over the committed drawing (needs the plugin; skipped without it, failing with SCHEMATIC_REQUIRED=1).
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py, test_swap_by_row.py

import build_device_map as bdm  # noqa: E402
from repo_read_only import RepoReadOnly  # noqa: E402
from plugin_needed import skip_or_fail  # noqa: E402
from hartlib import devices, level_masts, paths, railroad, tables, tables_build, wiring  # noqa: E402

TOP, BOTTOM, MAST = ("2", "mast:107:B:west:top"), ("2", "mast:107:B:west:bottom"), ("2", "mast:107:B:west")
SWAP = {TOP: "IH3332", BOTTOM: "IH3333"}
WIRED_MAST = "IF$shsm:basic:two-searchlight(IH3332)(IH3333)"


def swap_rows(rows: list[dict]) -> list[dict]:
    """The field rows with the two head rows added: key, layer, assignment and the two names only."""
    out = [dict(r) for r in rows]
    for (level, ident), name in SWAP.items():
        row = dict.fromkeys(devices.COLUMNS, "")
        row.update(level=level, id=ident, layer="head", assignment="field", system_name=name, jmri_name=name)
        out.append(row)
    return sorted(out, key=devices._rank)


class HeadSwapByRow(RepoReadOnly, unittest.TestCase):
    """The whole build over a copy of the device master with the two head rows in its field file."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        super().setUpClass()
        import build_layout_le as bl
        import build_masts as bm
        try:
            cls.bands, cls.joined, runs, corners = bdm.solve()
        except bl.BuildError as exc:
            skip_or_fail(exc)
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
        with unittest.mock.patch.object(bm, "DEVICE_MAP", cls.files.master):
            text, _gen, _vgen = bm.build()
        cls.masts_path = cls.tmp / "masts.csv"
        cls.masts_path.write_text(text[bm.MASTS], encoding="utf-8")
        cls.committed_masts = bm.MASTS.read_text(encoding="utf-8")
        cls.tables_path = cls.tmp / "swapped_tables.xml"
        cls.tables_path.write_bytes(tables_build.base(cls.rows).tobytes())
        cls.committed_tables = tables_build.base(list(devices.load()))
        # the wiring file beside the copy's device master, so the Digicon heads read the copy's rows
        cls.wiring_path = cls.files.master.parent / paths.WIRING.name
        shutil.copy2(paths.WIRING, cls.wiring_path)
        cls.rr = railroad.Railroad(railroad.Sources.under().but(devices=cls.files.master, tables=cls.tables_path,
                                                                masts=cls.masts_path))

    # ---- the device master and masts.csv

    def test_only_the_heads_and_their_mast_change(self):
        self.assertEqual(set(self.before), set(self.after))
        self.assertEqual({k for k in self.before if self.before[k] != self.after[k]}, {TOP, BOTTOM, MAST})

    def test_the_mast_stands_on_the_swapped_heads(self):
        m = self.after[MAST]
        self.assertEqual((m["jmri_name"], m["system_name"], m["assignment"]), (WIRED_MAST, WIRED_MAST, "field"))
        for k, name in SWAP.items():
            self.assertEqual((self.after[k]["assignment"], self.after[k]["jmri_name"]), ("field", name))

    def test_masts_csv_changes_in_that_mast_alone_and_reads_back(self):
        old = self.committed_masts.splitlines()
        new = self.masts_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(old), len(new))
        diff = [b for a, b in zip(old, new) if a != b]
        self.assertEqual(len(diff), 1)
        self.assertIn("Mast 108LA", diff[0])
        [row] = [r for r in level_masts.read(self.masts_path) if r["mast"] == "Mast 108LA"]
        self.assertEqual(row["heads"], [("IH3332", "Head 108LA Top"), ("IH3333", "Head 108LA Bottom")])
        import le_names       # the Layout Editor build's reader takes the swapped mast for the field
        [le_row] = [r for r in le_names.read_level_masts(self.masts_path) if r["mast"] == "Mast 108LA"]
        self.assertEqual(le_row["system_name"], WIRED_MAST)

    def test_the_railroad_check_passes(self):
        self.assertEqual([str(p) for p in self.rr.check()], [])

    # ---- the beans

    def test_the_beans_bind_the_physical_heads(self):
        def beans(root):
            return {(el.tag, tables.system_name(el)): tables.user_name(el)
                    for el in tables.signal_heads(root) + tables.masts(root)}
        got = beans(tables.read(self.tables_path))
        was = beans(self.committed_tables.root)
        gone, new = set(was) - set(got), set(got) - set(was)
        self.assertEqual({n for _t, n in gone}, {"IH:HART:C3:108LA_Top", "IH:HART:C3:108LA_Bottom",
                                                 "IF$shsm:basic:two-searchlight(IH:HART:C3:108LA_Top)"
                                                 "(IH:HART:C3:108LA_Bottom)"})
        self.assertEqual({n: got[(t, n)] for t, n in new},
                         {"IH3332": "Head 108LA Top", "IH3333": "Head 108LA Bottom", WIRED_MAST: "Mast 108LA"})

    def test_the_device_master_check_passes_on_the_copy(self):
        import check_device_master as cdm
        lines = [dict(r) for r in self.rows if r["role"] not in devices.OUT_OF_MAPS and not devices.is_unplaced(r)]
        self.assertEqual(cdm.check_tables(lines, self.rr), [])
        self.assertEqual(cdm.check_bean_cells([dict(r) for r in self.rows], self.rr.tables.root), [])

    # ---- the Digicon heads: signal_coordinator.py drives them

    def test_the_heads_are_digicon_heads_by_their_rows(self):
        got = wiring.digicon_rows(self.wiring_path)
        self.assertEqual(sorted({(r["system_name"], r["mast_user_name"]) for r in got}),
                         [("IH3332", "Mast 108LA"), ("IH3333", "Mast 108LA"), ("IH432", "Mast 6LB")])
        self.assertEqual([r["port_id"] for r in got if r["system_name"] == "IH3332"],
                         ["C33-OU3-1", "C33-OU3-2", "C33-OU3-3"])
        self.assertEqual({r["system_name"] for r in wiring.digicon_rows()}, {"IH432"})     # the committed rows
        root = tables.read(self.tables_path)
        self.assertEqual(tables_build.digicon_masts(root, self.wiring_path), {"Mast 108LA", "Mast 6LB"})

    # ---- the desks

    def test_the_desks_change_only_in_that_masts_bindings(self):
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
        self.assertTrue(all(part == "masts" for part, _k in changed), changed)
        text = json.dumps({f"{p}/{k}": got[p][k] for p, k in changed})
        self.assertNotIn("HART:C3:108LA", text)
        for key, path in (("ctc", bcp.OUT), ("abs", bcp.OUT_ABS)):
            old = path.read_text(encoding="utf-8").splitlines()
            new = paths_[key].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(old), len(new))
            diff = [(a, b) for a, b in zip(old, new) if a != b]
            self.assertTrue(all("108LA" in a for a, _b in diff), diff[:3])


if __name__ == "__main__":
    unittest.main()
