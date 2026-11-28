#!/usr/bin/env python3
"""The merge queue behind `make land`: one merge at a time across sessions, first come, first served.

    land_queue.py status        (make land-status) every ticket: number, PR, session, state, PID, and the last
                                lines of its own log; then the old merge lock's holder, if any
    land_queue.py wait N        (make land-wait PR=N) wait for PR N's land job to end; exit with its code (0 merged
                                and main green, 1 refused, 4 main red, 5 unwatched), read from the result file
                                the job writes; 2 when there is no job or result, or the newest ticket of the
                                PR left none (an earlier ticket's result never answers)

Each land job has a log and a result of its own, named by PR and ticket: ~/.cache/hart/land/<PR>-t<ticket>.log and
<PR>-t<ticket>.result. A job queued by older code wrote <PR>.log and <PR>.result; both are still read when a
ticket has no file of its own. Every land job also appends one line to ~/.cache/hart/land/events.log when its PR's
head moves and when it ends (event_line gives the format), so a coordinator can watch that one file; status prints
its last EVENTS_TAIL lines.

Each `make land` takes a numbered ticket in QUEUE_DIR (a JSON file NNNNNN.ticket: PID, PR, session, time, state),
written whole to a temporary name and linked to its number, so a reader never sees half a ticket. Numbers are
reserved in QUEUE_DIR/numbers/ with O_EXCL and never handed out twice, and each ticket carries its land's token:
update and release act only on a file that still carries it, and never make a missing ticket again. The lowest live ticket is the head of the queue and merges; the others wait behind it with no time
limit while every ticket ahead of them is alive, with a line every LOCK_SAY seconds naming their place and the head.
A ticket whose PID is gone is skipped: it is renamed away, only while its file is still the one judged dead, and
removed with a line. A ticket whose PID is alive but that has been the head, or in the queue, for over LOCK_CEILING seconds
is cleared the same way.

MergeLock is the old merge lock (LOCK_PATH, a folder made with mkdir) from before the queue. The head of the queue
still takes it before it merges, so a `make land` started from older code (which knows only the lock) and one from
this code never merge at the same time. It goes once no older land can still be running.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

QUEUE_DIR = Path(os.environ.get("HART_LAND_QUEUE") or "/tmp/hart-land-queue")
LOCK_PATH = Path(os.environ.get("HART_LAND_LOCK") or "/tmp/hart-land.lock")
LOG_DIR = Path(os.environ.get("HART_LAND_LOGS") or Path.home() / ".cache/hart/land")
LOCK_STALE = 2700           # seconds: an old lock whose holder process is gone and that is older than this is stale
LOCK_CEILING = 3 * LOCK_STALE   # seconds: a holder (lock or queue head) older than this is stale even when alive
LOCK_SAY = 60               # seconds between "waiting" lines
LOCK_POLL = 5
SESSION_ENV = "HART_SESSION_NAME"
SUFFIX = ".ticket"
LOG_TAIL = 3
EVENTS = "events.log"
EVENTS_TAIL = 10
RESERVED_KEEP = 50       # reserved-number files kept below the newest one
ADOPT_WAIT = 30          # seconds make land waits for its job to put its own PID on the ticket
ADOPT_POLL = 0.1

Say = Callable[[str], None]
Sleep = Callable[[float], None]
Clock = Callable[[], float]


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True         # another user's process: it exists
    return True


def session_name(holder: str = "") -> str:
    return (holder or os.environ.get(SESSION_ENV) or "unnamed").replace("\n", " ")


def _named(pr: int, ticket: int | None, suffix: str) -> str:
    return f"{pr}{suffix}" if ticket is None else f"{pr}-t{ticket}{suffix}"


def log_path(pr: int, log_dir: Path = LOG_DIR, ticket: int | None = None) -> Path:
    """Where the land job of `pr` under `ticket` writes its output (<PR>-t<ticket>.log); with no ticket, the name
    older code used (<PR>.log)."""
    return log_dir / _named(pr, ticket, ".log")


def find_log(pr: int, ticket: int | None, log_dir: Path = LOG_DIR) -> Path:
    """The ticket's own log; the old <PR>.log when the ticket has none and that file exists."""
    own = log_path(pr, log_dir, ticket)
    old = log_path(pr, log_dir)
    return old if not own.exists() and old.exists() else own


