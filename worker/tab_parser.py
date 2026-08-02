"""Parsers for the text formats people commonly paste from chord/tab sites.

The parser intentionally keeps source tokens and positions alongside pitches.
That lets the review UI explain a finding and lets the correction layer make a
small patch to the original text instead of rewriting the whole document.
"""

from __future__ import annotations

import re
from typing import Iterable


CHORD_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-G](?:#|b)?(?:maj7|maj|min7|min|m7|m|dim7|dim|aug|sus2|sus4|add9|7|9|6|5)?(?:/[A-G](?:#|b)?)?)(?![A-Za-z0-9])"
)
TAB_LINE_RE = re.compile(r"^\s*([eEbBgGdDaA])\s*\|([^\n]*)$")
FRET_RE = re.compile(r"(?<!\d)(x|\d{1,2})(?!\d)", re.IGNORECASE)

PITCH_CLASSES = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
DEFAULT_TUNING = ["E2", "A2", "D3", "G3", "B3", "E4"]
STRING_ORDER = ["e", "B", "G", "D", "A", "E"]


def parse_source(text: str, kind: str, capo: int = 0, tuning: list[str] | None = None) -> list[dict]:
    if not text.strip():
        raise ValueError("Tab or chord text is empty")
    if kind == "chords":
        events = _parse_chords(text, capo)
    elif kind == "tab":
        events = _parse_tab(text, capo, tuning or DEFAULT_TUNING)
    else:
        raise ValueError(f"Unsupported source kind: {kind}")
    if not events:
        raise ValueError("No chord or tab events could be recognised")
    return events


def schedule_events(events: list[dict], total_seconds: float) -> list[dict]:
    """Map source positions onto the recording duration.

    ASCII spacing is a useful relative timing hint, but not a clock. We preserve
    the hint and scale it to the detected clip duration until beat tracking is
    added to the worker.
    """
    positions = [float(event["position"]) for event in events]
    first, last = min(positions), max(positions)
    span = max(last - first, 1.0)
    usable_duration = max(total_seconds, 1.0)
    scheduled: list[dict] = []
    for event in events:
        onset = ((float(event["position"]) - first) / span) * max(usable_duration * 0.95, 0.1)
        scheduled.append({**event, "onset_seconds": round(onset, 4), "duration_seconds": 0.25})
    for index, event in enumerate(scheduled):
        next_onset = scheduled[index + 1]["onset_seconds"] if index + 1 < len(scheduled) else usable_duration
        event["duration_seconds"] = round(max(0.08, min(next_onset - event["onset_seconds"], 1.5)), 4)
    return scheduled


def schedule_events_to_beats(events: list[dict], beats: list[float], total_seconds: float) -> list[dict]:
    """Place source events on the nearest positions of an audio beat grid."""
    if len(beats) < 2:
        return schedule_events(events, total_seconds)
    positions = [float(event["position"]) for event in events]
    first, last = min(positions), max(positions)
    span = max(last - first, 1.0)
    scheduled: list[dict] = []
    for event in events:
        ratio = (float(event["position"]) - first) / span
        beat_index = min(len(beats) - 1, max(0, round(ratio * (len(beats) - 1))))
        scheduled.append({**event, "onset_seconds": round(beats[beat_index], 4), "duration_seconds": 0.25})
    for index, event in enumerate(scheduled):
        next_onset = scheduled[index + 1]["onset_seconds"] if index + 1 < len(scheduled) else total_seconds
        event["duration_seconds"] = round(max(0.08, min(next_onset - event["onset_seconds"], 1.5)), 4)
    return scheduled


def _parse_chords(text: str, capo: int) -> list[dict]:
    events: list[dict] = []
    sequence = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith(("[", "(", "#")):
            continue
        matches = list(CHORD_RE.finditer(line))
        if not matches or not _looks_like_chord_line(line, matches):
            continue
        for match in matches:
            token = match.group(1)
            root = re.match(r"[A-G](?:#|b)?", token).group(0)
            pitch = 48 + PITCH_CLASSES[root] + capo
            events.append(
                {
                    "kind": "chord",
                    "pitch": pitch,
                    "token": token,
                    "position": sequence,
                    "source_line": line_number,
                    "source_start": match.start(1),
                }
            )
            sequence += 1
    return events


def _looks_like_chord_line(line: str, matches: list[re.Match[str]]) -> bool:
    compact = re.sub(r"\s+", "", line)
    coverage = sum(len(match.group(1)) for match in matches) / max(len(compact), 1)
    has_modifier = any(re.search(r"(?:[#b]|m|maj|min|dim|aug|sus|add|/|\d)", match.group(1)) for match in matches)
    return coverage >= 0.35 or has_modifier and coverage >= 0.12


def _parse_tab(text: str, capo: int, tuning: list[str]) -> list[dict]:
    lines = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        match = TAB_LINE_RE.match(raw_line)
        if match:
            lines.append((match.group(1), match.group(2), line_number))
    if len(lines) < 2:
        return []
    events: list[dict] = []
    for label, content, line_number in lines:
        try:
            string_index = STRING_ORDER.index(label)
        except ValueError:
            continue
        tuning_index = len(tuning) - 1 - string_index
        if tuning_index < 0 or tuning_index >= len(tuning):
            continue
        open_pitch = _note_name_to_midi(tuning[tuning_index]) + capo
        for match in FRET_RE.finditer(content):
            if match.group(1).lower() == "x":
                continue
            fret = int(match.group(1))
            events.append(
                {
                    "kind": "tab",
                    "pitch": open_pitch + fret,
                    "token": match.group(1),
                    "string": label,
                    "fret": fret,
                    "position": match.start(1),
                    "source_line": line_number,
                    "source_start": raw_offset(content, match.start(1), label),
                }
            )
    return sorted(events, key=lambda event: (event["position"], STRING_ORDER.index(event["string"])))


def raw_offset(content: str, index: int, label: str) -> int:
    # The tab line prefix is not needed for scoring; preserving the content
    # offset is enough for a future correction patcher.
    # Include the label and separator so the offset addresses the original
    # source line, not only the portion after the pipe.
    return len(label) + 1 + index


def _note_name_to_midi(name: str) -> int:
    match = re.fullmatch(r"([A-G](?:#|b)?)(-?\d+)", name.strip())
    if not match or match.group(1) not in PITCH_CLASSES:
        raise ValueError(f"Unsupported tuning note: {name}")
    return (int(match.group(2)) + 1) * 12 + PITCH_CLASSES[match.group(1)]
