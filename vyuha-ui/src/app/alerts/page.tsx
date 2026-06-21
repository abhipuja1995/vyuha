"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, AlertMonitor } from "@/lib/api";
import { Bell, Plus, Trash2, Loader2, Volume2, VolumeX } from "lucide-react";
import { clsx } from "clsx";

function fmtDate(s: string) { return new Date(s).toLocaleDateString(); }

type CheckResult = { status: string; current_value: number; metric_type: string; checked_at: string };

export default function AlertsPage() {
  const qc = useQueryClient();
  const { data: alerts = [], isLoading, error } = useQuery({ queryKey: ["alerts"], queryFn: api.alerts.list });

  const [newOpen, setNewOpen] = useState(false);
  const [checkResults, setCheckResults] = useState<Record<string, CheckResult>>({});

  const [form, setForm] = useState<Partial<AlertMonitor>>({
    name: "",
    metric_type: "pass_rate",
    threshold_operator: "less_than",
    warning_threshold: 0.9,
    critical_threshold: 0.8,
    check_interval_minutes: 60,
    notification_emails: [],
    is_muted: false,
  });
  const [emailsInput, setEmailsInput] = useState("");

  const createMutation = useMutation({
    mutationFn: () => api.alerts.create({ ...form, notification_emails: emailsInput.split(",").map((e) => e.trim()).filter(Boolean) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["alerts"] }); setNewOpen(false); },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.alerts.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  const muteMutation = useMutation({
    mutationFn: (id: string) => api.alerts.mute(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  const checkMutation = useMutation({
    mutationFn: (id: string) => api.alerts.check(id),
    onSuccess: (data, id) => setCheckResults((prev) => ({ ...prev, [id]: data })),
  });

  const STATUS_COLORS: Record<string, string> = {
    ok: "bg-green-100 text-green-700",
    warning: "bg-yellow-100 text-yellow-700",
    critical: "bg-red-100 text-red-700",
  };

  return (
    <div className="space-y-5 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Alerts</h1>
          <p className="text-sm text-gray-500 mt-0.5">Threshold-based monitors for key metrics</p>
        </div>
        <button onClick={() => setNewOpen(true)} className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium px-3 py-2 rounded-lg">
          <Plus className="w-4 h-4" /> New Alert
        </button>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">{(error as Error).message}</div>}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {isLoading ? (
          <div className="p-10 text-center text-gray-400 flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
        ) : alerts.length === 0 ? (
          <div className="p-10 text-center text-gray-400">No alerts configured yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Name</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Metric</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Thresholds</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Interval</th>
                <th className="text-center px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Muted</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wide">Created</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {alerts.map((a) => (
                <tr key={a.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">
                    <div className="flex items-center gap-2">
                      <Bell className="w-4 h-4 text-brand-400 flex-shrink-0" />
                      <span>{a.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">{a.metric_type}</span>
                    <span className="text-xs text-gray-400 ml-1">{a.threshold_operator}</span>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {a.warning_threshold != null && <span className="text-yellow-600">warn: {a.warning_threshold} </span>}
                    {a.critical_threshold != null && <span className="text-red-600">crit: {a.critical_threshold}</span>}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-500 text-xs">{a.check_interval_minutes}min</td>
                  <td className="px-4 py-3 text-center">
                    <button onClick={() => muteMutation.mutate(a.id)} title={a.is_muted ? "Unmute" : "Mute"}
                      className={clsx("p-1 rounded", a.is_muted ? "text-gray-400 hover:text-brand-600" : "text-brand-500 hover:text-gray-400")}>
                      {a.is_muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{fmtDate(a.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 justify-end">
                      {checkResults[a.id] && (
                        <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", STATUS_COLORS[checkResults[a.id].status] ?? "bg-gray-100 text-gray-600")}>
                          {checkResults[a.id].status}: {checkResults[a.id].current_value}
                        </span>
                      )}
                      <button onClick={() => checkMutation.mutate(a.id)} disabled={checkMutation.isPending}
                        className="text-xs border border-gray-200 px-2.5 py-1 rounded-lg hover:bg-gray-100 flex items-center gap-1">
                        {checkMutation.isPending && checkMutation.variables === a.id ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                        Check
                      </button>
                      <button onClick={() => deleteMutation.mutate(a.id)} disabled={deleteMutation.isPending}
                        className="text-gray-400 hover:text-red-500 p-1">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {newOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl border border-gray-200 p-6 w-full max-w-md space-y-4 max-h-[90vh] overflow-y-auto">
            <h2 className="font-semibold">New Alert Monitor</h2>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Name</label>
              <input value={form.name ?? ""} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Alert name"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-gray-600 block mb-1">Metric Type</label>
                <select value={form.metric_type} onChange={(e) => setForm({ ...form, metric_type: e.target.value })} className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2">
                  <option value="pass_rate">pass_rate</option>
                  <option value="latency">latency</option>
                  <option value="error_rate">error_rate</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 block mb-1">Operator</label>
                <select value={form.threshold_operator} onChange={(e) => setForm({ ...form, threshold_operator: e.target.value })} className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2">
                  <option value="less_than">less_than</option>
                  <option value="greater_than">greater_than</option>
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-gray-600 block mb-1">Warning Threshold</label>
                <input type="number" step="0.01" value={form.warning_threshold ?? ""} onChange={(e) => setForm({ ...form, warning_threshold: parseFloat(e.target.value) })}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 block mb-1">Critical Threshold</label>
                <input type="number" step="0.01" value={form.critical_threshold ?? ""} onChange={(e) => setForm({ ...form, critical_threshold: parseFloat(e.target.value) })}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
              </div>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Check Interval (minutes)</label>
              <input type="number" value={form.check_interval_minutes ?? 60} onChange={(e) => setForm({ ...form, check_interval_minutes: parseInt(e.target.value) })}
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Notification Emails (comma-separated)</label>
              <input value={emailsInput} onChange={(e) => setEmailsInput(e.target.value)} placeholder="a@example.com, b@example.com"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
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
