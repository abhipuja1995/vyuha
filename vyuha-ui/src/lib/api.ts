// Use the Next.js server-side proxy route so VYUHA_API_URL is read at runtime
// (not frozen at Docker build time). Works identically in local dev and prod.
const API_BASE = "/api/proxy";

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ─── Types ────────────────────────────────────────────────────────────────────

export type TestCategory = "HAPPY_PATH" | "EDGE_CASE" | "FAILURE_MODE" | "CRITICAL" | "REGRESSION";
export type Language = "te" | "ta" | "hi" | "or" | "kn" | "ml" | "mr" | "bn" | "en-IN" | "en";
export type NoiseProfile = "quiet_indoor" | "moderate_indoor" | "busy_outdoor" | "call_centre" | "mobile_degraded" | "speakerphone";
export type Emotion = "neutral" | "frustrated" | "anxious" | "urgent" | "calm" | "distressed";
export type Verdict = "PASS" | "FAIL" | "ERROR" | "INVALID";

export interface PersonaConfig {
  language: Language;
  accent_variant: string;
  noise_profile: NoiseProfile;
  emotion: Emotion;
  speaking_rate: number;
  interruption_tendency: number;
  backstory: string;
  code_switch?: {
    primary_language: Language;
    secondary_language: Language;
    switch_probability: number;
  } | null;
}

export interface ConversationNode {
  node_id: string;
  utterance_template: string;
  is_terminal: boolean;
  audio_file?: string | null;
}

export interface ConversationEdge {
  from_node: string;
  to_node: string;
  condition: string;
}

export interface ConversationGraph {
  start_node: string;
  nodes: ConversationNode[];
  edges: ConversationEdge[];
}

export interface TestCase {
  test_id: string;
  title: string;
  category: TestCategory;
  user_goal: string;
  persona_config: PersonaConfig;
  conversation_graph: ConversationGraph;
  tool_call_sequence: Array<{ tool_name: string; is_required: boolean }>;
  ground_truth_end_state: Record<string, unknown>;
  pass_criteria: string;
  created_by: string;
  tags: string[];
  linked_production_call: string | null;
  created_at: string;
}

export interface EvaAScore { task_completion: number; faithfulness: number; speech_fidelity: number; }
export interface EvaXScore { conciseness: number; conversation_progression: number; turn_taking: number; }
export interface RunResult {
  run_id: string;
  test_id: string;
  verdict: Verdict;
  eva_a: EvaAScore;
  eva_x: EvaXScore;
  failure_report?: {
    failed_criterion: string;
    failure_turn_index: number;
    failure_excerpt: string;
    rca_tags: Array<{ code: string; description: string; confidence: number }>;
  } | null;
}

export interface IngestResult {
  ingested: boolean;
  call_id?: string;
  audio_path?: string;
  test_case_id?: string;
  reason?: string;
  failure_signals?: string[];
  confidence?: number;
  persona?: Record<string, unknown>;
  test_case?: TestCase;
  saved?: boolean;
  stt?: string;
}

export interface Summary {
  total_runs: number;
  passed: number;
  failed: number;
  pass_rate: number;
  critical_failures: number;
  avg_eva_a: number;
  avg_eva_x: number;
  avg_latency_p95_ms: number;
}

// ─── API functions ────────────────────────────────────────────────────────────

// ─── Provider Settings ────────────────────────────────────────────────────────

export interface ProviderEntry {
  provider: string;
  configured: boolean;
  ok?: boolean;
  url?: string | null;
  model?: string;
  error?: string;
  available_models?: string[];
  reachable?: boolean;
  api_key_set?: boolean;
  // STT-specific
  llm_url?: string | null;
  llm_model?: string;
  whisper_available?: boolean;
  // TTS/Azure-specific
  region?: string;
  voice?: string;
  note?: string;
  status_code?: number;
}

export interface ProviderStatus {
  llm: { primary: ProviderEntry; fallback: ProviderEntry; local: ProviderEntry };
  stt: { ollama_whisper: ProviderEntry };
  tts: { local: ProviderEntry; sarvam: ProviderEntry; azure: ProviderEntry };
  active_providers: { llm_judge: string; stt: string; tts: string };
}

export interface ProviderConfig {
  local_llm_url?: string;
  local_llm_model?: string;
  local_tts_url?: string;
  local_tts_voice?: string;
  ollama_url?: string;
  ollama_stt_model?: string;
  ollama_llm_url?: string;
  ollama_llm_model?: string;
}

