# sts_car_sync.py - takes car positions, loads and final destinations from STS.
#
# STS is the master of a session. Its jmri_ops plugin sends one batch of cars,
# and this script copies them into Operations Pro, so manifests, the roster and
# CATS show the same railroad. The stock JSON server can move a car, but cannot
# set its load or final destination, so the batch arrives in a Memory instead:
#
#   IMSTS_CAR_SYNC_REQUEST  JSON {"id", "dry_run", "save", "cars": [...]}
#   IMSTS_CAR_SYNC_REPLY    JSON {"id", "ok", "summary", "cars": [...]}
#   IMSTS_CAR_SYNC_READY    version, set once this script is listening
#
# Each car is {"car", "location", "track", "load", "final_location",
# "final_track"}, all JMRI names. {"id", "command": "names"} instead answers
# with JMRI's locations, their tracks and the loads, for STS's settings screen. A blank track keeps the car's track when it is
# already at that location, else takes the first track that accepts it. A blank
# load is JMRI's default empty. A blank final location clears it.
#
# Cars on a built train are left alone and reported. Nothing here touches
# turnouts, signals or MQTT. The logic below runs without JMRI so it can be
# tested; only the bottom of the file needs Jython.

from __future__ import print_function

import json
import sys

VERSION = "2"
REQUEST = "IMSTS_CAR_SYNC_REQUEST"
REPLY = "IMSTS_CAR_SYNC_REPLY"
READY = "IMSTS_CAR_SYNC_READY"
OKAY = "okay"  # jmri.jmrit.operations.locations.Track.OKAY


def _text(value):
    return ("%s" % value).strip() if value is not None else ""


def _name(bean):
    return bean.getName() if bean is not None else ""


def _where(location, track):
    if location is None:
        return "none"
    return location.getName() + (" / " + track.getName() if track is not None else "")


class Railroad(object):
    """What the sync needs from JMRI. The Jython part fills it with the managers."""

    def __init__(self, cars, locations, loads, types=None):
        self.cars = cars
        self.locations = locations
        self.loads = loads
        self.types = types

    def car(self, car_id):
        car = self.cars.getById(car_id)
        if car is None:
            for candidate in self.cars.getList():
                if car_id in (candidate.getId(), candidate.getRoadName() + candidate.getNumber(),
                              candidate.getRoadName() + " " + candidate.getNumber()):
                    return candidate
        return car

    def location(self, name):
        return self.locations.getLocationByName(name) if name else None

    def empty_name(self):
        return self.loads.getDefaultEmptyName()

    def load_known(self, car, load):
        return self.loads.containsName(car.getTypeName(), load)

    def names(self):
        """JMRI's location, track and load names, sorted."""
        locations = {}
        for location in self.locations.getLocationsByNameList():
            locations[location.getName()] = [t.getName() for t in location.getTracksByNameList(None)]
        loads = set()
        for kind in (self.types.getNames() if self.types is not None else []):
            for load in self.loads.getNames(kind):
                loads.add("%s" % load)
        return {"locations": locations, "loads": sorted(loads), "empty": self.empty_name()}


def choose_track(car, location, wanted):
    """The track to use, a note, and an error. wanted is a track name or blank."""
    if wanted:
        track = location.getTrackByName(wanted, None)
        if track is None:
            return None, "", "no track %s at %s" % (wanted, location.getName())
        status = car.testLocation(location, track)
        if status != OKAY:
            return track, "placed as STS has it, though JMRI would refuse it on %s: %s" % (wanted, status), ""
        return track, "", ""
    if car.getLocation() == location and car.getTrack() is not None:
        return car.getTrack(), "", ""
    tracks = list(location.getTracksByNameList(None))
    for track in tracks:
        if car.testLocation(location, track) == OKAY:
            return track, "", ""
    if tracks:
        return tracks[0], "no track at %s accepts it; placed on %s anyway" % (
            location.getName(), tracks[0].getName()), ""
    return None, "", "%s has no tracks" % location.getName()


