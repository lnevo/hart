"""tools/ctc_history/film_common.py: the concat list, the ffmpeg commands and errors, and the frame loop (build_film),
with a fake subprocess."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/ctc_history"))
import film_common  # noqa: E402
from hartlib import film_pace  # noqa: E402


class FakeRun:
    """Stands in for subprocess.run: records each call and answers with one result or exception."""

    def __init__(self, returncode: int = 0, stderr: str = "", raises: Exception | None = None) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.returncode, self.stderr, self.raises = returncode, stderr, raises

    def __call__(self, cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((cmd, kw))
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(cmd, self.returncode, "", self.stderr)


class RunFfmpeg(unittest.TestCase):
    CMD = ["ffmpeg", "-y", "-i", "concat.txt", "/tmp/out/LE_Panel_Evolution.mp4"]

    def test_success_runs_once_capturing_text(self) -> None:
        fake = FakeRun()
        film_common.run_ffmpeg(self.CMD, runner=fake)
        self.assertEqual(fake.calls, [(self.CMD, {"check": False, "capture_output": True, "text": True})])

    def test_failure_carries_stderr_command_and_code(self) -> None:
        fake = FakeRun(returncode=1, stderr="concat.txt: Invalid data found when processing input\n")
        with self.assertRaises(film_common.FfmpegError) as e:
            film_common.run_ffmpeg(self.CMD, runner=fake)
        self.assertEqual(e.exception.returncode, 1)
        self.assertEqual(e.exception.cmd, self.CMD)
        self.assertIn("Invalid data found", e.exception.stderr)
        self.assertEqual(str(e.exception), "ffmpeg exited 1 writing LE_Panel_Evolution.mp4\n"
                                           "concat.txt: Invalid data found when processing input")
        self.assertIsInstance(e.exception, film_common.FilmError)

    def test_failure_with_empty_stderr_keeps_the_head(self) -> None:
        with self.assertRaises(film_common.FfmpegError) as e:
            film_common.run_ffmpeg(self.CMD, runner=FakeRun(returncode=8))
        self.assertEqual(str(e.exception), "ffmpeg exited 8 writing LE_Panel_Evolution.mp4")

    def test_missing_ffmpeg_is_a_film_error_with_its_cause(self) -> None:
        missing = FileNotFoundError(2, "No such file or directory", "ffmpeg")
        with self.assertRaises(film_common.FfmpegError) as e:
            film_common.run_ffmpeg(self.CMD, runner=FakeRun(raises=missing))
        self.assertIsNone(e.exception.returncode)
        self.assertIs(e.exception.__cause__, missing)
        self.assertTrue(str(e.exception).startswith("ffmpeg not found on PATH (writing LE_Panel_Evolution.mp4)"))


class Commands(unittest.TestCase):
    def test_mp4_command_reads_the_list_and_cuts_to_the_film_length(self) -> None:
        cmd = film_common.mp4_command(Path("/w/concat.txt"), 6, ["-c:v", "libx264", "-crf", "26"], Path("/o/f.mp4"))
        self.assertEqual(cmd, ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "/w/concat.txt",
                               "-vf", "fps=30,format=yuv420p", "-t", str(film_pace.film_length(6)),
                               "-c:v", "libx264", "-crf", "26", "/o/f.mp4"])


class ConcatList(unittest.TestCase):
    def test_each_frame_has_its_duration_and_the_last_repeats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            frames = [Path(tmp) / f"f{i:02d}.png" for i in range(3)]
            lst = Path(tmp) / "concat.txt"
            film_common.write_concat_list(frames, lst)
            lines = lst.read_text().splitlines()
        durs = film_pace.durations(3)
        self.assertEqual(lines, [f"file '{frames[0]}'", f"duration {durs[0]:.3f}",
                                 f"file '{frames[1]}'", f"duration {durs[1]:.3f}",
                                 f"file '{frames[2]}'", f"duration {durs[2]:.3f}",
                                 f"file '{frames[2]}'"])

    def test_no_frames_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(film_common.FilmError):
            film_common.write_concat_list([], Path(tmp) / "concat.txt")


class Inputs(unittest.TestCase):
    def test_a_missing_screenshot_names_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gone = Path(tmp) / "le_panel_gone.png"
            with self.assertRaisesRegex(film_common.FilmError, "le_panel_gone.png"):
                film_common.open_frame(gone)

    def test_a_screenshot_opens_as_rgb(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.png"
            Image.new("RGBA", (4, 3), (1, 2, 3, 4)).save(p)
            img = film_common.open_frame(p)
        self.assertEqual((img.mode, img.size), ("RGB", (4, 3)))

    def test_load_font_falls_back_to_the_built_in_font(self) -> None:
        font = film_common.load_font(22, files=("/nonexistent/font.ttf",))
        self.assertIsNotNone(font.getbbox("A"))


class BuildFilm(unittest.TestCase):
    """The frame loop of the poster films, with small frames and a fake ffmpeg."""

    def test_frames_are_saved_in_order_the_last_is_the_poster_and_ffmpeg_reads_the_list(self) -> None:
        from PIL import Image

        colours = [(10, 0, 0), (0, 20, 0), (0, 0, 30)]
        fake = FakeRun()
        with tempfile.TemporaryDirectory() as tmp:
            out, poster = Path(tmp) / "film.mp4", Path(tmp) / "poster.jpg"
            seen: list[list[str]] = []

            def keep_list(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
                lst = Path(cmd[cmd.index("-i") + 1])
                frames = [Path(line[6:-1]) for line in lst.read_text().splitlines() if line.startswith("file ")]
                seen.append([str(Image.open(f).getpixel((0, 0))) for f in frames])
                self.assertTrue(lst.parent.name.startswith("t_evo_"))
                return fake(cmd, **kw)

            film_common.build_film([lambda c=c: Image.new("RGB", (4, 4), c) for c in colours], out, poster, "t_evo_",
                                   runner=keep_list)
            self.assertEqual(Image.open(poster).format, "JPEG")
            self.assertEqual(Image.open(poster).size, (4, 4))
        self.assertEqual(seen, [[str(c) for c in [*colours, colours[-1]]]])
        cmd = fake.calls[0][0]
        self.assertEqual(cmd[-7:], [*film_common.POSTER_FILM_CODEC, str(out)])
        self.assertEqual(cmd[cmd.index("-t") + 1], str(film_pace.film_length(3)))

    def test_fewer_than_two_frames_is_refused_before_any_is_composed(self) -> None:
        from PIL import Image

        made: list[int] = []

        def frame() -> Image.Image:
            made.append(1)
            return Image.new("RGB", (2, 2))

        one = [frame]
        for frames in ([], one):
            refused = rf"{len(frames)} frame\(s\) for .*film\.mp4: a film needs two"
            with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(film_common.FilmError, refused):
                film_common.build_film(frames, Path(tmp) / "film.mp4", Path(tmp) / "p.jpg", "t_", runner=FakeRun())
        self.assertEqual(made, [])

    def test_an_ffmpeg_failure_is_a_film_error(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(film_common.FfmpegError):
            film_common.build_film([lambda: Image.new("RGB", (2, 2))] * 2, Path(tmp) / "f.mp4", Path(tmp) / "p.jpg",
                                   "t_", runner=FakeRun(returncode=1))


if __name__ == "__main__":
    unittest.main()
