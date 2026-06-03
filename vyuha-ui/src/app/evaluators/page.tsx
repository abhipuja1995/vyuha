"use client";

import { useQuery, useMutation } from "@tanstack/react-query";
import { useState, useRef } from "react";
import { apiFetch } from "@/lib/api";
import {
  FlaskConical, Play, ChevronDown, ChevronUp, Plus, Trash2,
  CheckCircle, XCircle, AlertCircle, Loader2, BarChart3, Mic, FileAudio,
} from "lucide-react";
import { clsx } from "clsx";

// ── Types ─────────────────────────────────────────────────────────────────────
interface EvaluatorMeta { name: string; description: string; required_keys: string[] }
interface EvalResult { value: number | boolean | string; reason: string; passed: boolean | null; runtime_ms: number }
interface BatchResult { evaluator: string; total: number; passed: number; failed: number; avg_value: number | null; results: EvalResult[] }
interface ExperimentResult { id: string; name: string; dataset_size: number; started_at: string; duration_ms: number; evaluator_summaries: Record<string, any> }

// ── Helpers ───────────────────────────────────────────────────────────────────

const CATEGORIES: Record<string, string[]> = {
  "Heuristic": ["contains","contains_any","contains_all","contains_none","equals","starts_with","ends_with","regex","length_less_than","length_greater_than","length_between","word_count_in_range","one_line","is_json","is_url","is_email","is_refusal"],
  "Similarity": ["rouge_score","bleu_score","meteor_score","f1_score","levenshtein_similarity","jaccard_similarity","jaro_winkler_similarity","fuzzy_match","embedding_similarity"],
  "Audio / ASR": ["word_error_rate","character_error_rate","match_error_rate","word_info_lost","word_info_preserved"],
  "Agent": ["tool_call_accuracy","trajectory_match","step_count"],
  "Retrieval": ["recall_at_k","precision_at_k","ndcg_at_k","mean_reciprocal_rank","hit_rate"],
  "Safety": ["regex_pii_detection","latency_check"],
};

function verdictIcon(passed: boolean | null) {
  if (passed === true) return <CheckCircle className="w-4 h-4 text-green-500" />;
  if (passed === false) return <XCircle className="w-4 h-4 text-red-500" />;
  return <AlertCircle className="w-4 h-4 text-gray-400" />;
}

// ── Evaluator Playground ──────────────────────────────────────────────────────

