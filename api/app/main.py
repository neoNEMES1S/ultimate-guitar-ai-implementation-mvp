import json
import shutil
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import repository
from .config import settings
from .drive import DriveImportError, download_audio
from .schemas import AnalysisResult, InputKind, JobResponse, ReviewRequest

app = FastAPI(title="Ultimate Guitar AI Tab Verification API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    repository.initialise()


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/sources/image")
async def recognize_source_image(image: UploadFile = File(...)) -> dict:
    suffix = Path(image.filename or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(400, "Screenshot must be a PNG, JPG, JPEG, or WebP image")
    content = await image.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "Screenshot exceeds the 10 MB limit")
    from .image_ocr import OcrUnavailable, recognize_tab_image

    try:
        return recognize_tab_image(content)
    except OcrUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/jobs", response_model=JobResponse, status_code=202)
async def create_analysis_job(
    audio: UploadFile = File(...),
    source_text: str = Form(...),
    source_kind: InputKind = Form("chords"),
    bpm: str = Form(""),
    capo: int = Form(0),
    tuning: str = Form("E2,A2,D3,G3,B3,E4"),
    reference_url: str = Form(""),
) -> JobResponse:
    suffix = Path(audio.filename or "").suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".flac", ".mp4"}:
        raise HTTPException(400, "Audio must be a WAV, MP3, M4A, FLAC, or MP4 file")
    bpm_value, tuning_values = _validate_source(source_text, bpm, capo, tuning)
    _validate_reference_url(reference_url)

    job_id = str(uuid4())
    upload_dir = settings.data_dir / "uploads" / job_id
    upload_dir.mkdir(parents=True)
    audio_path = upload_dir / f"audio{suffix}"
    _save_upload(audio, audio_path)
    return _enqueue_job(job_id, audio_path, source_text, source_kind, bpm_value, capo, tuning_values, reference_url)


@app.post("/api/jobs/drive", response_model=JobResponse, status_code=202)
async def create_drive_analysis_job(
    drive_url: str = Form(...),
    source_text: str = Form(...),
    source_kind: InputKind = Form("chords"),
    bpm: str = Form(""),
    capo: int = Form(0),
    tuning: str = Form("E2,A2,D3,G3,B3,E4"),
    reference_url: str = Form(""),
    drive_access_token: str | None = Header(None, alias="X-Google-Drive-Access-Token"),
) -> JobResponse:
    if not drive_access_token:
        raise HTTPException(401, "Select the Drive file through Google authorization before importing it")
    bpm_value, tuning_values = _validate_source(source_text, bpm, capo, tuning)
    _validate_reference_url(reference_url)
    job_id = str(uuid4())
    upload_dir = settings.data_dir / "uploads" / job_id
    try:
        audio_path = download_audio(drive_url, drive_access_token, upload_dir)
    except DriveImportError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _enqueue_job(job_id, audio_path, source_text, source_kind, bpm_value, capo, tuning_values, reference_url or drive_url)


def _enqueue_job(job_id: str, audio_path: Path, source_text: str, source_kind: InputKind, bpm: float | None, capo: int, tuning: list[str], reference_url: str = "") -> JobResponse:
    job = repository.create_job(job_id, audio_path, source_text, source_kind, bpm, capo, tuning, reference_url)
    from worker.tasks import analyze_job

    analyze_job.delay(job_id)
    return JobResponse(id=job["id"], status=job["status"], source_kind=job["source_kind"])


def _validate_source(source_text: str, bpm: str, capo: int, tuning: str) -> tuple[float | None, list[str]]:
    if not source_text.strip():
        raise HTTPException(400, "Paste a chord sheet or tab before starting analysis")
    if len(source_text) > 100_000:
        raise HTTPException(413, "Source text is too large")
    try:
        bpm_value = float(bpm) if bpm.strip() else None
    except ValueError as exc:
        raise HTTPException(400, "BPM must be a number") from exc
    if bpm_value is not None and not 30 <= bpm_value <= 240:
        raise HTTPException(400, "BPM must be between 30 and 240")
    if not 0 <= capo <= 24:
        raise HTTPException(400, "Capo must be between 0 and 24")
    tuning_values = [item.strip() for item in tuning.split(",") if item.strip()]
    if len(tuning_values) != 6:
        raise HTTPException(400, "Tuning must contain six comma-separated notes")
    return bpm_value, tuning_values


def _validate_reference_url(reference_url: str) -> None:
    if not reference_url:
        return
    host = (urlparse(reference_url).hostname or "").lower()
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}:
        raise HTTPException(400, "Reference URL must be a YouTube URL")


def _save_upload(upload: UploadFile, destination: Path) -> None:
    total = 0
    with destination.open("wb") as output:
        while chunk := upload.file.read(1024 * 1024):
            total += len(chunk)
            if total > settings.max_audio_bytes:
                raise HTTPException(413, "Audio exceeds the 100 MB upload limit")
            output.write(chunk)


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_analysis_job(job_id: str) -> JobResponse:
    job = repository.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return JobResponse(id=job["id"], status=job["status"], source_kind=job.get("source_kind", "chords"), error=job["error"])


@app.get("/api/jobs/{job_id}/result")
def get_result(job_id: str) -> dict:
    job = repository.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "complete" or not job["result_json"]:
        raise HTTPException(409, "Analysis result is not ready")
    result = AnalysisResult.model_validate(json.loads(job["result_json"])).model_dump()
    return {**result, "reviews": repository.reviews_for_job(job_id)}


@app.get("/api/jobs/{job_id}/audio")
def get_job_audio(job_id: str) -> FileResponse:
    job = repository.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    audio_path = Path(job["audio_path"])
    if not audio_path.is_file():
        raise HTTPException(404, "Audio file is no longer available")
    media_type = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".flac": "audio/flac",
        ".mp4": "video/mp4",
    }.get(audio_path.suffix.lower(), "application/octet-stream")
    return FileResponse(audio_path, media_type=media_type, filename=audio_path.name)


@app.get("/api/jobs/{job_id}/corrected-source")
def get_corrected_source(job_id: str) -> dict:
    job = repository.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "complete" or not job["result_json"]:
        raise HTTPException(409, "Analysis result is not ready")
    from worker.corrections import apply_approved

    result = AnalysisResult.model_validate(json.loads(job["result_json"])).model_dump()
    corrected, applied = apply_approved(result["source_text"], result["findings"], repository.reviews_for_job(job_id))
    return {"source_kind": result["source_kind"], "source_text": result["source_text"], "corrected_text": corrected, "applied_finding_ids": applied}


@app.put("/api/jobs/{job_id}/findings/{finding_id}/review")
def review_finding(job_id: str, finding_id: str, body: ReviewRequest) -> dict:
    job = repository.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "complete" or not job["result_json"]:
        raise HTTPException(409, "Analysis result is not ready")
    findings = json.loads(job["result_json"]).get("findings", [])
    if not any(finding.get("id") == finding_id for finding in findings):
        raise HTTPException(404, "Finding not found for this job")
    repository.save_review(job_id, finding_id, body.decision)
    return {"finding_id": finding_id, "decision": body.decision}
