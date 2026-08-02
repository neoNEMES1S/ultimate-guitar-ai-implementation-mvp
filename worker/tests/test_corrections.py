from worker.corrections import apply_approved, apply_finding


def test_apply_finding_replaces_original_token() -> None:
    source = "G       D\nlyrics\n"
    finding = {"expected": {"token": "D", "source_line": 1, "source_start": 8}, "correction": "Em"}
    assert apply_finding(source, finding) == "G       Em\nlyrics\n"


def test_apply_approved_only_applies_accepted_findings() -> None:
    source = "G       D\n"
    finding = {"id": "f1", "expected": {"token": "D", "source_line": 1, "source_start": 8}, "correction": "Em"}
    corrected, applied = apply_approved(source, [finding], {"f1": "approved"})
    assert corrected == "G       Em\n"
    assert applied == ["f1"]
