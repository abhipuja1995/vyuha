"use client";

import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, IngestResult } from "@/lib/api";
import { CheckCircle, Download, FileAudio, HardDrive, Mic, Upload, XCircle } from "lucide-react";

// ─── Shared result banner ─────────────────────────────────────────────────────

function IngestResultBanner({ data }: { data: IngestResult }) {
  if (data.ingested) {
    return (
      <div className="bg-green-50 border border-green-200 rounded-xl p-5 space-y-2">
        <div className="flex items-center gap-2 text-green-700 font-medium">
          <CheckCircle className="w-5 h-5" /> Call ingested — test case created
        </div>
        <p className="text-sm text-green-700">
          Test case ID: <code className="font-mono">{data.test_case_id}</code>
        </p>
        {data.failure_signals && data.failure_signals.length > 0 && (
          <p className="text-xs text-green-600">
            Signals: {data.failure_signals.join(", ")}
            {data.confidence !== undefined && ` · Confidence: ${Math.round(data.confidence * 100)}%`}
          </p>
        )}
      </div>
    );
  }

  // Audio saved but no transcript → neutral info banner, not an error
  if (data.audio_path) {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 space-y-1">
        <div className="flex items-center gap-2 text-blue-700 font-medium">
          <HardDrive className="w-5 h-5" /> Audio saved
        </div>
        <p className="text-sm text-blue-700">
          Add a transcript above and upload again to generate a test case.
        </p>
        {data.call_id && (
          <p className="text-xs text-blue-600 font-mono">Call ID: {data.call_id}</p>
        )}
      </div>
    );
  }

  // Genuine non-ingestion (no failure signals detected, etc.)
  return (
    <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 space-y-1">
      <div className="flex items-center gap-2 text-amber-700 font-medium">
        <XCircle className="w-5 h-5" /> Not ingested
      </div>
      <p className="text-sm text-amber-700">{data.reason}</p>
      {data.call_id && (
        <p className="text-xs text-amber-600 font-mono">Call ID: {data.call_id}</p>
      )}
    </div>
  );
}

// ─── Tab 1: JSON / API form ───────────────────────────────────────────────────

const EXAMPLE_TRANSCRIPT = [
  { role: "agent", text: "Hello, thank you for calling. How can I help you?" },
  { role: "user", text: "I want to know my account balance" },
  { role: "agent", text: "I'm sorry, I didn't understand. Can you repeat that?" },
  { role: "user", text: "My account balance, please tell me" },
  { role: "agent", text: "I'm not able to process that request. Is there anything else?" },
  { role: "user", text: "Balance! I just want my balance!" },
];

function JsonIngestTab() {
  const [form, setForm] = useState({
    call_id: `CALL-${Date.now()}`,
    agent_id: "debt-collection-agent-v2",
    language_detected: "hi",
    task_completed: false,
    transcript: JSON.stringify(EXAMPLE_TRANSCRIPT, null, 2),
    sentiment_scores: "[0.7, 0.5, 0.3, 0.25, 0.2, 0.1]",
  });

  const mutation = useMutation({
    mutationFn: () => {
      const now = new Date().toISOString();
      return api.ingest.call({
        ...form,
        started_at: now,
        ended_at: now,
        transcript: JSON.parse(form.transcript),
        sentiment_scores: JSON.parse(form.sentiment_scores),
      });
    },
  });

  return (
    <div className="space-y-4">
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-800">
        <strong>How it works:</strong> The pipeline detects failure signals (repetition, abandonment,
        sentiment drop, tool errors), extracts the caller persona, and generates a reproducible test case.
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Call ID</label>
            <input value={form.call_id} onChange={(e) => setForm({ ...form, call_id: e.target.value })}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Agent ID</label>
            <input value={form.agent_id} onChange={(e) => setForm({ ...form, agent_id: e.target.value })}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Language Detected</label>
            <LanguageSelect value={form.language_detected} onChange={(v) => setForm({ ...form, language_detected: v })} />
          </div>
          <div className="flex items-center gap-2 pt-6">
            <input type="checkbox" id="tc_json" checked={form.task_completed}
              onChange={(e) => setForm({ ...form, task_completed: e.target.checked })} className="rounded" />
            <label htmlFor="tc_json" className="text-sm text-gray-700">Task completed?</label>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Transcript (JSON array)</label>
          <textarea value={form.transcript} onChange={(e) => setForm({ ...form, transcript: e.target.value })}
            rows={10} className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono resize-none" />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Sentiment Scores (per-turn, 0–1)</label>
          <input value={form.sentiment_scores} onChange={(e) => setForm({ ...form, sentiment_scores: e.target.value })}
            placeholder="[0.7, 0.5, 0.3, 0.25, 0.2, 0.1]"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono" />
        </div>

        <button onClick={() => mutation.mutate()} disabled={mutation.isPending}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-5 py-2.5 rounded-lg transition-colors">
          <Download className="w-4 h-4" />
          {mutation.isPending ? "Ingesting…" : "Ingest Call"}
        </button>
      </div>

      {mutation.isSuccess && mutation.data && <IngestResultBanner data={mutation.data} />}
      {mutation.isError && <ErrorBanner error={mutation.error as Error} />}
    </div>
  );
}

