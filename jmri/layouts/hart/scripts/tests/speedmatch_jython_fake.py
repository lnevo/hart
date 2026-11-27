"""Run the speed-match Jython jobs in CPython against a fake JMRI, a virtual clock and an in-memory file system.

A job text (settings, jobkit.py, runner) is executed with its imports answered by fakes:
`time` is a virtual clock whose sleep fires scheduled events, `threading.Thread` runs its target
at start(), `os` and `open` see a set of file names instead of /tmp, and `jmri` offers only what
the jobs may use: the roster, the sensor manager and the throttle manager. A job that reached for
anything else (track power, a turnout, a programmer) fails with an AttributeError, which the job
logs as ERROR. A fake throttle answers only the calls a job is allowed to make.
"""
from __future__ import annotations

import builtins
import io
import threading
import types
from typing import Any, Callable, NamedTuple

ALLOWED_THROTTLE_CALLS = {"setSpeedSetting", "setIsForward", "getIsForward", "setF0", "setF8", "release"}


class JavaThrowable(Exception):
    pass


class Clock:
    """Virtual time: sleep() moves it forward and runs the events scheduled up to the new time."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.events: list[tuple[float, Callable[[], None]]] = []

    def time(self) -> float:
        return self.now

    def after(self, seconds: float, fn: Callable[[], None]) -> None:
        self.events.append((self.now + seconds, fn))

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        due = sorted((e for e in self.events if e[0] <= self.now), key=lambda e: e[0])
        self.events = [e for e in self.events if e[0] > self.now]
        for _, fn in due:
            fn()


class Files:
    """The file names a job may create or remove, and what it wrote to each."""

    def __init__(self, existing: tuple[str, ...] = ()) -> None:
        self.names: set[str] = set(existing)
        self.text: dict[str, io.StringIO] = {}

    def open(self, name: str, mode: str = "r") -> io.StringIO:
        if "w" in mode or "a" in mode:
            self.names.add(name)
            return self.text.setdefault(name, io.StringIO())
        raise FileNotFoundError(name)

    def exists(self, name: str) -> bool:
        return name in self.names

    def remove(self, name: str) -> None:
        if name not in self.names:
            raise OSError("no such file: " + name)
        self.names.discard(name)

    def markers(self) -> set[str]:
        """The names that are not logs: the run-marker files."""
        return self.names - set(self.text)

    def written(self, name: str) -> str:
        return self.text[name].getvalue() if name in self.text else ""


class SensorEvent:
    def __init__(self, new: int) -> None:
        self.new = new

    def getPropertyName(self) -> str:
        return "KnownState"

    def getNewValue(self) -> int:
        return self.new


class FakeSensor:
    def __init__(self, user: str, system: str, state: int = 4) -> None:
        self.user, self.system, self.state = user, system, state
        self.listeners: list[Any] = []

    def getUserName(self) -> str:
        return self.user

    def getSystemName(self) -> str:
        return self.system

    def getKnownState(self) -> int:
        return self.state

    def addPropertyChangeListener(self, listener: Any) -> None:
        self.listeners.append(listener)

    def removePropertyChangeListener(self, listener: Any) -> None:
        self.listeners.remove(listener)

    def fire(self, state: int) -> None:
        self.state = state
        for listener in list(self.listeners):
            listener.propertyChange(SensorEvent(state))


class FakeThrottle:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.calls: list[tuple[str, Any]] = []
        self.forward = True
        self.on_speed: Callable[[float], None] | None = None

    def __getattr__(self, name: str) -> Callable[..., Any]:
        if name not in ALLOWED_THROTTLE_CALLS and not name.startswith("setF"):
            raise AttributeError("a job called the throttle's " + name)
        if name.startswith("setF"):
            return lambda on: self.calls.append((name, on))
        return lambda *args: self._call(name, *args)

    def _call(self, name: str, *args: Any) -> Any:
        if name == "setIsForward":
            self.forward = bool(args[0])
        if name == "getIsForward":
            return self.forward
        self.calls.append((name, args[0] if args else None))
        if name == "setSpeedSetting" and self.on_speed is not None:
            self.on_speed(args[0])
        return None

    def speeds(self) -> list[float]:
        return [v for n, v in self.calls if n == "setSpeedSetting"]

    def released(self) -> bool:
        return any(n == "release" for n, _ in self.calls)


class FakeProfile:
    def __init__(self, points: dict[int, tuple[float, float]] | None = None, calls: list[str] | None = None) -> None:
        self.points = dict(points or {})
        self.calls = calls if calls is not None else []

    def getProfileSpeeds(self) -> Any:
        pts = self.points
        speed = lambda key: types.SimpleNamespace(getForwardSpeed=lambda: pts[key][0], getReverseSpeed=lambda: pts[key][1])
        return types.SimpleNamespace(keySet=lambda: list(pts), get=speed)

    def clearCurrentProfile(self) -> None:
        self.calls.append("clearCurrentProfile")
        self.points.clear()

    def setSpeed(self, key: int, forward: float, reverse: float) -> None:
        self.calls.append("setSpeed")
        self.points[int(key)] = (forward, reverse)


class FakeRosterEntry:
    def __init__(self, profile: FakeProfile | None, calls: list[str], fail_on_update: bool = False) -> None:
        self.profile, self.calls, self.fail_on_update = profile, calls, fail_on_update

    def getSpeedProfile(self) -> FakeProfile | None:
        return self.profile

    def setSpeedProfile(self, profile: FakeProfile) -> None:
        self.profile = profile

    def updateFile(self) -> None:
        self.calls.append("updateFile")
        if self.fail_on_update:
            raise JavaThrowable("disk full")


class World:
    """Everything the fake JMRI knows: roster entries, sensors, the throttle each request gets."""

    def __init__(self) -> None:
        self.clock = Clock()
        self.files = Files()
        self.entries: dict[str, FakeRosterEntry] = {}
        self.sensors: list[FakeSensor] = []
        self.throttle = FakeThrottle(self.clock)
        self.throttle_requests: list[str] = []
        self.answer_throttle = True
        self.calls: list[str] = []

    def sensor(self, user: str, system: str, state: int = 4) -> FakeSensor:
        s = FakeSensor(user, system, state)
        self.sensors.append(s)
        return s


class Result(NamedTuple):
    ns: dict[str, Any]
    log: list[str]
    world: World


def _modules(world: World) -> dict[str, Any]:
    class NoWaitEvent(threading.Event):
        def wait(self, timeout: float | None = None) -> bool:  # a request nobody answers must not stall the test
            return self.is_set()

    class SyncThread:
        def __init__(self, target: Callable[[], None]) -> None:
            self.target = target

        def setDaemon(self, flag: bool) -> None:
            pass

        def start(self) -> None:
            self.target()

    class ThrottleListener:
        pass

    class Roster:
        @staticmethod
        def getDefault() -> Any:
            return types.SimpleNamespace(getEntryForId=world.entries.get,
                                         writeRoster=lambda: world.calls.append("writeRoster"))

    class ThrottleManager:
        def requestThrottle(self, entry: Any, listener: Any, _steal: bool) -> None:
            world.throttle_requests.append(entry)
            if world.answer_throttle:
                listener.notifyThrottleFound(world.throttle)

    roster = types.SimpleNamespace(
        Roster=Roster,
        RosterSpeedProfile=lambda entry: FakeProfile(calls=world.calls))
    instance = types.SimpleNamespace(
        sensorManagerInstance=lambda: types.SimpleNamespace(getNamedBeanSet=lambda: list(world.sensors)),
        throttleManagerInstance=lambda: ThrottleManager())
    return {
        "time": types.SimpleNamespace(time=world.clock.time, sleep=world.clock.sleep),
        "threading": types.SimpleNamespace(Thread=lambda target: SyncThread(target), Event=NoWaitEvent,
                                           Lock=threading.Lock),
        "os": types.SimpleNamespace(path=types.SimpleNamespace(exists=world.files.exists), remove=world.files.remove),
        "java": types.SimpleNamespace(lang=types.SimpleNamespace(Throwable=JavaThrowable),
                                      beans=types.SimpleNamespace(PropertyChangeListener=object)),
        "jmri": types.SimpleNamespace(ThrottleListener=ThrottleListener, InstanceManager=instance,
                                      jmrit=types.SimpleNamespace(roster=roster)),
    }


def run_job(text: str, world: World) -> Result:
    """Execute a job text and return its globals and the log lines it wrote to its LOGF."""
    fakes = _modules(world)
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kw: Any) -> Any:
        return fakes[name] if name in fakes else real_import(name, *args, **kw)

    scope = dict(vars(builtins), __import__=fake_import, open=world.files.open)
    ns: dict[str, Any] = {"__builtins__": scope}
    exec(compile(text, "job", "exec"), ns)  # noqa: S102  the Jython job text, run in its own fresh namespace
    return Result(ns, world.files.written(ns["LOGF"]).splitlines(), world)
