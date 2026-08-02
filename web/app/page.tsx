"use client";

import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const googleClientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";
const googleApiKey = process.env.NEXT_PUBLIC_GOOGLE_API_KEY ?? "";
const googleAppId = process.env.NEXT_PUBLIC_GOOGLE_APP_ID ?? "";
type SourceKind = "chords" | "tab";
type Job = { id: string; status: "queued" | "processing" | "complete" | "failed"; source_kind: SourceKind; error?: string };
type Event = { kind?: string; pitch: number; onset_seconds: number; duration_seconds: number; confidence?: number; token?: string; string?: string; fret?: number; source_line?: number };
type Finding = { id: string; measure_number: number; type: string; confidence: number; expected?: Event; detected?: Event; message: string; correction?: string; audio_start_seconds?: number; audio_end_seconds?: number };
type Measure = { number: number; start_seconds: number; end_seconds: number; score: number; expected_events: Event[]; detected_events: Event[] };
type Result = { source_kind: SourceKind; source_text: string; measures: Measure[]; findings: Finding[]; transcription_engine: string; timing_basis: string; suggested_text?: string; reviews: Record<string, string> };
type DriveFile = { id: string; name: string; url: string };

const exampleChordSheet = `[Verse]\nG                 D\nWhen your legs don't work like they used to before\nEm                C\nAnd I can't sweep you off of your feet`;
const exampleTab = `e|--0-----0-----3-----0--|\nB|--1-----1-----0-----1--|\nG|--0-----2-----0-----0--|\nD|--2-----2-----0-----2--|\nA|--3-----0-----2-----3--|\nE|-----------------------|`;

