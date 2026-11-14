#!/usr/bin/env python3
"""Original soundtracks for the promo cuts, synthesised from scratch.

Nothing here samples or imitates a recording: every sound is built from
oscillators and noise, so the music has no outside rights holder and nothing
for YouTube Content ID to match. The arrangement follows each cut's edit, with
the kick on the picture cuts and a crash on each title slam.

    .venv/bin/python tools/promo/soundtrack.py site out.wav

Progression: D - A - Bm - G (I - V - vi - IV) in D major, one chord per bar.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, fftconvolve, sawtooth, sosfilt, sosfilt_zi

SR = 44100
SEED = 7
RNG = np.random.default_rng(SEED)  # reseeded per track in render(): same track every time

PADS = [(62, 66, 69), (61, 64, 69), (62, 66, 71), (62, 67, 71)]  # D, A, Bm, G
BASS = [38, 33, 35, 31]
ARP = [0, 1, 2, 1, 0, 2, 1, 2]  # chord-tone order for 16th plucks


@dataclass
class Cue:
    """When things happen, in beats. Sections are (start, end, kind)."""
    bpm: float
    beats: int
    sections: list[tuple[int, int, str]]
    hits: list[int] = field(default_factory=list)  # crash + stop
    outro: float = 0  # beat of the final chord (may fall between beats)


CUES = {
    # build: 100 BPM, 0.6 s beat. Hook 3 beats, seven 0.6 s cuts, drop on the
    # reveal at 6.0 s (beat 10), end card at 24.8 s (beat 41.33), video ends 27.8 s.
    "build": Cue(bpm=100, beats=47, sections=[(0, 3, "intro"), (3, 10, "rise"),
                                              (10, 42, "full")], hits=[10], outro=24.8 / 0.6),
    # site: 85.71 BPM, 0.7 s beat, so every shot is one beat. Slams at beats
    # 3, 10, 17, 25; end card at 32; video ends 25.9 s (beat 37).
    "site": Cue(bpm=600 / 7, beats=37, sections=[(0, 3, "rise"), (3, 32, "full")],
                hits=[3, 10, 17, 25], outro=32),
}


# ---------------------------------------------------------------- primitives

def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def lp(x: np.ndarray, fc: float, order: int = 2) -> np.ndarray:
    return sosfilt(butter(order, min(fc, SR * 0.45), "low", fs=SR, output="sos"), x)


def hp(x: np.ndarray, fc: float, order: int = 2) -> np.ndarray:
    return sosfilt(butter(order, fc, "high", fs=SR, output="sos"), x)


def bp(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return sosfilt(butter(2, (lo, hi), "band", fs=SR, output="sos"), x)


def sweep_lp(x: np.ndarray, f0: float, f1: float, block: int = 512) -> np.ndarray:
    """Low-pass whose cutoff glides exponentially from f0 to f1."""
    out = np.empty_like(x)
    zi = None
    nblocks = max(1, len(x) // block + 1)
    for b in range(nblocks):
        seg = x[b * block:(b + 1) * block]
        if not len(seg):
            break
        fc = f0 * (f1 / f0) ** (b / nblocks)
        sos = butter(2, min(fc, SR * 0.45), "low", fs=SR, output="sos")
        if zi is None:
            zi = sosfilt_zi(sos) * 0
        seg_out, zi = sosfilt(sos, seg, zi=zi)
        out[b * block:b * block + len(seg)] = seg_out
    return out


def env(n: int, attack: float, release: float) -> np.ndarray:
    e = np.ones(n)
    a, r = int(attack * SR), int(release * SR)
    if a:
        e[:a] = np.linspace(0, 1, min(a, n))[:n] if a <= n else np.linspace(0, n / a, n)
    if r and r < n:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def decay(n: int, rate: float) -> np.ndarray:
    return np.exp(-np.arange(n) / SR * rate)


def saw(freq: float, n: int, detune_cents: float = 0.0) -> np.ndarray:
    f = freq * 2 ** (detune_cents / 1200)
    phase = RNG.random() * 2 * np.pi
    return sawtooth(2 * np.pi * f * np.arange(n) / SR + phase)


def place(buf: np.ndarray, sig: np.ndarray, t: float, gain: float = 1.0) -> None:
    i = int(t * SR)
    if i < 0:  # starts before the track: keep only the part after 0
        sig, i = sig[-i:], 0
    if i >= len(buf) or not len(sig):
        return
    m = min(len(sig), len(buf) - i)
    buf[i:i + m] += sig[:m] * gain


# ---------------------------------------------------------------- instruments

def kick() -> np.ndarray:
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 46 + 120 * np.exp(-t * 32)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6.5)
    click = hp(RNG.standard_normal(n), 2500) * np.exp(-t * 300) * 0.25
    return np.tanh((body + click) * 1.6)


def clap() -> np.ndarray:
    n = int(0.3 * SR)
    noise = bp(RNG.standard_normal(n), 900, 5000)
    e = decay(n, 22)
    for k in (0.0, 0.011, 0.022):  # three quick bursts, like hands
        i = int(k * SR)
        e[i:i + int(0.008 * SR)] = np.maximum(e[i:i + int(0.008 * SR)], 1.0)
    tone = np.sin(2 * np.pi * 190 * np.arange(n) / SR) * decay(n, 30) * 0.3
    return (noise * e * 0.6 + tone)


def hat(open_: bool = False) -> np.ndarray:
    n = int((0.25 if open_ else 0.06) * SR)
    return hp(RNG.standard_normal(n), 7500) * decay(n, 9 if open_ else 70)


def crash() -> np.ndarray:
    n = int(2.6 * SR)
    x = hp(RNG.standard_normal(n), 3500) * decay(n, 1.8)
    return x + hp(RNG.standard_normal(n), 9000) * decay(n, 4) * 0.5


def riser(seconds: float) -> np.ndarray:
    n = int(seconds * SR)
    x = sweep_lp(RNG.standard_normal(n), 300, 9000)
    return x * np.linspace(0, 1, n) ** 2


def pad_note(midi: int, seconds: float, cutoff: float, side: int) -> np.ndarray:
    n = int(seconds * SR)
    cents = 7 if side else -7
    x = saw(hz(midi), n, cents) + saw(hz(midi), n, -cents * 0.4) * 0.7
    return lp(x, cutoff) * env(n, 0.25, min(0.5, seconds * 0.4))


def bass_note(midi: int, seconds: float) -> np.ndarray:
    n = int(seconds * SR)
    x = saw(hz(midi), n) + np.sin(2 * np.pi * hz(midi) * np.arange(n) / SR) * 0.8
    return lp(x, 520) * env(n, 0.004, 0.03) * decay(n, 2.5)


def pluck(midi: int, seconds: float, cutoff: float) -> np.ndarray:
    n = int(seconds * SR)
    t = np.arange(n) / SR
    x = saw(hz(midi), n) * 0.6 + np.sign(np.sin(2 * np.pi * hz(midi) * t)) * 0.3
    return lp(x, cutoff) * decay(n, 13) * env(n, 0.002, 0.02)


def reverb(x: np.ndarray, seconds: float = 1.8, seed: int = 0) -> np.ndarray:
    n = int(seconds * SR)
    ir = np.random.default_rng(seed).standard_normal(n) * decay(n, 3.8)
    ir = lp(ir, 5000)
    ir /= np.sqrt(np.sum(ir ** 2))
    return fftconvolve(x, ir)[:len(x)]


# ---------------------------------------------------------------- arranger

def section_at(cue: Cue, beat: int) -> str:
    for a, b, kind in cue.sections:
        if a <= beat < b:
            return kind
    return "outro"


def render(cut: str) -> np.ndarray:
    global RNG
    RNG = np.random.default_rng(SEED)  # independent of what rendered before
    cue = CUES[cut]
    beat = 60.0 / cue.bpm
    total = cue.beats * beat
    n = int(total * SR) + SR
    mk = lambda: np.zeros(n)  # noqa: E731
    drums, bass, pad_l, pad_r, arp_l, arp_r, fx = (mk() for _ in range(7))
    kicks: list[float] = []
    K, C, H, HO = kick(), clap(), hat(), hat(True)

    for b in range(cue.beats):
        t = b * beat
        kind = section_at(cue, b)
        bar, pos = divmod(b, 4)
        chord = bar % 4
        hit = b in cue.hits
        if b >= cue.outro and cue.outro:
            continue
        # drums
        if kind in ("rise", "full"):
            place(drums, K, t, 1.0)
            kicks.append(t)
        if kind == "full" and not hit:
            if pos in (1, 3):
                place(drums, C, t, 0.55)
            for s in range(4):
                place(drums, H, t + s * beat / 4, 0.16 if s % 2 else 0.09)
            place(drums, HO, t + beat / 2, 0.08)
        if kind == "rise":
            place(drums, H, t + beat / 2, 0.12)
        # bass: 8ths, octave bounce
        if hit:
            place(bass, bass_note(BASS[chord], beat * 1.5), t, 0.6)
        elif kind == "full":
            root = BASS[chord]
            for s in range(2):
                note = root + (12 if s else 0)
                place(bass, bass_note(note, beat / 2 * 0.95), t + s * beat / 2, 0.55)
        # pad, one chord per bar
        if pos == 0:
            cutoff = {"intro": 700, "rise": 1100}.get(kind, 2200)
            dur = 4 * beat
            for m in PADS[chord]:
                place(pad_l, pad_note(m, dur, cutoff, 0), t, 0.11)
                place(pad_r, pad_note(m, dur, cutoff, 1), t, 0.11)
        # arp, 16ths
        if kind in ("intro", "rise", "full"):
            notes = PADS[chord]
            cutoff = 3800
            if kind == "intro":
                cutoff = 1400
            elif kind == "rise":  # filter opens across the section
                ra, rb = next((x, y) for x, y, k in cue.sections if x <= b < y)
                cutoff = 1400 + 2400 * (b - ra) / max(1, rb - ra - 1)
            for s in range(4):
                step = (b * 4 + s) % len(ARP)
                m = notes[ARP[step]] + 12
                place(arp_l if s % 2 == 0 else arp_r, pluck(m, beat / 4 * 1.6, cutoff),
                      t + s * beat / 4, 0.16)
        # transitions
        if hit:
            place(fx, crash(), t, 0.32)
            place(fx, riser(beat * 2), t - beat * 2, 0.14)

    # rise sections: a riser into the next section and a snare roll on the last beat
    for a, b2, kind in cue.sections:
        if kind == "rise":
            place(fx, riser((b2 - a) * beat), a * beat, 0.12)
            for s in range(8):
                place(drums, C, (b2 - 1) * beat + s * beat / 8, 0.12 + 0.05 * s)

    # outro: the home chord rings out under a crash
    if cue.outro:
        t = cue.outro * beat
        rest = total - t + 0.5
        place(drums, K, t, 1.0)
        place(fx, crash(), t, 0.35)
        place(bass, bass_note(BASS[0], rest), t, 0.6)
        for m in PADS[0] + (PADS[0][0] + 12,):
            place(pad_l, pad_note(m, rest, 2400, 0) * decay(int(rest * SR), 0.9), t, 0.12)
            place(pad_r, pad_note(m, rest, 2400, 1) * decay(int(rest * SR), 0.9), t, 0.12)

    # sidechain: pad, bass and arp duck under each kick
    duck = np.ones(n)
    tt = np.arange(n) / SR
    for k in kicks:
        i = int(k * SR)
        seg = tt[i:i + int(0.4 * SR)] - k
        duck[i:i + len(seg)] = np.minimum(duck[i:i + len(seg)], 1 - 0.6 * np.exp(-seg * 9))
    for buf in (bass, pad_l, pad_r, arp_l, arp_r):
        buf *= duck

    # dotted-8th echo on the arp, crossing sides
    d = int(beat * 0.75 * SR)
    echo_l, echo_r = arp_l.copy(), arp_r.copy()
    for k in range(1, 4):
        g = 0.38 ** k
        src_l, src_r = (arp_r, arp_l) if k % 2 else (arp_l, arp_r)
        echo_l[d * k:] += src_l[:-d * k] * g
        echo_r[d * k:] += src_r[:-d * k] * g

    left = drums + bass + pad_l + echo_l + fx
    right = drums + bass + pad_r + echo_r + fx
    left += reverb(pad_l + echo_l + fx * 0.5, seed=1) * 0.35
    right += reverb(pad_r + echo_r + fx * 0.5, seed=2) * 0.35

    mix = np.stack([left, right], axis=1)[: int(total * SR)]
    fade = int(0.4 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    mix /= np.max(np.abs(mix)) + 1e-9
    return np.tanh(mix * 1.3) / np.tanh(1.3) * 0.89


def write(cut: str, path: str) -> float:
    """Write the cut's track as 16-bit WAV; returns its length in seconds."""
    audio = render(cut)
    wavfile.write(path, SR, (audio * 32767).astype(np.int16))
    return len(audio) / SR


if __name__ == "__main__":
    print(write(sys.argv[1], sys.argv[2]))
