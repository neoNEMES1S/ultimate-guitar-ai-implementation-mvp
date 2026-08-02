"""Generate a tiny owned WAV fixture for local smoke demos.

The generated tones are intentionally simple. They validate file plumbing and
timing alignment; they are not a proxy for a real guitar recording.
"""

from __future__ import annotations

import math
import wave
from pathlib import Path


SAMPLE_RATE = 22050
PITCHES = (60, 67, 69, 65)  # C4, G4, A4, F4


def midi_hz(pitch: int) -> float:
    return 440.0 * 2 ** ((pitch - 69) / 12)


def generate(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    seconds_per_note = 1.0
    amplitude = 0.28
    with wave.open(str(destination), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        for pitch in PITCHES:
            frequency = midi_hz(pitch)
            for index in range(int(seconds_per_note * SAMPLE_RATE)):
                time = index / SAMPLE_RATE
                envelope = min(1.0, time * 35, (seconds_per_note - time) * 35)
                sample = int(32767 * amplitude * envelope * math.sin(2 * math.pi * frequency * time))
                output.writeframesraw(sample.to_bytes(2, "little", signed=True))
    return destination


if __name__ == "__main__":
    path = generate(Path(__file__).with_name("generated") / "synthetic-chord-check.wav")
    print(path)
