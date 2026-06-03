"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useRef } from "react";
import { api, TestCase, TestCategory, Language, apiFetch } from "@/lib/api";
import { Plus, Play, Trash2, ChevronRight, Wand2, Download, GitBranch, X, Loader2, CheckCircle } from "lucide-react";
import Link from "next/link";
import { clsx } from "clsx";

const CATEGORY_CLASSES: Record<TestCategory, string> = {
  HAPPY_PATH: "badge-happy",
  EDGE_CASE: "badge-edge",
  FAILURE_MODE: "badge-failure",
  CRITICAL: "badge-critical",
  REGRESSION: "badge-regression",
};

const LANGUAGE_NAMES: Record<string, string> = {
  "te": "Telugu", "ta": "Tamil", "hi": "Hindi", "or": "Odia",
  "kn": "Kannada", "ml": "Malayalam", "mr": "Marathi", "bn": "Bengali",
  "en-IN": "English (Indian)", "en": "English",
};

// ── Unified Create Panel ──────────────────────────────────────────────────────
type CreateMethod = "generate" | "ingest" | "workflow" | null;

function CreatePanel({ onClose, qc }: { onClose: () => void; qc: ReturnType<typeof useQueryClient> }) {
  const [method, setMethod] = useState<CreateMethod>(null);

  const methods = [
    { id: "generate" as const, icon: Wand2, label: "Generate from Prompt", desc: "Paste your agent's system prompt — best available LLM auto-creates test scenarios" },
    { id: "ingest" as const, icon: Download, label: "From Production Call", desc: "Upload a failed call recording or transcript — auto-converts to regression test" },
    { id: "workflow" as const, icon: GitBranch, label: "Import Workflow File", desc: "Upload JSON/YAML — supports Vyuha, FutureAGI, and compact formats" },
  ];

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-start justify-end">
      <div className="bg-white h-full w-full max-w-lg shadow-2xl overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 sticky top-0 bg-white z-10">
          <h2 className="font-semibold">Add Test Cases</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700"><X className="w-5 h-5" /></button>
        </div>

        {!method ? (
          <div className="p-5 space-y-3">
            <Link href="/test-cases/new" onClick={onClose}
              className="flex items-start gap-4 p-4 rounded-xl border border-gray-200 hover:border-brand-400 hover:bg-brand-50 transition-colors">
              <div className="w-8 h-8 rounded-lg bg-brand-100 flex items-center justify-center flex-shrink-0">
                <Plus className="w-4 h-4 text-brand-600" />
              </div>
              <div>
                <p className="font-medium text-sm">Create manually</p>
                <p className="text-xs text-gray-500 mt-0.5">Define persona, conversation graph, and pass criteria by hand</p>
              </div>
            </Link>
            {methods.map(({ id, icon: Icon, label, desc }) => (
              <button key={id} onClick={() => setMethod(id)}
                className="w-full flex items-start gap-4 p-4 rounded-xl border border-gray-200 hover:border-brand-400 hover:bg-brand-50 transition-colors text-left">
                <div className="w-8 h-8 rounded-lg bg-brand-100 flex items-center justify-center flex-shrink-0">
                  <Icon className="w-4 h-4 text-brand-600" />
                </div>
                <div>
                  <p className="font-medium text-sm">{label}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{desc}</p>
                </div>
              </button>
            ))}
          </div>
        ) : method === "generate" ? (
          <GenerateForm onClose={onClose} qc={qc} />
        ) : method === "ingest" ? (
          <IngestForm onClose={onClose} qc={qc} />
        ) : (
          <WorkflowForm onClose={onClose} qc={qc} />
        )}
      </div>
    </div>
  );
}

