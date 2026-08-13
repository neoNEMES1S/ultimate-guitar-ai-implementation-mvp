# Ultimate Guitar AI tab verification MVP

The first vertical slice accepts a short WAV/MP3 clip and a pasted chord sheet
or six-string ASCII tab, queues an analysis job, transcribes audio with Basic
Pitch, and presents measure-level findings for reviewer decisions. MIDI is an
internal analysis representation, not the user-facing tab input.

## Run locally

1. Install Docker Desktop.
2. From this directory run `docker compose -f infra/docker-compose.yml up --build`.
3. Open `http://localhost:3000`.

With the stack running, `npm run test:smoke --prefix web` checks the review
page, API health endpoint, and screenshot input guard.

The API is available at `http://localhost:8000/docs`. Uploaded files and the
SQLite job database live in the `data` Docker volume. The worker uses Basic
Pitch when it can be imported; it records a clear failed job if transcription
cannot run instead of fabricating musical evidence.

For a quick API-only development loop, install `api/requirements.txt`, set
`CELERY_TASK_ALWAYS_EAGER=true`, and run FastAPI from `api`.

The current text-first form supports chord labels above lyrics and common
six-string ASCII tab lines. It also accepts screenshot and PDF sheet imports:
PDF pages are rendered, six-line staff systems are detected, and OCR'd fret
numbers are converted into editable ASCII tab. It preserves source tokens and
character positions, uses the recording duration plus source spacing as an
initial timing basis, and marks corrections as proposals for review. Beat-grid
timing, monotonic alignment, audio evidence loops, approved text export, and
assisted OCR are included in this slice. OCR output is deliberately editable
and must be reviewed before analysis; it is not represented as ground truth.

The repository does not ship commercial recordings or scraped tabs. Add only
owned, licensed, or explicitly permissioned demo fixtures under `fixtures/` and
record their rights and seeded mismatch locations in the manifest.

Google Drive import is available through the optional Picker configuration. Set
`GOOGLE_CLIENT_ID`, `GOOGLE_API_KEY`, and optionally `GOOGLE_APP_ID` before
starting Compose. The user grants access to the selected file and the API
downloads it using a short-lived token. A YouTube URL can be supplied as a
reference for attribution; the application does not download arbitrary YouTube
audio.
