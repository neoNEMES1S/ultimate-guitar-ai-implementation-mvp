"""Convert notation-heavy PDF sheets into editable ASCII tab text.

Most exported tab PDFs do not contain a useful text layer: the fret numbers
and staff lines are often painted into a page image. We therefore use the text
layer for metadata (especially tuning), render each page, detect six-line staff
systems, and place OCR'd fret numbers on the nearest string line. The result is
an editable suggestion, never an authoritative transcription.
"""

from __future__ import annotations

import io
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from statistics import median


class PdfOcrUnavailable(RuntimeError):
    """Raised when the API image is missing PDF/OCR runtime dependencies."""


NOTE_RE = re.compile(r"([A-Ga-g])([#b♯♭\u0306]?)")
TUNING_RE = re.compile(r"tuning\s*:\s*((?:[A-Ga-g](?:[#b♯\u266f\u266d\u0306])?\s*){4,6})", re.IGNORECASE)
FRET_TOKEN_RE = re.compile(r"^\(?([0-9]{1,2})\)?$")
STRING_LABELS = ("e", "B", "G", "D", "A", "E")
STRING_OCTAVES = (2, 2, 3, 3, 3, 4)


@dataclass(frozen=True)
class OcrToken:
    text: str
    x_center: float
    y_center: float
    confidence: float


def recognize_tab_pdf(content: bytes, max_pages: int = 20) -> dict:
    """Return editable tab text and OCR metadata for a PDF upload."""
    try:
        from pypdf import PdfReader
        from PIL import Image, ImageOps
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise PdfOcrUnavailable("PDF OCR requires pypdf, Pillow, and Tesseract") from exc
    if not content.startswith(b"%PDF"):
        raise ValueError("The uploaded file is not a readable PDF")

    try:
        reader = PdfReader(io.BytesIO(content))
        page_count = len(reader.pages)
        if page_count < 1:
            raise ValueError("The PDF does not contain any pages")
        if page_count > max_pages:
            raise ValueError(f"PDF contains {page_count} pages; the limit is {max_pages}")
        native_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The uploaded file is not a readable PDF") from exc

    tuning_hint = extract_tuning_hint(native_text)
    systems: list[str] = []
    confidences: list[float] = []
    numeric_tokens = 0
    with tempfile.TemporaryDirectory(prefix="tab-pdf-") as temp_dir:
        pdf_path = Path(temp_dir) / "source.pdf"
        pdf_path.write_bytes(content)
        image_paths = _render_pages(pdf_path, Path(temp_dir), page_count)
        for image_path in image_paths:
            image = Image.open(image_path).convert("L")
            image = ImageOps.autocontrast(image)
            data = pytesseract.image_to_data(image, config="--psm 6", output_type=Output.DICT)
            tokens = _numeric_tokens(data)
            confidences.extend(token.confidence for token in tokens)
            numeric_tokens += len(tokens)
            lines = _staff_line_centers(image)
            page_systems = _ascii_systems(lines, tokens)
            systems.extend(page_systems)

    text = "\n\n".join(systems).strip()
    if not text:
        # Preserve useful metadata when a page is too sparse for staff OCR. The
        # UI will still let the reviewer replace this text before analysis.
        text = _clean_native_text(native_text)
    confidence = round(sum(confidences) / max(len(confidences), 1), 2)
    warnings: list[str] = []
    if not systems:
        warnings.append("No six-line tab systems were detected; review or paste the tab manually.")
    if numeric_tokens < 4:
        warnings.append("Few fret numbers were recognized; inspect the extracted text carefully.")
    if confidence < 0.70:
        warnings.append("OCR confidence is low; review every fret, rhythm mark, and technique before analysis.")
    warnings.append("PDF OCR preserves fret numbers and relative spacing; bends, slides, rests, and tuplets need manual review.")
    return {
        "text": text,
        "confidence": confidence,
        "suggested_kind": "tab" if systems else "chords",
        "warnings": warnings,
        "page_count": page_count,
        "systems_detected": len(systems),
        "tuning_hint": tuning_hint,
    }


def extract_tuning_hint(text: str) -> list[str] | None:
    match = TUNING_RE.search(text.replace("\u00a0", " "))
    if not match:
        return None
    notes = []
    for note_match in NOTE_RE.finditer(match.group(1)):
        accidental = note_match.group(2).replace("♭", "b").replace("♯", "#").replace("\u0306", "b")
        note = note_match.group(1).upper() + accidental
        notes.append(note)
    if len(notes) != 6:
        return None
    return [f"{note}{octave}" for note, octave in zip(notes, STRING_OCTAVES)]


