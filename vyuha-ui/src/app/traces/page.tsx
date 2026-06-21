"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, Span } from "@/lib/api";
import { Activity, Trash2, Loader2, ChevronDown, ChevronUp, Plus } from "lucide-react";
import { clsx } from "clsx";

function fmtDate(s: string) { return new Date(s).toLocaleString(); }

const SPAN_KIND_COLORS: Record<string, string> = {
  llm: "bg-blue-100 text-blue-700",
  tool: "bg-yellow-100 text-yellow-700",
  chain: "bg-purple-100 text-purple-700",
  retriever: "bg-green-100 text-green-700",
};

function SpanRow({ span }: { span: Span }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-3 px-3 py-2.5 bg-gray-50 hover:bg-gray-100 text-left text-xs">
        <span className={clsx("px-2 py-0.5 rounded-full font-medium text-xs", SPAN_KIND_COLORS[span.span_kind] ?? "bg-gray-100 text-gray-600")}>
          {span.span_kind}
        </span>
        <span className="font-medium text-gray-800 flex-1">{span.operation_name}</span>
        {span.model && <span className="text-gray-400">{span.model}</span>}
        {span.latency_ms != null && <span className="text-gray-500">{span.latency_ms.toFixed(0)}ms</span>}
        {span.total_tokens != null && <span className="text-gray-400">{span.total_tokens} tok</span>}
        <span className={clsx("px-1.5 py-0.5 rounded text-xs font-medium", span.status === "OK" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700")}>
          {span.status}
        </span>
        {open ? <ChevronUp className="w-3.5 h-3.5 text-gray-400" /> : <ChevronDown className="w-3.5 h-3.5 text-gray-400" />}
      </button>
      {open && (
        <div className="p-3 space-y-2 bg-white">
          {span.input && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Input</p>
              <pre className="text-xs bg-gray-50 p-2 rounded overflow-x-auto">{JSON.stringify(span.input, null, 2)}</pre>
            </div>
          )}
          {span.output && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Output</p>
              <pre className="text-xs bg-gray-50 p-2 rounded overflow-x-auto">{JSON.stringify(span.output, null, 2)}</pre>
            </div>
          )}
          {span.cost_usd != null && <p className="text-xs text-gray-400">Cost: ${span.cost_usd.toFixed(6)}</p>}
        </div>
      )}
    </div>
  );
}

function TraceDetail({ traceId }: { traceId: string }) {
  const { data, isLoading } = useQuery({ queryKey: ["traces", traceId], queryFn: () => api.traces.get(traceId) });
  if (isLoading) return <div className="p-4 text-xs text-gray-400 flex gap-2 items-center"><Loader2 className="w-3 h-3 animate-spin" /> Loading spans…</div>;
  const spans = [...(data?.spans ?? [])].sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime());
  return (
    <div className="p-4 space-y-2 bg-gray-50">
      {spans.length === 0 ? <p className="text-xs text-gray-400">No spans.</p> : spans.map((s) => <SpanRow key={s.id} span={s} />)}
    </div>
  );
}

export default function TracesPage() {
  const qc = useQueryClient();
  const [sessionFilter, setSessionFilter] = useState("");
  const [userFilter, setUserFilter] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [otlpOpen, setOtlpOpen] = useState(false);
  const [otlpPayload, setOtlpPayload] = useState("{}");

  const params = {
    ...(sessionFilter ? { session_id: sessionFilter } : {}),
    ...(userFilter ? { user_id: userFilter } : {}),
  };

  const { data: traces = [], isLoading, error } = useQuery({
    queryKey: ["traces", params],
    queryFn: () => api.traces.list(params),
  });

  const { data: stats } = useQuery({ queryKey: ["traces-stats"], queryFn: api.traces.stats });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.traces.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["traces"] }),
  });

  const otlpMutation = useMutation({
    mutationFn: () => api.traces.ingestOtlp(JSON.parse(otlpPayload)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["traces"] }); setOtlpOpen(false); },
  });

  return (
    <div className="space-y-5 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Traces</h1>
          <p className="text-sm text-gray-500 mt-0.5">Observability — LLM call traces and spans</p>
        </div>
        <button onClick={() => setOtlpOpen(true)} className="flex items-center gap-2 border border-gray-200 bg-white text-sm font-medium px-3 py-2 rounded-lg hover:bg-gray-50">
          <Plus className="w-4 h-4" /> Ingest OTLP
        </button>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {[
            ["Traces", stats.total_traces, ""],
            ["Spans", stats.total_spans, ""],
            ["Avg Latency", `${stats.avg_latency_ms?.toFixed(0)}ms`, ""],
            ["Total Tokens", stats.total_tokens?.toLocaleString(), ""],
            ["Total Cost", `$${stats.total_cost_usd?.toFixed(4)}`, ""],
          ].map(([label, value]) => (
            <div key={label as string} className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
              <p className="text-xl font-bold mt-1">{value}</p>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-3">
        <input value={sessionFilter} onChange={(e) => setSessionFilter(e.target.value)} placeholder="Filter by session ID"
          className="text-sm border border-gray-200 rounded-lg px-3 py-2 flex-1" />
        <input value={userFilter} onChange={(e) => setUserFilter(e.target.value)} placeholder="Filter by user ID"
          className="text-sm border border-gray-200 rounded-lg px-3 py-2 flex-1" />
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">{(error as Error).message}</div>}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {isLoading ? (
          <div className="p-10 text-center text-gray-400 flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
        ) : traces.length === 0 ? (
          <div className="p-10 text-center text-gray-400">No traces yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Trace ID</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Name</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Session</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">User</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Spans</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Created</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {traces.map((t) => (
                <>
                  <tr key={t.id} onClick={() => setExpandedId(expandedId === t.id ? null : t.id)} className="hover:bg-gray-50 cursor-pointer">
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">{t.id.slice(0, 12)}…</td>
                    <td className="px-4 py-3 font-medium">{t.name || "—"}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{t.session_id?.slice(0, 12) ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{t.user_id ?? "—"}</td>
                    <td className="px-4 py-3 text-right font-mono">{t.span_count ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{fmtDate(t.created_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={(e) => { e.stopPropagation(); deleteMutation.mutate(t.id); }}
                        className="text-gray-400 hover:text-red-500 p-1">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                  {expandedId === t.id && (
                    <tr key={`${t.id}-detail`}>
                      <td colSpan={7} className="p-0">
                        <TraceDetail traceId={t.id} />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {otlpOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl border border-gray-200 p-6 w-full max-w-lg space-y-4">
            <h2 className="font-semibold">Ingest OTLP Payload</h2>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">JSON Payload</label>
              <textarea value={otlpPayload} onChange={(e) => setOtlpPayload(e.target.value)} rows={10}
                className="w-full text-xs font-mono border border-gray-200 rounded-lg px-3 py-2 resize-none" />
            </div>
            {otlpMutation.isError && <p className="text-xs text-red-600">{(otlpMutation.error as Error).message}</p>}
            {otlpMutation.isSuccess && <p className="text-xs text-green-600">Ingested successfully.</p>}
            <div className="flex gap-2 justify-end">
              <button onClick={() => setOtlpOpen(false)} className="text-sm px-4 py-2 border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
              <button onClick={() => otlpMutation.mutate()} disabled={otlpMutation.isPending}
                className="flex items-center gap-2 text-sm bg-brand-600 text-white px-4 py-2 rounded-lg hover:bg-brand-500 disabled:opacity-50">
                {otlpMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} Ingest
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