def plan_car(railroad, entry):
    """Work out one car's changes without making them.

    Returns (result, actions); result is what goes back to STS and actions are
    callables that make the change.
    """
    car_id = _text(entry.get("car"))
    result = {"car": car_id, "status": "unchanged", "changes": [], "notes": []}
    car = railroad.car(car_id)
    if car is None:
        result.update(status="skipped", reason="not in the JMRI roster")
        return result, []
    if car.getTrain() is not None:
        result.update(status="skipped", reason="on train %s; terminate or reset it first" % _name(car.getTrain()))
        return result, []
    actions = []

    location_name = _text(entry.get("location"))
    if location_name:
        location = railroad.location(location_name)
        if location is None:
            result.update(status="error", reason="no location %s" % location_name)
            return result, []
        track, note, error = choose_track(car, location, _text(entry.get("track")))
        if error:
            result.update(status="error", reason=error)
            return result, []
        if note:
            result["notes"].append(note)
        if car.getLocation() != location or car.getTrack() != track:
            result["changes"].append("location %s -> %s" % (
                _where(car.getLocation(), car.getTrack()), _where(location, track)))
            actions.append(lambda: car.setLocation(location, track, True))

    load = _text(entry.get("load")) or railroad.empty_name()
    if load != car.getLoadName():
        if not railroad.load_known(car, load):
            result["notes"].append("load %s is not defined for %s" % (load, car.getTypeName()))
        result["changes"].append("load %s -> %s" % (car.getLoadName(), load))
        actions.append(lambda: car.setLoadName(load))

    final_name = _text(entry.get("final_location"))
    final, final_track = None, None
    if final_name:
        final = railroad.location(final_name)
        if final is None:
            result["notes"].append("no location %s; final destination left as it was" % final_name)
            final_name = None
        else:
            track_name = _text(entry.get("final_track"))
            if track_name:
                final_track = final.getTrackByName(track_name, None)
                if final_track is None:
                    result["notes"].append("no track %s at %s; final destination set without a track" % (
                        track_name, final_name))
    if final_name is not None and (car.getFinalDestination() != final or car.getFinalDestinationTrack() != final_track):
        result["changes"].append("final destination %s -> %s" % (
            _where(car.getFinalDestination(), car.getFinalDestinationTrack()), _where(final, final_track)))

        def set_final():
            car.setFinalDestination(final)
            car.setFinalDestinationTrack(final_track)
        actions.append(set_final)

    if actions:
        result["status"] = "changed"
    return result, actions


def run_batch(railroad, batch, on_gui=None, save=None):
    """Apply a batch. on_gui runs a callable on JMRI's GUI thread; save stores Operations."""
    dry_run = bool(batch.get("dry_run"))
    results, actions = [], []
    for entry in batch.get("cars") or []:
        try:
            result, todo = plan_car(railroad, entry)
        except Exception as exc:  # one bad car must not stop the rest
            result, todo = {"car": _text(entry.get("car")), "status": "error", "reason": str(exc),
                            "changes": [], "notes": []}, []
        results.append(result)
        actions.extend(todo)
    if actions and not dry_run:
        def apply_all():
            for action in actions:
                action()
        (on_gui or (lambda f: f()))(apply_all)
    summary = {}
    for result in results:
        summary[result["status"]] = summary.get(result["status"], 0) + 1
    saved = False
    if actions and not dry_run and batch.get("save", True) and save is not None:
        save()
        saved = True
    return {"id": batch.get("id"), "ok": True, "dry_run": dry_run, "saved": saved,
            "summary": summary, "cars": results}


def answer(railroad, text, on_gui=None, save=None):
    batch = {}
    try:
        batch = json.loads(text)
        if batch.get("command") == "names":
            out = railroad.names()
            out.update(id=batch.get("id"), ok=True)
            return out
        return run_batch(railroad, batch, on_gui, save)
    except Exception as exc:
        return {"id": batch.get("id") if isinstance(batch, dict) else None, "ok": False, "error": str(exc)}


def _start():
    import java
    from java.beans import PropertyChangeListener
    from java.util.concurrent import LinkedBlockingQueue
    from jmri import InstanceManager, MemoryManager
    from jmri.jmrit.operations import OperationsXml
    from jmri.jmrit.operations.locations import LocationManager
    from jmri.jmrit.operations.rollingstock.cars import CarLoads, CarManager, CarTypes
    from jmri.util import ThreadingUtil

    memories = InstanceManager.getDefault(MemoryManager)
    request = memories.provideMemory(REQUEST)
    reply = memories.provideMemory(REPLY)
    ready = memories.provideMemory(READY)
    jobs = LinkedBlockingQueue()

    def railroad():
        return Railroad(InstanceManager.getDefault(CarManager), InstanceManager.getDefault(LocationManager),
                        InstanceManager.getDefault(CarLoads), InstanceManager.getDefault(CarTypes))

    def on_gui(function):
        ThreadingUtil.runOnGUI(function)

    def work():
        while True:
            text = jobs.take()
            try:
                out = answer(railroad(), text, on_gui, OperationsXml.save)
            except java.lang.Exception as exc:
                out = {"ok": False, "error": str(exc)}
            reply.setValue(json.dumps(out))

    class RequestListener(PropertyChangeListener):
        def propertyChange(self, event):
            if event.getPropertyName() == "value" and event.getNewValue():
                jobs.put(str(event.getNewValue()))

    for old in request.getPropertyChangeListeners():
        if "RequestListener" in str(old):
            request.removePropertyChangeListener(old)
    thread = java.lang.Thread(work)
    thread.setName("STS car sync")
    thread.setDaemon(True)
    thread.start()
    request.addPropertyChangeListener(RequestListener())
    ready.setValue(VERSION)
    print("sts_car_sync listening on " + REQUEST)


if sys.platform.startswith("java"):  # Jython inside JMRI; plain Python is the tests
    _start()
