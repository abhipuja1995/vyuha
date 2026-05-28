"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, TestCase, Language } from "@/lib/api";
import { Wand2, CheckCircle } from "lucide-react";

export default function GeneratePage() {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    system_prompt: "",
    knowledge_base: "",
    use_cases: "",
    language: "en-IN" as Language,
    count: 50,
  });
  const [results, setResults] = useState<TestCase[] | null>(null);

  const mutation = useMutation({
    mutationFn: () => api.generate.fromPrompt(form),
    onSuccess: (data) => {
      setResults(data);
      qc.invalidateQueries({ queryKey: ["test-cases"] });
    },
  });

  const catCount = (cat: string) => results?.filter((tc) => tc.category === cat).length ?? 0;

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Generate Test Cases</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Paste your voice agent's system prompt to auto-generate {form.count} test scenarios using Claude Sonnet 4.6.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">System Prompt *</label>
          <textarea
            value={form.system_prompt}
            onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
            rows={8}
            placeholder="Paste the voice agent's system prompt here (minimum 100 characters)…"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none font-mono"
          />
          <p className="text-xs text-gray-400 mt-1">{form.system_prompt.length} characters</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Knowledge Base (optional)</label>
          <textarea
            value={form.knowledge_base}
            onChange={(e) => setForm({ ...form, knowledge_base: e.target.value })}
            rows={3}
            placeholder="Paste relevant knowledge base content…"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none"
          />
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Primary Language</label>
            <select
              value={form.language}
              onChange={(e) => setForm({ ...form, language: e.target.value as Language })}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
            >
              {[["en-IN","English (Indian)"],["hi","Hindi"],["te","Telugu"],["ta","Tamil"],["or","Odia"],["kn","Kannada"],["ml","Malayalam"],["mr","Marathi"],["bn","Bengali"]].map(([v,l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Use Cases</label>
            <input
              value={form.use_cases}
              onChange={(e) => setForm({ ...form, use_cases: e.target.value })}
              placeholder="e.g. debt collection, banking"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Count</label>
            <input
              type="number"
              min={10}
              max={100}
              step={5}
              value={form.count}
              onChange={(e) => setForm({ ...form, count: parseInt(e.target.value) })}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
            />
          </div>
        </div>

        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending || form.system_prompt.length < 100}
          className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-5 py-2.5 rounded-lg transition-colors"
        >
          <Wand2 className="w-4 h-4" />
          {mutation.isPending ? `Generating ${form.count} test cases…` : `Generate ${form.count} Test Cases`}
        </button>
      </div>

      {mutation.isError && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">
          {(mutation.error as Error).message}
        </div>
      )}

      {results && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-green-600 font-medium">
            <CheckCircle className="w-5 h-5" />
            Generated {results.length} test cases
          </div>
          <div className="grid grid-cols-3 gap-3">
            {[["HAPPY_PATH","Happy Path","badge-happy"],["EDGE_CASE","Edge Case","badge-edge"],["FAILURE_MODE","Failure Mode","badge-failure"]].map(([cat, label, cls]) => (
              <div key={cat} className="bg-white border border-gray-200 rounded-xl p-4 text-center">
                <p className="text-2xl font-bold">{catCount(cat)}</p>
                <span className={cls}>{label}</span>
              </div>
            ))}
          </div>
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left px-4 py-2 text-gray-500 font-medium">Title</th>
                  <th className="text-left px-4 py-2 text-gray-500 font-medium">Category</th>
                  <th className="text-left px-4 py-2 text-gray-500 font-medium">ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {results.map((tc) => (
                  <tr key={tc.test_id} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5 font-medium">{tc.title}</td>
                    <td className="px-4 py-2.5">
                      <span className={tc.category === "HAPPY_PATH" ? "badge-happy" : tc.category === "EDGE_CASE" ? "badge-edge" : "badge-failure"}>
                        {tc.category.replace("_", " ")}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-400">{tc.test_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
