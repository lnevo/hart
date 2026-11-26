"""The Diverging Route promo cut (tools/promo/tiktok_promo.py): voiceover timing and argument checks.

No rendering, no ffmpeg and no model: the voice lines are short silent WAVs with hand-written word timings.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, rel: str) -> types.ModuleType:
    """The script at ROOT/rel as module `name`, registered in sys.modules (dataclasses look the module up by name)."""
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


TP = _load("tiktok_promo_test", "tools/promo/tiktok_promo.py")
VO = _load("voiceover_test", "tools/promo/voiceover.py")    # imports without mlx: the model loads in main


def silent_wav(path: Path, seconds: float, rate: int = 24000) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(seconds * rate))


class VoiceLines(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.vo = Path(tmp.name)
        data = json.loads(TP.VO_LINES.read_text())
        keys = ["intro"] + [ln["key"] for ln in data["lines"]]
        (self.vo / "owner").mkdir()
        for k, key in enumerate(keys):
            wav = self.vo / "owner" / f"{k:02d}-{key}.wav"
            silent_wav(wav, 1.0 + k * 0.5)
            words = [{"w": "Alright,", "start": 0.10, "end": 0.40}, {"w": "switch.", "start": 0.50, "end": 0.90}]
            wav.with_suffix(".json").write_text(json.dumps({"text": "", "words": words}))
        self.keys = keys
        patch = mock.patch.object(TP, "VO_DIR", self.vo)
        patch.start()
        self.addCleanup(patch.stop)

    def test_lines_follow_each_other_on_the_timeline(self) -> None:
        lines = TP.load_vo("owner")
        self.assertEqual([ln.key for ln in lines], self.keys)
        self.assertAlmostEqual(lines[0].start, TP.VO_LEAD)
        for a, b in zip(lines, lines[1:]):
            self.assertAlmostEqual(b.start, a.start + a.seconds + TP.VO_GAP)

    def test_a_word_is_found_ignoring_case_and_punctuation(self) -> None:
        line = TP.load_vo("owner")[1]
        self.assertAlmostEqual(line.at("SWITCH"), line.start + 0.50 - 0.08)
        self.assertAlmostEqual(line.at("alright"), line.start + 0.10 - 0.08)

    def test_a_word_not_heard_stops_with_the_line_to_redo(self) -> None:
        line = TP.load_vo("owner")[0]
        with self.assertRaises(TP.PromoError) as e:
            line.at("helix")
        self.assertIn(line.wav.name, str(e.exception))

    def test_a_missing_line_names_the_command_to_run(self) -> None:
        next((self.vo / "owner").glob("03-*.wav")).unlink()
        with self.assertRaises(TP.PromoError) as e:
            TP.load_vo("owner")
        self.assertIn("voiceover.py --voice owner", str(e.exception))


class Render(unittest.TestCase):
    """render() pipes frames to the encoder; a failed encoder is a PromoError carrying what it wrote on stderr."""

    FMT = TP.Format("tiny", 4, 2, (0, 0, 4, 2))

    def segs(self, seconds: float = 1.0) -> list:
        def frames(n: int):
            for _ in range(n):
                yield TP.Image.new("RGB", (4, 2), (1, 2, 3))
        return [TP.Segment(frames, seconds)]

    def encoder(self, body: str) -> list[str]:
        return [sys.executable, "-c", body]

    def test_the_frames_reach_the_encoder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "got.raw"
            cmd = self.encoder(f"import sys; open({str(out)!r}, 'wb').write(sys.stdin.buffer.read())")
            TP.render(self.segs(), None, out, self.FMT, cmd)
            self.assertEqual(out.read_bytes(), bytes((1, 2, 3)) * 8 * TP.FPS)

    def test_a_failed_encoder_names_its_exit_code_and_stderr(self) -> None:
        cmd = self.encoder("import sys; sys.stdin.buffer.read(); sys.stderr.write('Unknown encoder libx264'); sys.exit(3)")
        with self.assertRaises(TP.PromoError) as e:
            TP.render(self.segs(), None, Path("x.mp4"), self.FMT, cmd)
        self.assertIn("exit 3", str(e.exception))
        self.assertIn("Unknown encoder libx264", str(e.exception))

    def test_an_encoder_that_stops_early_is_reported_not_a_broken_pipe(self) -> None:
        cmd = self.encoder("import sys; sys.stderr.write('Invalid argument'); sys.exit(1)")
        with self.assertRaises(TP.PromoError) as e:
            TP.render(self.segs(400.0), None, Path("x.mp4"), self.FMT, cmd)
        self.assertIn("Invalid argument", str(e.exception))

    def test_main_exits_with_the_message(self) -> None:
        with mock.patch.object(TP, "_main", side_effect=TP.PromoError("ffmpeg not found")), \
                self.assertRaises(SystemExit) as e:
            TP.main()
        self.assertEqual(str(e.exception.code), "tiktok_promo.py: ffmpeg not found")


class VoiceoverReference(unittest.TestCase):
    """voiceover.py takes a 24 kHz mono reference clip; anything else is a VoiceoverError, which main() exits with."""

    def test_mono_24_khz_passes(self) -> None:
        VO.check_reference(24000, (48000,))

    def test_stereo_or_another_rate_names_what_it_got(self) -> None:
        with self.assertRaisesRegex(VO.VoiceoverError, r"got 24000 Hz, 2 channels"):
            VO.check_reference(24000, (48000, 2))
        with self.assertRaisesRegex(VO.VoiceoverError, r"got 44100 Hz, 1 channels"):
            VO.check_reference(44100, (48000,))

    def test_main_exits_with_the_message(self) -> None:
        with mock.patch.object(VO, "_main", side_effect=VO.VoiceoverError("reference must be 24 kHz mono")), \
                self.assertRaises(SystemExit) as e:
            VO.main()
        self.assertEqual(str(e.exception.code), "reference must be 24 kHz mono")


class Timing(unittest.TestCase):
    def test_shots_add_up_to_the_frames_of_the_whole_cut(self) -> None:
        starts = [0.0, 1.013, 2.517, 4.0, 6.666]
        end = 9.031
        segs = TP.timed([(t, None, "", "") for t in starts], end)
        self.assertEqual(sum(round(s.seconds * TP.FPS) for s in segs), round(end * TP.FPS))


class Arguments(unittest.TestCase):
    def run_main(self, *argv: str) -> str:
        err = io.StringIO()
        with mock.patch.object(sys, "argv", ["tiktok_promo.py", *argv]), contextlib.redirect_stderr(err), \
                self.assertRaises(SystemExit) as e:
            TP.main()
        self.assertEqual(e.exception.code, 2)
        return err.getvalue()

    def test_voices_come_from_the_script(self) -> None:
        self.assertEqual(TP.vo_voices(), ["owner", "generic"])

    def test_unknown_voice_is_refused_before_any_capture(self) -> None:
        self.assertIn("unknown voice(s): Owner", self.run_main("--cuts", "diverging", "--voice", "Owner"))

    def test_landscape_diverging_is_refused(self) -> None:
        self.assertIn("vertical format only", self.run_main("--cuts", "diverging", "--format", "landscape"))


if __name__ == "__main__":
    unittest.main()