// ── Generate sub-form ─────────────────────────────────────────────────────────
function GenerateForm({ onClose, qc }: { onClose: () => void; qc: ReturnType<typeof useQueryClient> }) {
  const [form, setForm] = useState({ system_prompt: "", knowledge_base: "", use_cases: "", language: "en-IN", count: 50 });
  const [done, setDone] = useState<number | null>(null);

  const mutation = useMutation({
    mutationFn: () => api.generate.fromPrompt(form as any),
    onSuccess: (data) => { setDone(data.length); qc.invalidateQueries({ queryKey: ["test-cases"] }); },
  });

  return (
    <div className="p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Wand2 className="w-4 h-4 text-brand-500" />
        <span className="font-medium text-sm">Generate from Prompt</span>
      </div>
      {done !== null ? (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4">
          <div className="flex items-center gap-2 text-green-700 font-medium">
            <CheckCircle className="w-4 h-4" /> {done} test cases generated
          </div>
          <button onClick={onClose} className="mt-3 text-sm text-brand-600 hover:underline">Close panel</button>
        </div>
      ) : (
        <>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">System Prompt *</label>
            <textarea value={form.system_prompt} onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
              rows={8} placeholder="Paste your agent's system prompt (min 100 chars)…"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none font-mono" />
            <p className="text-xs text-gray-400 mt-0.5">{form.system_prompt.length} chars</p>
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">Use Cases</label>
            <input value={form.use_cases} onChange={(e) => setForm({ ...form, use_cases: e.target.value })}
              placeholder="e.g. balance inquiry, debt collection…"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Language</label>
              <select value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })}
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2">
                {[["en-IN","English (Indian)"],["hi","Hindi"],["te","Telugu"],["ta","Tamil"],["or","Odia"],["kn","Kannada"],["ml","Malayalam"],["mr","Marathi"],["bn","Bengali"]].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Count</label>
              <input type="number" min={5} max={100} value={form.count} onChange={(e) => setForm({ ...form, count: Number(e.target.value) })}
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
            </div>
          </div>
          <button onClick={() => mutation.mutate()} disabled={form.system_prompt.length < 100 || mutation.isPending}
            className="w-full flex items-center justify-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium py-2.5 rounded-lg">
            {mutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
            {mutation.isPending ? `Generating ${form.count} scenarios…` : `Generate ${form.count} test cases`}
          </button>
          {mutation.isError && <p className="text-xs text-red-600">{(mutation.error as Error).message}</p>}
        </>
      )}
    </div>
  );
}

// ── Ingest sub-form ───────────────────────────────────────────────────────────
function IngestForm({ onClose, qc }: { onClose: () => void; qc: ReturnType<typeof useQueryClient> }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [lang, setLang] = useState("en-IN");
  const [preview, setPreview] = useState<any>(null);
  const [savedId, setSavedId] = useState<string | null>(null);

  const previewMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Select a file");
      const fd = new FormData();
      fd.append("audio_file", file);
      fd.append("language_detected", lang);
      fd.append("auto_transcribe", "true");
      const res = await fetch("/api/proxy/ingest/upload/preview", { method: "POST", body: fd });
      const ct = res.headers.get("content-type") ?? "";
      if (!ct.includes("json")) throw new Error(await res.text());
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail ?? "Failed");
      return d;
    },
    onSuccess: setPreview,
  });

  const saveMutation = useMutation({
    mutationFn: () => apiFetch<any>("/test-cases/", { method: "POST", body: JSON.stringify(preview.test_case) }),
    onSuccess: (tc) => { setSavedId(tc.test_id); qc.invalidateQueries({ queryKey: ["test-cases"] }); },
  });

  return (
    <div className="p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Download className="w-4 h-4 text-brand-500" />
        <span className="font-medium text-sm">From Production Call</span>
      </div>

      {savedId ? (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4">
          <div className="flex items-center gap-2 text-green-700 font-medium text-sm">
            <CheckCircle className="w-4 h-4" /> Saved — <Link href={`/test-cases/${savedId}`} className="underline">view test case</Link>
          </div>
        </div>
      ) : preview?.ingested && preview.test_case ? (
        <div className="space-y-3">
          <div className="bg-brand-50 border border-brand-200 rounded-xl p-4 text-sm">
            <p className="font-medium">{preview.test_case.title}</p>
            <p className="text-xs text-gray-500 mt-1">{preview.test_case.persona_config?.language} · {preview.test_case.category}</p>
            <p className="text-xs text-gray-500 mt-0.5">{preview.test_case.pass_criteria?.slice(0, 120)}</p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}
              className="flex items-center gap-2 bg-brand-600 text-white text-sm px-4 py-2 rounded-lg disabled:opacity-50">
              {saveMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
              Save test case
            </button>
            <button onClick={() => setPreview(null)} className="text-sm border border-gray-200 px-4 py-2 rounded-lg">Discard</button>
          </div>
        </div>
      ) : (
        <>
          <button onClick={() => fileRef.current?.click()}
            className={`w-full border-2 border-dashed rounded-xl p-6 text-center ${file ? "border-brand-400 bg-brand-50" : "border-gray-200 bg-gray-50"}`}>
            {file ? <p className="text-sm font-medium text-brand-700">{file.name}</p> : <p className="text-sm text-gray-500">Click to select call recording (WAV/MP3/OGG…)</p>}
          </button>
          <input ref={fileRef} type="file" accept=".wav,.mp3,.ogg,.flac,.m4a,.aac,.webm" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) setFile(f); }} />
          <select value={lang} onChange={(e) => setLang(e.target.value)}
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2">
            {[["en-IN","English (Indian)"],["hi","Hindi"],["te","Telugu"],["ta","Tamil"],["or","Odia"],["kn","Kannada"],["ml","Malayalam"],["mr","Marathi"],["bn","Bengali"]].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <button onClick={() => previewMutation.mutate()} disabled={!file || previewMutation.isPending}
            className="w-full flex items-center justify-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium py-2.5 rounded-lg">
            {previewMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            {previewMutation.isPending ? "Processing…" : "Preview & import"}
          </button>
          {previewMutation.isError && <p className="text-xs text-red-600">{(previewMutation.error as Error).message}</p>}
          {preview && !preview.ingested && <p className="text-xs text-amber-600">{preview.reason}</p>}
        </>
      )}
    </div>
  );
}

