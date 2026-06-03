"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ConversationNode, TestCase, apiFetch } from "@/lib/api";
import {
  ArrowLeft, Mic, Trash2, Upload, Play, CheckCircle, XCircle,
  AlertCircle, Loader2, ChevronDown, ChevronUp,
} from "lucide-react";
import { clsx } from "clsx";

// ── Run result ─────────────────────────────────────────────────────────────────

function VerdictBadge({ verdict }: { verdict: string }) {
  if (verdict === "PASS") return <span className="flex items-center gap-1 text-green-700 text-sm font-medium"><CheckCircle className="w-4 h-4" /> Pass</span>;
  if (verdict === "FAIL") return <span className="flex items-center gap-1 text-red-700 text-sm font-medium"><XCircle className="w-4 h-4" /> Fail</span>;
  return <span className="flex items-center gap-1 text-yellow-600 text-sm font-medium"><AlertCircle className="w-4 h-4" /> {verdict}</span>;
}

function RunResultPanel({ runId }: { runId: string }) {
  const [open, setOpen] = useState(true);
  const { data: run, isLoading } = useQuery({
    queryKey: ["run", runId],
    queryFn: () => apiFetch<any>(`/runs/${runId}`),
    refetchInterval: (query) => {
      const v = (query.state.data as any)?.verdict;
      return (v === "PASS" || v === "FAIL" || v === "ERROR") ? false : 3000;
    },
  });

  if (isLoading || !run) return <div className="text-xs text-gray-400 animate-pulse">Loading result…</div>;

  return (
    <div className={clsx("rounded-xl border p-4", run.verdict === "PASS" ? "bg-green-50 border-green-200" : run.verdict === "FAIL" ? "bg-red-50 border-red-200" : "bg-gray-50 border-gray-200")}>
      <button className="w-full flex items-center justify-between" onClick={() => setOpen((v) => !v)}>
        <div className="flex items-center gap-3">
          <VerdictBadge verdict={run.verdict} />
          <span className="text-xs text-gray-400 font-mono">{runId}</span>
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
      </button>
      {open && (
        <div className="mt-3 grid grid-cols-3 gap-3">
          {[
            ["Task completion", `${((run.eva_a?.task_completion ?? 0) * 100).toFixed(0)}%`],
            ["Faithfulness", `${((run.eva_a?.faithfulness ?? 0) * 100).toFixed(0)}%`],
            ["Speech fidelity", `${((run.eva_a?.speech_fidelity ?? 0) * 100).toFixed(0)}%`],
          ].map(([l, v]) => (
            <div key={l} className="bg-white/60 rounded-lg p-2.5">
              <p className="text-xs text-gray-500">{l}</p>
              <p className="font-semibold text-sm">{v}</p>
            </div>
          ))}
          {run.failure_report && (
            <div className="col-span-3 text-xs text-red-700 bg-white/60 rounded-lg p-3">
              <p className="font-medium mb-0.5">Failed criterion</p>
              <p>{run.failure_report.failed_criterion}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Run controls ──────────────────────────────────────────────────────────────

function RunControls({ tc }: { tc: TestCase }) {
  const [taskIds, setTaskIds] = useState<string[]>([]);
  const hasAudio = tc.conversation_graph.nodes.some((n) => n.audio_file);

  const runMutation = useMutation({
    mutationFn: (mode: "text" | "audio") =>
      apiFetch<{ task_ids: string[] }>("/runs/", {
        method: "POST",
        body: JSON.stringify({ test_id: tc.test_id, k: 1, mode }),
      }),
    onSuccess: (data) => setTaskIds(data.task_ids),
  });

  return (
    <div className="border border-gray-200 rounded-xl p-5 space-y-3">
      <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">Run Test</h2>
      <div className="flex gap-2">
        <button
          onClick={() => runMutation.mutate("text")}
          disabled={runMutation.isPending}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg"
        >
          {runMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          Run
        </button>
        {hasAudio && (
          <button
            onClick={() => runMutation.mutate("audio")}
            disabled={runMutation.isPending}
            className="flex items-center gap-2 border border-brand-300 text-brand-700 hover:bg-brand-50 text-sm font-medium px-4 py-2 rounded-lg"
          >
            <Mic className="w-4 h-4" /> Run with audio
          </button>
        )}
      </div>
      {runMutation.isError && (
        <p className="text-xs text-red-600">{(runMutation.error as Error).message}</p>
      )}
      {taskIds.length > 0 && (
        <div className="space-y-2 pt-1">
          {taskIds.map((tid) => (
            <RunResultPanel key={tid} runId={tid} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Node audio row ────────────────────────────────────────────────────────────

function NodeAudioRow({
  testId, node, uploading, onUploadStart, onUploadDone, onDelete,
}: {
  testId: string; node: ConversationNode; uploading: boolean;
  onUploadStart: () => void; onUploadDone: () => void; onDelete: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const audioUrl = node.audio_file ? api.audio.url(testId, node.node_id) : null;

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    onUploadStart();
    try {
      await api.audio.upload(testId, node.node_id, file);
      onUploadDone();
    } catch (err) {
      alert(`Upload failed: ${err}`);
      onUploadDone();
    }
    if (fileRef.current) fileRef.current.value = "";
  };

  const handleDelete = async () => {
    setDeleteLoading(true);
    try { await api.audio.delete(testId, node.node_id); onDelete(); }
    finally { setDeleteLoading(false); }
  };

  return (
    <div className={clsx("border rounded-xl p-4", node.is_terminal ? "border-green-300 bg-green-50" : "border-gray-200 bg-white")}>
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono text-gray-400">{node.node_id}</span>
            {node.is_terminal && <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded">terminal</span>}
            {node.audio_file && (
              <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded flex items-center gap-1">
                <Mic className="w-3 h-3" /> audio ready
              </span>
            )}
          </div>
          <p className="text-sm text-gray-800 italic">"{node.utterance_template}"</p>
          {audioUrl && <audio controls src={audioUrl} className="mt-2 h-8 w-full max-w-xs" />}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <input ref={fileRef} type="file" accept=".wav,.mp3,.ogg,.flac,.m4a" className="hidden" onChange={handleFile} />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-1 text-xs bg-brand-50 hover:bg-brand-100 text-brand-700 border border-brand-200 px-2.5 py-1.5 rounded-lg disabled:opacity-50"
          >
            <Upload className="w-3.5 h-3.5" />
            {uploading ? "Uploading…" : node.audio_file ? "Replace" : "Upload audio"}
          </button>
          {node.audio_file && (
            <button onClick={handleDelete} disabled={deleteLoading}
              className="text-xs text-red-500 hover:text-red-700 p-1.5 rounded-lg hover:bg-red-50 disabled:opacity-50">
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50 rounded-lg px-3 py-2">
      <p className="text-xs text-gray-400">{label}</p>
      <p className="font-medium text-gray-800">{value}</p>
    </div>
  );
}

export default function TestCaseDetailPage() {
  const { test_id } = useParams<{ test_id: string }>();
  const router = useRouter();
  const [tc, setTc] = useState<TestCase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);

  useEffect(() => {
    api.testCases.get(test_id).then(setTc).catch((e) => setError(String(e)));
  }, [test_id]);

  const refresh = () => api.testCases.get(test_id).then(setTc);

  if (error) return <div className="p-8 text-red-600">{error}</div>;
  if (!tc) return <div className="p-8 text-gray-400">Loading…</div>;

  const hasAudio = tc.conversation_graph.nodes.some((n) => n.audio_file);

  return (
    <div className="max-w-3xl mx-auto px-6 py-10 space-y-8">
      <button onClick={() => router.push("/test-cases")}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800">
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-1">
          <span className="text-xs font-mono bg-gray-100 px-2 py-0.5 rounded text-gray-500">{tc.test_id}</span>
          <span className="text-xs font-medium bg-brand-50 text-brand-700 border border-brand-200 px-2 py-0.5 rounded">{tc.category}</span>
          {hasAudio && (
            <span className="text-xs bg-blue-100 text-blue-700 border border-blue-200 px-2 py-0.5 rounded flex items-center gap-1">
              <Mic className="w-3 h-3" /> audio attached
            </span>
          )}
        </div>
        <h1 className="text-2xl font-semibold text-gray-900">{tc.title}</h1>
        <p className="text-sm text-gray-500 mt-1">{tc.user_goal}</p>
      </div>

      {/* Run controls — prominent at top */}
      <RunControls tc={tc} />

      {/* Persona */}
      <section className="border border-gray-200 rounded-xl p-5 space-y-2">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">Persona</h2>
        <div className="grid grid-cols-3 gap-3 text-sm">
          <Chip label="Language" value={tc.persona_config.language} />
          <Chip label="Emotion" value={tc.persona_config.emotion} />
          <Chip label="Noise" value={tc.persona_config.noise_profile} />
        </div>
        {tc.persona_config.backstory && <p className="text-xs text-gray-500 mt-2">{tc.persona_config.backstory}</p>}
      </section>

      {/* Conversation nodes with audio upload */}
      <section className="space-y-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">Conversation Nodes</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Upload a WAV/MP3 per node to use real voice recordings instead of TTS synthesis.
            Once audio is uploaded on all nodes, use "Run with audio" above.
          </p>
        </div>
        {tc.conversation_graph.nodes.map((node) => (
          <NodeAudioRow
            key={node.node_id}
            testId={tc.test_id}
            node={node}
            uploading={uploading === node.node_id}
            onUploadStart={() => setUploading(node.node_id)}
            onUploadDone={() => { setUploading(null); refresh(); }}
            onDelete={() => refresh()}
          />
        ))}
      </section>

      {/* Pass criteria */}
      <section className="border border-gray-200 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">Pass Criteria</h2>
        <p className="text-sm text-gray-700">{tc.pass_criteria}</p>
      </section>

      {/* Tags */}
      {tc.tags.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {tc.tags.map((tag) => (
            <span key={tag} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{tag}</span>
          ))}
        </div>
      )}
    </div>
  );
}
