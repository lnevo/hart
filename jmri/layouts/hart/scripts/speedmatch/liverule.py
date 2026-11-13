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
