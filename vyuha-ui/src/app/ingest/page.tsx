"use client";

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, IngestResult, TestCase } from "@/lib/api";

// PreviewResult is a superset of IngestResult (same shape, just aliased for clarity)
type PreviewResult = IngestResult;
import {
  CheckCircle, Download, FileAudio, HardDrive, Mic, Upload, XCircle,
  AlertTriangle, Eye, Save, Trash2, ChevronDown, ChevronUp,
  Loader2, Radio, Cpu, Wand2, DatabaseZap,
} from "lucide-react";
import Link from "next/link";


// ─── Progress steps ───────────────────────────────────────────────────────────

const STEPS = [
  { id: "upload", label: "Uploading audio", icon: Upload },
  { id: "stt", label: "Transcribing with Whisper", icon: Mic },
  { id: "signals", label: "Detecting failure signals", icon: Radio },
  { id: "persona", label: "Extracting caller persona", icon: Cpu },
  { id: "generate", label: "Generating test case with LLM", icon: Wand2 },
  { id: "preview", label: "Ready to preview", icon: Eye },
] as const;

type StepId = typeof STEPS[number]["id"];

function ProgressStepper({ current, error }: { current: StepId | "done" | "error" | null; error?: string }) {
  if (!current) return null;
  const currentIdx = STEPS.findIndex((s) => s.id === current);

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-3">
      <p className="text-sm font-medium text-gray-700">Processing call…</p>
      <div className="space-y-2">
        {STEPS.map((step, i) => {
          const Icon = step.icon;
          const isDone = current === "done" || i < currentIdx;
          const isActive = step.id === current;
          const isError = current === "error" && isActive;
          return (
            <div key={step.id} className="flex items-center gap-3">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 ${
                isError ? "bg-red-100" :
                isDone ? "bg-green-100" :
                isActive ? "bg-brand-100" :
                "bg-gray-100"
              }`}>
                {isDone ? <CheckCircle className="w-3.5 h-3.5 text-green-600" /> :
                 isActive && !isError ? <Loader2 className="w-3.5 h-3.5 text-brand-600 animate-spin" /> :
                 isError ? <XCircle className="w-3.5 h-3.5 text-red-600" /> :
                 <Icon className="w-3.5 h-3.5 text-gray-400" />}
              </div>
              <span className={`text-sm ${
                isDone ? "text-green-700" :
                isActive ? "text-brand-700 font-medium" :
                "text-gray-400"
              }`}>{step.label}</span>
              {isActive && !isError && (
                <span className="text-xs text-gray-400 ml-auto animate-pulse">in progress…</span>
              )}
            </div>
          );
        })}
      </div>
      {error && <p className="text-xs text-red-600 bg-red-50 rounded-lg p-2 mt-2">{error}</p>}
    </div>
  );
}

// ─── Test case preview ────────────────────────────────────────────────────────

function NodeBadge({ tag, children }: { tag?: string; children: React.ReactNode }) {
  const colors: Record<string, string> = {
    CRITICAL: "bg-purple-100 text-purple-800",
    HAPPY_PATH: "bg-green-100 text-green-800",
    EDGE_CASE: "bg-yellow-100 text-yellow-800",
    FAILURE_MODE: "bg-red-100 text-red-800",
    REGRESSION: "bg-blue-100 text-blue-800",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${colors[tag ?? ""] ?? "bg-gray-100 text-gray-700"}`}>
      {children}
    </span>
  );
}

function TestCasePreview({ tc, signals, confidence, onSave, onDiscard, saving }: {
  tc: TestCase;
  signals?: string[];
  confidence?: number;
  onSave: () => void;
  onDiscard: () => void;
  saving: boolean;
}) {
  const [showGraph, setShowGraph] = useState(false);

  return (
    <div className="border border-brand-300 bg-brand-50 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="bg-brand-600 text-white px-5 py-4">
        <div className="flex items-center gap-2 mb-1">
          <Eye className="w-4 h-4" />
          <span className="font-semibold">Preview — generated test case</span>
          {confidence !== undefined && (
            <span className="ml-auto text-xs bg-white/20 px-2 py-0.5 rounded-full">
              {Math.round(confidence * 100)}% confidence
            </span>
          )}
        </div>
        <p className="text-xs text-white/70">Review before saving. You can edit after saving from Test Cases.</p>
      </div>

      <div className="p-5 space-y-5 bg-white">
        {/* Title + category */}
        <div className="space-y-2">
          <div className="flex items-start gap-3">
            <NodeBadge tag={tc.category}>{tc.category.replace("_", " ")}</NodeBadge>
            {signals && signals.map((s) => (
              <span key={s} className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full font-medium">
                {s}
              </span>
            ))}
          </div>
          <h3 className="font-semibold text-gray-900">{tc.title}</h3>
          <p className="text-sm text-gray-600">{tc.user_goal}</p>
        </div>

        {/* Persona */}
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {[
            ["Language", tc.persona_config.language],
            ["Accent", tc.persona_config.accent_variant || "—"],
            ["Noise", tc.persona_config.noise_profile.replace("_", " ")],
            ["Emotion", tc.persona_config.emotion],
            ["Speaking rate", `${tc.persona_config.speaking_rate}×`],
            tc.persona_config.code_switch
              ? ["Code-switch", `${tc.persona_config.code_switch.primary_language} + ${tc.persona_config.code_switch.secondary_language}`]
              : ["Code-switch", "none"],
          ].map(([label, val]) => (
            <div key={label} className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500">{label}</p>
              <p className="text-sm font-medium text-gray-800 truncate">{val}</p>
            </div>
          ))}
        </div>

        {/* Pass criteria */}
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
          <p className="text-xs font-medium text-amber-700 mb-1">Pass criteria</p>
          <p className="text-sm text-amber-900">{tc.pass_criteria}</p>
        </div>

        {/* Ground truth */}
        {Object.keys(tc.ground_truth_end_state).length > 0 && (
          <div>
            <p className="text-xs font-medium text-gray-500 mb-2">Ground truth end state</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(tc.ground_truth_end_state).map(([k, v]) => (
                <span key={k} className="text-xs bg-gray-100 px-2 py-1 rounded font-mono">
                  {k}: <span className="text-brand-600">{String(v)}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Conversation graph toggle */}
        <div>
          <button
            onClick={() => setShowGraph((v) => !v)}
            className="flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-gray-900"
          >
            {showGraph ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            Conversation graph ({tc.conversation_graph.nodes.length} nodes, {tc.conversation_graph.edges.length} edges)
          </button>
          {showGraph && (
            <div className="mt-3 space-y-2">
              {tc.conversation_graph.nodes.map((node) => (
                <div key={node.node_id} className={`flex gap-3 items-start p-3 rounded-lg border ${
                  node.node_id === tc.conversation_graph.start_node
                    ? "border-brand-200 bg-brand-50"
                    : node.is_terminal
                    ? "border-green-200 bg-green-50"
                    : "border-gray-200 bg-gray-50"
                }`}>
                  <span className={`text-xs font-mono px-1.5 py-0.5 rounded flex-shrink-0 ${
                    node.node_id === tc.conversation_graph.start_node
                      ? "bg-brand-200 text-brand-800"
                      : node.is_terminal
                      ? "bg-green-200 text-green-800"
                      : "bg-gray-200 text-gray-700"
                  }`}>
                    {node.node_id === tc.conversation_graph.start_node ? "start" : node.is_terminal ? "end" : node.node_id}
                  </span>
                  <p className="text-sm text-gray-700 italic">"{node.utterance_template}"</p>
                </div>
              ))}
              {tc.conversation_graph.edges.map((edge, i) => (
                <div key={i} className="flex items-center gap-2 px-3 text-xs text-gray-500">
                  <span className="font-mono">{edge.from_node}</span>
                  <span>→</span>
                  <span className="font-mono">{edge.to_node}</span>
                  <span className="text-gray-400">if "{edge.condition}"</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Tags */}
        {tc.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {tc.tags.map((tag) => (
              <span key={tag} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">{tag}</span>
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="px-5 py-4 bg-gray-50 border-t border-gray-200 flex items-center gap-3">
        <button
          onClick={onSave}
          disabled={saving}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-5 py-2 rounded-lg transition-colors"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? "Saving…" : "Save test case"}
        </button>
        <button
          onClick={onDiscard}
          disabled={saving}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-red-600 border border-gray-200 px-4 py-2 rounded-lg transition-colors"
        >
          <Trash2 className="w-4 h-4" /> Discard
        </button>
        <span className="text-xs text-gray-400 ml-auto">Changes can be made after saving in Test Cases</span>
      </div>
    </div>
  );
}

// ─── Saved banner ─────────────────────────────────────────────────────────────

function SavedBanner({ testCaseId }: { testCaseId: string }) {
  return (
    <div className="bg-green-50 border border-green-200 rounded-xl p-5">
      <div className="flex items-center gap-2 text-green-700 font-medium mb-2">
        <CheckCircle className="w-5 h-5" /> Test case saved successfully
      </div>
      <p className="text-sm text-green-700">
        ID: <code className="font-mono">{testCaseId}</code>
      </p>
      <Link
        href={`/test-cases/${testCaseId}`}
        className="inline-flex items-center gap-1.5 mt-3 text-sm font-medium text-brand-600 hover:underline"
      >
        View test case →
      </Link>
    </div>
  );
}

// ─── No signals banner ────────────────────────────────────────────────────────

function NoSignalsBanner({ reason }: { reason?: string }) {
  return (
    <div className="bg-amber-50 border border-amber-200 rounded-xl p-5">
      <div className="flex items-center gap-2 text-amber-700 font-medium">
        <AlertTriangle className="w-5 h-5" /> No failure signals detected
      </div>
      <p className="text-sm text-amber-700 mt-1">{reason ?? "Call does not meet the ingestion threshold."}</p>
      <p className="text-xs text-amber-600 mt-2">
        Tip: add <code className="bg-amber-100 px-1 rounded">sentiment_scores</code> dropping below 0.35,
        or repeated identical utterances, to trigger ingestion.
      </p>
    </div>
  );
}

// ─── JSON tab ─────────────────────────────────────────────────────────────────

const EXAMPLE_TRANSCRIPT = [
  { role: "agent", text: "Hello, thank you for calling. How can I help you?" },
  { role: "user", text: "I want to know my account balance" },
  { role: "agent", text: "I'm sorry, I didn't understand. Can you repeat that?" },
  { role: "user", text: "My account balance, please tell me" },
  { role: "agent", text: "I'm not able to process that request. Is there anything else?" },
  { role: "user", text: "Balance! I just want my balance!" },
];

function JsonIngestTab() {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    call_id: `CALL-${Date.now()}`,
    agent_id: "debt-collection-agent-v2",
    language_detected: "hi",
    task_completed: false,
    transcript: JSON.stringify(EXAMPLE_TRANSCRIPT, null, 2),
    sentiment_scores: "[0.7, 0.5, 0.3, 0.25, 0.2, 0.1]",
  });
  const [step, setStep] = useState<StepId | "done" | "error" | null>(null);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);

  const previewMutation = useMutation({
    mutationFn: async () => {
      const now = new Date().toISOString();
      setStep("signals");
      await new Promise((r) => setTimeout(r, 400));
      setStep("persona");
      await new Promise((r) => setTimeout(r, 400));
      setStep("generate");
      const result = await api.ingest.call({   // preview endpoint
        ...form,
        started_at: now,
        ended_at: now,
        transcript: JSON.parse(form.transcript),
        sentiment_scores: JSON.parse(form.sentiment_scores),
        _preview: true,  // hint — handled below
      } as any);
      return result;
    },
    onMutate: () => { setStep("signals"); setPreview(null); setSavedId(null); },
    onSuccess: (data) => {
      setStep("preview");
      setPreview(data);
    },
    onError: () => setStep("error"),
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!preview?.test_case) throw new Error("No test case to save");
      return api.testCases.create(preview.test_case);
    },
    onSuccess: (tc) => {
      setSavedId(tc.test_id);
      setPreview(null);
      setStep(null);
      qc.invalidateQueries({ queryKey: ["test-cases"] });
    },
  });

  // We call /ingest/call/preview endpoint directly
  const handlePreview = async () => {
    setStep("signals");
    setPreview(null);
    setSavedId(null);
    try {
      const now = new Date().toISOString();
      const body = {
        ...form,
        started_at: now,
        ended_at: now,
        transcript: JSON.parse(form.transcript),
        sentiment_scores: JSON.parse(form.sentiment_scores),
      };
      setStep("persona");
      await new Promise((r) => setTimeout(r, 300));
      setStep("generate");
      const res = await fetch("/api/proxy/ingest/call/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Ingestion failed");
      setStep("preview");
      setPreview(data);
    } catch (e: any) {
      setStep("error");
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-800">
        <strong>How it works:</strong> Detects failure signals → extracts persona → generates test case with LLM → preview before save.
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
            <label className="block text-sm font-medium text-gray-700 mb-1">Language</label>
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
            rows={8} className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono resize-none" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Sentiment scores (per-turn, 0–1)</label>
          <input value={form.sentiment_scores} onChange={(e) => setForm({ ...form, sentiment_scores: e.target.value })}
            placeholder="[0.7, 0.5, 0.3, 0.25, 0.2, 0.1]"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono" />
        </div>
        <button
          onClick={handlePreview}
          disabled={step !== null && step !== "error" && step !== "preview"}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-5 py-2.5 rounded-lg"
        >
          <Eye className="w-4 h-4" />
          {step && step !== "error" && step !== "preview" ? "Processing…" : "Preview test case"}
        </button>
      </div>

      {step && step !== "preview" && (
        <ProgressStepper current={step} />
      )}

      {preview && preview.ingested && preview.test_case && step === "preview" && (
        <TestCasePreview
          tc={preview.test_case}
          signals={preview.failure_signals}
          confidence={preview.confidence}
          onSave={() => saveMutation.mutate()}
          onDiscard={() => { setPreview(null); setStep(null); }}
          saving={saveMutation.isPending}
        />
      )}
      {preview && !preview.ingested && <NoSignalsBanner reason={preview.reason} />}
      {savedId && <SavedBanner testCaseId={savedId} />}
    </div>
  );
}

// ─── Upload tab ───────────────────────────────────────────────────────────────

function UploadTab() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState({
    call_id: "",
    agent_id: "",
    language_detected: "en-IN",
    task_completed: false,
    transcript: "",
  });
  const [step, setStep] = useState<StepId | "done" | "error" | null>(null);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [stepError, setStepError] = useState<string | undefined>();

  const sttMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Select a file first");
      const fd = new FormData();
      fd.append("audio_file", file);
      fd.append("language", form.language_detected);
      const res = await fetch("/api/proxy/ingest/transcribe", { method: "POST", body: fd });
      if (!res.ok) { const t = await res.text(); throw new Error(t || `HTTP ${res.status}`); }
      return res.json() as Promise<{ transcript: Array<{ role: string; text: string }>; turns: number }>;
    },
    onSuccess: ({ transcript }) =>
      setForm((f) => ({ ...f, transcript: JSON.stringify(transcript, null, 2) })),
  });

  const handlePreview = async () => {
    if (!file) return;
    setStep("upload");
    setPreview(null);
    setSavedId(null);
    setStepError(undefined);
    try {
      const fd = new FormData();
      fd.append("audio_file", file);
      fd.append("call_id", form.call_id);
      fd.append("agent_id", form.agent_id || "unknown-agent");
      fd.append("language_detected", form.language_detected);
      fd.append("task_completed", String(form.task_completed));
      fd.append("transcript_json", form.transcript.trim() || "[]");
      fd.append("auto_transcribe", "true");

      await new Promise((r) => setTimeout(r, 200));
      setStep("stt");
      await new Promise((r) => setTimeout(r, 200));

      // Long step — actual API call
      setStep("signals");
      const res = await fetch("/api/proxy/ingest/upload/preview", { method: "POST", body: fd });
      const data: PreviewResult = await res.json();
      if (!res.ok) throw new Error((data as any).detail ?? "Upload failed");

      if (!data.ingested) {
        setStep(null);
        setPreview(data);
        return;
      }

      setStep("persona");
      await new Promise((r) => setTimeout(r, 200));
      setStep("generate");
      await new Promise((r) => setTimeout(r, 300));
      setStep("preview");
      setPreview(data);
    } catch (e: any) {
      setStepError(e.message);
      setStep("error");
    }
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!preview?.test_case) throw new Error("No test case to save");
      return api.testCases.create(preview.test_case);
    },
    onSuccess: (tc) => {
      setSavedId(tc.test_id);
      setPreview(null);
      setStep(null);
      qc.invalidateQueries({ queryKey: ["test-cases"] });
    },
  });

  const PLACEHOLDER = `[
  {"role": "agent", "text": "Hello, how can I help you?"},
  {"role": "user",  "text": "I need to check my balance"}
]`;

  return (
    <div className="space-y-4">
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
        Upload a call recording. Whisper auto-transcribes it, the pipeline generates a test case, and you preview before saving.
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-5">
        {/* Drop zone */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Call Recording</label>
          <button type="button" onClick={() => fileRef.current?.click()}
            className={`w-full border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
              file ? "border-brand-400 bg-brand-50" : "border-gray-200 hover:border-gray-300 bg-gray-50"
            }`}>
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
          <input ref={fileRef} type="file" accept=".wav,.mp3,.ogg,.flac,.m4a,.aac,.webm" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFile(f); sttMutation.reset(); setPreview(null); setStep(null); setSavedId(null); } }} />
        </div>

        {/* Metadata */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Call ID <span className="text-gray-400 font-normal">(optional)</span></label>
            <input value={form.call_id} onChange={(e) => setForm({ ...form, call_id: e.target.value })}
              placeholder="Auto-generated if blank"
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

        {/* Transcript */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="block text-sm font-medium text-gray-700">
              Transcript <span className="text-gray-400 font-normal">(optional — Whisper will auto-fill)</span>
            </label>
            <button type="button" onClick={() => sttMutation.mutate()} disabled={!file || sttMutation.isPending}
              className="flex items-center gap-1.5 text-xs font-medium text-purple-700 border border-purple-200 bg-purple-50 hover:bg-purple-100 disabled:opacity-40 px-3 py-1.5 rounded-lg">
              {sttMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Mic className="w-3.5 h-3.5" />}
              {sttMutation.isPending ? "Transcribing…" : "Transcribe with Whisper"}
            </button>
          </div>
          <textarea value={form.transcript} onChange={(e) => setForm({ ...form, transcript: e.target.value })}
            placeholder={PLACEHOLDER} rows={6}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono resize-none" />
          {sttMutation.isSuccess && (
            <p className="text-xs text-purple-600 mt-1">✓ {sttMutation.data.turns} turns transcribed — review above, then click Preview.</p>
          )}
          {sttMutation.isError && (
            <p className="text-xs text-red-600 mt-1">{(sttMutation.error as Error).message}</p>
          )}
        </div>

        <button onClick={handlePreview} disabled={!file || (step !== null && step !== "error" && step !== "preview")}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-5 py-2.5 rounded-lg">
          <Eye className="w-4 h-4" />
          {step && step !== "error" && step !== "preview" ? "Processing…" : "Preview test case"}
        </button>
      </div>

      {step && step !== "preview" && step !== null && (
        <ProgressStepper current={step} error={stepError} />
      )}

      {preview && preview.ingested && preview.test_case && step === "preview" && (
        <TestCasePreview
          tc={preview.test_case}
          signals={preview.failure_signals}
          confidence={preview.confidence}
          onSave={() => saveMutation.mutate()}
          onDiscard={() => { setPreview(null); setStep(null); }}
          saving={saveMutation.isPending}
        />
      )}
      {preview && !preview.ingested && <NoSignalsBanner reason={preview.reason} />}
      {savedId && <SavedBanner testCaseId={savedId} />}
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
          Convert a production failure into a regression test case — preview before saving.
        </p>
      </div>

      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 w-fit">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-1.5 text-sm font-medium rounded-lg transition-colors ${
              tab === t ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
            }`}>
            {t === "Upload Recording" && <FileAudio className="w-3.5 h-3.5 inline mr-1.5 -mt-0.5" />}
            {t}
          </button>
        ))}
      </div>

      {tab === "API / JSON" ? <JsonIngestTab /> : <UploadTab />}
    </div>
  );
}