# ------------------------------------------------------------ the old merge lock (transition)

@dataclass(frozen=True)
class LockOwner:
    """The merge lock's owner file: "pid since-epoch pr holder", as written by MergeLock.claim."""
    raw: str
    pid: int | None
    since: float | None
    pr: str
    holder: str

    @classmethod
    def parse(cls, raw: str) -> LockOwner:
        words = raw.split(None, 3)
        pid = int(words[0]) if words and words[0].isdigit() else None
        since = float(words[1]) if len(words) > 1 and words[1].isdigit() else None
        return cls(raw, pid, since, words[2] if len(words) > 2 else "?", words[3].strip() if len(words) > 3 else "?")


@dataclass
class MergeLock:
    """The folder `path`, made with mkdir, holding an owner file (LockOwner). A lock whose holder process is gone (or
    that has no owner file) and that is older than LOCK_STALE seconds (its owner's time, else the folder's mtime), or
    any lock older than LOCK_CEILING, is stale: it is renamed away, only while its owner file is still the one judged
    stale, and removed with a line. The same rule as tools/hosts/win_run.sh's mac lock block."""
    path: Path
    pr: int
    say: Say
    sleep: Sleep = time.sleep
    wall: Clock = time.time
    alive: Callable[[int], bool] = pid_alive
    holder: str = ""
    held: bool = False

    def claim(self) -> bool:
        try:
            self.path.mkdir()
        except FileExistsError:
            return False
        try:
            (self.path / "owner").write_text(f"{os.getpid()} {int(self.wall())} {self.pr} {session_name(self.holder)}\n",
                                             encoding="utf-8")
        except BaseException:
            # a lock with no owner file would hold every other land for LOCK_STALE: take the folder back first
            (self.path / "owner").unlink(missing_ok=True)
            self.path.rmdir()
            raise
        self.held = True
        return True

    def owner(self) -> LockOwner:
        try:
            return LockOwner.parse((self.path / "owner").read_text(encoding="utf-8"))
        except OSError:
            return LockOwner.parse("")

    def age(self, owner: LockOwner) -> float:
        since = owner.since
        if since is None:
            try:
                since = self.path.stat().st_mtime
            except OSError:
                since = self.wall()
        return self.wall() - since

    def clear_if_stale(self, owner: LockOwner) -> None:
        age = self.age(owner)
        if age <= LOCK_STALE or (age <= LOCK_CEILING and owner.pid is not None and self.alive(owner.pid)):
            return
        if self.owner().raw != owner.raw:
            return
        aside = self.path.with_name(f"{self.path.name}.stale.{os.getpid()}")
        try:
            self.path.rename(aside)
        except OSError:
            return
        shutil.rmtree(aside, ignore_errors=True)
        why = "gone" if owner.pid is None or not self.alive(owner.pid) else f"alive past {LOCK_CEILING // 60} min"
        self.say(f"the merge lock {self.path} was stale (holder {owner.holder}, PID {owner.pid or 'none'} {why}, "
                 f"{int(age // 60)} min old); cleared it")

    def take(self) -> bool:
        """Return once this process holds the lock; True when it had to wait. No time limit: a live holder is
        waited for until it ends or passes LOCK_CEILING."""
        waited = 0.0
        while True:
            if self.claim():
                return waited > 0
            owner = self.owner()
            self.clear_if_stale(owner)
            if self.claim():
                return waited > 0
            if waited % LOCK_SAY == 0:
                self.say(f"{time.strftime('%H:%M')} waiting for the old merge lock ({self.path}): {owner.holder} "
                         f"holds it for PR #{owner.pr} (PID {owner.pid or '?'}, {int(self.age(owner) // 60)} min)")
            self.sleep(LOCK_POLL)
            waited += LOCK_POLL

    def release(self) -> None:
        if not self.held:
            return
        (self.path / "owner").unlink(missing_ok=True)
        try:
            self.path.rmdir()
        except OSError:
            pass
        self.held = False