export default function Home() {
  const [job, setJob] = useState<Job>();
  const [result, setResult] = useState<Result>();
  const [selected, setSelected] = useState<Finding>();
  const [message, setMessage] = useState("Paste a chord sheet or tab and add its recording to begin.");
  const [audioSource, setAudioSource] = useState<"upload" | "drive">("upload");
  const [driveFile, setDriveFile] = useState<DriveFile>();
  const [driveToken, setDriveToken] = useState<string>();
  const [ocrMessage, setOcrMessage] = useState("Screenshot OCR is optional; review its result before analysis.");
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    if (!job || ["complete", "failed"].includes(job.status)) return;
    const interval = window.setInterval(async () => {
      const response = await fetch(`${apiUrl}/api/jobs/${job.id}`);
      const next = await response.json() as Job;
      setJob(next);
      setMessage(next.status === "queued" ? "Queued for analysis…" : "Aligning the source text to the recording…");
    }, 1500);
    return () => window.clearInterval(interval);
  }, [job]);

  useEffect(() => {
    if (job?.status !== "complete") return;
    fetch(`${apiUrl}/api/jobs/${job.id}/result`).then(response => response.json()).then((data: Result) => {
      setResult(data);
      setMessage(`Analysis complete using ${data.transcription_engine}. ${data.timing_basis}.`);
    });
  }, [job?.status, job?.id]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setResult(undefined); setSelected(undefined); setMessage("Uploading source and audio…");
    let response: Response;
    if (audioSource === "drive") {
      if (!driveFile || !driveToken) { setMessage("Choose a Google Drive audio file first."); return; }
      const driveForm = new FormData();
      ["source_text", "source_kind", "bpm", "capo", "tuning", "reference_url"].forEach(name => driveForm.append(name, String(form.get(name) ?? "")));
      driveForm.append("drive_url", driveFile.url);
      response = await fetch(`${apiUrl}/api/jobs/drive`, { method: "POST", headers: { "X-Google-Drive-Access-Token": driveToken }, body: driveForm });
    } else {
      response = await fetch(`${apiUrl}/api/jobs`, { method: "POST", body: form });
    }
    if (!response.ok) { setMessage((await response.json()).detail ?? "Upload failed."); return; }
    setJob(await response.json());
  }

  function chooseDriveFile() {
    if (!googleClientId || !googleApiKey) {
      setMessage("Google Drive import needs GOOGLE_CLIENT_ID and GOOGLE_API_KEY in the web environment.");
      return;
    }
    const browserWindow = window as unknown as { google?: any; gapi?: any };
    if (!browserWindow.google?.accounts?.oauth2 || !browserWindow.gapi) {
      setMessage("Google services are still loading; try the Drive button again in a moment.");
      return;
    }
    const tokenClient = browserWindow.google.accounts.oauth2.initTokenClient({
      client_id: googleClientId,
      scope: "https://www.googleapis.com/auth/drive.file",
      callback: (tokenResponse: { access_token?: string }) => {
        if (tokenResponse.access_token) openDrivePicker(tokenResponse.access_token);
      },
    });
    tokenClient.requestAccessToken({ prompt: "consent" });
  }

  function openDrivePicker(token: string) {
    const browserWindow = window as unknown as { google?: any; gapi?: any };
    browserWindow.gapi.load("picker", () => {
      const view = new browserWindow.google.picker.DocsView(browserWindow.google.picker.ViewId.DOCS).setMimeTypes("audio/mpeg,audio/wav,audio/mp4,audio/flac,video/mp4");
      const builder = new browserWindow.google.picker.PickerBuilder().setDeveloperKey(googleApiKey).setOAuthToken(token).addView(view).setCallback((data: any) => {
        if (data.action === browserWindow.google.picker.Action.PICKED && data.docs?.[0]) {
          const doc = data.docs[0];
          setDriveToken(token);
          setDriveFile({ id: doc.id, name: doc.name, url: `https://drive.google.com/open?id=${doc.id}` });
          setMessage(`Selected ${doc.name} from Google Drive.`);
        }
      });
      if (googleAppId) builder.setAppId(googleAppId);
      builder.build().setVisible(true);
    });
  }

  async function recognizeImage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("image", file);
    setOcrMessage("Reading screenshot…");
    const response = await fetch(`${apiUrl}/api/sources/image`, { method: "POST", body: form });
    const data = await response.json() as { text?: string; confidence?: number; suggested_kind?: SourceKind; warnings?: string[]; detail?: string };
    if (!response.ok) { setOcrMessage(data.detail ?? "Screenshot OCR failed."); return; }
    const textarea = document.querySelector<HTMLTextAreaElement>("textarea[name=source_text]");
    const select = document.querySelector<HTMLSelectElement>("select[name=source_kind]");
    if (textarea) textarea.value = data.text ?? "";
    if (select && data.suggested_kind) select.value = data.suggested_kind;
    setOcrMessage(`OCR confidence ${Math.round((data.confidence ?? 0) * 100)}%. ${data.warnings?.join(" ") ?? "Review the extracted text."}`);
  }

  async function decide(decision: "approved" | "dismissed" | "ignored") {
    if (!job || !selected) return;
    await fetch(`${apiUrl}/api/jobs/${job.id}/findings/${selected.id}/review`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision }) });
    setResult(current => current ? { ...current, reviews: { ...current.reviews, [selected.id]: decision } } : current);
  }

  async function downloadCorrected() {
    if (!job || !result) return;
    const response = await fetch(`${apiUrl}/api/jobs/${job.id}/corrected-source`);
    if (!response.ok) { setMessage("Review at least one proposed correction before exporting."); return; }
    const data = await response.json() as { corrected_text: string };
    const blob = new Blob([data.corrected_text], { type: "text/plain;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob); link.download = `${result.source_kind}-corrected.txt`; link.click(); URL.revokeObjectURL(link.href);
  }

  async function playEvidence() {
    if (!selected || !audioRef.current) return;
    const player = audioRef.current;
    const start = selected.audio_start_seconds ?? 0;
    const end = selected.audio_end_seconds ?? start + 3;
    player.currentTime = start;
    await player.play().catch(() => undefined);
    window.setTimeout(() => {
      if (player.currentTime >= end - 0.05) player.pause();
    }, Math.max(500, (end - start) * 1000));
  }

  const selectedDecision = useMemo(() => selected && result?.reviews[selected.id], [selected, result]);
  return <main>
    <header><p className="eyebrow">ULTIMATE GUITAR · MVP</p><h1>Verify and repair a chord sheet or tab.</h1><p className="subtle">Paste the source users already have, add a recording, and review every proposed change.</p></header>
    <section className="upload"><form onSubmit={submit}>
      <div className="source-editor"><label>Chord sheet or tab <select name="source_kind" defaultValue="chords"><option value="chords">Chords + lyrics</option><option value="tab">Six-string ASCII tab</option></select></label><textarea required name="source_text" defaultValue={exampleChordSheet} rows={9} spellCheck={false} aria-label="Chord sheet or tab text" /><div className="ocr-import"><label>Import screenshot <input type="file" accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp" onChange={recognizeImage} /></label><span>{ocrMessage}</span></div><p className="hint">Text spacing is retained as a timing clue; the audio supplies the rhythm evidence.</p></div>
      <div className="source-options"><div className="audio-source-toggle"><button type="button" className={audioSource === "upload" ? "active" : "secondary"} onClick={() => setAudioSource("upload")}>Upload audio</button><button type="button" className={audioSource === "drive" ? "active" : "secondary"} onClick={() => setAudioSource("drive")}>Google Drive</button></div>{audioSource === "upload" ? <label>Audio recording <input required name="audio" type="file" accept="audio/wav,audio/mpeg,audio/mp4,audio/flac,video/mp4,.wav,.mp3,.m4a,.flac,.mp4" /></label> : <div className="drive-box"><button type="button" onClick={chooseDriveFile}>Choose Drive file</button><span>{driveFile ? driveFile.name : "No Drive file selected"}</span></div>}<label>BPM hint <input name="bpm" type="number" min="30" max="240" placeholder="Infer" /></label><label>Capo <input name="capo" type="number" min="0" max="24" defaultValue="0" /></label><label>Tuning <input name="tuning" defaultValue="E2,A2,D3,G3,B3,E4" /></label><label>YouTube reference <input name="reference_url" type="url" placeholder="Optional source link" /></label><button type="submit">Start analysis</button></div>
    </form><div className="examples"><button type="button" onClick={() => fillExample("chords")}>Load chord example</button><button type="button" onClick={() => fillExample("tab")}>Load tab example</button></div><p aria-live="polite">{job ? `${job.status.toUpperCase()} — ` : ""}{job?.error ?? message}</p></section>
    {result && <section className="review"><div><h2>Measure confidence</h2><div className="measures">{result.measures.map(measure => <button className={measure.score > .85 ? "good" : measure.score > .6 ? "caution" : "bad"} key={measure.number} onClick={() => setSelected(result.findings.find(item => item.measure_number === measure.number))} title={`${measure.score * 100}% confidence`}>M{measure.number}<small>{Math.round(measure.score * 100)}%</small></button>)}</div><h2>Findings and proposed repairs</h2><div className="findings">{result.findings.length === 0 ? <p>No mismatches were found at the current thresholds.</p> : result.findings.map(finding => <button key={finding.id} className={selected?.id === finding.id ? "finding selected" : "finding"} onClick={() => setSelected(finding)}><strong>M{finding.measure_number} · {finding.type.replaceAll("_", " ")}</strong><span>{finding.message}</span>{finding.correction && <em>Suggested correction: {finding.correction}</em>}<em>{Math.round(finding.confidence * 100)}% confidence</em></button>)}</div><button className="export" onClick={downloadCorrected}>Download approved corrections</button></div>
      <aside><h2>Reviewer evidence</h2>{selected ? <><p><b>{selected.type.replaceAll("_", " ")}</b><br />{selected.message}</p><dl><dt>Expected</dt><dd>{eventText(selected.expected)}</dd><dt>Detected</dt><dd>{eventText(selected.detected)}</dd><dt>Confidence</dt><dd>{Math.round(selected.confidence * 100)}%</dd><dt>Decision</dt><dd>{selectedDecision ?? "Awaiting review"}</dd></dl><div className="audio-evidence"><button onClick={playEvidence}>Play evidence loop</button><audio ref={audioRef} controls preload="metadata" src={`${apiUrl}/api/jobs/${job?.id}/audio`} /></div>{selected.correction && <div className="proposal"><b>Proposed repair</b><p>{selected.correction}</p><small>Approve the finding, then export the corrected source text.</small></div>}<div className="actions"><button onClick={() => decide("approved")}>Approve</button><button onClick={() => decide("dismissed")}>Dismiss</button><button onClick={() => decide("ignored")}>Ignore</button></div></> : <p>Select a flagged measure or finding to inspect its evidence.</p>}</aside>
    </section>}
  </main>;

  function fillExample(kind: SourceKind) {
    const textarea = document.querySelector<HTMLTextAreaElement>("textarea[name=source_text]");
    const select = document.querySelector<HTMLSelectElement>("select[name=source_kind]");
    if (textarea) textarea.value = kind === "tab" ? exampleTab : exampleChordSheet;
    if (select) select.value = kind;
  }
}

function eventText(event?: Event) {
  if (!event) return "—";
  const source = event.token ? `${event.token}${event.string ? ` on string ${event.string}` : ""}` : `MIDI ${event.pitch}`;
  return `${source} at ${event.onset_seconds.toFixed(2)} s${event.confidence ? ` (${Math.round(event.confidence * 100)}%)` : ""}`;
}
