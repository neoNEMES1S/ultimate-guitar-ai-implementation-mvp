from api.app.pdf_ocr import OcrToken, _ascii_systems, extract_tuning_hint


def test_extract_tuning_hint_adds_standard_string_octaves() -> None:
    assert extract_tuning_hint("Tuning: E♭ A♭ D♭ G♭ B♭ E♭") == ["Eb2", "Ab2", "Db3", "Gb3", "Bb3", "Eb4"]
    # Some exported sheets encode flats as a combining breve-like mark in the
    # PDF text layer instead of the Unicode flat glyph.
    assert extract_tuning_hint("Tuning: Ĕ Ă D̆ Ğ B̆ Ĕ") == ["Eb2", "Ab2", "Db3", "Gb3", "Bb3", "Eb4"]


def test_ascii_systems_preserve_simultaneous_fret_columns() -> None:
    lines = [float(value) for value in (10, 20, 30, 40, 50, 60)]
    tokens = [
        OcrToken("15", 100, 10, 0.95),
        OcrToken("12", 100, 20, 0.95),
        OcrToken("14", 150, 10, 0.95),
    ]

    result = _ascii_systems(lines, tokens)

    assert result[0].splitlines()[0].startswith("e|")
    assert result[0].splitlines()[1].startswith("B|")
    assert "15" in result[0].splitlines()[0]
    assert "12" in result[0].splitlines()[1]
    assert result[0].splitlines()[0].index("15") == result[0].splitlines()[1].index("12")
