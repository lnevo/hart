#!/usr/bin/env python3
"""The merge queue behind `make land`: one merge at a time across sessions, first come, first served.

    land_queue.py status        (make land-status) every ticket: number, PR, session, state, PID, and the last
                                lines of its log; then the old merge lock's holder, if any

Each `make land` takes a numbered ticket in QUEUE_DIR (a JSON file NNNNNN.ticket: PID, PR, session, time, state),
written whole to a temporary name and linked to its number, so a reader never sees half a ticket and two takers never
share a number. The lowest live ticket is the head of the queue and merges; the others wait behind it with no time
limit while every ticket ahead of them is alive, with a line every LOCK_SAY seconds naming their place and the head.
A ticket whose PID is gone is skipped: it is renamed away, only while its file is still the one judged dead, and
removed with a line. A head whose PID is alive but that has been the head for over LOCK_CEILING seconds is cleared the
same way.

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


def log_path(pr: int, log_dir: Path = LOG_DIR) -> Path:
    """Where a detached land for `pr` writes its output."""
    return log_dir / f"{pr}.log"


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

@dataclass(frozen=True)
class Ticket:
    """One ticket file. `raw` is the file's text when read: a ticket is cleared only while it still reads the same."""
    number: int
    path: Path
    raw: str
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
        return cls(number=int(path.name[:-len(SUFFIX)]), path=path, raw=raw,
                   pid=None if pid is None else int(pid), pr=None if pr is None else int(pr),
                   session=str(data.get("session", "?")), since=num("since"), state=str(data.get("state", "?")),
                   head_since=num("head_since"))

    def fields(self) -> dict[str, object]:
        return {"pid": self.pid, "pr": self.pr, "session": self.session, "since": self.since, "state": self.state,
                "head_since": self.head_since}

    def label(self) -> str:
        return f"ticket {self.number} (PR #{self.pr}, {self.session}, PID {self.pid or '?'})"


@dataclass
class LandQueue:
    root: Path
    say: Say
    sleep: Sleep = time.sleep
    wall: Clock = time.time
    alive: Callable[[int], bool] = pid_alive
    _tmp: int = field(default=0, repr=False)

    def tickets(self) -> list[Ticket]:
        try:
            names = [p for p in self.root.iterdir() if p.name.endswith(SUFFIX) and p.name[:-len(SUFFIX)].isdigit()]
        except FileNotFoundError:
            return []
        found = [Ticket.read(p) for p in names]
        return sorted((t for t in found if t is not None), key=lambda t: t.number)

    def _write_new(self, text: str) -> Path:
        """`text` in a new file of its own in the queue folder, not yet a ticket."""
        self._tmp += 1
        tmp = self.root / f".new-{os.getpid()}-{time.time_ns()}-{self._tmp}"
        tmp.write_text(text, encoding="utf-8")
        return tmp

    def take(self, pr: int, session: str, pid: int | None = None) -> Ticket:
        """A new ticket, numbered after every ticket in the queue, for PR `pr`, held by `pid` (this process)."""
        self.root.mkdir(parents=True, exist_ok=True)
        now = self.wall()
        text = json.dumps({"pid": pid or os.getpid(), "pr": pr, "session": session, "since": now,
                           "state": "queued", "head_since": None})
        tmp = self._write_new(text)
        try:
            number = max((t.number for t in self.tickets()), default=0) + 1
            while True:
                target = self.root / f"{number:06d}{SUFFIX}"
                try:
                    os.link(tmp, target)      # fails when the number is taken: the next one
                except FileExistsError:
                    number += 1
                    continue
                break
        finally:
            tmp.unlink(missing_ok=True)
        ticket = Ticket.read(target)
        if ticket is None:
            raise OSError(f"the ticket {target} was removed as it was taken")
        return ticket

    def update(self, ticket: Ticket, **changes: object) -> Ticket:
        """The ticket with `changes`, rewritten whole (a temporary file replaces it)."""
        fields = {**ticket.fields(), **changes}
        tmp = self._write_new(json.dumps(fields))
        os.replace(tmp, ticket.path)
        return Ticket.read(ticket.path) or ticket

    def release(self, ticket: Ticket) -> None:
        ticket.path.unlink(missing_ok=True)

    def stale(self, ticket: Ticket) -> str:
        """Why `ticket` no longer holds its place ("" when it does)."""
        if ticket.pid is None or not self.alive(ticket.pid):
            return "its PID is gone"
        if ticket.head_since is not None and self.wall() - ticket.head_since > LOCK_CEILING:
            return f"its PID is alive but it has been the head for over {LOCK_CEILING // 60} min"
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

    def wait_turn(self, mine: Ticket) -> tuple[Ticket, bool]:
        """Return once `mine` is the head of the queue (its ticket marked so), and whether it had to wait. No time
        limit: it waits while any ticket ahead is alive."""
        waited = 0.0
        while True:
            ahead = self.ahead(mine)
            if not ahead:
                if not mine.path.exists():
                    raise OSError(f"ticket {mine.number} ({mine.path}) is gone from the merge queue")
                return self.update(mine, state="head", head_since=self.wall()), waited > 0
            if waited % LOCK_SAY == 0:
                head = ahead[0]
                self.say(f"{time.strftime('%H:%M')} waiting in the merge queue: place {len(ahead) + 1}, ticket "
                         f"{mine.number}; the head is {head.label()}, {head.state}")
            self.sleep(LOCK_POLL)
            waited += LOCK_POLL


# ------------------------------------------------------------ make land-status

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
            log = log_path(ticket.pr, log_dir)
            out.extend(f"    {line}" for line in tail(log))
    owner = MergeLock(lock_path, 0, queue.say).owner() if lock_path.exists() else None
    if owner is not None:
        out.append(f"old merge lock {lock_path}: held by {owner.holder} for PR #{owner.pr} (PID {owner.pid or '?'})")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="land_queue.py", description="make land's merge queue.")
    ap.add_argument("command", choices=["status"], help="status: the queue and the last lines of each log")
    ap.parse_args(argv)
    for line in status(LandQueue(QUEUE_DIR, print)):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
