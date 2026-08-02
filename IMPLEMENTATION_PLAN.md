# Ultimate Guitar AI Tab Verification MVP

## Objective

Deliver a working, real-life demonstration of an AI-assisted Tab Verification and Repair workflow. A user submits a short mixed-song audio clip and its tab; the system aligns the two, scores each measure, highlights likely mismatches, and gives a reviewer the evidence needed to approve or dismiss the finding.

The product claim for this MVP is **AI-assisted tab verification**, not fully automatic tab correction.

## MVP user journey

1. Choose a demo song or upload a 30-90 second MP3/WAV clip and a corresponding tab.
2. Select the guitar track to review.
3. Start analysis and view live job progress.
4. Open a tab view coloured by measure confidence.
5. Select a flagged measure to:
   - hear a short audio loop;
   - compare expected tab notes with detected notes;
   - see the mismatch type and confidence;
   - approve, dismiss, or ignore the AI finding.

## Technical architecture

```text
Next.js review UI
      |
      | upload audio + tab, poll job status
      v
FastAPI API ---- PostgreSQL (jobs, measures, findings, reviews)
      |                 |
      |                 +---- Object storage (audio, stems, results)
      v
Redis + Celery job queue
      |
      v
GPU analysis worker
  FFmpeg -> Demucs -> Basic Pitch -> alignment -> scoring
      |
      v
Structured measure and mismatch results returned to the UI
```

## Proposed stack

| Area | Technology | Responsibility |
|---|---|---|
| Frontend | Next.js, TypeScript, Tailwind CSS | Upload flow, job progress, review experience |
| Tab rendering | alphaTab | Render, play, and visually annotate Guitar Pro/MIDI tabs |
| API | FastAPI, Pydantic | Validation, presigned uploads, job and result APIs |
| Job processing | Celery, Redis | Durable asynchronous analysis jobs |
| Database | PostgreSQL | Jobs, tab structures, measures, findings, reviewer feedback |
| Object storage | S3-compatible storage | Original audio, normalized WAV, stems, generated artifacts |
| Audio processing | FFmpeg, librosa, numpy/scipy | Normalization, feature extraction, clips, alignment helpers |
| Source separation | Demucs | Extract a guitar-containing accompaniment stem from mixed audio |
| Note transcription | Spotify Basic Pitch | Produce timestamped pitch/note events |
| Alignment and scoring | Custom Python module | Align expected tab events to detected events and score differences |
| Development/runtime | Docker Compose | Reproducible local application and worker stack |

## Repository layout

```text
web/                 Next.js application
api/                 FastAPI application and database migrations
worker/              Celery tasks and ML/audio pipeline
packages/contracts/  Shared API schemas and generated types
infra/               Docker Compose, local development configuration
fixtures/            Licensed demo audio, tabs, and expected findings
docs/                Architecture and demo notes
```

## Delivery milestones

### Milestone 1: foundation and uploads

**Deliverables**

- Docker Compose environment with web, API, worker, Postgres, Redis, and object storage.
- Audio upload and validation for WAV/MP3 files up to 90 seconds.
- MIDI upload and normalized tab-event representation.
- Persistent analysis-job state machine: `queued`, `processing`, `complete`, `failed`.

**Acceptance criteria**

- A user can upload valid audio and MIDI files.
- The API creates a job and the UI renders its status.
- Files and job metadata survive an API restart.

### Milestone 2: initial analysis vertical slice

**Deliverables**

- Worker normalizes uploaded audio to a stable WAV format.
- Basic Pitch creates timestamped detected note events.
- Baseline MIDI-to-audio timing alignment.
- Results API returns expected and detected notes per measure.

**Acceptance criteria**

- A known audio/MIDI pair completes end-to-end without manual worker intervention.
- Every tab measure has analysis timestamps and a preliminary score.
- The results page lists detected differences, even if alignment is still basic.

### Milestone 3: mixed-song verification

**Deliverables**

- Demucs stage before transcription for mixed audio.
- Guitar-track selection and standard-tuning configuration.
- Dynamic-time-warping alignment resilient to small tempo drift.
- Mismatch classifier: wrong pitch, missing note, extra note, and timing deviation.

**Acceptance criteria**

- Two curated mixed-song examples complete successfully.
- Intentional errors inserted into their source tabs are flagged in the expected measure.
- Low-confidence findings are clearly distinguished from strong findings.

### Milestone 4: reviewer-grade UI

**Deliverables**

- alphaTab integration with measure-level confidence colours.
- A finding drawer showing expected/detected notes, reason, and confidence.
- Click-to-seek and 3-5 second audio loop around the flagged measure.
- Reviewer actions: approve, dismiss, and ignore.

**Acceptance criteria**