# ------------------------------------------------------------ the queue

class NotOurs(OSError):
    """The ticket file is gone or now carries another land's token: this handle may not write or remove it."""


@dataclass(frozen=True)
class Ticket:
    """One ticket file. `raw` is the file's text when read: a ticket is cleared only while it still reads the same.
    `token` is the land's own mark, written when it took the ticket: update and release act only on a file that
    still carries it."""
    number: int
    path: Path
    raw: str
    token: str
    pid: int | None
    pr: int | None
    session: str
    since: float | None
    state: str
    head_since: float | None

    @classmethod
    def read(cls, path: Path) -> Ticket | None:
        """The ticket at `path`; None when it is gone. A file that is not a ticket's JSON has no PID: it is dead."""
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            obj = json.loads(raw)
        except ValueError:
            obj = None
        data = obj if isinstance(obj, dict) else {}

        def num(key: str) -> float | None:
            value = data.get(key)
            return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

        pid, pr = num("pid"), num("pr")
        return cls(number=int(path.name[:-len(SUFFIX)]), path=path, raw=raw, token=str(data.get("token", "")),
                   pid=None if pid is None else int(pid), pr=None if pr is None else int(pr),
                   session=str(data.get("session", "?")), since=num("since"), state=str(data.get("state", "?")),
                   head_since=num("head_since"))

    def fields(self) -> dict[str, object]:
        return {"token": self.token, "pid": self.pid, "pr": self.pr, "session": self.session, "since": self.since,
                "state": self.state, "head_since": self.head_since}

    def label(self) -> str:
        return f"ticket {self.number} (PR #{self.pr}, {self.session}, PID {self.pid or '?'})"


@dataclass(frozen=True)
class Result:
    """What a land job wrote when it ended: its ticket and exit code."""
    ticket: int | None
    code: int


def result_path(pr: int, log_dir: Path = LOG_DIR, ticket: int | None = None) -> Path:
    """The result file of the land job of `pr` under `ticket` (<PR>-t<ticket>.result); with no ticket, the name
    older code used (<PR>.result)."""
    return log_dir / _named(pr, ticket, ".result")


def write_result(pr: int, ticket: int | None, code: int, log_dir: Path = LOG_DIR) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    tmp = log_dir / f".{pr}.result.{os.getpid()}"
    tmp.write_text(json.dumps({"ticket": ticket, "code": code, "at": time.time()}), encoding="utf-8")
    os.replace(tmp, result_path(pr, log_dir, ticket))


def ticket_files(pr: int, log_dir: Path = LOG_DIR, suffix: str = ".result") -> list[int]:
    """The tickets with a <PR>-t<ticket><suffix> file for `pr`."""
    prefix = f"{pr}-t"
    return [int(p.name[len(prefix):-len(suffix)]) for p in log_dir.glob(f"{prefix}*{suffix}")
            if p.name[len(prefix):-len(suffix)].isdigit()]


def newest_ticket(pr: int, log_dir: Path = LOG_DIR) -> int | None:
    """The highest ticket with a result file for `pr`; None when there is none."""
    return max(ticket_files(pr, log_dir), default=None)


