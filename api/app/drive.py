from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .config import settings


DRIVE_ID_RE = re.compile(r"(?:/d/|[?&]id=)([A-Za-z0-9_-]{10,})")
MIME_EXTENSIONS = {
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/flac": ".flac",
    "video/mp4": ".mp4",
}


class DriveImportError(ValueError):
    pass


def parse_file_id(url: str) -> str:
    match = DRIVE_ID_RE.search(url)
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    if not match or host not in {"drive.google.com", "www.drive.google.com"}:
        raise DriveImportError("Use a Google Drive file URL such as drive.google.com/file/d/<id>/view")
    return match.group(1)


def download_audio(url: str, access_token: str, destination_dir: Path) -> Path:
    file_id = parse_file_id(url)
    metadata = _request_json(
        f"https://www.googleapis.com/drive/v3/files/{file_id}?fields=name,mimeType,size,capabilities(canDownload,fileExtension)",
        access_token,
    )
    if not metadata.get("capabilities", {}).get("canDownload", False):
        raise DriveImportError("Google Drive does not permit downloading this file")
    mime_type = metadata.get("mimeType", "")
    extension = Path(metadata.get("name", "")).suffix.lower() or MIME_EXTENSIONS.get(mime_type, "")
    if extension not in {".wav", ".mp3", ".m4a", ".flac", ".mp4"}:
        raise DriveImportError("Drive file must be an audio file or an MP4 recording")
    declared_size = int(metadata.get("size") or 0)
    if declared_size and declared_size > settings.max_audio_bytes:
        raise DriveImportError("Drive audio exceeds the 100 MB upload limit")
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"audio{extension}"
    request = urllib.request.Request(
        f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response, destination.open("wb") as output:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_audio_bytes:
                    raise DriveImportError("Drive audio exceeds the 100 MB upload limit")
                output.write(chunk)
    except urllib.error.HTTPError as exc:
        raise DriveImportError(f"Google Drive download failed ({exc.code})") from exc
    return destination


def _request_json(url: str, access_token: str) -> dict:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise DriveImportError(f"Google Drive authorization or file lookup failed ({exc.code})") from exc
