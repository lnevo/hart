"""tools/ops/check_fleet_gallery.py: each difference it finds between the public rolling-stock gallery and the
car and loco masters, and the repo's gallery passing (lane L6 of ADR-039)."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("check_fleet_gallery", ROOT / "tools/ops/check_fleet_gallery.py")
F = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(F)


def car(photo: str, number: str, kind: str = "Hopper", rid: str = "") -> dict:
    return {"source_image": photo, "road_name": "B&O", "road_number": number, "car_type": kind, "roster_id": rid}


def loco(photo: str, number: str) -> dict:
    return {"source_image": photo, "road_name": "CSX", "road_number": number, "roster_id": f"CSX {number}"}


def item(photo: str, number: str, kind: str = "Hopper", album: str = "freight", **extra) -> dict:
    return {"id": f"x-{number}", "album": album, "src": f"../ops/car-cards/car-images/CarImagesFinal/{photo}.png",
            "title": f"X {number}", "number": number, "type": kind, **extra}


def gallery(*items: dict) -> dict:
    albums = sorted({i["album"] for i in items})
    return {"albums": [{"id": a, "count": sum(i["album"] == a for i in items)} for a in albums], "items": list(items)}


class CheckTests(unittest.TestCase):
    def test_a_gallery_of_every_photo_passes(self) -> None:
        g = gallery(item("IMG_1", "10"), item("loco_CSX_1_left", "1", "Locomotive", "locos"))
        self.assertEqual(F.check(g, [car("IMG_1.png", "10")], [loco("loco_CSX_1_left.jpg", "1")]), [])

    def test_an_item_whose_photo_is_no_master_row_fails(self) -> None:
        (problem,) = F.check(gallery(item("IMG_9", "10")), [], [])
        self.assertIn("is no master row's source_image", problem)

    def test_a_photo_from_elsewhere_names_its_row_by_roster_id(self) -> None:
        cars = [car("IMG_1.png", "10", rid="BO10")]
        g = gallery(item("IMG_1", "10"), {**item("21", "10"), "id": "x-10-2", "roster_id": "BO10"})
        self.assertEqual(F.check(g, cars, []), [])
        g["items"][1]["roster_id"] = "BO11"
        self.assertIn("is in neither master", F.check(g, cars, [])[0])

    def test_two_rows_with_one_photo_and_a_wrong_roster_id_fail(self) -> None:
        cars = [car("IMG_1.png", "10", rid="BO10"), car("IMG_1.jpg", "11")]
        self.assertIn("2 car rows share the photo 'IMG_1'", F.check(gallery(item("IMG_1", "10")), cars, [])[0])
        problems = F.check(gallery(item("IMG_1", "10", roster_id="BO99")), cars[:1], [])
        self.assertEqual(problems, ["item x-10: roster_id 'BO99'; its photo's row has BO10"])

    def test_a_wrong_number_or_type_fails_and_a_blank_number_does_not(self) -> None:
        cars = [car("IMG_1.png", "10")]
        self.assertIn("number '11'", F.check(gallery(item("IMG_1", "11")), cars, [])[0])
        self.assertIn("type 'Boxcar'", F.check(gallery(item("IMG_1", "10", "Boxcar")), cars, [])[0])
        self.assertEqual(F.check(gallery(item("IMG_1", "")), cars, []), [])

    def test_locomotives_and_only_locomotives_are_in_the_locos_album(self) -> None:
        problems = F.check(gallery(item("IMG_1", "10", album="locos")), [car("IMG_1.png", "10")], [])
        self.assertTrue(any("goes in 'locos'" in p for p in problems), problems)

    def test_one_type_in_two_albums_fails(self) -> None:
        g = gallery(item("IMG_1", "10"), item("IMG_2", "11", album="mow"))
        problems = F.check(g, [car("IMG_1.png", "10"), car("IMG_2.png", "11")], [])
        self.assertEqual(problems, ["type 'Hopper' is in several albums: freight, mow"])

    def test_a_stale_album_count_and_a_shared_id_fail(self) -> None:
        g = gallery(item("IMG_1", "10"), item("IMG_2", "11"))
        g["albums"][0]["count"] = 3
        g["items"][1]["id"] = "x-10"
        problems = F.check(g, [car("IMG_1.png", "10"), car("IMG_2.png", "11")], [])
        self.assertEqual(problems, ["album 'freight' count is 3; it has 2 items", "id 'x-10' is given to 2 items"])

    def test_a_photographed_row_missing_from_the_gallery_fails(self) -> None:
        problems = F.check(gallery(item("IMG_1", "10")), [car("IMG_1.png", "10"), car("IMG_2.png", "11")],
                           [loco("loco_CSX_1_left.jpg", "1")])
        self.assertEqual(len(problems), 2, problems)
        self.assertTrue(all("has a photo but no gallery item" in p for p in problems))

    def test_a_row_with_the_private_name_is_not_expected(self) -> None:
        F.contains_private_name, real = (lambda text: "SECRET" in text), F.contains_private_name
        try:
            self.assertEqual(F.check(gallery(item("IMG_1", "10")), [car("IMG_1.png", "10"),
                                                                    car("IMG_2.png", "SECRET")], []), [])
        finally:
            F.contains_private_name = real

    def test_the_repo_gallery_matches_the_masters(self) -> None:
        g = json.loads(F.GALLERY.read_text(encoding="utf-8"))
        self.assertEqual(F.check(g, F.read_csv(F.CARS), F.read_csv(F.LOCOS)), [])


if __name__ == "__main__":
    unittest.main()
