from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .tab_parser import parse_source, schedule_events, schedule_events_to_beats


def parse_midi(path: Path, track_index: int) -> tuple[list[dict], list[tuple[float, float]]]:
    """Compatibility parser for future structured MIDI imports.

    Current user-facing input is pasted chord/tab text; this path remains useful
    when Guitar Pro/MusicXML/MIDI adapters are added later.
    """
    import mido

    midi = mido.MidiFile(path)
    if track_index < 0 or track_index >= len(midi.tracks):
        raise ValueError(f"Track {track_index} is unavailable; MIDI has {len(midi.tracks)} tracks")
    ticks_per_beat = midi.ticks_per_beat
    tempo = 500000
    seconds = 0.0
    active: dict[tuple[int, int], list[tuple[float, int]]] = defaultdict(list)
    notes: list[dict] = []
    numerator, denominator = 4, 4
    for message in midi.tracks[track_index]:
        seconds += mido.tick2second(message.time, ticks_per_beat, tempo)
        if message.type == "set_tempo":
            tempo = message.tempo
        elif message.type == "time_signature":
            numerator, denominator = message.numerator, message.denominator
        elif message.type == "note_on" and message.velocity > 0:
            active[(message.channel, message.note)].append((seconds, message.note))
        elif message.type in {"note_off", "note_on"} and (message.type == "note_off" or message.velocity == 0):
            key = (message.channel, message.note)
            if active[key]:
                onset, pitch = active[key].pop(0)
                notes.append({"pitch": pitch, "onset_seconds": onset, "duration_seconds": max(0, seconds - onset)})
    end_time = max([seconds, *(note["onset_seconds"] + note["duration_seconds"] for note in notes)])
    # A constant-tempo measure approximation is intentional for this initial slice.
    measure_seconds = (60_000_000 / tempo) / 1_000_000 * numerator * (4 / denominator)
    bars = [(start, min(start + measure_seconds, end_time)) for start in _frange(0.0, max(end_time, measure_seconds), measure_seconds)]
    return sorted(notes, key=lambda item: item["onset_seconds"]), bars


def transcribe(audio_path: Path) -> tuple[list[dict], str]:
    try:
        from basic_pitch.inference import predict
    except ImportError as exc:
        raise RuntimeError("Basic Pitch is not installed in the worker image") from exc
    try:
        _, _, note_events = predict(str(audio_path))
    except Exception as exc:
        raise RuntimeError(f"Basic Pitch could not transcribe this audio: {exc}") from exc
    events = [
        {
            "kind": "detected",
            "pitch": int(round(pitch)),
            "onset_seconds": round(float(start), 4),
            "duration_seconds": round(max(0.0, float(end) - float(start)), 4),
            "confidence": round(float(confidence), 3),
        }
        for start, end, pitch, confidence, *_ in note_events
    ]
    return events, "basic-pitch"


def analyze_source(
    audio_path: Path,
    source_text: str,
    source_kind: str,
    bpm: float | None = None,
    capo: int = 0,
    tuning: list[str] | None = None,
) -> dict:
    """Transcribe audio and compare it with a pasted chord sheet or tab.

    This first implementation uses the source's relative spacing scaled to the
    detected clip length. Beat tracking is deliberately isolated behind this
    function so the API contract can remain stable when it is added.
    """
    detected, engine = transcribe(audio_path)
    clip_duration = max(
        [event["onset_seconds"] + event["duration_seconds"] for event in detected] or [1.0]
    )
    raw_expected = parse_source(source_text, source_kind, capo, tuning)
    beats = detect_beats(audio_path, bpm)
    expected = schedule_events_to_beats(raw_expected, beats, clip_duration) if beats else schedule_events(raw_expected, clip_duration)
    bars = _bars_for_duration(clip_duration)
    result = score_events(expected, detected, bars, source_kind)
    result.update(
        {
            "source_kind": source_kind,
            "source_text": source_text,
            "transcription_engine": engine,
            "timing_basis": "audio beat grid + source spacing" + (f" (BPM hint: {bpm:g})" if bpm else "") if beats else "audio duration + source spacing (beat grid unavailable)",
            "suggested_text": None,
        }
    )
    return result


def detect_beats(audio_path: Path, bpm: float | None = None) -> list[float]:
    """Return beat times when librosa is available; gracefully fall back."""
    try:
        import librosa

        y, sample_rate = librosa.load(str(audio_path), sr=None, mono=True)
        _, beat_frames = librosa.beat.beat_track(y=y, sr=sample_rate, start_bpm=bpm or 120)
        return [float(value) for value in librosa.frames_to_time(beat_frames, sr=sample_rate)]
    except Exception:
        return []


