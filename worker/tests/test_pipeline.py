from worker import pipeline
from worker.pipeline import _ensure_unique_finding_ids, _finding, align_events, score, score_events


def test_score_flags_wrong_pitch_in_expected_measure() -> None:
    result = score(
        [{"pitch": 60, "onset_seconds": 0.1, "duration_seconds": 0.5}],
        [{"pitch": 62, "onset_seconds": 0.1, "duration_seconds": 0.5, "confidence": 0.9}],
        [(0, 2)],
    )
    assert result["measures"][0]["score"] < 1
    assert result["findings"][0]["type"] == "wrong_pitch"


def test_score_flags_missing_note() -> None:
    result = score([{"pitch": 60, "onset_seconds": 0.1, "duration_seconds": 0.5}], [], [(0, 2)])
    assert result["findings"][0]["type"] == "missing_note"


def test_alignment_skips_an_extra_detected_note_without_shifting_later_notes() -> None:
    expected = [
        {"kind": "tab", "pitch": 60, "onset_seconds": 0.0, "duration_seconds": 0.2},
        {"kind": "tab", "pitch": 62, "onset_seconds": 1.0, "duration_seconds": 0.2},
    ]
    detected = [
        {"kind": "detected", "pitch": 60, "onset_seconds": 0.0, "duration_seconds": 0.2, "confidence": 0.9},
        {"kind": "detected", "pitch": 65, "onset_seconds": 0.5, "duration_seconds": 0.2, "confidence": 0.9},
        {"kind": "detected", "pitch": 62, "onset_seconds": 1.0, "duration_seconds": 0.2, "confidence": 0.9},
    ]
    assert align_events(expected, detected, "tab") == {0: 0, 1: 2}


def test_source_score_exposes_audio_loop_bounds() -> None:
    result = score_events(
        [{"kind": "tab", "pitch": 60, "token": "0", "string": "e", "fret": 0, "onset_seconds": 1.0, "duration_seconds": 0.2}],
        [{"kind": "detected", "pitch": 61, "onset_seconds": 1.0, "duration_seconds": 0.2, "confidence": 0.9}],
        [(0, 4)],
        "tab",
    )
    finding = result["findings"][0]
    assert finding["type"] == "wrong_pitch"
    assert finding["audio_start_seconds"] == 0.0
    assert finding["audio_end_seconds"] == 2.5


def test_finding_ids_are_unique_when_the_base_identity_repeats() -> None:
    findings = [
        _finding(1, "timing_deviation", 0.6, {"pitch": 75, "onset_seconds": 0.06}, {"pitch": 75, "onset_seconds": 0.12}, "first"),
        _finding(1, "timing_deviation", 0.6, {"pitch": 75, "onset_seconds": 0.06}, {"pitch": 75, "onset_seconds": 0.12}, "second"),
    ]

    _ensure_unique_finding_ids(findings)

    assert len({finding["id"] for finding in findings}) == 2
    assert findings[1]["id"].endswith("-2")


def test_analyze_source_runs_source_schedule_transcription_and_scoring(monkeypatch, tmp_path) -> None:
    audio_path = tmp_path / "synthetic.wav"
    audio_path.write_bytes(b"placeholder")
    detected = [
        {"kind": "detected", "pitch": 48, "onset_seconds": 0.0, "duration_seconds": 0.5, "confidence": 0.95},
        {"kind": "detected", "pitch": 55, "onset_seconds": 1.0, "duration_seconds": 0.5, "confidence": 0.95},
        {"kind": "detected", "pitch": 57, "onset_seconds": 2.0, "duration_seconds": 0.5, "confidence": 0.95},
        {"kind": "detected", "pitch": 64, "onset_seconds": 3.0, "duration_seconds": 0.5, "confidence": 0.95},
    ]
    monkeypatch.setattr(pipeline, "transcribe", lambda path: (detected, "test-transcriber"))
    monkeypatch.setattr(pipeline, "detect_beats", lambda path, bpm: [])

    result = pipeline.analyze_source(audio_path, "C       G       Am      F", "chords")

    assert result["source_kind"] == "chords"
    assert result["transcription_engine"] == "test-transcriber"
    assert result["timing_basis"].startswith("audio duration")
    assert len(result["measures"]) == 1
    assert any(finding["type"] == "wrong_chord" for finding in result["findings"])
