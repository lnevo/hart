# liverule.py - the decision logic shared by the analysis and the live runner.
#
# Written in the common subset of Python 2.7 (Jython in JMRI) and Python 3: no f-strings,
# no annotations, no imports outside the standard library, no `statistics` module.
# `make_job.py` pastes this file in front of jython/step_runner.py, so the runner on the Pi
# runs exactly the code the tests run. Do not add imports of other repo modules here.
#
# Speed is measured per span: the time from the loco lighting block sensor i to lighting
# block sensor i+n, over the summed length of blocks i .. i+n-1 (n = 1 is one block). That is
# the same entry-to-entry method as the 2026-11-08 block_speeds.py.
import math

# Defaults (the owner can change them as settings of a run).
LOW_MAX = 48        # steps up to here use every block (span of 1)
HIGH_SPAN = 3       # steps above LOW_MAX may use spans of up to this many blocks
STOP_K = 5          # the last K readings decide whether a step has settled
STOP_REL = 0.02     # relative standard deviation under which a step has settled
MAX_READINGS = 12   # move on after this many readings whatever the spread
SETTLE_EVENTS = 2   # sensor events after a step change that are thrown away


def mean(v):
    return sum(v) / float(len(v))


def median(v):
    s = sorted(v)
    n = len(s)
    if n == 0:
        raise ValueError("median of nothing")
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def stdev(v):
    """Sample standard deviation; 0.0 for fewer than two values."""
    n = len(v)
    if n < 2:
        return 0.0
    m = mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1.0))


def rel_stdev(v):
    m = mean(v)
    return stdev(v) / m if m else float("inf")


def settled(vals, k=STOP_K, rel=STOP_REL):
    """True when at least k readings exist and the last k have a relative stdev under rel."""
    if len(vals) < k:
        return False
    return rel_stdev(vals[-k:]) < rel


def should_move_on(vals, k=STOP_K, rel=STOP_REL, max_n=MAX_READINGS):
    """The stop rule. Returns (move_on, reason); reason is 'settled', 'max' or ''."""
    if settled(vals, k, rel):
        return True, "settled"
    if len(vals) >= max_n:
        return True, "max"
    return False, ""


def replay(vals, k=STOP_K, rel=STOP_REL, max_n=MAX_READINGS):
    """Run the stop rule over readings already taken, as the runner did live.

    Returns (readings_used, reason, window). The window is the last k readings (or all of
    them if fewer) when the rule fired, or at the end of the data when it never did."""
    for n in range(1, len(vals) + 1):
        move, why = should_move_on(vals[:n], k, rel, max_n)
        if move:
            return n, why, vals[max(0, n - k):n]
    return len(vals), "", vals[-k:]


def span_for_step(step, low_max=LOW_MAX, high_span=HIGH_SPAN):
    """Low steps use every block (1); higher steps may use longer spans."""
    return 1 if step <= low_max else high_span


def span_speed(hist, order, lengths, n):
    """Speed over a span from the last n+1 sensor activations.

    hist    list of (epoch, sensor) in time order, newest last
    order   sensor names around the loop in one fixed direction (a ring)
    lengths dict sensor -> block length in mm, or None when the length is not trusted
    n       blocks in the span

    The n+1 activations must be consecutive blocks of the ring, all one way round (either
    way), and every block entered (all but the last) must have a trusted length. Returns
    (mm_per_s, seconds, mm) or None.
    """
    if n < 1 or len(hist) < n + 1:
        return None
    h = hist[-(n + 1):]
    size = len(order)
    try:
        idx = [order.index(s) for _, s in h]
    except ValueError:
        return None
    step = (idx[1] - idx[0]) % size
    if step not in (1, size - 1) or size < 3:
        return None
    for a, b in zip(idx, idx[1:]):
        if (b - a) % size != step:
            return None
    total = 0.0
    for _, s in h[:-1]:
        ln = lengths.get(s)
        if ln is None:
            return None
        total += ln
    dt = h[-1][0] - h[0][0]
    if dt <= 0:
        return None
    return total / dt, dt, total


class SpanReader(object):
    """Turns a stream of sensor activations into span speeds for one step.

    The live runner and the analysis both use this class, so they cannot disagree.
    Call restart(n) at every step change. feed() takes each ACTIVE event and returns a
    reading (mm_per_s, seconds, mm, blocks) or None. The first `settle` events after a
    restart are thrown away (the loco is still changing speed). Spans do not overlap:
    the event that ends a span starts the next one. If a span of n blocks is not possible
    (a block with no trusted length in it), shorter spans are tried, down to one block.
    """

    def __init__(self, order, lengths, settle=SETTLE_EVENTS):
        self.order = order
        self.lengths = lengths
        self.settle = settle
        self.n = 1
        self.skip = settle
        self.hist = []

    def restart(self, n):
        self.n = n
        self.skip = self.settle
        self.hist = []

    def feed(self, t, sensor):
        if self.skip > 0:
            self.skip -= 1
            return None
        if self.hist and self.hist[-1][1] == sensor:
            return None  # a retrigger of the same block
        self.hist.append((t, sensor))
        self.hist = self.hist[-(self.n + 1):]
        if len(self.hist) < self.n + 1:
            return None  # wait until a whole span has been seen
        for m in range(self.n, 0, -1):
            r = span_speed(self.hist, self.order, self.lengths, m)
            if r is not None:
                self.hist = [self.hist[-1]]
                return (r[0], r[1], r[2], m)
        return None


STALL_CAP = 300.0   # a stall limit never grows past this many seconds


