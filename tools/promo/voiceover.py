#!/usr/bin/env python3
"""Speak the Diverging Route promo lines with F5-TTS (MLX), one WAV per line.

Runs in its own venv, not the root .venv (it pulls in mlx):

    python3 -m venv ~/.venvs/f5 && ~/.venvs/f5/bin/pip install f5-tts-mlx mlx-whisper
    ~/.venvs/f5/bin/python tools/promo/voiceover.py --voice owner \
        --ref media/promo/voice/ref.wav --ref-text "All right, TikTok, ..."
    ~/.venvs/f5/bin/python tools/promo/voiceover.py --voice generic

"owner" clones the voice in --ref (a 5 to 10 second clean clip, 24 kHz mono,
with its exact transcript). "generic" uses the model's bundled reference voice.
Lines come from diverging_vo.json; WAVs go to media/promo/vo/<voice>/NN-key.wav
(gitignored media mirror). Each line is rendered as one generation with a
character-rate length estimate, which is steadier than the model's duration
predictor. Listen to every line: rerun with --only key to redo one.

f5-tts-mlx 0.2.6 with mlx 0.32 needs int(dur) in cfm.py's random.normal call.
"""
from __future__ import annotations

import argparse
import json
import pkgutil
import tempfile
from pathlib import Path

import mlx.core as mx
import numpy as np
import soundfile as sf
from f5_tts_mlx.cfm import F5TTS
from f5_tts_mlx.utils import convert_char_to_pinyin

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SR, HOP = 24000, 256
GENERIC_TEXT = "Some call me nature, others call me mother nature."


def lines_for(voice: str) -> list[tuple[str, str]]:
    data = json.loads((HERE / "diverging_vo.json").read_text())
    out = [("intro", data["intro"][voice]["say"])]
    out += [(ln["key"], ln["say"]) for ln in data["lines"]]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--voice", choices=("owner", "generic"), required=True)
    ap.add_argument("--ref", type=Path, help="reference clip for --voice owner")
    ap.add_argument("--ref-text", help="exact words in the reference clip")
    ap.add_argument("--only", help="comma list of line keys to redo")
    ap.add_argument("--speed", type=float, default=1.0, help="above 1 speaks faster")
    ap.add_argument("--steps", type=int, default=32)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--words-only", action="store_true", help="only redo the word timings")
    ap.add_argument("--no-words", action="store_true", help="skip the Whisper word timings")
    ap.add_argument("--out", type=Path, default=ROOT / "media" / "promo" / "vo")
    args = ap.parse_args()

    only = set(args.only.split(",")) if args.only else None
    if args.words_only:
        write_words(sorted((args.out / args.voice).glob("*.wav")), only)
        return
    if args.voice == "owner":
        if not (args.ref and args.ref_text):
            ap.error("--voice owner needs --ref and --ref-text")
        ref_path, ref_text = args.ref, args.ref_text
    else:
        tmp = Path(tempfile.mkdtemp()) / "ref.wav"
        tmp.write_bytes(pkgutil.get_data("f5_tts_mlx", "tests/test_en_1_ref_short.wav"))
        ref_path, ref_text = tmp, GENERIC_TEXT
    audio, sr = sf.read(ref_path)
    if sr != SR:
        raise SystemExit("reference must be 24 kHz mono")
    audio = mx.array(audio)
    rms = mx.sqrt(mx.mean(mx.square(audio)))
    if rms < 0.1:
        audio = audio * 0.1 / rms

    model = F5TTS.from_pretrained("lucasnewman/f5-tts-mlx")
    out = args.out / args.voice
    out.mkdir(parents=True, exist_ok=True)
    ref_frames = audio.shape[0] // HOP
    for k, (key, text) in enumerate(lines_for(args.voice)):
        if only and key not in only:
            continue
        frames = ref_frames + int(ref_frames / len(ref_text) * len(text) / args.speed)
        wave, _ = model.sample(mx.expand_dims(audio, 0),
                               text=convert_char_to_pinyin([ref_text + " " + text]),
                               duration=frames, steps=args.steps, method="rk4",
                               cfg_strength=2.0, sway_sampling_coef=-1.0, seed=args.seed + k)
        wave = np.array(wave[audio.shape[0]:])
        path = out / f"{k:02d}-{key}.wav"
        sf.write(path, wave, SR)
        print(f"{path}  {len(wave) / SR:.2f}s")
    if not args.no_words:
        write_words(sorted(out.glob("*.wav")), only)


def write_words(wavs: list[Path], only: set[str] | None) -> None:
    """Word timings for each line (NN-key.json), so cuts land on the words.

    Also the check that the voice said the line: read the "text" field.
    """
    import mlx_whisper

    for wav in wavs:
        if only and wav.stem.split("-", 1)[1] not in only:
            continue
        r = mlx_whisper.transcribe(str(wav), word_timestamps=True,
                                   path_or_hf_repo="mlx-community/whisper-large-v3-turbo")
        words = [{"w": w["word"].strip(), "start": round(w["start"], 3), "end": round(w["end"], 3)}
                 for seg in r["segments"] for w in seg["words"]]
        wav.with_suffix(".json").write_text(json.dumps({"text": r["text"].strip(),
                                                        "words": words}, indent=1))
        print(f"{wav.name}: {r['text'].strip()}")


if __name__ == "__main__":
    main()
