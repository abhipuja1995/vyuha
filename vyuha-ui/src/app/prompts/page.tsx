"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, PromptTemplate, PromptVersion } from "@/lib/api";
import { FileText, Plus, Trash2, Loader2, Play, ChevronRight } from "lucide-react";
import { clsx } from "clsx";

function fmtDate(s: string) { return new Date(s).toLocaleDateString(); }

const LABEL_COLORS: Record<string, string> = {
  production: "bg-green-100 text-green-700",
  staging: "bg-yellow-100 text-yellow-700",
  dev: "bg-gray-100 text-gray-600",
};

function VersionDetail({ templateId, version }: { templateId: string; version: PromptVersion }) {
  const qc = useQueryClient();
  const [runOpen, setRunOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [vars, setVars] = useState<Record<string, string>>({});
  const [runResult, setRunResult] = useState<{ output: string; provider: string; latency_ms: number } | null>(null);
  const [compareVersionId, setCompareVersionId] = useState("");
  const [compareResult, setCompareResult] = useState<unknown>(null);

  const { data: template } = useQuery({ queryKey: ["prompts", templateId], queryFn: () => api.prompts.get(templateId) });
  const versions = template?.versions ?? [];

  const runMutation = useMutation({
    mutationFn: () => api.prompts.runVersion(templateId, version.id, vars),
    onSuccess: setRunResult,
  });

  const promoteMutation = useMutation({
    mutationFn: () => api.prompts.updateVersion(templateId, version.id, { label: "production" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["prompts", templateId] }),
  });

  const compareMutation = useMutation({
    mutationFn: () => api.prompts.compare(templateId, [version.id, compareVersionId], vars),
    onSuccess: setCompareResult,
  });

  const deleteVersionMutation = useMutation({
    mutationFn: () => api.prompts.deleteVersion(templateId, version.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["prompts", templateId] }),
  });

  return (
    <div className="space-y-4 p-4 bg-gray-50 rounded-lg">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", LABEL_COLORS[version.label] ?? "bg-gray-100 text-gray-600")}>
          {version.label}
        </span>
        {version.model && <span className="text-xs text-gray-500">{version.model}</span>}
        {version.temperature != null && <span className="text-xs text-gray-400">temp: {version.temperature}</span>}
        <div className="ml-auto flex gap-2">
          <button onClick={() => setRunOpen(!runOpen)} className="flex items-center gap-1 text-xs border border-gray-200 bg-white px-2.5 py-1.5 rounded-lg hover:bg-gray-100">
            <Play className="w-3 h-3" /> Run
          </button>
          <button onClick={() => promoteMutation.mutate()} disabled={promoteMutation.isPending || version.label === "production"}
            className="flex items-center gap-1 text-xs border border-green-200 bg-green-50 text-green-700 px-2.5 py-1.5 rounded-lg hover:bg-green-100 disabled:opacity-50">
            {promoteMutation.isPending && <Loader2 className="w-3 h-3 animate-spin" />} Promote to Production
          </button>
          <button onClick={() => setCompareOpen(!compareOpen)} className="flex items-center gap-1 text-xs border border-gray-200 bg-white px-2.5 py-1.5 rounded-lg hover:bg-gray-100">
            Compare
          </button>
          <button onClick={() => deleteVersionMutation.mutate()} disabled={deleteVersionMutation.isPending}
            className="text-gray-400 hover:text-red-500 p-1.5 rounded-lg hover:bg-red-50">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {version.messages.map((msg, i) => (
          <div key={i} className={clsx("rounded-lg p-3 text-sm", msg.role === "system" ? "bg-gray-200 text-gray-700" : msg.role === "user" ? "bg-brand-50 text-brand-800" : "bg-white border border-gray-200 text-gray-700")}>
            <p className="text-xs font-medium text-gray-400 mb-1 uppercase">{msg.role}</p>
            <p className="whitespace-pre-wrap text-xs">{msg.content}</p>
          </div>
        ))}
      </div>

      {runOpen && (
        <div className="space-y-3 border border-gray-200 rounded-lg p-3 bg-white">
          <p className="text-xs font-medium text-gray-600">Variables</p>
          {Object.keys(vars).length === 0 && (
            <button onClick={() => setVars({ ...vars, "": "" })} className="text-xs text-brand-600 hover:underline">+ Add variable</button>
          )}
          {Object.entries(vars).map(([k, v], i) => (
            <div key={i} className="flex gap-2">
              <input value={k} onChange={(e) => {
                const newVars: Record<string, string> = {};
                Object.entries(vars).forEach(([ok, ov], j) => { newVars[j === i ? e.target.value : ok] = ov; });
                setVars(newVars);
              }} placeholder="key" className="text-xs border border-gray-200 rounded px-2 py-1 w-32" />
              <input value={v} onChange={(e) => setVars({ ...vars, [k]: e.target.value })} placeholder="value" className="text-xs border border-gray-200 rounded px-2 py-1 flex-1" />
            </div>
          ))}
          <div className="flex gap-2">
            <button onClick={() => setVars({ ...vars, "": "" })} className="text-xs text-brand-600 hover:underline">+ Add</button>
            <button onClick={() => runMutation.mutate()} disabled={runMutation.isPending}
              className="flex items-center gap-1 text-xs bg-brand-600 text-white px-3 py-1.5 rounded-lg ml-auto">
              {runMutation.isPending && <Loader2 className="w-3 h-3 animate-spin" />} Run
            </button>
          </div>
          {runResult && (
            <div className="bg-gray-50 rounded-lg p-3 space-y-1">
              <p className="text-xs text-gray-400">{runResult.provider} · {runResult.latency_ms}ms</p>
              <p className="text-sm whitespace-pre-wrap">{runResult.output}</p>
            </div>
          )}
        </div>
      )}

      {compareOpen && (
        <div className="space-y-3 border border-gray-200 rounded-lg p-3 bg-white">
          <p className="text-xs font-medium text-gray-600">Compare with version</p>
          <select value={compareVersionId} onChange={(e) => setCompareVersionId(e.target.value)} className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 w-full">
            <option value="">Select version…</option>
            {versions.filter((v) => v.id !== version.id).map((v) => (
              <option key={v.id} value={v.id}>v{v.version_number} — {v.label}</option>
            ))}
          </select>
          <button onClick={() => compareMutation.mutate()} disabled={!compareVersionId || compareMutation.isPending}
            className="flex items-center gap-1 text-xs bg-brand-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50">
            {compareMutation.isPending && <Loader2 className="w-3 h-3 animate-spin" />} Compare
          </button>
          {compareResult && (
            <div className="grid grid-cols-2 gap-3">
              {(compareResult as { versions: Array<{ version_id: string; version_number: number; label: string; output: string; provider: string; latency_ms: number }> }).versions.map((v) => (
                <div key={v.version_id} className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-400 mb-1">v{v.version_number} ({v.label}) · {v.latency_ms}ms</p>
                  <p className="text-xs whitespace-pre-wrap">{v.output}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function PromptsPage() {
  const qc = useQueryClient();
  const { data: templates = [], isLoading, error } = useQuery({ queryKey: ["prompts"], queryFn: api.prompts.list });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [newVersionOpen, setNewVersionOpen] = useState(false);

  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newFolder, setNewFolder] = useState("");

  const [vMessages, setVMessages] = useState('[{"role":"system","content":"You are a helpful assistant."}]');
  const [vModel, setVModel] = useState("");
  const [vTemp, setVTemp] = useState("0.7");
  const [vCommit, setVCommit] = useState("");
  const [vLabel, setVLabel] = useState("dev");

  const createMutation = useMutation({
    mutationFn: () => api.prompts.create({ name: newName, description: newDesc, folder: newFolder || undefined }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["prompts"] }); setNewOpen(false); setNewName(""); setNewDesc(""); setNewFolder(""); },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.prompts.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["prompts"] }); setSelectedId(null); },
  });

  const createVersionMutation = useMutation({
    mutationFn: () => api.prompts.createVersion(selectedId!, {
      messages: JSON.parse(vMessages),
      model: vModel || undefined,
      temperature: parseFloat(vTemp),
      commit_message: vCommit,
      label: vLabel,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prompts", selectedId] });
      qc.invalidateQueries({ queryKey: ["prompts"] });
      setNewVersionOpen(false);
    },
  });

  const { data: selectedTemplate } = useQuery({
    queryKey: ["prompts", selectedId],
    queryFn: () => api.prompts.get(selectedId!),
    enabled: !!selectedId,
  });

  const versions = selectedTemplate?.versions ?? [];
  const selectedVersion = versions.find((v) => v.id === selectedVersionId);

  return (
    <div className="space-y-5 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Prompts</h1>
          <p className="text-sm text-gray-500 mt-0.5">Version-controlled prompt templates</p>
        </div>
        <button onClick={() => setNewOpen(true)} className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium px-3 py-2 rounded-lg">
          <Plus className="w-4 h-4" /> New Template
        </button>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">{(error as Error).message}</div>}

      <div className="flex gap-4 h-[calc(100vh-200px)]">
        {/* Left: template list */}
        <div className="w-72 flex-shrink-0 bg-white rounded-xl border border-gray-200 overflow-y-auto">
          {isLoading ? (
            <div className="p-6 text-center text-gray-400"><Loader2 className="w-4 h-4 animate-spin mx-auto" /></div>
          ) : templates.length === 0 ? (
            <div className="p-6 text-center text-gray-400 text-sm">No templates yet.</div>
          ) : templates.map((t) => (
            <button key={t.id} onClick={() => { setSelectedId(t.id); setSelectedVersionId(null); }}
              className={clsx("w-full text-left px-4 py-3 border-b border-gray-100 hover:bg-gray-50 transition-colors", selectedId === t.id && "bg-brand-50 border-l-2 border-l-brand-500")}>
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-gray-400 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{t.name}</p>
                  {t.folder && <p className="text-xs text-gray-400">{t.folder}</p>}
                  <p className="text-xs text-gray-400">{(t.versions?.length ?? 0)} versions</p>
                </div>
                <ChevronRight className="w-4 h-4 text-gray-300" />
              </div>
            </button>
          ))}
        </div>

        {/* Right: template detail */}
        <div className="flex-1 bg-white rounded-xl border border-gray-200 overflow-y-auto">
          {!selectedId ? (
            <div className="p-10 text-center text-gray-400">Select a template to view details.</div>
          ) : (
            <div className="divide-y divide-gray-100">
              <div className="px-5 py-4 flex items-center gap-3">
                <div className="flex-1">
                  <h2 className="font-semibold">{selectedTemplate?.name}</h2>
                  {selectedTemplate?.description && <p className="text-sm text-gray-500">{selectedTemplate.description}</p>}
                </div>
                <button onClick={() => setNewVersionOpen(!newVersionOpen)} className="flex items-center gap-1 text-xs border border-gray-200 px-2.5 py-1.5 rounded-lg hover:bg-gray-50">
                  <Plus className="w-3 h-3" /> New Version
                </button>
                <button onClick={() => deleteMutation.mutate(selectedId!)} disabled={deleteMutation.isPending} className="text-gray-400 hover:text-red-500 p-1.5">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>

              {newVersionOpen && (
                <div className="px-5 py-4 space-y-3 bg-gray-50">
                  <p className="text-xs font-medium text-gray-600">New Version</p>
                  <div>
                    <label className="text-xs text-gray-500 block mb-1">Messages (JSON array)</label>
                    <textarea value={vMessages} onChange={(e) => setVMessages(e.target.value)} rows={5}
                      className="w-full text-xs font-mono border border-gray-200 rounded-lg px-3 py-2 resize-none" />
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <label className="text-xs text-gray-500 block mb-1">Model</label>
                      <input value={vModel} onChange={(e) => setVModel(e.target.value)} placeholder="gpt-4o"
                        className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5" />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500 block mb-1">Temperature</label>
                      <input value={vTemp} onChange={(e) => setVTemp(e.target.value)} type="number" step="0.1" min="0" max="2"
                        className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5" />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500 block mb-1">Label</label>
                      <select value={vLabel} onChange={(e) => setVLabel(e.target.value)} className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5">
                        <option value="dev">dev</option>
                        <option value="staging">staging</option>
                        <option value="production">production</option>
                      </select>
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 block mb-1">Commit message</label>
                    <input value={vCommit} onChange={(e) => setVCommit(e.target.value)} placeholder="Initial prompt"
                      className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5" />
                  </div>
                  {createVersionMutation.isError && <p className="text-xs text-red-600">{(createVersionMutation.error as Error).message}</p>}
                  <div className="flex gap-2 justify-end">
                    <button onClick={() => setNewVersionOpen(false)} className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-100">Cancel</button>
                    <button onClick={() => createVersionMutation.mutate()} disabled={createVersionMutation.isPending}
                      className="flex items-center gap-1 text-xs bg-brand-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50">
                      {createVersionMutation.isPending && <Loader2 className="w-3 h-3 animate-spin" />} Create
                    </button>
                  </div>
                </div>
              )}

              {/* Version list */}
              {versions.length === 0 ? (
                <div className="px-5 py-10 text-center text-gray-400 text-sm">No versions yet.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="text-left px-4 py-2 text-xs font-medium text-gray-500">Version</th>
                      <th className="text-left px-4 py-2 text-xs font-medium text-gray-500">Label</th>
                      <th className="text-left px-4 py-2 text-xs font-medium text-gray-500">Model</th>
                      <th className="text-left px-4 py-2 text-xs font-medium text-gray-500">Commit</th>
                      <th className="text-left px-4 py-2 text-xs font-medium text-gray-500">Created</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {versions.map((v) => (
                      <>
                        <tr key={v.id} onClick={() => setSelectedVersionId(selectedVersionId === v.id ? null : v.id)}
                          className="hover:bg-gray-50 cursor-pointer">
                          <td className="px-4 py-3 font-mono text-sm">v{v.version_number}</td>
                          <td className="px-4 py-3">
                            <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", LABEL_COLORS[v.label] ?? "bg-gray-100 text-gray-600")}>{v.label}</span>
                          </td>
                          <td className="px-4 py-3 text-gray-500 text-xs">{v.model ?? "—"}</td>
                          <td className="px-4 py-3 text-gray-500 text-xs truncate max-w-xs">{v.commit_message}</td>
                          <td className="px-4 py-3 text-gray-500 text-xs">{fmtDate(v.created_at)}</td>
                        </tr>
                        {selectedVersionId === v.id && (
                          <tr key={`${v.id}-detail`}>
                            <td colSpan={5} className="px-4 pb-4 pt-2">
                              <VersionDetail templateId={selectedId!} version={v} />
                            </td>
                          </tr>
                        )}
                      </>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      </div>

      {newOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl border border-gray-200 p-6 w-full max-w-md space-y-4">
            <h2 className="font-semibold">New Template</h2>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Name</label>
              <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Template name"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Description</label>
              <input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="Optional"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Folder</label>
              <input value={newFolder} onChange={(e) => setNewFolder(e.target.value)} placeholder="e.g. customer-support"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
            </div>
            {createMutation.isError && <p className="text-xs text-red-600">{(createMutation.error as Error).message}</p>}
            <div className="flex gap-2 justify-end">
              <button onClick={() => setNewOpen(false)} className="text-sm px-4 py-2 border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
              <button onClick={() => createMutation.mutate()} disabled={!newName || createMutation.isPending}
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