def score_events(expected: list[dict], detected: list[dict], bars: list[tuple[float, float]], source_kind: str) -> dict:
    """Score normalized events after a monotonic alignment pass."""
    alignment = align_events(expected, detected, source_kind)
    measures: list[dict] = []
    findings: list[dict] = []
    used_detected: set[int] = set()
    for number, (start, end) in enumerate(bars, start=1):
        expected_indices = [index for index, event in enumerate(expected) if start <= event["onset_seconds"] < end]
        detected_indices = [index for index, event in enumerate(detected) if start <= event["onset_seconds"] < end]
        measure_findings: list[dict] = []
        for expected_index in expected_indices:
            expected_event = expected[expected_index]
            detected_index = alignment.get(expected_index)
            closest = detected[detected_index] if detected_index is not None else None
            if closest is None:
                measure_findings.append(_finding(number, "missing_note", 0.62 if expected_event.get("kind") == "chord" else 0.65, expected_event, None, f"No compatible audio event near {expected_event.get('token', 'the expected note')}.", None))
                continue
            used_detected.add(detected_index)
            if expected_event.get("kind") == "chord":
                candidates = [
                    event for event_index, event in enumerate(detected)
                    if event_index in detected_indices and abs(event["onset_seconds"] - closest["onset_seconds"]) <= max(0.35, expected_event["duration_seconds"] * 0.5)
                ]
                supported = any(event["pitch"] % 12 == expected_event["pitch"] % 12 for event in candidates)
                if not supported:
                    detected_name = _pitch_name(closest["pitch"])
                    detected_root = _pitch_class_name(closest["pitch"])
                    measure_findings.append(_finding(number, "wrong_chord", min(0.96, 0.55 + closest.get("confidence", 0.5) * 0.4), expected_event, closest, f"Expected chord {expected_event['token']}; strongest detected pitch is {detected_name}.", detected_root))
                continue
            if closest["pitch"] != expected_event["pitch"]:
                detected_name = _pitch_name(closest["pitch"])
                proposed_fret = None
                if source_kind == "tab" and expected_event.get("fret") is not None:
                    proposed_fret = max(0, expected_event["fret"] + closest["pitch"] - expected_event["pitch"])
                correction = str(proposed_fret) if proposed_fret is not None else detected_name
                measure_findings.append(_finding(number, "wrong_pitch", min(0.98, 0.55 + closest.get("confidence", 0.5) * 0.4), expected_event, closest, f"Expected pitch {_pitch_name(expected_event['pitch'])}; detected {detected_name}.", correction))
            elif abs(closest["onset_seconds"] - expected_event["onset_seconds"]) > 0.08:
                difference_ms = round((closest["onset_seconds"] - expected_event["onset_seconds"]) * 1000)
                measure_findings.append(_finding(number, "timing_deviation", 0.60, expected_event, closest, f"Detected onset differs by {difference_ms} ms.", None))
        if source_kind == "tab":
            for detected_index in detected_indices:
                note = detected[detected_index]
                if detected_index not in used_detected and note.get("confidence", 0) >= 0.5:
                    measure_findings.append(_finding(number, "extra_note", note["confidence"], None, note, "Detected note has no expected tab match.", None))
        findings.extend(measure_findings)
        measures.append({
            "number": number,
            "start_seconds": round(start, 3),
            "end_seconds": round(end, 3),
            "score": round(max(0.0, 1 - 0.15 * len(measure_findings)), 2),
            "expected_events": [expected[index] for index in expected_indices],
            "detected_events": [detected[index] for index in detected_indices],
        })
    _ensure_unique_finding_ids(findings)
    return {"measures": measures, "findings": findings}


def align_events(expected: list[dict], detected: list[dict], source_kind: str) -> dict[int, int]:
    """Return expected-index → detected-index matches using monotonic DP.

    The matcher allows insertions/deletions, so a missing or extra note does not
    shift every later event. Pitch agreement is preferred, while source/audio
    onset distance provides a gentle timing tie-breaker.
    """
    if not expected or not detected:
        return {}
    rows, columns = len(expected), len(detected)
    dp = [[float("inf")] * (columns + 1) for _ in range(rows + 1)]
    moves: list[list[str | None]] = [[None] * (columns + 1) for _ in range(rows + 1)]
    dp[0][0] = 0.0
    for row in range(rows + 1):
        for column in range(columns + 1):
            base = dp[row][column]
            if base == float("inf"):
                continue
            if row < rows and base + 1.0 < dp[row + 1][column]:
                dp[row + 1][column] = base + 1.0
                moves[row + 1][column] = "skip_expected"
            if column < columns:
                skip_cost = 0.25 if source_kind == "chords" else 0.45
                if base + skip_cost < dp[row][column + 1]:
                    dp[row][column + 1] = base + skip_cost
                    moves[row][column + 1] = "skip_detected"
            if row < rows and column < columns:
                expected_event, detected_event = expected[row], detected[column]
                pitch_match = expected_event["pitch"] % 12 == detected_event["pitch"] % 12 if expected_event.get("kind") == "chord" else expected_event["pitch"] == detected_event["pitch"]
                pitch_cost = 0.0 if pitch_match else 0.85
                timing_cost = min(0.45, abs(expected_event["onset_seconds"] - detected_event["onset_seconds"]) * 0.25)
                if base + pitch_cost + timing_cost < dp[row + 1][column + 1]:
                    dp[row + 1][column + 1] = base + pitch_cost + timing_cost
                    moves[row + 1][column + 1] = "match"
    matches: dict[int, int] = {}
    row, column = rows, columns
    while row or column:
        move = moves[row][column]
        if move == "match":
            matches[row - 1] = column - 1
            row -= 1
            column -= 1
        elif move == "skip_expected":
            row -= 1
        elif move == "skip_detected":
            column -= 1
        else:
            break
    return matches