export interface ActiveLLM {
  provider: string;     // e.g. "claude/claude-sonnet-4-6" or "ollama/llama3.2"
  configured: boolean;
  label: string;
}

export const api = {
  testCases: {
    list: (params?: { category?: TestCategory; language?: Language; tag?: string }) =>
      apiFetch<TestCase[]>(`/test-cases/${params ? "?" + new URLSearchParams(params as Record<string, string>) : ""}`),
    get: (id: string) => apiFetch<TestCase>(`/test-cases/${id}`),
    create: (body: unknown) => apiFetch<TestCase>("/test-cases/", { method: "POST", body: JSON.stringify(body) }),
    delete: (id: string) => apiFetch<{ deleted: string }>(`/test-cases/${id}`, { method: "DELETE" }),
  },
  runs: {
    start: (body: { test_id: string; k?: number; mode?: string }) =>
      apiFetch<{ task_ids: string[] }>("/runs/", { method: "POST", body: JSON.stringify(body) }),
    get: (id: string) => apiFetch<RunResult>(`/runs/${id}`),
    forTest: (testId: string) => apiFetch<RunResult[]>(`/runs/for-test/${testId}`),
  },
  reports: {
    summary: () => apiFetch<Summary>("/reports/summary"),
    rcaBreakdown: () => apiFetch<{ breakdown: Array<{ rca_code: string; count: number; percentage: number }> }>("/reports/rca-breakdown"),
    executiveScorecard: () => apiFetch<{ overall_quality_score: number; pass_rate_pct: number; critical_failures: number; top_3_rca_codes: unknown[] }>("/reports/executive-scorecard"),
  },
  generate: {
    fromPrompt: (body: { system_prompt: string; language?: Language; count?: number; knowledge_base?: string; use_cases?: string }) =>
      apiFetch<TestCase[]>("/generate/from-prompt", { method: "POST", body: JSON.stringify(body) }),
  },
  ingest: {
    call: (body: unknown) => apiFetch<IngestResult>("/ingest/call", { method: "POST", body: JSON.stringify(body) }),
    upload: (params: {
      audioFile: File;
      callId?: string;
      agentId?: string;
      languageDetected?: string;
      taskCompleted?: boolean;
      transcriptJson?: string;
    }) => {
      const form = new FormData();
      form.append("audio_file", params.audioFile);
      if (params.callId) form.append("call_id", params.callId);
      if (params.agentId) form.append("agent_id", params.agentId ?? "unknown-agent");
      form.append("language_detected", params.languageDetected ?? "en-IN");
      form.append("task_completed", String(params.taskCompleted ?? false));
      form.append("transcript_json", params.transcriptJson ?? "[]");
      return fetch(`${API_BASE}/ingest/upload`, { method: "POST", body: form })
        .then(async (r) => {
          if (!r.ok) throw new Error(`API ${r.status}: ${await r.text()}`);
          return r.json() as Promise<IngestResult>;
        });
    },
  },
  settings: {
    providers: () => apiFetch<ProviderStatus>("/settings/providers"),
    updateProviders: (config: ProviderConfig) =>
      apiFetch<{ updated: Record<string, string>; message: string }>("/settings/providers", {
        method: "POST",
        body: JSON.stringify(config),
      }),
    testLLM: () => apiFetch<Record<string, ProviderEntry>>("/settings/providers/test/llm"),
    testSTT: () => apiFetch<ProviderEntry>("/settings/providers/test/stt"),
    testTTS: () => apiFetch<Record<string, ProviderEntry>>("/settings/providers/test/tts"),
  },
  audio: {
    upload: (testId: string, nodeId: string, file: File) => {
      const form = new FormData();
      form.append("file", file);
      return fetch(`${API_BASE}/test-cases/${testId}/nodes/${nodeId}/audio`, { method: "POST", body: form })
        .then(async (r) => {
          if (!r.ok) throw new Error(`API ${r.status}: ${await r.text()}`);
          return r.json() as Promise<{ audio_file: string; size_bytes: number }>;
        });
    },
    url: (testId: string, nodeId: string) => `${API_BASE}/test-cases/${testId}/nodes/${nodeId}/audio`,
    delete: (testId: string, nodeId: string) =>
      apiFetch<{ deleted: boolean }>(`/test-cases/${testId}/nodes/${nodeId}/audio`, { method: "DELETE" }),
  },
};
