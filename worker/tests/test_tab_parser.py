from worker.tab_parser import parse_source, schedule_events, schedule_events_to_beats


def test_parse_chord_sheet_ignores_lyrics() -> None:
    events = parse_source("[Verse]\nG              D\nWhen you smile at me\nEm             C", "chords")
    assert [event["token"] for event in events] == ["G", "D", "Em", "C"]
    assert all(event["kind"] == "chord" for event in events)


def test_parse_ascii_tab_maps_string_and_fret_to_pitch() -> None:
    events = parse_source("e|--0--3--|\nB|--1--0--|\nG|--0--0--|\nD|--2--0--|\nA|--3--2--|\nE|--------|", "tab")
    assert events[0]["string"] == "e"
    assert events[0]["pitch"] == 64
    assert events[0]["fret"] == 0


def test_schedule_preserves_relative_positions() -> None:
    events = parse_source("G    D    Em", "chords")
    scheduled = schedule_events(events, 20)
    assert scheduled[0]["onset_seconds"] == 0
    assert scheduled[1]["onset_seconds"] < scheduled[2]["onset_seconds"]


def test_schedule_can_use_audio_beat_grid() -> None:
    events = parse_source("G    D    Em", "chords")
    scheduled = schedule_events_to_beats(events, [0.0, 0.5, 1.0, 1.5], 2.0)
    assert [event["onset_seconds"] for event in scheduled] == [0.0, 1.0, 1.5]
