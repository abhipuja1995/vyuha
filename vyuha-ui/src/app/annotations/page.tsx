"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, AnnotationQueue, AnnotationItem } from "@/lib/api";
import { MessageSquare, Plus, Trash2, Loader2, ChevronRight } from "lucide-react";
import { clsx } from "clsx";

function fmtDate(s: string) { return new Date(s).toLocaleDateString(); }

const STATUS_COLORS: Record<string, string> = {
  open: "bg-blue-100 text-blue-700",
  in_progress: "bg-yellow-100 text-yellow-700",
  completed: "bg-green-100 text-green-700",
  pending: "bg-gray-100 text-gray-600",
};

const SOURCE_COLORS: Record<string, string> = {
  trace: "bg-purple-100 text-purple-700",
  span: "bg-blue-100 text-blue-700",
  run: "bg-green-100 text-green-700",
};

type QueueStats = { total: number; pending: number; completed: number; completion_rate: number };

export default function AnnotationsPage() {
  const qc = useQueryClient();
  const { data: queues = [], isLoading, error } = useQuery({ queryKey: ["annotation-queues"], queryFn: api.annotations.listQueues });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [newQueueOpen, setNewQueueOpen] = useState(false);
  const [addItemOpen, setAddItemOpen] = useState(false);
  const [annotateItem, setAnnotateItem] = useState<AnnotationItem | null>(null);

  // New queue form
  const [qName, setQName] = useState("");
  const [qDesc, setQDesc] = useState("");
  const [qLabels, setQLabels] = useState<Array<{ name: string; type: string; options: string }>>([{ name: "", type: "thumbs", options: "" }]);

  // Add item form
  const [itemSource, setItemSource] = useState("trace");
  const [itemSourceId, setItemSourceId] = useState("");

  // Annotate form
  const [annotateValues, setAnnotateValues] = useState<Record<string, string>>({});

  const createQueueMutation = useMutation({
    mutationFn: () => api.annotations.createQueue({
      name: qName,
      description: qDesc,
      labels: qLabels.map((l) => ({ name: l.name, type: l.type, ...(l.options ? { options: l.options.split(",").map((o) => o.trim()) } : {}) })),
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["annotation-queues"] }); setNewQueueOpen(false); },
  });

  const deleteQueueMutation = useMutation({
    mutationFn: (id: string) => api.annotations.deleteQueue(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["annotation-queues"] }); setSelectedId(null); },
  });

  const addItemMutation = useMutation({
    mutationFn: () => api.annotations.addItem(selectedId!, { source_type: itemSource, source_id: itemSourceId }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["annotation-queue", selectedId] }); setAddItemOpen(false); setItemSourceId(""); },
  });

  const { data: selectedQueue } = useQuery({
    queryKey: ["annotation-queue", selectedId],
    queryFn: () => api.annotations.getQueue(selectedId!),
    enabled: !!selectedId,
  });

  const { data: queueStats } = useQuery({
    queryKey: ["annotation-queue-stats", selectedId],
    queryFn: () => api.annotations.queueStats(selectedId!),
    enabled: !!selectedId,
  });

  const annotateMutation = useMutation({
    mutationFn: () => {
      if (!annotateItem || !selectedQueue) throw new Error("No item selected");
      const promises = selectedQueue.labels.map((label) =>
        api.annotations.annotate(selectedId!, annotateItem.id, {
          label: label.name,
          value: annotateValues[label.name] ?? "",
          annotator: "user",
          notes: "",
        })
      );
      return Promise.all(promises);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["annotation-queue", selectedId] });
      setAnnotateItem(null);
      setAnnotateValues({});
    },
  });

  const items = selectedQueue?.items ?? [];

  return (
    <div className="space-y-5 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Annotations</h1>
          <p className="text-sm text-gray-500 mt-0.5">Human review queues for LLM outputs</p>
        </div>
        <button onClick={() => setNewQueueOpen(true)} className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium px-3 py-2 rounded-lg">
          <Plus className="w-4 h-4" /> New Queue
        </button>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">{(error as Error).message}</div>}

      <div className="flex gap-4 h-[calc(100vh-200px)]">
        {/* Left: queue list */}
        <div className="w-72 flex-shrink-0 bg-white rounded-xl border border-gray-200 overflow-y-auto">
          {isLoading ? (
            <div className="p-6 text-center text-gray-400"><Loader2 className="w-4 h-4 animate-spin mx-auto" /></div>
          ) : queues.length === 0 ? (
            <div className="p-6 text-center text-gray-400 text-sm">No queues yet.</div>
          ) : queues.map((q) => (
            <button key={q.id} onClick={() => setSelectedId(q.id)}
              className={clsx("w-full text-left px-4 py-3 border-b border-gray-100 hover:bg-gray-50 transition-colors", selectedId === q.id && "bg-brand-50 border-l-2 border-l-brand-500")}>
              <div className="flex items-start gap-2">
                <MessageSquare className="w-4 h-4 text-gray-400 flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{q.name}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={clsx("text-xs px-1.5 py-0.5 rounded-full", STATUS_COLORS[q.status] ?? "bg-gray-100 text-gray-600")}>{q.status}</span>
                  </div>
                </div>
                <ChevronRight className="w-4 h-4 text-gray-300 flex-shrink-0" />
              </div>
            </button>
          ))}
        </div>

        {/* Right: queue detail */}
        <div className="flex-1 bg-white rounded-xl border border-gray-200 overflow-y-auto">
          {!selectedId ? (
            <div className="p-10 text-center text-gray-400">Select a queue to view items.</div>
          ) : (
            <div className="divide-y divide-gray-100">
              <div className="px-5 py-4 flex items-start gap-3">
                <div className="flex-1">
                  <h2 className="font-semibold">{selectedQueue?.name}</h2>
                  {selectedQueue?.description && <p className="text-sm text-gray-500">{selectedQueue.description}</p>}
                  <div className="flex flex-wrap gap-2 mt-2">
                    {selectedQueue?.labels.map((l) => (
                      <span key={l.name} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{l.name} ({l.type})</span>
                    ))}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setAddItemOpen(true)} className="flex items-center gap-1 text-xs border border-gray-200 px-2.5 py-1.5 rounded-lg hover:bg-gray-50">
                    <Plus className="w-3 h-3" /> Add Item
                  </button>
                  <button onClick={() => deleteQueueMutation.mutate(selectedId!)} disabled={deleteQueueMutation.isPending} className="text-gray-400 hover:text-red-500 p-1.5">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {queueStats && (
                <div className="px-5 py-3 bg-gray-50">
                  <div className="flex items-center gap-6 text-sm">
                    <div><span className="text-gray-500 text-xs">Total</span><p className="font-bold">{queueStats.total}</p></div>
                    <div><span className="text-gray-500 text-xs">Pending</span><p className="font-bold text-yellow-600">{queueStats.pending}</p></div>
                    <div><span className="text-gray-500 text-xs">Completed</span><p className="font-bold text-green-600">{queueStats.completed}</p></div>
                    <div className="flex-1">
                      <span className="text-gray-500 text-xs">Completion</span>
                      <div className="flex items-center gap-2 mt-0.5">
                        <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                          <div className="h-full bg-green-500 rounded-full" style={{ width: `${(queueStats.completion_rate * 100).toFixed(0)}%` }} />
                        </div>
                        <span className="text-xs font-medium">{(queueStats.completion_rate * 100).toFixed(0)}%</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {addItemOpen && (
                <div className="px-5 py-4 bg-gray-50 space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-medium text-gray-600 block mb-1">Source Type</label>
                      <select value={itemSource} onChange={(e) => setItemSource(e.target.value)} className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2">
                        <option value="trace">trace</option>
                        <option value="span">span</option>
                        <option value="run">run</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-xs font-medium text-gray-600 block mb-1">Source ID</label>
                      <input value={itemSourceId} onChange={(e) => setItemSourceId(e.target.value)} placeholder="ID of the source"
                        className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
                    </div>
                  </div>
                  <div className="flex gap-2 justify-end">
                    <button onClick={() => setAddItemOpen(false)} className="text-xs px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-100">Cancel</button>
                    <button onClick={() => addItemMutation.mutate()} disabled={!itemSourceId || addItemMutation.isPending}
                      className="flex items-center gap-1 text-xs bg-brand-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50">
                      {addItemMutation.isPending && <Loader2 className="w-3 h-3 animate-spin" />} Add
                    </button>
                  </div>
                </div>
              )}

              {items.length === 0 ? (
                <div className="px-5 py-10 text-center text-gray-400 text-sm">No items in this queue.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="text-left px-4 py-2 text-xs font-medium text-gray-500">Source</th>
                      <th className="text-left px-4 py-2 text-xs font-medium text-gray-500">Source ID</th>
                      <th className="text-left px-4 py-2 text-xs font-medium text-gray-500">Status</th>
                      <th className="text-right px-4 py-2 text-xs font-medium text-gray-500">Annotations</th>
                      <th className="px-4 py-2"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {items.map((item) => (
                      <tr key={item.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3">
                          <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", SOURCE_COLORS[item.source_type] ?? "bg-gray-100 text-gray-600")}>
                            {item.source_type}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-gray-500">{item.source_id.slice(0, 16)}…</td>
                        <td className="px-4 py-3">
                          <span className={clsx("text-xs px-2 py-0.5 rounded-full", STATUS_COLORS[item.status] ?? "bg-gray-100 text-gray-600")}>{item.status}</span>
                        </td>
                        <td className="px-4 py-3 text-right text-gray-500 text-xs">{item.annotations?.length ?? 0}</td>
                        <td className="px-4 py-3 text-right">
                          <button onClick={() => setAnnotateItem(item)} className="text-xs border border-brand-200 text-brand-600 px-2.5 py-1 rounded-lg hover:bg-brand-50">
                            Annotate
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      </div>

      {/* New Queue Dialog */}
      {newQueueOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl border border-gray-200 p-6 w-full max-w-lg space-y-4 max-h-[90vh] overflow-y-auto">
            <h2 className="font-semibold">New Annotation Queue</h2>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Name</label>
              <input value={qName} onChange={(e) => setQName(e.target.value)} placeholder="Queue name"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Description</label>
              <input value={qDesc} onChange={(e) => setQDesc(e.target.value)} placeholder="Optional"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-medium text-gray-600">Labels</label>
                <button onClick={() => setQLabels([...qLabels, { name: "", type: "thumbs", options: "" }])} className="text-xs text-brand-600 hover:underline flex items-center gap-1">
                  <Plus className="w-3 h-3" /> Add label
                </button>
              </div>
              <div className="space-y-2">
                {qLabels.map((l, i) => (
                  <div key={i} className="flex gap-2 items-start">
                    <input value={l.name} onChange={(e) => setQLabels(qLabels.map((ql, j) => j === i ? { ...ql, name: e.target.value } : ql))}
                      placeholder="Label name" className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 flex-1" />
                    <select value={l.type} onChange={(e) => setQLabels(qLabels.map((ql, j) => j === i ? { ...ql, type: e.target.value } : ql))}
                      className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 w-28">
                      <option value="thumbs">thumbs</option>
                      <option value="text">text</option>
                      <option value="categorical">categorical</option>
                      <option value="numeric">numeric</option>
                    </select>
                    {l.type === "categorical" && (
                      <input value={l.options} onChange={(e) => setQLabels(qLabels.map((ql, j) => j === i ? { ...ql, options: e.target.value } : ql))}
                        placeholder="opt1,opt2" className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 w-24" />
                    )}
                    <button onClick={() => setQLabels(qLabels.filter((_, j) => j !== i))} className="text-gray-400 hover:text-red-500 p-1">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
            {createQueueMutation.isError && <p className="text-xs text-red-600">{(createQueueMutation.error as Error).message}</p>}
            <div className="flex gap-2 justify-end">
              <button onClick={() => setNewQueueOpen(false)} className="text-sm px-4 py-2 border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
              <button onClick={() => createQueueMutation.mutate()} disabled={!qName || createQueueMutation.isPending}
                className="flex items-center gap-2 text-sm bg-brand-600 text-white px-4 py-2 rounded-lg hover:bg-brand-500 disabled:opacity-50">
                {createQueueMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Annotate Dialog */}
      {annotateItem && selectedQueue && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl border border-gray-200 p-6 w-full max-w-md space-y-4">
            <h2 className="font-semibold">Annotate Item</h2>
            <p className="text-xs text-gray-500 font-mono">{annotateItem.source_type}: {annotateItem.source_id}</p>
            {selectedQueue.labels.map((label) => (
              <div key={label.name}>
                <label className="text-xs font-medium text-gray-600 block mb-1">{label.name}</label>
                {label.type === "thumbs" ? (
                  <div className="flex gap-2">
                    {["thumbs_up", "thumbs_down"].map((v) => (
                      <button key={v} onClick={() => setAnnotateValues({ ...annotateValues, [label.name]: v })}
                        className={clsx("px-3 py-1.5 text-xs border rounded-lg", annotateValues[label.name] === v ? "bg-brand-600 text-white border-brand-600" : "border-gray-200 hover:bg-gray-50")}>
                        {v === "thumbs_up" ? "👍" : "👎"}
                      </button>
                    ))}
                  </div>
                ) : label.type === "categorical" && label.options ? (
                  <div className="flex flex-wrap gap-2">
                    {label.options.map((opt) => (
                      <button key={opt} onClick={() => setAnnotateValues({ ...annotateValues, [label.name]: opt })}
                        className={clsx("px-3 py-1.5 text-xs border rounded-lg", annotateValues[label.name] === opt ? "bg-brand-600 text-white border-brand-600" : "border-gray-200 hover:bg-gray-50")}>
                        {opt}
                      </button>
                    ))}
                  </div>
                ) : label.type === "numeric" ? (
                  <input type="number" value={annotateValues[label.name] ?? ""} onChange={(e) => setAnnotateValues({ ...annotateValues, [label.name]: e.target.value })}
                    className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
                ) : (
                  <input value={annotateValues[label.name] ?? ""} onChange={(e) => setAnnotateValues({ ...annotateValues, [label.name]: e.target.value })}
                    className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
                )}
              </div>
            ))}
            {annotateMutation.isError && <p className="text-xs text-red-600">{(annotateMutation.error as Error).message}</p>}
            <div className="flex gap-2 justify-end">
              <button onClick={() => setAnnotateItem(null)} className="text-sm px-4 py-2 border border-gray-200 rounded-lg hover:bg-gray-50">Cancel</button>
              <button onClick={() => annotateMutation.mutate()} disabled={annotateMutation.isPending}
                className="flex items-center gap-2 text-sm bg-brand-600 text-white px-4 py-2 rounded-lg hover:bg-brand-500 disabled:opacity-50">
                {annotateMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} Submit
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
