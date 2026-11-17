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
import unittest
import wave
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("tiktok_promo_test", ROOT / "tools/promo/tiktok_promo.py")
TP = importlib.util.module_from_spec(spec)
sys.modules["tiktok_promo_test"] = TP  # dataclasses look the module up by name
spec.loader.exec_module(TP)


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
        with self.assertRaises(SystemExit) as e:
            line.at("helix")
        self.assertIn(line.wav.name, str(e.exception))

    def test_a_missing_line_names_the_command_to_run(self) -> None:
        next((self.vo / "owner").glob("03-*.wav")).unlink()
        with self.assertRaises(SystemExit) as e:
            TP.load_vo("owner")
        self.assertIn("voiceover.py --voice owner", str(e.exception))


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