// ─── Tab 2: File upload ───────────────────────────────────────────────────────

function UploadTab() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState({
    call_id: "",
    agent_id: "",
    language_detected: "en-IN",
    task_completed: false,
    transcript: "",
  });

  // ── Ollama transcription ────────────────────────────────────────────────
  const sttMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Select a file first");
      const fd = new FormData();
      fd.append("audio_file", file);
      fd.append("language", form.language_detected); // tells Whisper which script to use
      const res = await fetch("/api/proxy/ingest/transcribe", {
        method: "POST",
        body: fd,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const data = await res.json() as { transcript: Array<{ role: string; text: string }>; turns: number };
      return data;
    },
    onSuccess: ({ transcript }) => {
      setForm((f) => ({ ...f, transcript: JSON.stringify(transcript, null, 2) }));
    },
  });

  // ── Upload + ingest ─────────────────────────────────────────────────────
  const mutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("Select a file first");
      return api.ingest.upload({
        audioFile: file,
        callId: form.call_id || undefined,
        agentId: form.agent_id || undefined,
        languageDetected: form.language_detected,
        taskCompleted: form.task_completed,
        transcriptJson: form.transcript.trim() ? form.transcript.trim() : "[]",
      });
    },
  });

  const TRANSCRIPT_PLACEHOLDER = `[
  {"role": "agent", "text": "Hello, how can I help you?"},
  {"role": "user",  "text": "I need to check my balance"},
  {"role": "agent", "text": "Sorry, I didn't catch that."}
]`;

  return (
    <div className="space-y-4">
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
        <strong>For when the pipeline isn't wired up:</strong> Upload any call recording directly.
        Use <strong>Transcribe with Ollama</strong> to auto-fill the transcript, or paste one manually.
        Leave the transcript blank to just archive the file.
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-5">

        {/* File drop zone */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Call Recording</label>
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className={`w-full border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
              file
                ? "border-brand-400 bg-brand-50"
                : "border-gray-200 hover:border-gray-300 bg-gray-50"
            }`}
          >
            <FileAudio className={`w-8 h-8 mx-auto mb-2 ${file ? "text-brand-500" : "text-gray-300"}`} />
            {file ? (
              <div>
                <p className="text-sm font-medium text-brand-700">{file.name}</p>
                <p className="text-xs text-brand-500 mt-0.5">{(file.size / 1024).toFixed(1)} KB · click to change</p>
              </div>
            ) : (
              <div>
                <p className="text-sm font-medium text-gray-600">Click to select a call recording</p>
                <p className="text-xs text-gray-400 mt-0.5">WAV · MP3 · OGG · FLAC · M4A · AAC · WebM</p>
              </div>
            )}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".wav,.mp3,.ogg,.flac,.m4a,.aac,.webm"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFile(f); sttMutation.reset(); mutation.reset(); } }}
          />
        </div>

        {/* Metadata */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Call ID <span className="text-gray-400 font-normal">(optional)</span></label>
            <input value={form.call_id} onChange={(e) => setForm({ ...form, call_id: e.target.value })}
              placeholder="CALL-001 — auto-generated if blank"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Agent ID <span className="text-gray-400 font-normal">(optional)</span></label>
            <input value={form.agent_id} onChange={(e) => setForm({ ...form, agent_id: e.target.value })}
              placeholder="e.g. ivr-agent-v3"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Language</label>
            <LanguageSelect value={form.language_detected} onChange={(v) => setForm({ ...form, language_detected: v })} />
          </div>
          <div className="flex items-center gap-2 pt-6">
            <input type="checkbox" id="tc_upload" checked={form.task_completed}
              onChange={(e) => setForm({ ...form, task_completed: e.target.checked })} className="rounded" />
            <label htmlFor="tc_upload" className="text-sm text-gray-700">Task completed?</label>
          </div>
        </div>

        {/* Transcript + Ollama button */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="block text-sm font-medium text-gray-700">
              Transcript{" "}
              <span className="text-gray-400 font-normal">
                (JSON array — leave blank to archive file only)
              </span>
            </label>
            <button
              type="button"
              onClick={() => sttMutation.mutate()}
              disabled={!file || sttMutation.isPending}
              title="Transcribe using local Ollama (requires OLLAMA_URL set on the server)"
              className="flex items-center gap-1.5 text-xs font-medium text-purple-700 border border-purple-200 bg-purple-50 hover:bg-purple-100 disabled:opacity-40 disabled:cursor-not-allowed px-3 py-1.5 rounded-lg transition-colors"
            >
              <Mic className="w-3.5 h-3.5" />
              {sttMutation.isPending ? "Transcribing…" : "Transcribe with Ollama"}
            </button>
          </div>
          <textarea
            value={form.transcript}
            onChange={(e) => setForm({ ...form, transcript: e.target.value })}
            placeholder={TRANSCRIPT_PLACEHOLDER}
            rows={8}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono resize-none"
          />
          {sttMutation.isSuccess && (
            <p className="text-xs text-purple-600 mt-1">
              ✓ Transcribed {sttMutation.data.turns} turns — review and edit before uploading.
            </p>
          )}
          {sttMutation.isError && (
            <p className="text-xs text-red-600 mt-1">
              Transcription error: {(sttMutation.error as Error).message}
            </p>
          )}
          {!sttMutation.isSuccess && !sttMutation.isError && !sttMutation.isPending && (
            <p className="text-xs text-gray-400 mt-1">
              Click <strong>Transcribe with Ollama</strong> to auto-fill from the recording, or paste the transcript manually.
            </p>
          )}
        </div>

        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending || !file}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-5 py-2.5 rounded-lg transition-colors"
        >
          <Upload className="w-4 h-4" />
          {mutation.isPending ? "Uploading…" : "Upload & Process"}
        </button>
      </div>

      {mutation.isSuccess && mutation.data && <IngestResultBanner data={mutation.data} />}
      {mutation.isError && <ErrorBanner error={mutation.error as Error} />}
    </div>
  );
}

// ─── Shared helpers ───────────────────────────────────────────────────────────

function LanguageSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm">
      {[
        ["en-IN", "English (Indian)"], ["hi", "Hindi"], ["te", "Telugu"],
        ["ta", "Tamil"], ["or", "Odia"], ["kn", "Kannada"],
        ["ml", "Malayalam"], ["mr", "Marathi"], ["bn", "Bengali"],
      ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );
}

function ErrorBanner({ error }: { error: Error }) {
  return (
    <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">
      {error.message}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

const TABS = ["API / JSON", "Upload Recording"] as const;
type Tab = typeof TABS[number];

export default function IngestPage() {
  const [tab, setTab] = useState<Tab>("API / JSON");

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Ingest Failed Call</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Convert a production call failure into a regression test case automatically.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 w-fit">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              tab === t
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {t === "Upload Recording" && <FileAudio className="w-3.5 h-3.5 inline mr-1.5 -mt-0.5" />}
            {t}
          </button>
        ))}
      </div>

      {tab === "API / JSON" ? <JsonIngestTab /> : <UploadTab />}
    </div>
  );
}
