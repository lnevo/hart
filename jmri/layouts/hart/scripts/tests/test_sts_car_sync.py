from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "sts_car_sync.py"
spec = importlib.util.spec_from_file_location("sts_car_sync", SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class Track:
    def __init__(self, name, types=("Boxcar", "Tank", "Covered Hopper")):
        self.name, self.types = name, types

    def getName(self):
        return self.name


class Location:
    def __init__(self, name, *tracks):
        self.name, self.tracks = name, list(tracks)

    def getName(self):
        return self.name

    def getTrackByName(self, name, kind):
        return next((t for t in self.tracks if t.name == name), None)

    def getTracksByNameList(self, kind):
        return list(self.tracks)


class Car:
    def __init__(self, road, number, kind="Boxcar", location=None, track=None, load="E"):
        self.road, self.number, self.kind = road, number, kind
        self.location, self.track, self.load = location, track, load
        self.final, self.final_track, self.train = None, None, None

    def getId(self):
        return self.road + self.number

    def getRoadName(self):
        return self.road

    def getNumber(self):
        return self.number

    def getTypeName(self):
        return self.kind

    def getLocation(self):
        return self.location

    def getTrack(self):
        return self.track

    def getLoadName(self):
        return self.load

    def getFinalDestination(self):
        return self.final

    def getFinalDestinationTrack(self):
        return self.final_track

    def getTrain(self):
        return self.train

    def testLocation(self, location, track):
        return sync.OKAY if self.kind in track.types else "type (%s)" % self.kind

    def setLocation(self, location, track, force):
        self.location, self.track = location, track
        return sync.OKAY

    def setLoadName(self, load):
        self.load = load

    def setFinalDestination(self, location):
        self.final = location

    def setFinalDestinationTrack(self, track):
        self.final_track = track


class Cars:
    def __init__(self, *cars):
        self.cars = list(cars)

    def getById(self, car_id):
        return next((c for c in self.cars if c.getId() == car_id), None)

    def getList(self):
        return list(self.cars)


class Locations:
    def __init__(self, *locations):
        self.locations = list(locations)

    def getLocationByName(self, name):
        return next((l for l in self.locations if l.name == name), None)


class Loads:
    known = {("Boxcar", "E"), ("Boxcar", "Steel"), ("Tank", "E"), ("Tank", "LPG")}

    def getDefaultEmptyName(self):
        return "E"

    def containsName(self, kind, load):
        return (kind, load) in self.known


class Train:
    def getName(self):
        return "NVL"


def railroad():
    s1, s2 = Track("S-1", ("Tank",)), Track("S-2")
    south = Location("South Yard", s1, s2)
    team = Track("Team Track")
    stucki = Location("A. Stucki Co.", team)
    ferr = Location("Ferrellgas", Track("LPG Unload", ("Tank",)))
    cars = Cars(Car("BO", "8476", location=south, track=s2), Car("UTLX", "1", "Tank"))
    return sync.Railroad(cars, Locations(south, stucki, ferr), Loads()), south, stucki, ferr


class PlanTest(unittest.TestCase):
    def test_full_update_sets_location_load_and_final_destination(self):
        rr, south, stucki, _ = railroad()
        out = sync.run_batch(rr, {"cars": [{"car": "BO8476", "location": "A. Stucki Co.", "track": "Team Track",
                                            "load": "Steel", "final_location": "South Yard", "final_track": ""}]})
        car = rr.cars.getById("BO8476")
        self.assertEqual(out["summary"], {"changed": 1})
        self.assertEqual((car.location, car.track.name, car.load), (stucki, "Team Track", "Steel"))
        self.assertIs(car.final, south)
        self.assertIsNone(car.final_track)

    def test_blank_track_keeps_the_current_track_at_the_same_location(self):
        rr, south, _, _ = railroad()
        out = sync.run_batch(rr, {"cars": [{"car": "BO8476", "location": "South Yard", "load": ""}]})
        self.assertEqual(out["cars"][0]["status"], "unchanged")
        self.assertEqual(rr.cars.getById("BO8476").track.name, "S-2")

    def test_blank_track_picks_the_first_track_that_accepts_the_car(self):
        rr, south, _, _ = railroad()
        sync.run_batch(rr, {"cars": [{"car": "UTLX1", "location": "South Yard"}]})
        self.assertEqual(rr.cars.getById("UTLX1").track.name, "S-1")

    def test_no_accepting_track_places_on_the_first_and_says_so(self):
        rr, _, stucki, _ = railroad()
        stucki.tracks[0].types = ("Flatcar",)
        out = sync.run_batch(rr, {"cars": [{"car": "BO8476", "location": "A. Stucki Co."}]})
        self.assertEqual(rr.cars.getById("BO8476").track.name, "Team Track")
        self.assertIn("accepts it", out["cars"][0]["notes"][0])

    def test_blank_final_location_clears_it(self):
        rr, south, _, _ = railroad()
        car = rr.cars.getById("BO8476")
        car.final = south
        sync.run_batch(rr, {"cars": [{"car": "BO8476", "location": "South Yard", "final_location": ""}]})
        self.assertIsNone(car.final)

    def test_dry_run_reports_but_changes_nothing_and_does_not_save(self):
        rr, _, _, _ = railroad()
        saved = []
        out = sync.run_batch(rr, {"dry_run": True, "cars": [{"car": "BO8476", "location": "A. Stucki Co.",
                                                             "load": "Steel"}]}, save=lambda: saved.append(1))
        car = rr.cars.getById("BO8476")
        self.assertEqual(out["cars"][0]["status"], "changed")
        self.assertEqual((car.track.name, car.load), ("S-2", "E"))
        self.assertEqual(saved, [])
        self.assertFalse(out["saved"])

    def test_save_runs_once_after_changes_and_is_skipped_when_nothing_changed(self):
        rr, _, _, _ = railroad()
        saved = []
        sync.run_batch(rr, {"cars": [{"car": "BO8476", "location": "South Yard"}]}, save=lambda: saved.append(1))
        self.assertEqual(saved, [])
        out = sync.run_batch(rr, {"cars": [{"car": "BO8476", "load": "Steel"}]}, save=lambda: saved.append(1))
        self.assertEqual(saved, [1])
        self.assertTrue(out["saved"])

    def test_cars_on_a_train_unknown_cars_and_bad_names_are_reported_not_applied(self):
        rr, _, _, _ = railroad()
        rr.cars.getById("UTLX1").train = Train()
        out = sync.run_batch(rr, {"cars": [
            {"car": "UTLX1", "location": "Ferrellgas"},
            {"car": "XX9", "location": "South Yard"},
            {"car": "BO8476", "location": "Nowhere"},
            {"car": "BO8476", "location": "South Yard", "track": "S-9"},
        ]})
        self.assertEqual([c["status"] for c in out["cars"]], ["skipped", "skipped", "error", "error"])
        self.assertIn("NVL", out["cars"][0]["reason"])
        self.assertIsNone(rr.cars.getById("UTLX1").location)

    def test_named_track_that_refuses_the_car_is_still_used_with_a_note(self):
        rr, _, _, _ = railroad()
        out = sync.run_batch(rr, {"cars": [{"car": "BO8476", "location": "Ferrellgas", "track": "LPG Unload"}]})
        self.assertEqual(rr.cars.getById("BO8476").track.name, "LPG Unload")
        self.assertIn("would refuse", out["cars"][0]["notes"][0])

    def test_change_text_names_none_for_a_blank_side(self):
        rr, _, _, _ = railroad()
        out = sync.run_batch(rr, {"cars": [{"car": "BO8476", "location": "South Yard", "final_location": "Ferrellgas",
                                            "final_track": "LPG Unload"}]})
        self.assertIn("final destination none -> Ferrellgas / LPG Unload", out["cars"][0]["changes"])

    def test_unknown_load_is_still_set_with_a_note(self):
        rr, _, _, _ = railroad()
        out = sync.run_batch(rr, {"cars": [{"car": "BO8476", "load": "Cheese"}]})
        self.assertEqual(rr.cars.getById("BO8476").load, "Cheese")
        self.assertIn("not defined", out["cars"][0]["notes"][0])

    def test_changes_run_through_the_gui_hook(self):
        rr, _, _, _ = railroad()
        calls = []
        sync.run_batch(rr, {"cars": [{"car": "BO8476", "load": "Steel"}]}, on_gui=lambda f: (calls.append(1), f()))
        self.assertEqual(calls, [1])
        self.assertEqual(rr.cars.getById("BO8476").load, "Steel")

    def test_answer_echoes_the_id_and_survives_bad_json(self):
        rr, _, _, _ = railroad()
        self.assertEqual(sync.answer(rr, json.dumps({"id": "a1", "cars": []}))["id"], "a1")
        bad = sync.answer(rr, "{not json")
        self.assertFalse(bad["ok"])

    def test_script_never_touches_turnouts_signals_or_mqtt(self):
        src = SCRIPT.read_text(encoding="utf-8")
        for word in ("Turnout", "SignalMast", "mqtt", "setCommandedState"):
            self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