function EvalPlayground({ evaluators }: { evaluators: EvaluatorMeta[] }) {
  const [selected, setSelected] = useState("rouge_score");
  const [userInput, setUserInput] = useState("Mujhe apna account balance batao");
  const [systemPrompt, setSystemPrompt] = useState("You are a banking voice agent. Be concise and helpful.");
  const [expected, setExpected] = useState("Your account balance is");
  const [config, setConfig] = useState("{}");
  const [result, setResult] = useState<any>(null);

  const runMutation = useMutation({
    mutationFn: () => apiFetch<any>("/evaluators/run", {
      method: "POST",
      body: JSON.stringify({
        evaluator: selected,
        config: JSON.parse(config || "{}"),
        user_input: userInput,
        system_prompt: systemPrompt,
        expected,
      }),
    }),
    onSuccess: setResult,
  });

  const meta = evaluators.find((e) => e.name === selected);

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2">
        <FlaskConical className="w-4 h-4 text-brand-500" />
        <h2 className="font-semibold">Playground</h2>
      </div>

      <div className="p-5 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Evaluator</label>
            <select value={selected} onChange={(e) => setSelected(e.target.value)}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2">
              {Object.entries(CATEGORIES).map(([cat, names]) => (
                <optgroup key={cat} label={cat}>
                  {names.map((n) => <option key={n} value={n}>{n}</option>)}
                </optgroup>
              ))}
            </select>
            {meta && <p className="text-xs text-gray-400 mt-1">{meta.description}</p>}
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Config (JSON)</label>
            <textarea value={config} onChange={(e) => setConfig(e.target.value)} rows={3}
              className="w-full text-xs font-mono border border-gray-200 rounded-lg px-3 py-2 resize-none" />
          </div>
        </div>

        <div>
          <label className="text-xs font-medium text-gray-600 mb-1 block">Input</label>
          <textarea value={userInput} onChange={(e) => setUserInput(e.target.value)} rows={2}
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none" />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 mb-1 block">System context (optional)</label>
          <textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} rows={2}
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none" />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 mb-1 block">Expected output</label>
          <input value={expected} onChange={(e) => setExpected(e.target.value)}
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
        </div>

        <button onClick={() => runMutation.mutate()} disabled={runMutation.isPending}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg">
          {runMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          Run
        </button>

        {runMutation.isError && (
          <div className="text-xs text-red-600 bg-red-50 rounded-lg p-3">{(runMutation.error as Error).message}</div>
        )}

        {result && (
          <div className={clsx("rounded-xl border p-4",
            result.passed === true ? "bg-green-50 border-green-200"
            : result.passed === false ? "bg-red-50 border-red-200"
            : "bg-gray-50 border-gray-200")}>
            <div className="flex items-center gap-2 mb-2">
              {verdictIcon(result.passed)}
              <span className="font-medium text-sm">
                {result.passed === true ? "Passed" : result.passed === false ? "Failed" : "Scored"}
              </span>
              <span className="ml-auto text-xs text-gray-400">{result.runtime_ms?.toFixed(0)}ms</span>
            </div>
            <div className="text-sm mb-1">
              <span className="text-gray-500">Score: </span>
              <code className="font-mono font-semibold text-brand-700">{String(result.value)}</code>
            </div>
            <p className="text-xs text-gray-500">{result.reason}</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Experiment Builder ────────────────────────────────────────────────────────

interface EvalRow { name: string; config: string }

function ExperimentBuilder() {
  const [name, setName] = useState("Voice eval experiment");
  const [evals, setEvals] = useState<EvalRow[]>([
    { name: "rouge_score", config: "{}" },
    { name: "contains_any", config: '{"keywords": ["balance","account"]}' },
  ]);
  const [dataset, setDataset] = useState(JSON.stringify([
    { output: "Your account balance is 5000 rupees.", expected: "The balance is 5000 INR." },
    { output: "I cannot help with that request.", expected: "The balance is 5000 INR." },
  ], null, 2));
  const [result, setResult] = useState<any>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const runMutation = useMutation({
    mutationFn: () => apiFetch<any>("/evaluators/experiment", {
      method: "POST",
      body: JSON.stringify({
        name,
        evaluators: evals.map((e) => ({ name: e.name, config: JSON.parse(e.config || "{}") })),
        dataset: JSON.parse(dataset),
      }),
    }),
    onSuccess: setResult,
  });

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2">
        <BarChart3 className="w-4 h-4 text-brand-500" />
        <h2 className="font-semibold">Experiment</h2>
        <span className="text-xs text-gray-400">Run multiple evaluators over a dataset</span>
      </div>
      <div className="p-5 space-y-4">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Experiment name"
          className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />

        {/* Evaluators */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-medium text-gray-600">Evaluators</label>
            <button onClick={() => setEvals([...evals, { name: "f1_score", config: "{}" }])}
              className="flex items-center gap-1 text-xs text-brand-600 hover:underline">
              <Plus className="w-3 h-3" /> Add
            </button>
          </div>
          <div className="space-y-2">
            {evals.map((ev, i) => (
              <div key={i} className="flex gap-2">
                <select value={ev.name} onChange={(e) => setEvals(evals.map((r, j) => j === i ? {...r, name: e.target.value} : r))}
                  className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 flex-1">
                  {Object.values(CATEGORIES).flat().map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
                <input value={ev.config} onChange={(e) => setEvals(evals.map((r, j) => j === i ? {...r, config: e.target.value} : r))}
                  placeholder="{}" className="text-xs font-mono border border-gray-200 rounded-lg px-2 py-1.5 w-48" />
                <button onClick={() => setEvals(evals.filter((_, j) => j !== i))}
                  className="text-gray-400 hover:text-red-500"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            ))}
          </div>
        </div>

        {/* Dataset */}
        <div>
          <label className="text-xs font-medium text-gray-600 mb-1 block">Dataset (JSON array)</label>
          <textarea value={dataset} onChange={(e) => setDataset(e.target.value)} rows={6}
            className="w-full text-xs font-mono border border-gray-200 rounded-lg px-3 py-2 resize-none" />
        </div>

        <button onClick={() => runMutation.mutate()} disabled={runMutation.isPending}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg">
          {runMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          Run Experiment
        </button>

        {result && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500">Experiment <code className="font-mono">{result.id}</code> — {result.dataset_size} rows, {result.duration_ms}ms</p>
            {Object.entries(result.results as Record<string, any>).map(([evalName, data]: [string, any]) => (
              <div key={evalName} className="border border-gray-200 rounded-xl overflow-hidden">
                <button className="w-full flex items-center px-4 py-3 bg-gray-50 hover:bg-gray-100 text-sm"
                  onClick={() => setExpanded((p) => ({...p, [evalName]: !p[evalName]}))}>
                  <span className="font-medium">{evalName}</span>
                  {data.error
                    ? <span className="ml-2 text-red-500 text-xs">{data.error}</span>
                    : <>
                        <span className="ml-3 text-green-600 text-xs font-medium">{data.passed}/{data.total} passed</span>
                        {data.avg_value !== null && <span className="ml-2 text-gray-500 text-xs">avg: {data.avg_value}</span>}
                      </>
                  }
                  {expanded[evalName] ? <ChevronUp className="w-4 h-4 ml-auto" /> : <ChevronDown className="w-4 h-4 ml-auto" />}
                </button>
                {expanded[evalName] && !data.error && (
                  <div className="divide-y divide-gray-100">
                    {(data.rows as EvalResult[]).map((row, i) => (
                      <div key={i} className="flex items-center gap-3 px-4 py-2 text-xs">
                        {verdictIcon(row.passed)}
                        <code className="font-mono text-brand-700">{String(row.value)}</code>
                        <span className="text-gray-400 truncate flex-1">{row.reason}</span>
                        <span className="text-gray-300">{row.runtime_ms.toFixed(0)}ms</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Audio Test ────────────────────────────────────────────────────────────────

interface TranscriptTurn { role: string; text: string }

function AudioTestTab({ evaluators }: { evaluators: EvaluatorMeta[] }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [lang, setLang] = useState("en-IN");
  const [transcript, setTranscript] = useState<TranscriptTurn[]>([]);
  const [expected, setExpected] = useState("");
  const [selectedEvals, setSelectedEvals] = useState<string[]>(["word_error_rate", "contains_any"]);
  const [evalConfig, setEvalConfig] = useState<Record<string, string>>({ contains_any: '{"keywords":["balance","account","sorry"]}' });
  const [scores, setScores] = useState<Record<string, any>>({});

  const transcribeMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Select a file");
      const fd = new FormData();
      fd.append("audio_file", file);
      fd.append("language", lang);
      const res = await fetch("/api/proxy/ingest/transcribe", { method: "POST", body: fd });
      const ct = res.headers.get("content-type") ?? "";
      if (!ct.includes("json")) throw new Error(await res.text());
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail ?? "Transcription failed");
      return d as { transcript: TranscriptTurn[]; turns: number };
    },
    onSuccess: (d) => setTranscript(d.transcript),
  });

  const evaluateMutation = useMutation({
    mutationFn: async () => {
      const agentText = transcript.filter((t) => t.role === "agent").map((t) => t.text).join(" ");
      const userText = transcript.filter((t) => t.role === "user").map((t) => t.text).join(" ");
      const fullText = transcript.map((t) => `${t.role.toUpperCase()}: ${t.text}`).join("\n");

      const results: Record<string, any> = {};
      for (const evalName of selectedEvals) {
        try {
          const config = evalConfig[evalName] ? JSON.parse(evalConfig[evalName]) : {};
          const inputs: Record<string, string> = { output: agentText };
          if (expected) inputs["expected"] = expected;
          if (evalName === "word_error_rate" || evalName === "character_error_rate") {
            inputs["output"] = agentText;
            inputs["expected"] = expected || agentText;
          }
          const r = await apiFetch<any>("/evaluators/run", {
            method: "POST",
            body: JSON.stringify({ evaluator: evalName, inputs, config }),
          });
          results[evalName] = r;
        } catch (e) {
          results[evalName] = { error: String(e) };
        }
      }
      return results;
    },
    onSuccess: setScores,
  });

  const toggleEval = (name: string) =>
    setSelectedEvals((prev) => prev.includes(name) ? prev.filter((e) => e !== name) : [...prev, name]);

  return (
    <div className="space-y-5">
      {/* Step 1: Upload */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-full bg-brand-600 text-white text-xs flex items-center justify-center font-bold flex-shrink-0">1</div>
          <h3 className="font-medium text-sm">Upload call recording</h3>
        </div>
        <button onClick={() => fileRef.current?.click()}
          className={`w-full border-2 border-dashed rounded-xl p-6 text-center transition-colors ${file ? "border-brand-400 bg-brand-50" : "border-gray-200 bg-gray-50 hover:border-gray-300"}`}>
          <FileAudio className={`w-7 h-7 mx-auto mb-2 ${file ? "text-brand-500" : "text-gray-300"}`} />
          {file
            ? <p className="text-sm font-medium text-brand-700">{file.name} — {(file.size / 1024).toFixed(1)} KB</p>
            : <p className="text-sm text-gray-500">Click to select call recording (WAV · MP3 · OGG · FLAC · M4A)</p>}
        </button>
        <input ref={fileRef} type="file" accept=".wav,.mp3,.ogg,.flac,.m4a" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFile(f); setTranscript([]); setScores({}); } }} />
        <div className="flex gap-3">
          <select value={lang} onChange={(e) => setLang(e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-3 py-2">
            {[["en-IN","English (Indian)"],["hi","Hindi"],["te","Telugu"],["ta","Tamil"],["or","Odia"],["kn","Kannada"],["ml","Malayalam"],["mr","Marathi"],["bn","Bengali"]].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <button onClick={() => transcribeMutation.mutate()} disabled={!file || transcribeMutation.isPending}
            className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg">
            {transcribeMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mic className="w-4 h-4" />}
            Transcribe
          </button>
        </div>
        {transcribeMutation.isError && <p className="text-xs text-red-600">{(transcribeMutation.error as Error).message}</p>}
      </div>

      {/* Step 2: Transcript */}
      {transcript.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded-full bg-brand-600 text-white text-xs flex items-center justify-center font-bold flex-shrink-0">2</div>
            <h3 className="font-medium text-sm">Transcript ({transcript.length} turns)</h3>
          </div>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {transcript.map((t, i) => (
              <div key={i} className={`flex gap-3 text-sm ${t.role === "agent" ? "justify-start" : "justify-end"}`}>
                <div className={`rounded-xl px-3 py-2 max-w-xs ${t.role === "agent" ? "bg-gray-100 text-gray-800" : "bg-brand-600 text-white"}`}>
                  <p className="text-xs opacity-60 mb-0.5 capitalize">{t.role}</p>
                  <p>{t.text}</p>
                </div>
              </div>
            ))}
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Expected transcript (for WER/CER comparison)</label>
            <textarea value={expected} onChange={(e) => setExpected(e.target.value)} rows={2} placeholder="Paste expected agent responses here…"
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none" />
          </div>
        </div>
      )}

      {/* Step 3: Evaluators */}
      {transcript.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded-full bg-brand-600 text-white text-xs flex items-center justify-center font-bold flex-shrink-0">3</div>
            <h3 className="font-medium text-sm">Select evaluators</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            {["word_error_rate","character_error_rate","rouge_score","f1_score","contains_any","contains_none","is_refusal","regex_pii_detection","levenshtein_similarity"].map((name) => (
              <button key={name} onClick={() => toggleEval(name)}
                className={clsx("text-xs px-3 py-1.5 rounded-full border transition-colors font-medium",
                  selectedEvals.includes(name) ? "bg-brand-600 text-white border-brand-600" : "border-gray-200 text-gray-600 hover:border-brand-300")}>
                {name}
              </button>
            ))}
          </div>
          {selectedEvals.filter(n => ["contains_any","contains_none","regex"].includes(n.split("_")[0])).map((name) => (
            <div key={name}>
              <label className="text-xs font-medium text-gray-600 mb-1 block">{name} config (JSON)</label>
              <input value={evalConfig[name] ?? "{}"} onChange={(e) => setEvalConfig({ ...evalConfig, [name]: e.target.value })}
                className="w-full text-xs font-mono border border-gray-200 rounded-lg px-3 py-2" />
            </div>
          ))}
          <button onClick={() => evaluateMutation.mutate()} disabled={selectedEvals.length === 0 || evaluateMutation.isPending}
            className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2.5 rounded-lg">
            {evaluateMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            Run evaluators
          </button>
        </div>
      )}

      {/* Step 4: Scores */}
      {Object.keys(scores).length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded-full bg-green-600 text-white text-xs flex items-center justify-center font-bold flex-shrink-0">✓</div>
            <h3 className="font-medium text-sm">Results</h3>
          </div>
          {Object.entries(scores).map(([name, result]: [string, any]) => (
            <div key={name} className={clsx("rounded-xl border p-3",
              result.error ? "bg-red-50 border-red-200"
              : result.passed === true ? "bg-green-50 border-green-200"
              : result.passed === false ? "bg-red-50 border-red-200"
              : "bg-gray-50 border-gray-200")}>
              <div className="flex items-center gap-2">
                {result.error ? <XCircle className="w-4 h-4 text-red-500" />
                : result.passed === true ? <CheckCircle className="w-4 h-4 text-green-500" />
                : result.passed === false ? <XCircle className="w-4 h-4 text-red-500" />
                : <AlertCircle className="w-4 h-4 text-gray-400" />}
                <span className="font-mono text-xs text-gray-600">{name}</span>
                {!result.error && (
                  <code className="ml-auto font-semibold text-sm text-brand-700">{String(result.value)}</code>
                )}
              </div>
              <p className="text-xs text-gray-500 mt-1 ml-6">{result.error ?? result.reason}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function EvaluatorsPage() {
  const { data: evaluators = [] } = useQuery({
    queryKey: ["evaluators"],
    queryFn: () => apiFetch<EvaluatorMeta[]>("/evaluators"),
  });

  const [activeTab, setActiveTab] = useState<"audio" | "playground" | "experiment" | "library">("audio");

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold">Eval Studio</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          {evaluators.length} evaluators — heuristic, similarity, audio, agent, retrieval, safety
        </p>
      </div>

      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 w-fit">
        {([
          { id: "audio", label: "Audio Test" },
          { id: "playground", label: "Playground" },
          { id: "experiment", label: "Experiment" },
          { id: "library", label: "Library" },
        ] as const).map(({ id, label }) => (
          <button key={id} onClick={() => setActiveTab(id)}
            className={clsx("px-4 py-1.5 text-sm font-medium rounded-lg", activeTab === id ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700")}>
            {label}
          </button>
        ))}
      </div>

      {activeTab === "audio" && <AudioTestTab evaluators={evaluators} />}
      {activeTab === "playground" && <EvalPlayground evaluators={evaluators} />}
      {activeTab === "experiment" && <ExperimentBuilder />}
      {activeTab === "library" && (
        <div className="space-y-4">
          {Object.entries(CATEGORIES).map(([cat, names]) => (
            <div key={cat} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-5 py-3 border-b border-gray-100 bg-gray-50">
                <h3 className="font-semibold text-sm">{cat}</h3>
              </div>
              <div className="divide-y divide-gray-50">
                {names.map((n) => {
                  const meta = evaluators.find((e) => e.name === n);
                  return (
                    <div key={n} className="px-5 py-3 flex items-start gap-4">
                      <code className="text-xs font-mono text-brand-600 bg-brand-50 px-2 py-0.5 rounded w-48 flex-shrink-0">{n}</code>
                      <p className="text-xs text-gray-500">{meta?.description || "—"}</p>
                      {meta?.required_keys && meta.required_keys.length > 0 && (
                        <div className="ml-auto flex gap-1 flex-shrink-0">
                          {meta.required_keys.map((k) => (
                            <span key={k} className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">{k}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
