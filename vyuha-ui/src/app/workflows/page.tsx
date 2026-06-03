"use client";

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import {
  Upload, FileJson, Download, CheckCircle, AlertTriangle,
  ChevronDown, ChevronUp, Eye, Save, Trash2, Loader2, Plus, Copy,
} from "lucide-react";
import Link from "next/link";

// ── Types ─────────────────────────────────────────────────────────────────────
interface ImportResult {
  imported: boolean;
  test_case_id: string;
  format_detected: string;
  test_case: Record<string, any>;
}
interface BulkResult {
  total: number;
  imported: number;
  errors: number;
  results: Array<{ status: string; test_case_id?: string; title?: string; file?: string; error?: string }>;
}

// ── Template Download ─────────────────────────────────────────────────────────

function TemplateCard() {
  const [copied, setCopied] = useState(false);
  const { data: template, isLoading } = { data: null as any, isLoading: false };

  const fetchTemplate = async () => {
    const t = await apiFetch<any>("/workflows/template");
    const text = JSON.stringify(t, null, 2);
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-medium text-blue-800 text-sm">Workflow template</h3>
          <p className="text-xs text-blue-600 mt-0.5">Copy a starter JSON template, edit it, then upload.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={fetchTemplate}
            className="flex items-center gap-1.5 text-xs bg-blue-600 text-white px-3 py-1.5 rounded-lg hover:bg-blue-500">
            {copied ? <CheckCircle className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
            {copied ? "Copied!" : "Copy template"}
          </button>
          <a href="/api/proxy/workflows/schema" target="_blank"
            className="flex items-center gap-1.5 text-xs border border-blue-200 text-blue-700 px-3 py-1.5 rounded-lg hover:bg-blue-100">
            <FileJson className="w-3.5 h-3.5" /> JSON schema
          </a>
        </div>
      </div>
    </div>
  );
}

// ── Test case preview (reused from ingest) ─────────────────────────────────────

function PreviewPanel({ tc, onSave, onDiscard, saving }: {
  tc: Record<string, any>;
  onSave: () => void;
  onDiscard: () => void;
  saving: boolean;
}) {
  const [showGraph, setShowGraph] = useState(false);
  const CATEGORY_COLORS: Record<string, string> = {
    CRITICAL: "bg-purple-100 text-purple-800",
    HAPPY_PATH: "bg-green-100 text-green-800",
    EDGE_CASE: "bg-yellow-100 text-yellow-800",
    FAILURE_MODE: "bg-red-100 text-red-800",
    REGRESSION: "bg-blue-100 text-blue-800",
  };

  return (
    <div className="border border-brand-300 bg-brand-50 rounded-xl overflow-hidden">
      <div className="bg-brand-600 text-white px-5 py-3 flex items-center gap-2">
        <Eye className="w-4 h-4" />
        <span className="font-semibold text-sm">Preview — workflow converted to test case</span>
      </div>
      <div className="p-5 space-y-4 bg-white">
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${CATEGORY_COLORS[tc.category] ?? "bg-gray-100 text-gray-700"}`}>
            {tc.category?.replace("_", " ")}
          </span>
        </div>
        <h3 className="font-semibold">{tc.title}</h3>
        <p className="text-sm text-gray-600">{tc.user_goal}</p>

        {/* Persona */}
        <div className="grid grid-cols-3 gap-2">
          {[
            ["Language", tc.persona_config?.language],
            ["Noise", tc.persona_config?.noise_profile?.replace("_"," ")],
            ["Emotion", tc.persona_config?.emotion],
          ].map(([l, v]) => (
            <div key={l} className="bg-gray-50 rounded-lg p-2.5">
              <p className="text-xs text-gray-400">{l}</p>
              <p className="text-sm font-medium">{v || "—"}</p>
            </div>
          ))}
        </div>

        {tc.pass_criteria && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
            <p className="text-xs font-medium text-amber-700 mb-0.5">Pass criteria</p>
            <p className="text-sm text-amber-900">{tc.pass_criteria}</p>
          </div>
        )}

        {/* Graph */}
        <button onClick={() => setShowGraph((v) => !v)}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900">
          {showGraph ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          Conversation graph ({tc.conversation_graph?.nodes?.length ?? 0} nodes)
        </button>
        {showGraph && (
          <div className="space-y-2 pl-2">
            {tc.conversation_graph?.nodes?.map((n: any) => (
              <div key={n.node_id} className={`flex gap-3 items-start p-2.5 rounded-lg border text-sm ${
                n.node_id === tc.conversation_graph.start_node ? "border-brand-200 bg-brand-50"
                : n.is_terminal ? "border-green-200 bg-green-50" : "border-gray-200 bg-gray-50"
              }`}>
                <span className="font-mono text-xs opacity-60">{n.node_id}</span>
                <span className="italic text-gray-700">"{n.utterance_template}"</span>
              </div>
            ))}
          </div>
        )}

        {/* Tags */}
        {tc.tags?.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {tc.tags.map((t: string) => <span key={t} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">{t}</span>)}
          </div>
        )}
      </div>
      <div className="px-5 py-3 bg-gray-50 border-t border-gray-200 flex gap-3">
        <button onClick={onSave} disabled={saving}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? "Saving…" : "Save test case"}
        </button>
        <button onClick={onDiscard} className="flex items-center gap-2 text-sm text-gray-600 border border-gray-200 px-3 py-2 rounded-lg hover:text-red-600">
          <Trash2 className="w-4 h-4" /> Discard
        </button>
      </div>
    </div>
  );
}

// ── Single upload ─────────────────────────────────────────────────────────────

function SingleUpload() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [tags, setTags] = useState("");
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);

  const previewMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Select a file");
      const fd = new FormData();
      fd.append("file", file);
      fd.append("save", "false");
      fd.append("tags", tags);
      const res = await fetch("/api/proxy/workflows/import", { method: "POST", body: fd });
      const ct = res.headers.get("content-type") ?? "";
      if (!ct.includes("application/json")) throw new Error(await res.text());
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Import failed");
      return data as ImportResult;
    },
    onSuccess: setPreview,
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!preview?.test_case) throw new Error("No test case");
      return apiFetch<any>("/test-cases/", { method: "POST", body: JSON.stringify(preview.test_case) });
    },
    onSuccess: (tc) => {
      setSavedId(tc.test_id);
      setPreview(null);
      qc.invalidateQueries({ queryKey: ["test-cases"] });
    },
  });

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
        <button type="button" onClick={() => fileRef.current?.click()}
          className={`w-full border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
            file ? "border-brand-400 bg-brand-50" : "border-gray-200 hover:border-gray-300 bg-gray-50"}`}>
          <FileJson className={`w-8 h-8 mx-auto mb-2 ${file ? "text-brand-500" : "text-gray-300"}`} />
          {file ? (
            <div>
              <p className="text-sm font-medium text-brand-700">{file.name}</p>
              <p className="text-xs text-brand-500 mt-0.5">{(file.size / 1024).toFixed(1)} KB · click to change</p>
            </div>
          ) : (
            <div>
              <p className="text-sm font-medium text-gray-600">Click to select a workflow file</p>
              <p className="text-xs text-gray-400 mt-0.5">JSON · YAML · YAML format</p>
              <p className="text-xs text-gray-400">Supports Vyuha native, FutureAGI scenario graph, or compact format</p>
            </div>
          )}
        </button>
        <input ref={fileRef} type="file" accept=".json,.yaml,.yml" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFile(f); setPreview(null); setSavedId(null); } }} />

        <div>
          <label className="text-xs font-medium text-gray-600 mb-1 block">Extra tags (comma-separated)</label>
          <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="e.g. imported, hindi, banking"
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
        </div>

        <button onClick={() => previewMutation.mutate()} disabled={!file || previewMutation.isPending}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2.5 rounded-lg">
          {previewMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Eye className="w-4 h-4" />}
          Preview workflow
        </button>

        {previewMutation.isError && (
          <div className="text-sm text-red-600 bg-red-50 rounded-lg p-3">{(previewMutation.error as Error).message}</div>
        )}
      </div>

      {preview && (
        <div className="space-y-2">
          <p className="text-xs text-gray-500">Format detected: <code className="font-mono">{preview.format_detected}</code></p>
          <PreviewPanel
            tc={preview.test_case}
            onSave={() => saveMutation.mutate()}
            onDiscard={() => setPreview(null)}
            saving={saveMutation.isPending}
          />
        </div>
      )}

      {savedId && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4">
          <div className="flex items-center gap-2 text-green-700 font-medium mb-1">
            <CheckCircle className="w-4 h-4" /> Saved successfully
          </div>
          <Link href={`/test-cases/${savedId}`} className="text-sm text-brand-600 hover:underline">
            View test case →
          </Link>
        </div>
      )}
    </div>
  );
}

// ── Bulk upload ───────────────────────────────────────────────────────────────

function BulkUpload() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<BulkResult | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Select a file");
      const fd = new FormData();
      fd.append("file", file);
      fd.append("save", "true");
      const res = await fetch("/api/proxy/workflows/import/bulk", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Bulk import failed");
      return data as BulkResult;
    },
    onSuccess: (data) => {
      setResult(data);
      qc.invalidateQueries({ queryKey: ["test-cases"] });
    },
  });

  return (
    <div className="space-y-4">
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-800">
        Upload a <strong>JSON array</strong> of workflows or a <strong>ZIP</strong> of JSON/YAML files. All workflows are imported and saved immediately.
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
        <button type="button" onClick={() => fileRef.current?.click()}
          className={`w-full border-2 border-dashed rounded-xl p-6 text-center transition-colors ${
            file ? "border-brand-400 bg-brand-50" : "border-gray-200 hover:border-gray-300 bg-gray-50"}`}>
          <Upload className={`w-7 h-7 mx-auto mb-2 ${file ? "text-brand-500" : "text-gray-300"}`} />
          {file ? (
            <p className="text-sm font-medium text-brand-700">{file.name} ({(file.size/1024).toFixed(1)} KB)</p>
          ) : (
            <p className="text-sm text-gray-600">JSON array or ZIP of workflows</p>
          )}
        </button>
        <input ref={fileRef} type="file" accept=".json,.yaml,.yml,.zip" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) setFile(f); }} />

        <button onClick={() => mutation.mutate()} disabled={!file || mutation.isPending}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2.5 rounded-lg">
          {mutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
          Import all
        </button>
      </div>

      {result && (
        <div className={`rounded-xl border p-4 ${result.errors === 0 ? "bg-green-50 border-green-200" : "bg-amber-50 border-amber-200"}`}>
          <div className="flex items-center gap-2 font-medium text-sm mb-2">
            {result.errors === 0 ? <CheckCircle className="w-4 h-4 text-green-600" /> : <AlertTriangle className="w-4 h-4 text-amber-600" />}
            {result.imported} of {result.total} imported{result.errors > 0 ? `, ${result.errors} errors` : ""}
          </div>
          <div className="space-y-1">
            {result.results.map((r, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                {r.status === "ok"
                  ? <><CheckCircle className="w-3.5 h-3.5 text-green-500" /><span>{r.title}</span><code className="text-gray-400 font-mono ml-auto">{r.test_case_id}</code></>
                  : <><AlertTriangle className="w-3.5 h-3.5 text-red-500" /><span className="text-red-600">{r.file}: {r.error}</span></>
                }
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function WorkflowsPage() {
  const [tab, setTab] = useState<"single" | "bulk">("single");

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Import Workflows</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Convert conversation workflow files into test cases. Supports Vyuha, FutureAGI, and compact JSON/YAML formats.
        </p>
      </div>

      <TemplateCard />

      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 w-fit">
        {(["single", "bulk"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-1.5 text-sm font-medium rounded-lg capitalize ${tab === t ? "bg-white shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>
            {t === "single" ? "Single file" : "Bulk import"}
          </button>
        ))}
      </div>

      {tab === "single" ? <SingleUpload /> : <BulkUpload />}
    </div>
  );
}
