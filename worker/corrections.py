from __future__ import annotations


def apply_finding(source_text: str, finding: dict) -> str:
    """Apply one approved, source-backed correction to the original text."""
    expected = finding.get("expected") or {}
    correction = finding.get("correction")
    line_number = expected.get("source_line")
    start = expected.get("source_start")
    token = expected.get("token")
    if correction is None or line_number is None or start is None or not token:
        return source_text
    lines = source_text.splitlines(keepends=True)
    index = int(line_number) - 1
    if index < 0 or index >= len(lines):
        return source_text
    line = lines[index]
    if line[start : start + len(token)] != token:
        return source_text
    lines[index] = f"{line[:start]}{correction}{line[start + len(token):]}"
    return "".join(lines)


def apply_approved(source_text: str, findings: list[dict], reviews: dict[str, str]) -> tuple[str, list[str]]:
    corrected = source_text
    applied: list[str] = []
    # Apply from right to left within each line so earlier offsets remain valid.
    approved = [finding for finding in findings if reviews.get(finding.get("id")) == "approved" and finding.get("correction")]
    approved.sort(key=lambda finding: (-(finding.get("expected") or {}).get("source_line", 0), -(finding.get("expected") or {}).get("source_start", 0)))
    for finding in approved:
        next_text = apply_finding(corrected, finding)
        if next_text != corrected:
            applied.append(finding["id"])
            corrected = next_text
    return corrected, applied
