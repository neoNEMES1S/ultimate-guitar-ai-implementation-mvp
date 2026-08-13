# First vertical slice

The initial implementation accepts a WAV/MP3/M4A/FLAC/MP4 recording and either a
pasted chord sheet or six-string ASCII tab. The upload endpoint stores the
source text and metadata under the job ID, queues a Celery task, parses source
tokens into normalized events, calls Basic Pitch, and scores pitch/onset
evidence inside clip-duration measure windows. MIDI remains an internal
interchange option for later structured imports.

The score is rule-based and evidence-first: a reviewer sees expected source
tokens, detected pitches, onset times, mismatch class, confidence, and a
proposed correction where one can be expressed. `approved`, `dismissed`, and
`ignored` decisions are persisted in SQLite.

Known first-slice limitations: no duration limit inspection yet, no FFmpeg
normalisation, and no Demucs/source separation. Assisted screenshot and PDF OCR
are available through the API and UI: PDF staff systems become editable ASCII
tab, while bends, slides, rests, and tuplets remain manual-review items.
Beat-grid timing, monotonic sequence alignment, evidence loops, Drive import
plumbing, YouTube reference validation, and approved text export are included;
Google Picker requires application credentials to be configured.
