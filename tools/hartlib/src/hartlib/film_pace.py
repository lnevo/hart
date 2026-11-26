"""The pace of the four panel films on www/behind/panel-evolution.html.

Every film shows each version for STEP_S seconds and holds the last one for FINAL_HOLD_S, so a film grows
as versions are added. The schematic film (tools/schematic/evolution.py) and the three stop-motion films
(tools/ctc_history/films.py) all take their timing from here.
"""

STEP_S = 0.4
FINAL_HOLD_S = 2.0


def durations(n: int) -> list[float]:
    """Seconds on screen for each of n frames: STEP_S each, the last held FINAL_HOLD_S."""
    if n < 2:
        raise ValueError(f"{n} frame: a film needs at least two")
    return [STEP_S] * (n - 1) + [FINAL_HOLD_S]


def film_length(n: int) -> float:
    """Total seconds of a film of n frames."""
    return round(sum(durations(n)), 4)
