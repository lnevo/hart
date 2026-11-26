"""Shared parts of the panel evolution films (films.py ctc, cats, le).

Each film composes its frames with Pillow, writes an ffmpeg concat list that
holds every frame for its film_pace duration, and runs ffmpeg on it. This module
holds the font loader, the concat list, the ffmpeg runner and the film errors.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TypeAlias

from PIL import Image, ImageFont

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import film_pace  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
HISTORY = REPO / "docs/ctc/history"

Font: TypeAlias = ImageFont.FreeTypeFont | ImageFont.ImageFont
Box: TypeAlias = tuple[int, int, int, int]
Runner = Callable[..., "subprocess.CompletedProcess[str]"]

FONT_FILES: tuple[str, ...] = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial Bold.ttf",
)
CAPTION_INK = (220, 200, 140)


class FilmError(RuntimeError):
    """A film cannot be built; the message names the file or command."""


class FfmpegError(FilmError):
    """ffmpeg failed or is missing; carries the command and ffmpeg's stderr."""

    def __init__(self, cmd: Sequence[str], returncode: int | None, stderr: str) -> None:
        self.cmd = list(cmd)
        self.returncode = returncode
        self.stderr = stderr
        out = Path(self.cmd[-1]).name if self.cmd else "?"
        if returncode is None:
            head = f"ffmpeg not found on PATH (writing {out})"
        else:
            head = f"ffmpeg exited {returncode} writing {out}"
        tail = stderr.strip()
        super().__init__(f"{head}\n{tail}" if tail else head)


def load_font(size: int, files: Sequence[str] = FONT_FILES) -> Font:
    """The first of ``files`` that loads at ``size``, else Pillow's built-in font."""
    for name in files:
        if Path(name).exists():
            try:
                return ImageFont.truetype(name, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def open_frame(path: Path) -> Image.Image:
    """The screenshot at ``path`` as RGB; a missing file is a FilmError naming it."""
    if not path.is_file():
        raise FilmError(f"film screenshot missing: {path}")
    return Image.open(path).convert("RGB")


def write_concat_list(frame_paths: Sequence[Path], list_path: Path) -> None:
    """ffmpeg concat list: each frame for its film_pace duration, the last frame repeated to close the list."""
    if not frame_paths:
        raise FilmError(f"no frames for {list_path}")
    durations = film_pace.durations(len(frame_paths))
    lines: list[str] = []
    for p, dur in zip(frame_paths, durations):
        lines += [f"file '{p}'", f"duration {dur:.3f}"]
    lines.append(f"file '{frame_paths[-1]}'")
    list_path.write_text("\n".join(lines) + "\n")


def concat_input(list_path: Path) -> list[str]:
    """ffmpeg arguments that read ``list_path`` as a concat list (overwriting the output)."""
    return ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path)]


def mp4_command(list_path: Path, n_frames: int, codec: Sequence[str], out: Path) -> list[str]:
    """ffmpeg command for an MP4 of the concat list at 30 fps, cut to the film length."""
    return [*concat_input(list_path), "-vf", "fps=30,format=yuv420p",
            "-t", str(film_pace.film_length(n_frames)), *codec, str(out)]


def run_ffmpeg(cmd: Sequence[str], runner: Runner | None = None) -> None:
    """Run ``cmd`` through ``runner`` (subprocess.run when None).

    A missing ffmpeg or a non-zero exit raises FfmpegError with ffmpeg's stderr.
    """
    run = runner or subprocess.run
    try:
        done = run(list(cmd), check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise FfmpegError(cmd, None, str(exc)) from exc
    if done.returncode != 0:
        raise FfmpegError(cmd, done.returncode, done.stderr or "")