def next_stall(stall0, cap, settled_interval):
    """The no-sensor-event limit for the next step.

    settled_interval is the mean seconds per reading of the last step that settled, or None.
    The limit follows slow steps up to four intervals, never below stall0 and never above
    cap. A step that stalled or gave no readings must not raise it: pass None."""
    base = stall0 if settled_interval is None else max(stall0, 4.0 * settled_interval)
    return min(base, cap)


def stall_action(step, skip_below):
    """What a stall at this step does: 'skip' the step (creep steps may not move) or 'end'."""
    return "skip" if step <= skip_below else "end"


# ---- distance mode (one continuous pass, measured over a distance, not a reading count) ----
DIST_STEPS = [8, 16, 24, 32, 48, 64, 96, 126]
DIST_TARGET_MM = 6000.0   # a step is done once the crossed blocks add up to this many mm ...
DIST_MIN_BLOCKS = 2       # ... and at least this many blocks were crossed
DIST_MAX_S = 60.0         # seconds of measuring after which a step ends whatever it has
DIST_REL = 0.03           # block readings that spread more than this earn one more reading
DIST_WARM_S = 60.0
DIST_WARM_STEP = 48
DIST_CV3 = 26             # momentum CVs of CSX 2121 and CSX 2738 (roster values)
DIST_CV4 = 24
MOMENTUM_K = 0.896        # seconds per CV3/CV4 unit for a change of the whole 126 steps
SETTLE_BASE_S = 2.0


def settle_time(cv3, cv4, prev_step, step):
    """Seconds to wait after a step change before measuring: momentum (CV3 going up, CV4
    going down) scaled by the size of the change, plus a fixed margin."""
    d = step - prev_step
    cv = cv3 if d >= 0 else cv4
    return MOMENTUM_K * cv * abs(d) / 126.0 + SETTLE_BASE_S


def aggregate(blocks):
    """blocks: list of (mm, seconds). Returns (n, mm, seconds, mm_per_s, relsd) with
    mm_per_s = sum(mm) / sum(seconds) and relsd the relative standard deviation of the
    single-block speeds (0.0 for fewer than two blocks)."""
    n = len(blocks)
    if n == 0:
        return 0, 0.0, 0.0, 0.0, 0.0
    mm = sum(b[0] for b in blocks)
    s = sum(b[1] for b in blocks)
    speeds = [b[0] / b[1] for b in blocks]
    return n, mm, s, (mm / s if s > 0 else 0.0), (rel_stdev(speeds) if n > 1 else 0.0)


class BlockReader(object):
    """Turns route sensor ACTIVE events into whole-block readings (distance mode).

    The first event only starts the chain. Each next event that is the neighbour of the last
    one on the ring, in one steady direction, completes the block of the last sensor
    (entry to entry); a block with no trusted length is skipped. An event that is not that
    neighbour (a missed sensor) starts the chain again. feed() returns
    (sensor, mm, seconds) or None. The live runner and the analysis both use it."""

    def __init__(self, order, lengths):
        self.order = order
        self.lengths = lengths
        self.restart()

    def restart(self):
        self.last = None
        self.dir = None

    def feed(self, t, sensor):
        if sensor not in self.order:
            return None
        if self.last is not None and self.last[1] == sensor:
            return None  # a retrigger of the same block
        prev = self.last
        self.last = (t, sensor)
        if prev is None:
            return None
        size = len(self.order)
        d = (self.order.index(sensor) - self.order.index(prev[1])) % size
        if size < 3 or d not in (1, size - 1) or (self.dir is not None and d != self.dir):
            self.dir = None
            return None
        self.dir = d
        mm = self.lengths.get(prev[1])
        dt = t - prev[0]
        if mm is None or dt <= 0:
            return None
        return (prev[1], mm, dt)


class DistanceStep(object):
    """The end rule of one distance-mode step. add() each block reading, then ask check()
    with the seconds measured so far: (done, reason). reason is 'settled' (enough distance and
    blocks), 'timed' (the time ran out with at least min_blocks blocks spreading within rel:
    still valid) or 'max' (the time ran out and the data is not good enough). When the distance is reached but the single-block
    speeds spread more than rel and a second reading of target_mm still fits in the time left,
    the step goes on for one more target_mm (extra_new is True once, for the log)."""

    def __init__(self, target_mm=DIST_TARGET_MM, min_blocks=DIST_MIN_BLOCKS,
                 max_s=DIST_MAX_S, rel=DIST_REL):
        self.target_mm = target_mm
        self.min_blocks = min_blocks
        self.max_s = max_s
        self.rel = rel
        self.blocks = []
        self.goal = target_mm
        self.extra = False
        self.extra_new = False
        self.relsd = 0.0

    def add(self, mm, dt):
        self.blocks.append((mm, dt))

    def check(self, elapsed):
        n, mm, s, v, rsd = aggregate(self.blocks)
        if mm >= self.goal and n >= self.min_blocks:
            if not self.extra:
                self.relsd = rsd
                if rsd > self.rel and v > 0 and elapsed + self.target_mm / v <= self.max_s:
                    self.extra = True
                    self.extra_new = True
                    self.goal = mm + self.target_mm
                    return False, ""
            return True, "settled"
        if elapsed >= self.max_s:
            if n >= self.min_blocks and rsd <= self.rel:
                self.relsd = rsd
                return True, "timed"
            return True, "max"
        return False, ""


def is_valid_reason(reason):
    """A distance step's reading is used when it ended 'settled' (distance reached) or
    'timed' (time limit, but at least min_blocks blocks with a spread within rel)."""
    return reason in ("settled", "timed")


def next_after(order, frm, to):
    """The sensor after `to`, going the way round the ring that leads from `frm` to `to`
    (the shorter way). The pass job ends when this one lights."""
    size = len(order)
    i, j = order.index(frm), order.index(to)
    step = 1 if (j - i) % size <= size // 2 else -1
    return order[(j + step) % size]
