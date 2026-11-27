"""The live STS over its API, for compare --live-sts and sync --live-sts.

Reads are GET /health and GET /cars; sync's only write is PATCH /cars/{id} with ``remarks``, after a
backup (ADR-018). Every refusal raises LiveStsError, and nothing falls back to the seed. A non-local
STS is not touched while the operating flag is set.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from car_fields import expected_cars, field_diffs, print_diffs, seed_helpers
from car_records import CarRow, FieldDiff
from car_repo import HART_ROOT, NO_SEED_DIR, STS_HELPERS

LIVE_STS_TIMEOUT = 20
BACKUP_TIMEOUT = 120  # a database backup takes longer than a read
OPERATING_SH = HART_ROOT / "tools/hosts/operating.sh"
SYNC_BACKUP_PREFIX = "cars_sync_"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


class LiveStsError(RuntimeError):
    """The live section cannot run; the message says why. Never falls back to the seed."""


class StsApi(Protocol):
    """The parts of the sts-helpers client (lib/sts_api.py) used here."""

    # sts_api.ApiError (attributes code and message). The client lives in the sts-helpers submodule,
    # which mypy does not read, so its class is not known here.
    ApiError: Any

    def base_url(self) -> str: ...

    def backups_dir(self) -> Path: ...

    def get(self, path: str) -> object: ...

    def get_all(self, path: str) -> list[object]: ...

    def post(self, path: str, body: object = None) -> object: ...

    def patch(self, path: str, body: object) -> object: ...


@dataclass(frozen=True)
class LiveCar:
    """One car of GET /cars: its STS id and the identity fields compare and sync read."""

    sts_id: int | None
    reporting_marks: str
    remarks: str

    @classmethod
    def from_api(cls, body: object, url: str) -> LiveCar:
        if not isinstance(body, dict):
            raise LiveStsError(f"STS at {url} gave a car that is not an object: {body!r}")
        sts_id = body.get("id")
        if sts_id is not None and not isinstance(sts_id, int):
            raise LiveStsError(f"STS at {url} gave a car id that is not a number: {body!r}")
        return cls(sts_id, str(body.get("reporting_marks") or ""), str(body.get("remarks") or ""))


@dataclass(frozen=True)
class LiveCars:
    """GET /health and GET /cars of one STS."""

    url: str
    stack: str
    cars: list[LiveCar]


def operating_reason() -> str | None:
    """The operating flag's reason when it is set, else None (operating.sh status exits 0 when set)."""
    try:
        out = subprocess.run(
            [str(OPERATING_SH), "status"], capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError) as err:
        raise LiveStsError(f"cannot read the operating flag ({err}); not touching the live STS") from err
    if out.returncode == 1:
        return None
    if out.returncode != 0:
        raise LiveStsError(f"cannot read the operating flag (exit {out.returncode}); not touching the STS")
    line = out.stdout.strip()
    return line.split("reason=", 1)[1] if "reason=" in line else (line or "set")


def target_is_local(url: str) -> bool:
    """The Mac's own STS (UAT or sandbox) is Mac-only work and stays open while operating."""
    return (urlsplit(url).hostname or "") in LOCAL_HOSTS


def target_url() -> str:
    return os.environ.get("STS_API_URL", "").strip() or "http://localhost:8980/sts/api/v1"


def refuse_while_operating(operating: Callable[[], str | None], verb: str) -> None:
    """Raise when the target is not this Mac and the operating flag is set."""
    if target_is_local(target_url()):
        return
    reason = operating()
    if reason:
        raise LiveStsError(f"the operating flag is set ({reason}); {target_url()} is not {verb}")


@contextlib.contextmanager
def capped_timeout(seconds: int) -> Iterator[None]:
    """sts_api waits up to an hour per request (for long tasks); a read here must not."""
    real = urllib.request.urlopen

    def capped(url: Any, data: Any = None, timeout: Any = None, *a: Any, **kw: Any) -> Any:
        # urlopen's own signature; only the timeout is replaced.
        return real(url, data, seconds, *a, **kw)

    urllib.request.urlopen = capped
    try:
        yield
    finally:
        urllib.request.urlopen = real


def load_sts_api() -> StsApi:
    """The sts-helpers client, the one place the car workflow imports it (and sts_paths beside it)."""
    helpers_lib = str(STS_HELPERS / "lib")
    if not (STS_HELPERS / "lib/sts_api.py").is_file():
        raise LiveStsError(NO_SEED_DIR.format(path=STS_HELPERS / "lib"))
    if helpers_lib not in sys.path:
        sys.path.insert(0, helpers_lib)
    import sts_api

    return sts_api  # type: ignore[no-any-return]  # the submodule is not on mypy's path


def fetch_live_cars() -> LiveCars:
    """GET /health and GET /cars through the sts-helpers client.

    The URL is STS_API_URL (the caller sets it for this job only); GET requests only.
    """
    sts_api = load_sts_api()
    url = sts_api.base_url()
    try:
        with capped_timeout(LIVE_STS_TIMEOUT):
            health = sts_api.get("/health")
            cars = sts_api.get_all("/cars")
    except sts_api.ApiError as err:
        if err.code == "unreachable":
            raise LiveStsError(f"cannot reach STS at {url}: {err.message.split(': ', 1)[-1]}") from err
        raise LiveStsError(f"STS at {url} refused the read: {err}") from err
    except (OSError, ValueError, TypeError) as err:  # timeouts and bad bodies
        raise LiveStsError(f"cannot read STS at {url}: {type(err).__name__}: {err}") from err
    if not isinstance(health, dict):
        raise LiveStsError(f"STS at {url} gave an unexpected /health answer: {health!r}")
    return LiveCars(url, str(health.get("stack", "unknown")), [LiveCar.from_api(c, url) for c in cars])


