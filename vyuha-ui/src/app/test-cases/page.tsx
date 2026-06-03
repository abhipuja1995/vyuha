"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, TestCase, TestCategory, Language } from "@/lib/api";
import { Plus, Play, Trash2, ChevronRight, GitBranch } from "lucide-react";
import Link from "next/link";
import { clsx } from "clsx";

const CATEGORY_CLASSES: Record<TestCategory, string> = {
  HAPPY_PATH: "badge-happy",
  EDGE_CASE: "badge-edge",
  FAILURE_MODE: "badge-failure",
  CRITICAL: "badge-critical",
  REGRESSION: "badge-regression",
};

const LANGUAGE_NAMES: Record<string, string> = {
  "te": "Telugu", "ta": "Tamil", "hi": "Hindi", "or": "Odia",
  "kn": "Kannada", "ml": "Malayalam", "mr": "Marathi", "bn": "Bengali",
  "en-IN": "English (Indian)", "en": "English",
};

export default function TestCasesPage() {
  const qc = useQueryClient();
  const [categoryFilter, setCategoryFilter] = useState<TestCategory | "">("");
  const [langFilter, setLangFilter] = useState<Language | "">("");

  const { data: cases = [], isLoading } = useQuery({
    queryKey: ["test-cases", categoryFilter, langFilter],
    queryFn: () => api.testCases.list({
      ...(categoryFilter ? { category: categoryFilter } : {}),
      ...(langFilter ? { language: langFilter } : {}),
    }),
  });

  const runMutation = useMutation({
    mutationFn: (testId: string) => api.runs.start({ test_id: testId, k: 3 }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["summary"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: api.testCases.delete,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["test-cases"] }),
  });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Test Cases</h1>
          <p className="text-sm text-gray-500 mt-0.5">{cases.length} cases in library</p>
        </div>
        <div className="flex gap-2">
          <Link href="/workflows" className="flex items-center gap-2 border border-gray-200 hover:bg-gray-50 text-gray-700 text-sm font-medium px-4 py-2 rounded-lg transition-colors">
            <GitBranch className="w-4 h-4" /> Import Workflow
          </Link>
          <Link href="/test-cases/new" className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors">
            <Plus className="w-4 h-4" /> New Test Case
          </Link>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value as TestCategory | "")}
          className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white"
        >
          <option value="">All categories</option>
          {(["HAPPY_PATH", "EDGE_CASE", "FAILURE_MODE", "CRITICAL", "REGRESSION"] as TestCategory[]).map((c) => (
            <option key={c} value={c}>{c.replace("_", " ")}</option>
          ))}
        </select>
        <select
          value={langFilter}
          onChange={(e) => setLangFilter(e.target.value as Language | "")}
          className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white"
        >
          <option value="">All languages</option>
          {Object.entries(LANGUAGE_NAMES).map(([code, name]) => (
            <option key={code} value={code}>{name}</option>
          ))}
        </select>
      </div>

      {isLoading && <p className="text-gray-400 text-sm">Loading...</p>}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {cases.length === 0 && !isLoading ? (
          <div className="p-10 text-center text-gray-400">
            <p className="font-medium">No test cases found.</p>
            <p className="text-sm mt-1">Generate from an agent prompt or create manually.</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600 w-10">#</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Title</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Category</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Language</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Noise</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Tags</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {cases.map((tc, i) => (
                <tr key={tc.test_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-gray-400 font-mono text-xs">{i + 1}</td>
                  <td className="px-4 py-3">
                    <Link href={`/test-cases/${tc.test_id}`} className="font-medium text-brand-600 hover:underline">
                      {tc.title}
                    </Link>
                    <p className="text-xs text-gray-400 mt-0.5 truncate max-w-xs">{tc.user_goal}</p>
                  </td>
                  <td className="px-4 py-3">
                    <span className={CATEGORY_CLASSES[tc.category]}>{tc.category.replace("_", " ")}</span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{LANGUAGE_NAMES[tc.persona_config.language] ?? tc.persona_config.language}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{tc.persona_config.noise_profile.replace("_", " ")}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {tc.tags.slice(0, 3).map((tag) => (
                        <span key={tag} className="bg-gray-100 text-gray-600 text-xs px-1.5 py-0.5 rounded">{tag}</span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 justify-end">
                      <button
                        onClick={() => runMutation.mutate(tc.test_id)}
                        disabled={runMutation.isPending}
                        title="Run (k=3)"
                        className="p-1.5 text-gray-400 hover:text-brand-600 hover:bg-brand-50 rounded transition-colors"
                      >
                        <Play className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => { if (confirm("Delete this test case?")) deleteMutation.mutate(tc.test_id); }}
                        title="Delete"
                        className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                      <Link href={`/test-cases/${tc.test_id}`} className="p-1.5 text-gray-400 hover:text-gray-700 rounded transition-colors">
                        <ChevronRight className="w-4 h-4" />
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
