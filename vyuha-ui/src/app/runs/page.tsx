"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { CheckCircle, XCircle, AlertCircle } from "lucide-react";

const VERDICT_ICON = {
  PASS: <CheckCircle className="w-4 h-4 text-green-500" />,
  FAIL: <XCircle className="w-4 h-4 text-red-500" />,
  ERROR: <AlertCircle className="w-4 h-4 text-yellow-500" />,
  INVALID: <AlertCircle className="w-4 h-4 text-gray-400" />,
};

export default function RunsPage() {
  const { data: summary } = useQuery({ queryKey: ["summary"], queryFn: api.reports.summary });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Test Runs</h1>
        <p className="text-sm text-gray-500 mt-0.5">Aggregate results across all runs</p>
      </div>

      {summary ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            ["Total Runs", summary.total_runs, ""],
            ["Passed", summary.passed, "text-green-600"],
            ["Failed", summary.failed, "text-red-600"],
            ["Pass Rate", `${(summary.pass_rate * 100).toFixed(1)}%`, summary.pass_rate >= 0.97 ? "text-green-600" : "text-red-600"],
          ].map(([label, value, color]) => (
            <div key={label as string} className="bg-white rounded-xl border border-gray-200 p-5">
              <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
              <p className={`text-3xl font-bold mt-1 ${color}`}>{value}</p>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 p-10 text-center text-gray-400">
          No runs yet. Go to Test Cases and click the run button.
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h2 className="font-semibold mb-3">Run a test case from here</h2>
        <p className="text-sm text-gray-500">
          Click the <span className="inline-flex items-center gap-1 font-medium">▶ run</span> button on any test case
          in the Test Cases page to trigger k=3 runs via Celery. Task status is polled at{" "}
          <code className="text-xs bg-gray-100 px-1 py-0.5 rounded">GET /runs/task/&#123;task_id&#125;</code>.
        </p>
      </div>
    </div>
  );
}
