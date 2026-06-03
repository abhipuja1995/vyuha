"use client";

import { useQuery, useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch } from "@/lib/api";
import {
  FlaskConical, Play, ChevronDown, ChevronUp, Plus, Trash2,
  CheckCircle, XCircle, AlertCircle, Loader2, BarChart3,
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
  const [inputs, setInputs] = useState('{\n  "output": "Your account balance is 5000 rupees",\n  "expected": "The balance is 5000"\n}');
  const [config, setConfig] = useState("{}");
  const [result, setResult] = useState<EvalResult | null>(null);

  const runMutation = useMutation({
    mutationFn: () => apiFetch<EvalResult>("/evaluators/run", {
      method: "POST",
      body: JSON.stringify({ evaluator: selected, inputs: JSON.parse(inputs), config: JSON.parse(config) }),
    }),
    onSuccess: setResult,
  });

  const meta = evaluators.find((e) => e.name === selected);

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center gap-2">
        <FlaskConical className="w-4 h-4 text-brand-500" />
        <h2 className="font-semibold">Evaluator Playground</h2>
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
            {meta && <p className="text-xs text-gray-400">Required: <code>{meta.required_keys.join(", ")}</code></p>}
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Config (JSON)</label>
            <textarea value={config} onChange={(e) => setConfig(e.target.value)} rows={3}
              className="w-full text-xs font-mono border border-gray-200 rounded-lg px-3 py-2 resize-none" />
          </div>
        </div>

        <div>
          <label className="text-xs font-medium text-gray-600 mb-1 block">Inputs (JSON)</label>
          <textarea value={inputs} onChange={(e) => setInputs(e.target.value)} rows={5}
            className="w-full text-sm font-mono border border-gray-200 rounded-lg px-3 py-2 resize-none" />
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
          <div className={clsx("rounded-xl border p-4", result.passed === true ? "bg-green-50 border-green-200" : result.passed === false ? "bg-red-50 border-red-200" : "bg-gray-50 border-gray-200")}>
            <div className="flex items-center gap-2 mb-2">
              {verdictIcon(result.passed)}
              <span className="font-medium text-sm">{result.passed === true ? "Passed" : result.passed === false ? "Failed" : "No threshold"}</span>
              <span className="ml-auto text-xs text-gray-400">{result.runtime_ms.toFixed(1)}ms</span>
            </div>
            <div className="flex gap-4 text-sm">
              <div><span className="text-gray-500">Value: </span><code className="font-mono text-brand-700">{String(result.value)}</code></div>
            </div>
            <p className="text-xs text-gray-600 mt-1">{result.reason}</p>
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

// ── Page ──────────────────────────────────────────────────────────────────────

export default function EvaluatorsPage() {
  const { data: evaluators = [] } = useQuery({
    queryKey: ["evaluators"],
    queryFn: () => apiFetch<EvaluatorMeta[]>("/evaluators"),
  });

  const [activeTab, setActiveTab] = useState<"playground" | "experiment" | "library">("playground");

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold">Evaluators</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          {evaluators.length} evaluators — heuristic, similarity, audio, agent, retrieval, safety
        </p>
      </div>

      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 w-fit">
        {(["playground", "experiment", "library"] as const).map((t) => (
          <button key={t} onClick={() => setActiveTab(t)}
            className={clsx("px-4 py-1.5 text-sm font-medium rounded-lg capitalize", activeTab === t ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700")}>
            {t}
          </button>
        ))}
      </div>

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