- A reviewer can inspect and decide on any flagged finding without leaving the page.
- Review decisions persist and are reflected in the tab UI.
- The page remains usable on a typical laptop screen.

### Milestone 5: founder demo package

**Deliverables**

- Two or three licensed or permissioned demo examples.
- Seeded tab errors which the pipeline reliably detects.
- Hosted web/API deployment and a separately deployed GPU worker.
- A short demo script and known-limitations page.

**Acceptance criteria**

- A first-time viewer can complete the demo in under five minutes.
- The demo visibly catches multiple intentional tab errors in real mixed-song audio.
- Every finding has inspectable evidence; the UI never represents uncertainty as certainty.

## Analysis pipeline

1. Validate audio type, duration, and sample rate.
2. Convert to normalized mono/stereo WAV with FFmpeg.
3. Parse the selected tab track into measure-bound expected notes: pitch, onset, duration, string, fret, and technique metadata where available.
4. Separate the input mix into stems with Demucs.
5. Transcribe the guitar-containing stem into detected pitch events with Basic Pitch.
6. Estimate alignment anchors and apply dynamic time warping to reconcile timing differences.
7. Assign detected events to expected tab events within timing and pitch tolerances.
8. Aggregate event evidence into a measure confidence score and classified mismatches.
9. Store result artifacts and return structured findings to the review UI.

## Initial scoring policy

Start with transparent rules rather than a black-box quality score.

| Finding | Initial rule | UI treatment |
|---|---|---|
| Wrong pitch | Aligned onset but detected pitch outside tolerance | High confidence when transcription confidence is high |
| Missing note | Expected note has no compatible detected event | Review required |
| Extra note | Strong detected event has no expected match | Review required |
| Timing deviation | Matched note onset differs beyond tolerance | Show magnitude in milliseconds |
| Ambiguous evidence | Low-quality stem or weak transcription | Do not suggest a repair |

Only high-confidence wrong-pitch cases should offer a basic correction suggestion in the MVP. String/fret recommendations come later, after pitch verification is reliable.

## Scope boundaries

### Included

- Short audio clips, initially 30-90 seconds.
- Standard tuning, one selected guitar track.
- MIDI import first; Guitar Pro tab rendering/import can follow through alphaTab.
- Mixed-song analysis with explicitly visible uncertainty.
- Human review and feedback capture.

### Deferred

- Perfect transcription of every full commercial track.
- Automatic edits to original Guitar Pro files.
- Complex effect and technique interpretation: bends, slides, palm muting, harmonics, tremolo, and dense layered guitars.
- Record-to-Tab, adaptive arrangements, skill graph, and live setlist features.
- Automatic scraping or ingestion of Ultimate Guitar content.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Guitar is difficult to isolate in dense mixes | Curate demos with audible guitar; display low-confidence results rather than forcing a verdict |
| Transcription errors create false positives | Require confidence thresholds and reviewer approval; retain audio evidence |
| Tab timing differs from studio recording | Use measure anchors and dynamic time warping; initially select well-aligned examples |
| Long GPU processing time | Restrict clip duration, queue work, show progress, and cache artifacts |
| Copyright and data rights | Use owned, licensed, or explicitly permissioned demo audio and tabs only |
| Library/model licensing uncertainty | Record exact versions and licenses; complete a legal review before commercial integration |

## Test strategy

- Unit tests for tab parsing, event matching, scoring, and result serialization.
- Integration test for the full worker pipeline using a small owned fixture.
- Golden-result tests against curated songs with intentional known errors.
- UI test covering upload, processing status, finding inspection, and reviewer decision persistence.
- Manual listening review of every founder-demo example after each pipeline change.

## First implementation task

Create the monorepo skeleton and local Docker Compose stack, then implement a vertical slice for one fixture: upload (or select fixture) -> asynchronous job -> Basic Pitch analysis -> measure result JSON -> basic review screen.

Do not add mixed-song separation or automated correction suggestions until this slice is working reliably.

## Current implementation notes

The working slice now uses pasted chord sheets and six-string ASCII tabs as the
user-facing source format. MIDI remains an internal event representation so
users are not forced to author or upload a MIDI file. It also includes:

- beat-grid timing with a source-spacing fallback;
- monotonic expected/detected event alignment;
- reviewer-approved source-text corrections and download;
- short audio evidence loops around findings;
- authorized Google Drive audio import through Google Picker;
- YouTube URL validation as an attribution/reference field only (no arbitrary
  YouTube downloading);
- assisted screenshot OCR that returns editable chord/tab text and confidence;
- a permissioned-fixture manifest, synthetic smoke-fixture generator, and an
  end-to-end worker pipeline test.

The remaining founder-demo work is to add real owned/licensed recordings and
run a manual listening pass. Source separation, richer technique detection,
and automatic edits to Guitar Pro files remain outside this slice.
