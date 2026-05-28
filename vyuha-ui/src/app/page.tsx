"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { AlertTriangle, CheckCircle, TrendingUp, Zap } from "lucide-react";

function StatCard({ label, value, sub, accent }: { label: string; value: string | number; sub?: string; accent?: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${accent ?? "text-gray-900"}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const { data: scorecard } = useQuery({ queryKey: ["scorecard"], queryFn: api.reports.executiveScorecard });
  const { data: summary } = useQuery({ queryKey: ["summary"], queryFn: api.reports.summary });
  const { data: rca } = useQuery({ queryKey: ["rca"], queryFn: api.reports.rcaBreakdown });

  const passRate = summary?.pass_rate ?? 0;
  const threshold = 0.97;
  const gateColor = passRate >= threshold ? "text-green-600" : "text-red-600";
  const gateLabel = passRate >= threshold ? "Above regression threshold" : "BELOW regression threshold — gate blocked";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Executive Scorecard</h1>
        <p className="text-sm text-gray-500 mt-0.5">Live quality score across all test runs</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Quality Score" value={`${scorecard?.overall_quality_score ?? 0}%`} accent="text-brand-600" />
        <StatCard
          label="Pass Rate"
          value={`${((summary?.pass_rate ?? 0) * 100).toFixed(1)}%`}
          sub={gateLabel}
          accent={gateColor}
        />
        <StatCard label="Critical Failures" value={scorecard?.critical_failures ?? 0} accent={(scorecard?.critical_failures ?? 0) > 0 ? "text-red-600" : "text-gray-900"} />
        <StatCard label="Total Runs" value={summary?.total_runs ?? 0} />
      </div>

      <div className="grid grid-cols-3 gap-4">
        <StatCard label="EVA-A (Accuracy)" value={`${((summary?.avg_eva_a ?? 0) * 100).toFixed(1)}%`} sub="Task completion + faithfulness + speech fidelity" />
        <StatCard label="EVA-X (Experience)" value={`${((summary?.avg_eva_x ?? 0) * 100).toFixed(1)}%`} sub="Conciseness + progression + turn-taking" />
        <StatCard label="P95 Latency" value={`${summary?.avg_latency_p95_ms?.toFixed(0) ?? 0}ms`} sub="Target: < 800ms" accent={(summary?.avg_latency_p95_ms ?? 0) > 800 ? "text-red-600" : "text-gray-900"} />
      </div>

      {(scorecard?.critical_failures ?? 0) > 0 && (
        <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-xl p-4 text-red-700">
          <AlertTriangle className="w-5 h-5 flex-shrink-0" />
          <span className="font-medium">{scorecard?.critical_failures} CRITICAL failure(s) detected — release is blocked until resolved</span>
        </div>
      )}

      {rca?.breakdown && rca.breakdown.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="font-semibold mb-4">Top Root Causes</h2>
          <div className="space-y-2">
            {rca.breakdown.slice(0, 5).map((item) => (
              <div key={item.rca_code} className="flex items-center gap-3">
                <span className="font-mono text-xs text-gray-500 w-28 flex-shrink-0">{item.rca_code}</span>
                <div className="flex-1 bg-gray-100 rounded-full h-2">
                  <div className="bg-brand-500 h-2 rounded-full" style={{ width: `${item.percentage}%` }} />
                </div>
                <span className="text-sm font-medium w-12 text-right">{item.count}</span>
                <span className="text-xs text-gray-400 w-10 text-right">{item.percentage}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!summary && (
        <div className="bg-white rounded-xl border border-gray-200 p-10 text-center text-gray-400">
          <p className="font-medium">No data yet.</p>
          <p className="text-sm mt-1">Generate test cases and start a run to see results here.</p>
        </div>
      )}
    </div>
  );
}
