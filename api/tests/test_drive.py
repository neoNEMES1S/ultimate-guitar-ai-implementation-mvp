import pytest

from api.app.drive import DriveImportError, parse_file_id


def test_parse_drive_file_id_from_view_url() -> None:
    assert parse_file_id("https://drive.google.com/file/d/1AbCdEfGhIjKlMn/view?usp=sharing") == "1AbCdEfGhIjKlMn"


def test_parse_drive_file_id_rejects_non_drive_url() -> None:
    with pytest.raises(DriveImportError):
        parse_file_id("https://example.com/audio.mp3")


def test_parse_drive_file_id_rejects_lookalike_host() -> None:
    with pytest.raises(DriveImportError):
        parse_file_id("https://notdrive.google.com/file/d/1AbCdEfGhIjKlMn/view")
