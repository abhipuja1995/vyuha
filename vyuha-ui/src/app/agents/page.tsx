"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, AgentDefinition } from "@/lib/api";
import { Bot, Plus, Trash2, Loader2, CheckCircle, XCircle, ChevronRight } from "lucide-react";
import { clsx } from "clsx";

function fmtDate(s: string) { return new Date(s).toLocaleDateString(); }

const PROVIDER_FIELDS: Record<string, string[]> = {
  vapi: ["api_key", "assistant_id"],
  retell: ["api_key", "agent_id"],
  livekit: ["url", "api_key", "api_secret", "agent_name"],
  eleven_labs: ["api_key", "agent_id"],
  others: ["webhook_url"],
};

export default function AgentsPage() {
  const qc = useQueryClient();
  const { data: agents = [], isLoading, error } = useQuery({ queryKey: ["agents"], queryFn: api.agents.list });

  const [newOpen, setNewOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { connected: boolean; error?: string; note?: string }>>({});
  const [callId, setCallId] = useState("");
  const [importResult, setImportResult] = useState<unknown>(null);

  const [form, setForm] = useState({
    name: "",
    description: "",
    agent_type: "text",
    voice_provider: "vapi",
    system_prompt: "",
    is_active: true,
    config: {} as Record<string, string>,
  });

  const provider = form.agent_type === "voice" ? form.voice_provider : null;
  const providerFields = provider ? (PROVIDER_FIELDS[provider] ?? PROVIDER_FIELDS["others"]) : [];

  const createMutation = useMutation({
    mutationFn: () => api.agents.create({
      name: form.name,
      description: form.description,
      agent_type: form.agent_type,
      voice_provider: form.agent_type === "voice" ? form.voice_provider : undefined,
      system_prompt: form.system_prompt,
      is_active: form.is_active,
      config: form.config,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["agents"] }); setNewOpen(false); },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.agents.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["agents"] }); setSelectedId(null); },
  });

  const testMutation = useMutation({
    mutationFn: (id: string) => api.agents.test(id),
    onSuccess: (data, id) => setTestResults((prev) => ({ ...prev, [id]: data })),
  });

  const importMutation = useMutation({
    mutationFn: () => api.agents.importCall(selectedId!, callId),
    onSuccess: setImportResult,
  });

  const selectedAgent = agents.find((a) => a.id === selectedId);

  return (
    <div className="space-y-5 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Agents</h1>
          <p className="text-sm text-gray-500 mt-0.5">Voice and text agent definitions</p>
        </div>
        <button onClick={() => setNewOpen(true)} className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium px-3 py-2 rounded-lg">
          <Plus className="w-4 h-4" /> New Agent
        </button>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">{(error as Error).message}</div>}

      <div className="flex gap-4">
        {/* Agent table */}
        <div className="flex-1 bg-white rounded-xl border border-gray-200 overflow-hidden">
          {isLoading ? (
            <div className="p-10 text-center text-gray-400 flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
          ) : agents.length === 0 ? (
            <div className="p-10 text-center text-gray-400">No agents yet.</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Name</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Type</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Provider</th>
                  <th className="text-center px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Status</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Created</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {agents.map((a) => (
                  <tr key={a.id} onClick={() => setSelectedId(selectedId === a.id ? null : a.id)} className="hover:bg-gray-50 cursor-pointer">
                    <td className="px-4 py-3 font-medium flex items-center gap-2">
                      <Bot className="w-4 h-4 text-brand-400 flex-shrink-0" />
                      {a.name}
                    </td>
                    <td className="px-4 py-3">
                      <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", a.agent_type === "voice" ? "bg-purple-100 text-purple-700" : "bg-blue-100 text-blue-700")}>
                        {a.agent_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{a.voice_provider ?? "—"}</td>
                    <td className="px-4 py-3 text-center">
                      {testResults[a.id] ? (
                        testResults[a.id].connected
                          ? <CheckCircle className="w-4 h-4 text-green-500 mx-auto" />
                          : <XCircle className="w-4 h-4 text-red-500 mx-auto" />
                      ) : (
                        <span className={clsx("text-xs px-2 py-0.5 rounded-full", a.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500")}>
                          {a.is_active ? "active" : "inactive"}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{fmtDate(a.created_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 justify-end" onClick={(e) => e.stopPropagation()}>
                        <button onClick={() => testMutation.mutate(a.id)} disabled={testMutation.isPending}
                          className="text-xs border border-gray-200 px-2.5 py-1 rounded-lg hover:bg-gray-100 flex items-center gap-1">
                          {testMutation.isPending && testMutation.variables === a.id ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                          Test
                        </button>
                        <button onClick={() => deleteMutation.mutate(a.id)} disabled={deleteMutation.isPending} className="text-gray-400 hover:text-red-500 p-1">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                        <ChevronRight className={clsx("w-4 h-4 text-gray-300 transition-transform", selectedId === a.id && "rotate-90")} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Detail panel */}
        {selectedAgent && (
          <div className="w-80 flex-shrink-0 bg-white rounded-xl border border-gray-200 p-5 space-y-4">
            <div>
              <h3 className="font-semibold">{selectedAgent.name}</h3>
              {selectedAgent.description && <p className="text-xs text-gray-500 mt-0.5">{selectedAgent.description}</p>}
            </div>

            {selectedAgent.system_prompt && (
              <div>
                <p className="text-xs font-medium text-gray-500 mb-1">System Prompt</p>
                <p className="text-xs text-gray-600 bg-gray-50 rounded p-2 whitespace-pre-wrap line-clamp-6">{selectedAgent.system_prompt}</p>
              </div>
            )}

            {Object.keys(selectedAgent.config ?? {}).length > 0 && (
              <div>
                <p className="text-xs font-medium text-gray-500 mb-1">Config</p>
                {Object.entries(selectedAgent.config).map(([k, v]) => (
                  <div key={k} className="flex gap-2 text-xs">
                    <span className="text-gray-400">{k}:</span>
                    <span className="font-mono truncate">{String(v)}</span>
                  </div>
                ))}
              </div>
            )}

            {testResults[selectedAgent.id] && (
              <div className={clsx("rounded-lg p-3 text-xs", testResults[selectedAgent.id].connected ? "bg-green-50 border border-green-200" : "bg-red-50 border border-red-200")}>
                {testResults[selectedAgent.id].connected ? "Connected successfully" : `Error: ${testResults[selectedAgent.id].error}`}
                {testResults[selectedAgent.id].note && <p className="text-gray-500 mt-1">{testResults[selectedAgent.id].note}</p>}
              </div>
            )}

            <div className="border-t border-gray-100 pt-4 space-y-3">
              <p className="text-xs font-medium text-gray-600">Import Call</p>
              <input value={callId} onChange={(e) => setCallId(e.target.value)} placeholder="Call ID"
                className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2" />
              <button onClick={() => importMutation.mutate()} disabled={!callId || importMutation.isPending}
                className="w-full flex items-center justify-center gap-1 text-xs bg-brand-600 text-white px-3 py-2 rounded-lg disabled:opacity-50 hover:bg-brand-500">
                {importMutation.isPending && <Loader2 className="w-3 h-3 animate-spin" />} Import Transcript
              </button>
              {importResult && (
                <pre className="text-xs bg-gray-50 rounded p-2 overflow-x-auto max-h-40">{JSON.stringify(importResult, null, 2)}</pre>
              )}
            </div>
          </div>
        )}
      </div>

      {newOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl border border-gray-200 p-6 w-full max-w-lg space-y-4 max-h-[90vh] overflow-y-auto">
            <h2 className="font-semibold">New Agent</h2>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-gray-600 block mb-1">Name</label>
                <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Agent name"
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 block mb-1">Type</label>
                <select value={form.agent_type} onChange={(e) => setForm({ ...form, agent_type: e.target.value })} className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2">
                  <option value="text">text</option>
                  <option value="voice">voice</option>
                </select>
              </div>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Description</label>
              <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Optional"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
            </div>
            {form.agent_type === "voice" && (
              <>
                <div>
                  <label className="text-xs font-medium text-gray-600 block mb-1">Voice Provider</label>
                  <select value={form.voice_provider} onChange={(e) => setForm({ ...form, voice_provider: e.target.value, config: {} })} className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2">
                    <option value="vapi">VAPI</option>
                    <option value="retell">Retell</option>
                    <option value="livekit">LiveKit</option>
                    <option value="eleven_labs">Eleven Labs</option>
                    <option value="others">Others</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-medium text-gray-600 block">Provider Config</label>
                  {providerFields.map((field) => (
                    <div key={field}>
                      <label className="text-xs text-gray-500 block mb-0.5">{field}</label>
                      <input value={(form.config[field] ?? "")} onChange={(e) => setForm({ ...form, config: { ...form.config, [field]: e.target.value } })}
                        placeholder={field} className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2" />
                    </div>
                  ))}
                </div>
              </>
            )}
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">System Prompt</label>
              <textarea value={form.system_prompt} onChange={(e) => setForm({ ...form, system_prompt: e.target.value })} rows={4}
                placeholder="You are a helpful assistant…" className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none" />
            </div>
            {createMutation.isError && <p className="text-xs text-red-600">{(createMutation.error as Error).message}</p>}
            <div className="flex gap-2 justify-end">
              <button onClick={() => setNewOpen(false)} className="text-sm px-4 py-2 border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
              <button onClick={() => createMutation.mutate()} disabled={!form.name || createMutation.isPending}
                className="flex items-center gap-2 text-sm bg-brand-600 text-white px-4 py-2 rounded-lg hover:bg-brand-500 disabled:opacity-50">
                {createMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