// ── Workflow sub-form ─────────────────────────────────────────────────────────
function WorkflowForm({ onClose, qc }: { onClose: () => void; qc: ReturnType<typeof useQueryClient> }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<any>(null);
  const [savedId, setSavedId] = useState<string | null>(null);

  const previewMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Select a file");
      const fd = new FormData();
      fd.append("file", file);
      fd.append("save", "false");
      const res = await fetch("/api/proxy/workflows/import", { method: "POST", body: fd });
      const ct = res.headers.get("content-type") ?? "";
      if (!ct.includes("json")) throw new Error(await res.text());
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail ?? "Failed");
      return d;
    },
    onSuccess: setPreview,
  });

  const saveMutation = useMutation({
    mutationFn: () => apiFetch<any>("/test-cases/", { method: "POST", body: JSON.stringify(preview.test_case) }),
    onSuccess: (tc) => { setSavedId(tc.test_id); qc.invalidateQueries({ queryKey: ["test-cases"] }); },
  });

  return (
    <div className="p-5 space-y-4">
      <div className="flex items-center gap-2">
        <GitBranch className="w-4 h-4 text-brand-500" />
        <span className="font-medium text-sm">Import Workflow File</span>
        <a href="/api/proxy/workflows/template" target="_blank" className="ml-auto text-xs text-brand-600 hover:underline">template ↗</a>
      </div>

      {savedId ? (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-sm">
          <CheckCircle className="w-4 h-4 text-green-600 inline mr-1.5" />
          Saved — <Link href={`/test-cases/${savedId}`} className="text-brand-600 underline">view test case</Link>
        </div>
      ) : preview?.test_case ? (
        <div className="space-y-3">
          <div className="text-xs text-gray-400">Format: <code>{preview.format_detected}</code></div>
          <div className="bg-brand-50 border border-brand-200 rounded-xl p-4 text-sm">
            <p className="font-medium">{preview.test_case.title}</p>
            <p className="text-xs text-gray-500 mt-1">{preview.test_case.category} · {preview.test_case.persona_config?.language}</p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}
              className="flex items-center gap-2 bg-brand-600 text-white text-sm px-4 py-2 rounded-lg disabled:opacity-50">
              {saveMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
              Save test case
            </button>
            <button onClick={() => setPreview(null)} className="text-sm border border-gray-200 px-4 py-2 rounded-lg">Discard</button>
          </div>
        </div>
      ) : (
        <>
          <button onClick={() => fileRef.current?.click()}
            className={`w-full border-2 border-dashed rounded-xl p-6 text-center ${file ? "border-brand-400 bg-brand-50" : "border-gray-200 bg-gray-50"}`}>
            {file ? <p className="text-sm font-medium text-brand-700">{file.name}</p> : <p className="text-sm text-gray-500">Click to select JSON or YAML workflow file</p>}
          </button>
          <input ref={fileRef} type="file" accept=".json,.yaml,.yml" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) setFile(f); }} />
          <button onClick={() => previewMutation.mutate()} disabled={!file || previewMutation.isPending}
            className="w-full flex items-center justify-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium py-2.5 rounded-lg">
            {previewMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitBranch className="w-4 h-4" />}
            Preview & import
          </button>
          {previewMutation.isError && <p className="text-xs text-red-600">{(previewMutation.error as Error).message}</p>}
        </>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function TestCasesPage() {
  const qc = useQueryClient();
  const [categoryFilter, setCategoryFilter] = useState<TestCategory | "">("");
  const [langFilter, setLangFilter] = useState<Language | "">("");
  const [showCreate, setShowCreate] = useState(false);;

  const { data: cases = [], isLoading } = useQuery({
    queryKey: ["test-cases", categoryFilter, langFilter],
    queryFn: () => api.testCases.list({
      ...(categoryFilter ? { category: categoryFilter } : {}),
      ...(langFilter ? { language: langFilter } : {}),
    }),
  });

  const runMutation = useMutation({
    mutationFn: (testId: string) => api.runs.start({ test_id: testId, k: 3 }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["summary"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: api.testCases.delete,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["test-cases"] }),
  });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Test Cases</h1>
          <p className="text-sm text-gray-500 mt-0.5">{cases.length} cases in library</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4" /> Add Test Cases
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value as TestCategory | "")}
          className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white"
        >
          <option value="">All categories</option>
          {(["HAPPY_PATH", "EDGE_CASE", "FAILURE_MODE", "CRITICAL", "REGRESSION"] as TestCategory[]).map((c) => (
            <option key={c} value={c}>{c.replace("_", " ")}</option>
          ))}
        </select>
        <select
          value={langFilter}
          onChange={(e) => setLangFilter(e.target.value as Language | "")}
          className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white"
        >
          <option value="">All languages</option>
          {Object.entries(LANGUAGE_NAMES).map(([code, name]) => (
            <option key={code} value={code}>{name}</option>
          ))}
        </select>
      </div>

      {isLoading && <p className="text-gray-400 text-sm">Loading...</p>}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {cases.length === 0 && !isLoading ? (
          <div className="p-10 text-center text-gray-400">
            <p className="font-medium">No test cases found.</p>
            <p className="text-sm mt-1">Generate from an agent prompt or create manually.</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600 w-10">#</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Title</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Category</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Language</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Noise</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Tags</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {cases.map((tc, i) => (
                <tr key={tc.test_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-gray-400 font-mono text-xs">{i + 1}</td>
                  <td className="px-4 py-3">
                    <Link href={`/test-cases/${tc.test_id}`} className="font-medium text-brand-600 hover:underline">
                      {tc.title}
                    </Link>
                    <p className="text-xs text-gray-400 mt-0.5 truncate max-w-xs">{tc.user_goal}</p>
                  </td>
                  <td className="px-4 py-3">
                    <span className={CATEGORY_CLASSES[tc.category]}>{tc.category.replace("_", " ")}</span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{LANGUAGE_NAMES[tc.persona_config.language] ?? tc.persona_config.language}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{tc.persona_config.noise_profile.replace("_", " ")}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {tc.tags.slice(0, 3).map((tag) => (
                        <span key={tag} className="bg-gray-100 text-gray-600 text-xs px-1.5 py-0.5 rounded">{tag}</span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 justify-end">
                      <button
                        onClick={() => runMutation.mutate(tc.test_id)}
                        disabled={runMutation.isPending}
                        title="Run (k=3)"
                        className="p-1.5 text-gray-400 hover:text-brand-600 hover:bg-brand-50 rounded transition-colors"
                      >
                        <Play className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => { if (confirm("Delete this test case?")) deleteMutation.mutate(tc.test_id); }}
                        title="Delete"
                        className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                      <Link href={`/test-cases/${tc.test_id}`} className="p-1.5 text-gray-400 hover:text-gray-700 rounded transition-colors">
                        <ChevronRight className="w-4 h-4" />
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {showCreate && <CreatePanel onClose={() => setShowCreate(false)} qc={qc} />}
    </div>
  );
}