def _render_pages(pdf_path: Path, temp_dir: Path, page_count: int) -> list[Path]:
    output_prefix = temp_dir / "page"
    try:
        subprocess.run(
            ["pdftoppm", "-f", "1", "-l", str(page_count), "-png", "-r", "180", str(pdf_path), str(output_prefix)],
            check=True,
            capture_output=True,
            timeout=90,
        )
    except FileNotFoundError as exc:
        raise PdfOcrUnavailable("PDF rendering is not installed in this API image") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("PDF rendering timed out; try a shorter sheet") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError("The PDF pages could not be rendered for OCR") from exc
    paths = sorted(temp_dir.glob("page-*.png"), key=_page_number)
    if len(paths) != page_count:
        raise ValueError("The PDF renderer did not produce every page")
    return paths


def _page_number(path: Path) -> int:
    match = re.search(r"-(\d+)\.png$", path.name)
    return int(match.group(1)) if match else 0


def _numeric_tokens(data: dict) -> list[OcrToken]:
    tokens: list[OcrToken] = []
    for index, raw_text in enumerate(data.get("text", [])):
        value = str(raw_text).strip().replace("O", "0")
        match = FRET_TOKEN_RE.fullmatch(value)
        if not match:
            continue
        fret = int(match.group(1))
        if fret > 30:
            continue
        try:
            confidence = float(data.get("conf", ["0"])[index]) / 100
        except (ValueError, TypeError, IndexError):
            confidence = 0.0
        if confidence < 0.20:
            continue
        left = float(data.get("left", [0])[index])
        top = float(data.get("top", [0])[index])
        width = float(data.get("width", [0])[index])
        height = float(data.get("height", [0])[index])
        tokens.append(OcrToken(str(fret), left + width / 2, top + height / 2, confidence))
    return tokens


def _staff_line_centers(image) -> list[float]:
    width, height = image.size
    pixels = image.load()
    left, right = int(width * 0.03), int(width * 0.97)
    minimum_dark = max(40, int((right - left) * 0.30))
    centers: list[float] = []
    run: list[int] = []
    for y in range(height):
        dark = sum(1 for x in range(left, right) if pixels[x, y] < 180)
        if dark >= minimum_dark:
            run.append(y)
        elif run:
            centers.append(sum(run) / len(run))
            run = []
    if run:
        centers.append(sum(run) / len(run))
    return centers


def _ascii_systems(line_centers: list[float], tokens: list[OcrToken]) -> list[str]:
    groups: list[tuple[float, ...]] = []
    index = 0
    while index <= len(line_centers) - 6:
        candidate = tuple(line_centers[index : index + 6])
        gaps = [candidate[offset + 1] - candidate[offset] for offset in range(5)]
        typical_gap = median(gaps)
        if 3 <= typical_gap <= 90 and max(gaps) <= typical_gap * 1.8 and min(gaps) >= typical_gap * 0.45:
            groups.append(candidate)
            index += 6
        else:
            index += 1
    systems: list[str] = []
    for group in groups:
        gap = median([group[offset + 1] - group[offset] for offset in range(5)])
        top, bottom = group[0] - gap * 0.35, group[-1] + gap * 0.35
        group_tokens = [token for token in tokens if top <= token.y_center <= bottom]
        if not group_tokens:
            continue
        left = min(token.x_center for token in group_tokens)
        scale = max(6.0, gap * 1.5)
        positions = [max(0, round((token.x_center - left) / scale)) for token in group_tokens]
        body_length = max(position + len(token.text) for position, token in zip(positions, group_tokens)) + 2
        rows = [["-"] * body_length for _ in range(6)]
        for token, position in zip(group_tokens, positions):
            nearest = min(range(6), key=lambda row: abs(token.y_center - group[row]))
            start = min(max(0, position), body_length - len(token.text))
            for offset, character in enumerate(token.text):
                rows[nearest][start + offset] = character
        systems.append("\n".join(f"{label}|{''.join(row)}" for label, row in zip(STRING_LABELS, rows)))
    return systems


def _clean_native_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(line for line in lines if not line.lower().startswith("http"))
