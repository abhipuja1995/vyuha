"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api, ConversationGraph, Language, Emotion, NoiseProfile, TestCategory } from "@/lib/api";
import { ConversationGraphEditor } from "@/components/graph/ConversationGraphEditor";

const DEFAULT_GRAPH: ConversationGraph = {
  start_node: "n1",
  nodes: [
    { node_id: "n1", utterance_template: "Hello, I need help with...", is_terminal: false },
    { node_id: "n2", utterance_template: "Thank you, goodbye.", is_terminal: true },
  ],
  edges: [{ from_node: "n1", to_node: "n2", condition: "agent greets" }],
};

export default function NewTestCasePage() {
  const router = useRouter();
  const qc = useQueryClient();

  const [form, setForm] = useState({
    title: "",
    category: "HAPPY_PATH" as TestCategory,
    user_goal: "",
    pass_criteria: "",
    tags: "",
    language: "en-IN" as Language,
    accent_variant: "",
    noise_profile: "quiet_indoor" as NoiseProfile,
    emotion: "neutral" as Emotion,
    speaking_rate: 1.0,
    backstory: "",
  });
  const [graph, setGraph] = useState<ConversationGraph>(DEFAULT_GRAPH);
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: (body: unknown) => api.testCases.create(body),
    onSuccess: (tc) => {
      qc.invalidateQueries({ queryKey: ["test-cases"] });
      router.push(`/test-cases/${tc.test_id}`);
    },
    onError: (err: Error) => setError(err.message),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    createMutation.mutate({
      title: form.title,
      category: form.category,
      user_goal: form.user_goal,
      pass_criteria: form.pass_criteria,
      tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
      created_by: "analyst",
      persona_config: {
        language: form.language,
        accent_variant: form.accent_variant,
        noise_profile: form.noise_profile,
        emotion: form.emotion,
        speaking_rate: form.speaking_rate,
        interruption_tendency: 0.1,
        backstory: form.backstory,
      },
      conversation_graph: graph,
      tool_call_sequence: [],
      ground_truth_end_state: {},
    });
  };

  const field = (name: keyof typeof form, label: string, type = "text", options?: string[]) => (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      {options ? (
        <select
          value={form[name] as string}
          onChange={(e) => setForm({ ...form, [name]: e.target.value })}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
        >
          {options.map((o) => <option key={o} value={o}>{o.replace(/_/g, " ")}</option>)}
        </select>
      ) : (
        <input
          type={type}
          value={form[name] as string | number}
          step={type === "number" ? 0.1 : undefined}
          min={type === "number" ? 0.5 : undefined}
          max={type === "number" ? 2.0 : undefined}
          onChange={(e) => setForm({ ...form, [name]: type === "number" ? parseFloat(e.target.value) : e.target.value })}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
        />
      )}
    </div>
  );

  return (
    <form onSubmit={handleSubmit} className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">New Test Case</h1>
        <p className="text-sm text-gray-500 mt-0.5">Design a conversation test case without writing code</p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg p-3 text-sm">{error}</div>
      )}

      {/* Basic info */}
      <section className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
        <h2 className="font-semibold text-gray-800">Basic Info</h2>
        {field("title", "Title *")}
        {field("category", "Category", "text", ["HAPPY_PATH", "EDGE_CASE", "FAILURE_MODE", "CRITICAL", "REGRESSION"])}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">User Goal *</label>
          <textarea
            value={form.user_goal}
            onChange={(e) => setForm({ ...form, user_goal: e.target.value })}
            rows={2}
            placeholder="What is the caller trying to achieve?"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Pass Criteria *</label>
          <textarea
            value={form.pass_criteria}
            onChange={(e) => setForm({ ...form, pass_criteria: e.target.value })}
            rows={2}
            placeholder="Explicit conditions for PASS verdict"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none"
          />
        </div>
        {field("tags", "Tags (comma-separated)", "text")}
      </section>

      {/* Persona */}
      <section className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
        <h2 className="font-semibold text-gray-800">Caller Persona</h2>
        <div className="grid grid-cols-2 gap-4">
          {field("language", "Language", "text", ["en-IN", "hi", "te", "ta", "or", "kn", "ml", "mr", "bn"])}
          {field("accent_variant", "Accent Variant", "text")}
          {field("noise_profile", "Noise Profile", "text", ["quiet_indoor", "moderate_indoor", "busy_outdoor", "call_centre", "mobile_degraded", "speakerphone"])}
          {field("emotion", "Emotion", "text", ["neutral", "frustrated", "anxious", "urgent", "calm", "distressed"])}
          {field("speaking_rate", "Speaking Rate", "number")}
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Backstory</label>
          <textarea
            value={form.backstory}
            onChange={(e) => setForm({ ...form, backstory: e.target.value })}
            rows={2}
            placeholder="Why is this caller reaching out?"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none"
          />
        </div>
      </section>

      {/* Conversation graph */}
      <section className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
        <h2 className="font-semibold text-gray-800">Conversation Flow</h2>
        <p className="text-xs text-gray-500">Add caller utterances as nodes, then connect them by dragging between handles.</p>
        <ConversationGraphEditor value={graph} onChange={setGraph} />
      </section>

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={createMutation.isPending || !form.title || !form.user_goal}
          className="bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-6 py-2.5 rounded-lg transition-colors"
        >
          {createMutation.isPending ? "Saving…" : "Save Test Case"}
        </button>
        <button
          type="button"
          onClick={() => router.back()}
          className="text-sm text-gray-600 hover:text-gray-800 px-4 py-2.5 rounded-lg border border-gray-200 hover:border-gray-300 transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