def score(expected: list[dict], detected: list[dict], bars: list[tuple[float, float]]) -> dict:
    measures: list[dict] = []
    findings: list[dict] = []
    for number, (start, end) in enumerate(bars, start=1):
        expected_here = [event for event in expected if start <= event["onset_seconds"] < end]
        detected_here = [event for event in detected if start <= event["onset_seconds"] < end]
        used_detected: set[int] = set()
        measure_findings: list[dict] = []
        for expected_note in expected_here:
            candidates = [
                (index, note)
                for index, note in enumerate(detected_here)
                if index not in used_detected and abs(note["onset_seconds"] - expected_note["onset_seconds"]) <= 0.20
            ]
            if not candidates:
                measure_findings.append(_finding(number, "missing_note", 0.65, expected_note, None, "No compatible detected note near the expected onset."))
                continue
            index, closest = min(candidates, key=lambda item: abs(item[1]["onset_seconds"] - expected_note["onset_seconds"]))
            used_detected.add(index)
            pitch_difference = abs(closest["pitch"] - expected_note["pitch"])
            if pitch_difference > 0:
                confidence = min(0.98, 0.55 + 0.4 * closest.get("confidence", 0.5))
                measure_findings.append(_finding(number, "wrong_pitch", confidence, expected_note, closest, f"Expected MIDI pitch {expected_note['pitch']}; detected {closest['pitch']}."))
            elif abs(closest["onset_seconds"] - expected_note["onset_seconds"]) > 0.08:
                difference_ms = round((closest["onset_seconds"] - expected_note["onset_seconds"]) * 1000)
                measure_findings.append(_finding(number, "timing_deviation", 0.60, expected_note, closest, f"Detected onset differs by {difference_ms} ms."))
        for index, note in enumerate(detected_here):
            if index not in used_detected and note.get("confidence", 0) >= 0.5:
                measure_findings.append(_finding(number, "extra_note", note["confidence"], None, note, "Detected note has no expected tab match."))
        findings.extend(measure_findings)
        measures.append({
            "number": number,
            "start_seconds": round(start, 3),
            "end_seconds": round(end, 3),
            "score": round(max(0.0, 1 - 0.15 * len(measure_findings)), 2),
            "expected_notes": expected_here,
            "detected_notes": detected_here,
        })
    _ensure_unique_finding_ids(findings)
    return {"measures": measures, "findings": findings}


def _finding(number: int, kind: str, confidence: float, expected: dict | None, detected: dict | None, message: str, correction: str | int | None = None) -> dict:
    suffix = expected or detected or {}
    target_onset = float((detected or expected or {}).get("onset_seconds", 0.0))
    return {
        "id": f"m{number}-{kind}-{suffix.get('pitch', 'unknown')}-{round(suffix.get('onset_seconds', 0), 2)}",
        "measure_number": number,
        "type": kind,
        "confidence": round(confidence, 2),
        "expected": expected,
        "detected": detected,
        "message": message,
        "correction": str(correction) if correction is not None else None,
        "audio_start_seconds": round(max(0.0, target_onset - 1.5), 3),
        "audio_end_seconds": round(target_onset + 1.5, 3),
    }


def _ensure_unique_finding_ids(findings: list[dict]) -> None:
    """Disambiguate rounded IDs when several findings share a timestamp/pitch."""
    occurrences: dict[str, int] = {}
    for finding in findings:
        base_id = str(finding.get("id") or "finding")
        occurrence = occurrences.get(base_id, 0) + 1
        occurrences[base_id] = occurrence
        if occurrence > 1:
            finding["id"] = f"{base_id}-{occurrence}"


def _bars_for_duration(duration: float) -> list[tuple[float, float]]:
    measure_seconds = 4.0
    return [(start, min(start + measure_seconds, duration)) for start in _frange(0.0, max(duration, measure_seconds), measure_seconds)]


def _pitch_name(pitch: int) -> str:
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    return f"{names[pitch % 12]}{pitch // 12 - 1}"


def _pitch_class_name(pitch: int) -> str:
    return ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")[pitch % 12]


def _frange(start: float, stop: float, step: float):
    value = start
    while value < stop:
        yield value
        value += step
