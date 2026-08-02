from __future__ import annotations

import io
import re


class OcrUnavailable(RuntimeError):
    pass


def recognize_tab_image(content: bytes) -> dict:
    try:
        from PIL import Image, ImageOps
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise OcrUnavailable("Screenshot OCR is not installed in this API image") from exc
    try:
        image = Image.open(io.BytesIO(content)).convert("L")
    except Exception as exc:
        raise ValueError("The uploaded file is not a readable image") from exc
    if image.width < 200 or image.height < 50:
        raise ValueError("Use a larger, high-resolution tab screenshot")
    scale = 2 if image.width < 1800 else 1
    image = image.resize((image.width * scale, image.height * scale))
    image = ImageOps.autocontrast(image)
    config = "--psm 6"
    text = pytesseract.image_to_string(image, config=config)
    data = pytesseract.image_to_data(image, config=config, output_type=Output.DICT)
    confidences = [float(value) for value in data["conf"] if str(value).strip() not in {"", "-1"}]
    confidence = round(max(0.0, min(1.0, (sum(confidences) / max(len(confidences), 1)) / 100)), 2)
    tab_lines = sum(1 for line in text.splitlines() if re.match(r"^\s*[eEbBgGdDaA]\s*\|", line))
    kind = "tab" if tab_lines >= 2 else "chords"
    warnings: list[str] = []
    if confidence < 0.70:
        warnings.append("OCR confidence is low; review every fret and chord before analysis.")
    if kind == "chords":
        warnings.append("Fewer than two six-string tab lines were detected; review the text format or choose Chords + lyrics.")
    return {"text": text.strip(), "confidence": confidence, "suggested_kind": kind, "warnings": warnings}
