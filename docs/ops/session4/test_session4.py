"""Checks for the session 4 design generators. Run: /Users/lnevo/hart/.venv/bin/python -W ignore docs/ops/session4/test_session4.py (pytest also collects it)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import facts
import make_signals
import make_signs


def test_every_interlocking_has_a_name_and_switches():
    cps = facts.control_points()
    assert len(cps) >= 11
    assert all(cp["name"] and cp["switches"] and cp["level"] in ("Staging", "Main", "Upper") for cp in cps)


def test_board_jobs_come_from_the_primer_with_colours_where_known():
    jobs = facts.board_jobs()
    assert [j["code"] for j in jobs][:3] == ["D749", "NVL", "CK1"]
    assert next(j for j in jobs if j["code"] == "NVL")["colors"]


def test_every_sign_sheet_holds_all_signs():
    cps = facts.control_points()
    for draw, cell, cols, rows in ((make_signs.sign_a, (66, 56), 3, 4), (make_signs.sign_b, (46, 72), 4, 3),
                                   (make_signs.sign_c, (62, 78), 3, 3)):
        pages = make_signs.sheets(cps, draw, cell, "t", cols, rows)
        assert all(any(cp["name"].replace("CP ", "") + "<" in p for p in pages) for cp in cps)


def test_signal_parts_are_single_watertight_pieces_over_9_mm3():
    for fn in make_signals.OPTIONS.values():
        for mesh in fn().values():
            assert mesh.is_watertight and len(mesh.split(only_watertight=False)) == 1
            assert mesh.volume > 9


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