def read_result(pr: int, log_dir: Path = LOG_DIR, ticket: int | None = None) -> Result | None:
    """The result of `ticket`'s land of `pr`; with no ticket, the newest ticket's. The old <PR>.result is read when
    no ticket file is found."""
    own = result_path(pr, log_dir, ticket if ticket is not None else newest_ticket(pr, log_dir))
    path = own if own.exists() else result_path(pr, log_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("code"), int):
        return None
    ticket = data.get("ticket")
    return Result(ticket if isinstance(ticket, int) else None, data["code"])


@dataclass
class LandQueue:
    root: Path
    say: Say
    sleep: Sleep = time.sleep
    wall: Clock = time.time
    alive: Callable[[int], bool] = pid_alive
    _tmp: int = field(default=0, repr=False)

    @property
    def numbers(self) -> Path:
        """The reserved numbers: one empty file per number ever handed out, so a number is never handed out twice."""
        return self.root / "numbers"

    def tickets(self) -> list[Ticket]:
        try:
            names = [p for p in self.root.iterdir() if p.name.endswith(SUFFIX) and p.name[:-len(SUFFIX)].isdigit()]
        except FileNotFoundError:
            return []
        found = [Ticket.read(p) for p in names]
        return sorted((t for t in found if t is not None), key=lambda t: t.number)

    def live(self, pr: int) -> Ticket | None:
        """The first ticket for `pr` that still holds its place."""
        return next((t for t in self.tickets() if t.pr == pr and not self.stale(t)), None)

    def _write_new(self, text: str) -> Path:
        """`text` in a new file of its own in the queue folder, not yet a ticket."""
        self._tmp += 1
        tmp = self.root / f".new-{os.getpid()}-{time.time_ns()}-{self._tmp}"
        tmp.write_text(text, encoding="utf-8")
        return tmp

    def reserve(self) -> int:
        """A number no ticket ever had: one past the highest reserved, claimed by creating its file (O_EXCL)."""
        self.numbers.mkdir(parents=True, exist_ok=True)
        marks = [int(p.name) for p in self.numbers.iterdir() if p.name.isdigit()]
        number = max([*marks, *(t.number for t in self.tickets())], default=0) + 1
        while True:
            try:
                os.close(os.open(self.numbers / f"{number:06d}", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            except FileExistsError:
                number += 1
                continue
            for old in marks:       # the highest mark is all a later reserve needs
                if old < number - RESERVED_KEEP:
                    (self.numbers / f"{old:06d}").unlink(missing_ok=True)
            return number

    def take(self, pr: int, session: str, pid: int | None = None) -> Ticket:
        """A new ticket, numbered after every number handed out before, for PR `pr`, held by `pid` (this process)."""
        self.root.mkdir(parents=True, exist_ok=True)
        text = json.dumps({"token": uuid.uuid4().hex, "pid": pid or os.getpid(), "pr": pr, "session": session,
                           "since": self.wall(), "state": "queued", "head_since": None})
        tmp = self._write_new(text)
        try:
            target = self.root / f"{self.reserve():06d}{SUFFIX}"
            os.link(tmp, target)            # the whole file appears at once
        finally:
            tmp.unlink(missing_ok=True)
        ticket = Ticket.read(target)
        if ticket is None:
            raise NotOurs(f"the ticket {target} was removed as it was taken")
        return ticket

    def _ours(self, ticket: Ticket) -> Ticket:
        now = Ticket.read(ticket.path)
        if now is None or now.token != ticket.token:
            raise NotOurs(f"ticket {ticket.number} ({ticket.path}) is no longer this land's: it was cleared")
        return now

    def update(self, ticket: Ticket, **changes: object) -> Ticket:
        """The ticket with `changes`, rewritten whole, only while the file still carries this land's token; a
        missing ticket is never made again (NotOurs)."""
        self._ours(ticket)
        tmp = self._write_new(json.dumps({**ticket.fields(), **changes}))
        os.replace(tmp, ticket.path)
        return Ticket.read(ticket.path) or ticket

    def adopt(self, path: Path) -> Ticket | None:
        """The ticket at `path`, now naming this process: what a land job does first with the ticket it was given."""
        ticket = Ticket.read(path)
        if ticket is None:
            return None
        return self.update(ticket, pid=os.getpid(), state="started")

    def release(self, ticket: Ticket) -> None:
        """Remove the ticket, only while it is still this land's."""
        try:
            self._ours(ticket)
        except NotOurs:
            return
        ticket.path.unlink(missing_ok=True)

    def stale(self, ticket: Ticket) -> str:
        """Why `ticket` no longer holds its place ("" when it does)."""
        if ticket.pid is None or not self.alive(ticket.pid):
            return "its PID is gone"
        for since, what in ((ticket.head_since, "the head"), (ticket.since, "in the queue")):
            if since is not None and self.wall() - since > LOCK_CEILING:
                return f"its PID is alive but it has been {what} for over {LOCK_CEILING // 60} min"
        return ""

    def clear(self, ticket: Ticket, why: str) -> None:
        """Remove `ticket`, only while its file still reads as it did when judged."""
        now = Ticket.read(ticket.path)
        if now is None or now.raw != ticket.raw:
            return
        aside = ticket.path.with_name(f".stale-{ticket.path.name}-{os.getpid()}")
        try:
            ticket.path.rename(aside)
        except OSError:
            return
        aside.unlink(missing_ok=True)
        self.say(f"skipped {ticket.label()} in the merge queue: {why}; cleared it")

    def ahead(self, mine: Ticket) -> list[Ticket]:
        """The live tickets ahead of `mine`, stale ones cleared on the way."""
        live = []
        for ticket in self.tickets():
            if ticket.number >= mine.number:
                break
            why = self.stale(ticket)
            if why:
                self.clear(ticket, why)
            else:
                live.append(ticket)
        return live

    def wait_turn(self, mine: Ticket, guard: Callable[[], None] = lambda: None) -> tuple[Ticket, bool]:
        """Return once `mine` is the head of the queue (its ticket marked so), and whether it had to wait. No time
        limit: it waits while any ticket ahead is alive. `guard` runs before every poll and raises to stop the wait
        (land.py: the PR closed, conflicts or has a new head)."""
        waited = 0.0
        while True:
            guard()
            ahead = self.ahead(mine)
            if not ahead:
                return self.update(mine, state="head", head_since=self.wall()), waited > 0
            if waited % LOCK_SAY == 0:
                head = ahead[0]
                self.say(f"{time.strftime('%H:%M')} waiting in the merge queue: place {len(ahead) + 1}, ticket "
                         f"{mine.number}; the head is {head.label()}, {head.state}")
            self.sleep(LOCK_POLL)
            waited += LOCK_POLL

    def wait_adopted(self, ticket: Ticket, pid: int, limit: float = ADOPT_WAIT) -> bool:
        """Whether the job `pid` took over `ticket` within `limit` seconds (it writes its own PID first)."""
        waited = 0.0
        while waited <= limit:
            now = Ticket.read(ticket.path)
            if now is None or now.token != ticket.token or now.pid == pid:
                return True             # adopted, or already done and released
            self.sleep(ADOPT_POLL)
            waited += ADOPT_POLL
        return False


# ------------------------------------------------------------ the events log

def event_line(when: str, ticket: int | None, pr: int, session: str, code: int | None, reason: str) -> str:
    """One events.log line: "HH:MM:SS ticket T PR #N SESSION exit C: REASON" ("running" in place of "exit C" for a
    job that goes on, such as a head that moved). The reason is one line."""
    end = "running" if code is None else f"exit {code}"
    return f"{when} ticket {'?' if ticket is None else ticket} PR #{pr} {session_name(session)} {end}: " + \
        " ".join(reason.split())


def append_event(line: str, log_dir: Path = LOG_DIR) -> None:
    """Append one line to events.log; a single short write in append mode, so lines of jobs ending together do not
    mix."""
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / EVENTS).open("a", encoding="utf-8") as out:
        out.write(line.rstrip("\n") + "\n")


# ------------------------------------------------------------ make land-status and make land-wait

def tail(path: Path, lines: int = LOG_TAIL) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [line for line in text.splitlines() if line.strip()][-lines:]


def status(queue: LandQueue, log_dir: Path = LOG_DIR, lock_path: Path = LOCK_PATH) -> list[str]:
    """The lines `make land-status` prints."""
    out: list[str] = []
    tickets = queue.tickets()
    out.append(f"merge queue {queue.root}: " + (f"{len(tickets)} ticket(s)" if tickets else "empty"))
    for ticket in tickets:
        alive = ticket.pid is not None and queue.alive(ticket.pid)
        age = "" if ticket.since is None else f", {int((queue.wall() - ticket.since) // 60)} min"
        out.append(f"  ticket {ticket.number}: PR #{ticket.pr}, {ticket.session}, {ticket.state}, "
                   f"PID {ticket.pid or '?'} {'alive' if alive else 'gone'}{age}")
        if ticket.pr is not None:
            out.extend(f"    {line}" for line in tail(find_log(ticket.pr, ticket.number, log_dir)))
    owner = MergeLock(lock_path, 0, queue.say).owner() if lock_path.exists() else None
    if owner is not None:
        out.append(f"old merge lock {lock_path}: held by {owner.holder} for PR #{owner.pr} (PID {owner.pid or '?'})")
    events = tail(log_dir / EVENTS, EVENTS_TAIL)
    if events:
        out.append(f"land events ({log_dir / EVENTS}, last {len(events)}):")
        out.extend(f"  {line}" for line in events)
    return out


def newest_queued(queue: LandQueue, pr: int, log_dir: Path = LOG_DIR) -> int | None:
    """The highest ticket known for `pr`: from its result files, its log files (detach writes one per ticket) and
    the tickets still in the queue, live or not; None when there is none."""
    queued = [t.number for t in queue.tickets() if t.pr == pr]
    return max([*ticket_files(pr, log_dir), *ticket_files(pr, log_dir, ".log"), *queued], default=None)


def wait(queue: LandQueue, pr: int, log_dir: Path = LOG_DIR) -> int:
    """make land-wait: wait for PR `pr`'s land job to end and return its exit code (0 merged and main green, 1
    refused, 4 main red, 5 unwatched); 2 when there is neither a job nor a result for it. With no live job, only
    the result of the newest ticket known for the PR answers: an earlier ticket's result is not this land's."""
    seen = queue.live(pr)
    number = seen.number if seen is not None else newest_queued(queue, pr, log_dir)
    log = find_log(pr, number, log_dir)
    if seen is not None:
        queue.say(f"waiting for the land of #{pr} ({seen.label()}, {seen.state}); log: {log}")
    while seen is not None and queue.live(pr) is not None:
        queue.sleep(LOCK_POLL)
    result = read_result(pr, log_dir, number)
    if result is None or (seen is not None and result.ticket not in (None, seen.number)) or \
            (seen is None and number is not None and result.ticket != number):
        queue.say(f"no result for a land of #{pr} in {result_path(pr, log_dir, number)}: see {log}")
        return 2
    queue.say(f"the land of #{pr} (ticket {result.ticket}) ended with exit {result.code}; log: {log}")
    return result.code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="land_queue.py", description="make land's merge queue.")
    ap.add_argument("command", choices=["status", "wait"],
                    help="status: the queue and each log's last lines; wait PR: wait for that land's exit code")
    ap.add_argument("pr", nargs="?", type=int, help="the PR, for wait")
    a = ap.parse_args(argv)
    queue = LandQueue(QUEUE_DIR, print)
    if a.command == "wait":
        if a.pr is None:
            ap.error("wait needs the PR number")
        return wait(queue, a.pr)
    for line in status(queue):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