def live_sts_diffs(rows: list[CarRow], live: Sequence[LiveCar], passenger_types: frozenset[str] | set[str]
                   ) -> list[FieldDiff]:
    """Differences between the repository and the live STS car list, keyed by reporting marks.

    Compared: remarks ("{type} {length}ft"), as the seed builds it. Reporting marks are the key.
    Not compared: position, load, status, job or destination (ADR-016).
    """
    tool = {c.reporting_marks: {"remarks": c.remarks} for c in live if c.reporting_marks}
    want = {
        f"{a['roadName']}{a['roadNumber']}": {"remarks": f"{a['type']} {a['length']}ft"}
        for a in expected_cars(rows, frozenset(passenger_types)).values()
        if a.get("type") and a.get("length")
    }
    return field_diffs(want, tool, {"remarks": "remarks"})


def print_live_sts(rows: list[CarRow], show_all: bool, fetch: Callable[[], LiveCars] = fetch_live_cars,
                   operating: Callable[[], str | None] = operating_reason) -> int:
    """The opt-in live STS section. Returns 0, or 2 when it could not run (nothing else is read instead)."""
    print("\nSTS API fields (GET /cars, read only):")
    try:
        refuse_while_operating(operating, "read")
        gen, why = seed_helpers()
        if gen is None:
            raise LiveStsError(f"cannot check: {why}")
        live = fetch()
    except LiveStsError as err:
        print(f"  Cannot check the STS API: {err}")
        return 2
    print(f"  Target: {live.stack} ({live.url}), {len(live.cars)} cars")
    marks = [c.reporting_marks for c in live.cars]
    seen = {m for m in marks if m}
    dups = sorted({m for m in seen if marks.count(m) > 1})
    if dups:
        print(f"  Duplicate reporting marks in the STS: {' '.join(dups)}")
    print_diffs(live_sts_diffs(rows, live.cars, set(gen.PASSENGER_TYPES)), show_all)
    repo_marks = {f"{a['roadName']}{a['roadNumber']}" for a in expected_cars(rows, frozenset()).values()}
    extra = sorted(seen - repo_marks)
    print(f"  In the live STS, not in the repository: {' '.join(extra) or 'none'}")
    return 0


def take_sts_backup(api: StsApi, local: bool, now: float | None = None) -> str:
    """ADR-018: a backup under 12 hours old, else make one with POST /admin/backups.

    A folder on this Mac says nothing about the Pi, so a non-local STS always gets a new backup.
    """
    import publish_gate as gate

    backups = api.backups_dir()
    if local and not gate.backup_missing(backups, now):
        return f"a backup under {gate.BACKUP_MAX_AGE_HOURS} hours old is in {backups}"
    name = f"{SYNC_BACKUP_PREFIX}{int(time.time() if now is None else now)}"
    try:
        with capped_timeout(BACKUP_TIMEOUT):
            api.post("/admin/backups", {"name": name})
    except api.ApiError as err:
        raise LiveStsError(f"could not take an STS backup first ({err})") from err
    except (OSError, ValueError, TypeError) as err:
        raise LiveStsError(f"could not take an STS backup first ({type(err).__name__}: {err})") from err
    return f"took STS backup {name}"


def read_back(body: object, field: str) -> object:
    """The field of a GET /cars/{id} answer, unwrapping a {"data": ...} envelope if the client hands one back."""
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        body = body["data"]
    return body.get(field) if isinstance(body, dict) else body


def write_live_cars(api: StsApi, live: Sequence[LiveCar], diffs: list[FieldDiff]) -> list[str]:
    """PATCH one car at a time and read it back; stops at the first problem."""
    by_marks: dict[str, list[LiveCar]] = {}
    for car in live:
        by_marks.setdefault(car.reporting_marks, []).append(car)
    done: list[str] = []

    def stop(marks: str, why: str) -> LiveStsError:
        return LiveStsError(f"sync stopped at car {marks}: {why}; written so far: {' '.join(done) or 'none'}")

    for marks, field, want, _have in diffs:
        found = by_marks.get(marks, [])
        if len(found) != 1:
            raise stop(marks, f"{len(found)} STS cars have these reporting marks")
        car_id = found[0].sts_id
        if car_id is None:
            raise stop(marks, "the STS car has no id")
        try:
            with capped_timeout(LIVE_STS_TIMEOUT):
                api.patch(f"/cars/{car_id}", {field: want})
                back = api.get(f"/cars/{car_id}")
        except api.ApiError as err:
            raise stop(marks, str(err)) from err
        except (OSError, ValueError, TypeError) as err:
            raise stop(marks, f"{type(err).__name__}: {err}") from err
        got = read_back(back, field)
        if (got or "") != want:
            raise stop(marks, f"read back {field}={got!r}, wanted {want!r}")
        done.append(marks)
    return done
