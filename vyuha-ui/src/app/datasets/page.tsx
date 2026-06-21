"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, Dataset, DatasetItem } from "@/lib/api";
import { Database, Upload, Plus, Trash2, Download, ChevronDown, ChevronUp, Loader2 } from "lucide-react";

function fmtDate(s: string) {
  return new Date(s).toLocaleDateString();
}

export default function DatasetsPage() {
  const qc = useQueryClient();
  const { data: datasets = [], isLoading, error } = useQuery({ queryKey: ["datasets"], queryFn: api.datasets.list });

  const [uploadOpen, setUploadOpen] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [addRowsOpen, setAddRowsOpen] = useState(false);
  const [addRowsJson, setAddRowsJson] = useState("[]");

  // Upload state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState("");
  const [uploadDesc, setUploadDesc] = useState("");

  // New dataset state
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");

  const uploadMutation = useMutation({
    mutationFn: () => api.datasets.upload(uploadFile!, uploadName, uploadDesc),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["datasets"] }); setUploadOpen(false); setUploadFile(null); setUploadName(""); setUploadDesc(""); },
  });

  const createMutation = useMutation({
    mutationFn: () => api.datasets.create({ name: newName, description: newDesc }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["datasets"] }); setNewOpen(false); setNewName(""); setNewDesc(""); },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.datasets.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["datasets"] }); setSelectedId(null); },
  });

  const { data: detail } = useQuery({
    queryKey: ["datasets", selectedId],
    queryFn: () => api.datasets.get(selectedId!),
    enabled: !!selectedId,
  });

  const addRowsMutation = useMutation({
    mutationFn: () => api.datasets.addRows(selectedId!, JSON.parse(addRowsJson)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["datasets", selectedId] }); setAddRowsOpen(false); setAddRowsJson("[]"); },
  });

  const exportMutation = useMutation({
    mutationFn: () => api.datasets.export(selectedId!),
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data.rows, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dataset-${selectedId}.json`;
      a.click();
      URL.revokeObjectURL(url);
    },
  });

  const selected = datasets.find((d) => d.id === selectedId);
  const items: DatasetItem[] = detail?.items ?? [];

  return (
    <div className="space-y-5 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Datasets</h1>
          <p className="text-sm text-gray-500 mt-0.5">Manage evaluation datasets</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setUploadOpen(true)} className="flex items-center gap-2 border border-gray-200 bg-white text-sm font-medium px-3 py-2 rounded-lg hover:bg-gray-50">
            <Upload className="w-4 h-4" /> Upload File
          </button>
          <button onClick={() => setNewOpen(true)} className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium px-3 py-2 rounded-lg">
            <Plus className="w-4 h-4" /> New Dataset
          </button>
        </div>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">{(error as Error).message}</div>}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {isLoading ? (
          <div className="p-10 text-center text-gray-400 flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
        ) : datasets.length === 0 ? (
          <div className="p-10 text-center text-gray-400">No datasets yet. Upload a CSV/JSON file or create one manually.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Name</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Description</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Source</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Rows</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {datasets.map((d) => (
                <>
                  <tr
                    key={d.id}
                    onClick={() => setSelectedId(selectedId === d.id ? null : d.id)}
                    className="hover:bg-gray-50 cursor-pointer"
                  >
                    <td className="px-4 py-3 font-medium flex items-center gap-2">
                      <Database className="w-4 h-4 text-brand-500 flex-shrink-0" />
                      {d.name}
                    </td>
                    <td className="px-4 py-3 text-gray-500 truncate max-w-xs">{d.description || "—"}</td>
                    <td className="px-4 py-3 text-gray-500">{d.source || "—"}</td>
                    <td className="px-4 py-3 text-right font-mono">{d.row_count}</td>
                    <td className="px-4 py-3 text-gray-500">{fmtDate(d.created_at)}</td>
                  </tr>
                  {selectedId === d.id && (
                    <tr key={`${d.id}-detail`}>
                      <td colSpan={5} className="px-4 pb-4 pt-2 bg-gray-50">
                        <div className="space-y-3">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-xs text-gray-500">ID: <code className="font-mono">{d.id}</code></span>
                            {Object.entries(d.column_types ?? {}).map(([col, type]) => (
                              <span key={col} className="text-xs bg-gray-200 text-gray-700 px-2 py-0.5 rounded-full">{col}: {type}</span>
                            ))}
                            <div className="ml-auto flex gap-2">
                              <button onClick={() => setAddRowsOpen(!addRowsOpen)} className="flex items-center gap-1 text-xs border border-gray-200 bg-white px-2.5 py-1.5 rounded-lg hover:bg-gray-100">
                                <Plus className="w-3 h-3" /> Add Rows
                              </button>
                              <button onClick={() => exportMutation.mutate()} disabled={exportMutation.isPending} className="flex items-center gap-1 text-xs border border-gray-200 bg-white px-2.5 py-1.5 rounded-lg hover:bg-gray-100">
                                <Download className="w-3 h-3" /> Export
                              </button>
                              <button onClick={() => deleteMutation.mutate(d.id)} disabled={deleteMutation.isPending} className="flex items-center gap-1 text-xs bg-red-50 text-red-600 border border-red-200 px-2.5 py-1.5 rounded-lg hover:bg-red-100">
                                <Trash2 className="w-3 h-3" /> Delete
                              </button>
                            </div>
                          </div>

                          {addRowsOpen && (
                            <div className="space-y-2">
                              <label className="text-xs font-medium text-gray-600">JSON Array of rows</label>
                              <textarea value={addRowsJson} onChange={(e) => setAddRowsJson(e.target.value)} rows={4}
                                className="w-full text-xs font-mono border border-gray-200 rounded-lg px-3 py-2 resize-none" />
                              <div className="flex gap-2">
                                <button onClick={() => addRowsMutation.mutate()} disabled={addRowsMutation.isPending}
                                  className="flex items-center gap-1 text-xs bg-brand-600 text-white px-3 py-1.5 rounded-lg hover:bg-brand-500">
                                  {addRowsMutation.isPending && <Loader2 className="w-3 h-3 animate-spin" />} Add Rows
                                </button>
                                <button onClick={() => setAddRowsOpen(false)} className="text-xs text-gray-500 px-3 py-1.5 rounded-lg hover:bg-gray-100">Cancel</button>
                              </div>
                            </div>
                          )}

                          {items.length > 0 ? (
                            <div className="overflow-x-auto rounded-lg border border-gray-200">
                              <table className="text-xs w-full">
                                <thead className="bg-gray-100 border-b border-gray-200">
                                  <tr>
                                    <th className="px-3 py-2 text-left text-gray-500">#</th>
                                    {Object.keys(items[0]?.data ?? {}).map((k) => (
                                      <th key={k} className="px-3 py-2 text-left text-gray-500">{k}</th>
                                    ))}
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100 bg-white">
                                  {items.slice(0, 50).map((item) => (
                                    <tr key={item.id}>
                                      <td className="px-3 py-2 text-gray-400">{item.row_index}</td>
                                      {Object.values(item.data).map((v, i) => (
                                        <td key={i} className="px-3 py-2 max-w-xs truncate">{String(v)}</td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          ) : (
                            <p className="text-xs text-gray-400">No rows yet.</p>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Upload Dialog */}
      {uploadOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl border border-gray-200 p-6 w-full max-w-md space-y-4">
            <h2 className="font-semibold">Upload Dataset File</h2>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">File (CSV, JSON, JSONL)</label>
              <input type="file" accept=".csv,.json,.jsonl" onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Dataset Name</label>
              <input value={uploadName} onChange={(e) => setUploadName(e.target.value)} placeholder="My dataset"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Description</label>
              <input value={uploadDesc} onChange={(e) => setUploadDesc(e.target.value)} placeholder="Optional"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
            </div>
            {uploadMutation.isError && <p className="text-xs text-red-600">{(uploadMutation.error as Error).message}</p>}
            <div className="flex gap-2 justify-end">
              <button onClick={() => setUploadOpen(false)} className="text-sm px-4 py-2 border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
              <button onClick={() => uploadMutation.mutate()} disabled={!uploadFile || !uploadName || uploadMutation.isPending}
                className="flex items-center gap-2 text-sm bg-brand-600 text-white px-4 py-2 rounded-lg hover:bg-brand-500 disabled:opacity-50">
                {uploadMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} Upload
              </button>
            </div>
          </div>
        </div>
      )}

      {/* New Dataset Dialog */}
      {newOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl border border-gray-200 p-6 w-full max-w-md space-y-4">
            <h2 className="font-semibold">New Dataset</h2>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Name</label>
              <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Dataset name"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Description</label>
              <input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="Optional"
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
