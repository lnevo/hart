"""Checks for the session 4 design generators. Run: /Users/lnevo/hart/.venv/bin/python -W ignore docs/ops/session4/test_session4.py (pytest also collects it)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import facts
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
    pages = make_signs.sheets(cps, make_signs.sign_a, (66, 56), "t", 3, 4)
    assert len(pages) == 1 and all(">" + cp["name"] + "<" in pages[0] for cp in cps)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
