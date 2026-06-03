"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ProviderConfig, ProviderEntry } from "@/lib/api";
import {
  CheckCircle, XCircle, AlertCircle, RefreshCw, Save, Cpu, Mic, Volume2, ChevronDown, ChevronUp,
} from "lucide-react";
import { clsx } from "clsx";

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ ok, configured }: { ok?: boolean; configured?: boolean }) {
  if (!configured) return (
    <span className="inline-flex items-center gap-1 text-xs text-gray-400">
      <AlertCircle className="w-3.5 h-3.5" /> Not configured
    </span>
  );
  if (ok === undefined) return (
    <span className="inline-flex items-center gap-1 text-xs text-yellow-600">
      <AlertCircle className="w-3.5 h-3.5" /> Untested
    </span>
  );
  return ok ? (
    <span className="inline-flex items-center gap-1 text-xs text-green-600 font-medium">
      <CheckCircle className="w-3.5 h-3.5" /> Reachable
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-xs text-red-600 font-medium">
      <XCircle className="w-3.5 h-3.5" /> Unreachable
    </span>
  );
}

// ── Provider card ─────────────────────────────────────────────────────────────

function ProviderCard({
  label, badge, children, active,
}: { label: string; badge?: React.ReactNode; children: React.ReactNode; active?: boolean }) {
  return (
    <div className={clsx(
      "rounded-xl border p-4 space-y-2",
      active ? "border-brand-500 bg-brand-50" : "border-gray-200 bg-white"
    )}>
      <div className="flex items-center justify-between">
        <span className="font-medium text-sm">{label}</span>
        {badge}
      </div>
      {children}
    </div>
  );
}

// ── Info row ──────────────────────────────────────────────────────────────────

function InfoRow({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-2 text-xs">
      <span className="text-gray-500 w-28 flex-shrink-0">{label}</span>
      <span className="text-gray-800 font-mono break-all">{value}</span>
    </div>
  );
}

// ── Editable field ────────────────────────────────────────────────────────────

function Field({
  label, value, onChange, placeholder, type = "text",
}: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-gray-600">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2 font-mono bg-white focus:outline-none focus:border-brand-500"
      />
    </div>
  );
}

// ── Section header ────────────────────────────────────────────────────────────

function Section({ icon: Icon, title, active, children }: {
  icon: React.ElementType; title: string; active?: string; children: React.ReactNode;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Icon className="w-5 h-5 text-brand-500" />
        <h2 className="font-semibold text-base">{title}</h2>
        {active && (
          <span className="ml-auto text-xs bg-brand-100 text-brand-700 px-2 py-0.5 rounded-full font-medium">
            Active: {active}
          </span>
        )}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {children}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const qc = useQueryClient();
  const [config, setConfig] = useState<ProviderConfig>({});
  const [testResults, setTestResults] = useState<Record<string, Record<string, ProviderEntry>>>({});
  const [testing, setTesting] = useState<string | null>(null);
  const [showEnvHelp, setShowEnvHelp] = useState(false);

  const { data: status, isLoading, refetch } = useQuery({
    queryKey: ["provider-status"],
    queryFn: api.settings.providers,
    refetchInterval: false,
  });

  const updateMutation = useMutation({
    mutationFn: api.settings.updateProviders,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provider-status"] });
      refetch();
      setConfig({});
    },
  });

  const handleTest = async (type: "llm" | "stt" | "tts") => {
    setTesting(type);
    try {
      let result: Record<string, ProviderEntry>;
      if (type === "llm") result = await api.settings.testLLM();
      else if (type === "stt") result = { ollama: await api.settings.testSTT() };
      else result = await api.settings.testTTS();
      setTestResults((prev) => ({ ...prev, [type]: result }));
    } finally {
      setTesting(null);
    }
  };

  const set = (key: keyof ProviderConfig) => (v: string) =>
    setConfig((prev) => ({ ...prev, [key]: v }));

  const hasChanges = Object.keys(config).some((k) => config[k as keyof ProviderConfig] !== undefined && config[k as keyof ProviderConfig] !== "");

  if (isLoading) return <div className="text-gray-400 text-sm p-6">Loading provider status…</div>;

  const active = status?.active_providers;

  return (
    <div className="space-y-8 max-w-5xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">Providers & Settings</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Configure LLM, STT, and TTS providers. Changes take effect immediately (until next restart).
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 border border-gray-200 px-3 py-1.5 rounded-lg"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {/* ── LLM Judges ── */}
      <Section icon={Cpu} title="LLM Judges" active={active?.llm_judge}>
        <ProviderCard
          label="Anthropic Claude"
          active={active?.llm_judge === "anthropic"}
          badge={<StatusBadge configured={status?.llm.primary.api_key_set} ok={testResults.llm?.anthropic?.ok} />}
        >
          <InfoRow label="Model" value={status?.llm.primary.model} />
          <InfoRow label="Key" value={status?.llm.primary.api_key_set ? "●●●●●●●● (set)" : "Not set"} />
          {testResults.llm?.anthropic?.error && (
            <p className="text-xs text-red-500">{testResults.llm.anthropic.error}</p>
          )}
        </ProviderCard>

        <ProviderCard
          label="OpenAI GPT (fallback)"
          active={active?.llm_judge === "openai"}
          badge={<StatusBadge configured={status?.llm.fallback.api_key_set} ok={testResults.llm?.openai?.ok} />}
        >
          <InfoRow label="Model" value={status?.llm.fallback.model} />
          <InfoRow label="Key" value={status?.llm.fallback.api_key_set ? "●●●●●●●● (set)" : "Not set"} />
          {testResults.llm?.openai?.error && (
            <p className="text-xs text-red-500">{testResults.llm.openai.error}</p>
          )}
        </ProviderCard>

        <ProviderCard
          label="Local Ollama LLM"
          active={active?.llm_judge === "local"}
          badge={<StatusBadge configured={status?.llm.local.configured} ok={status?.llm.local.ok} />}
        >
          <InfoRow label="URL" value={status?.llm.local.url} />
          <InfoRow label="Model" value={status?.llm.local.model} />
          {status?.llm.local.available_models && status.llm.local.available_models.length > 0 && (
            <div className="text-xs text-gray-500">
              {status.llm.local.available_models.slice(0, 4).join(", ")}
            </div>
          )}
          {testResults.llm?.local?.error && (
            <p className="text-xs text-red-500">{testResults.llm.local.error}</p>
          )}
          <div className="pt-2 space-y-2 border-t border-gray-100">
            <Field label="Ollama URL" value={config.local_llm_url ?? ""} onChange={set("local_llm_url")}
              placeholder="http://host.docker.internal:11434/v1" />
            <Field label="Model" value={config.local_llm_model ?? ""} onChange={set("local_llm_model")}
              placeholder="llama3.2" />
          </div>
        </ProviderCard>

        <div className="md:col-span-2 xl:col-span-3 flex justify-end">
          <button
            onClick={() => handleTest("llm")}
            disabled={testing === "llm"}
            className="flex items-center gap-2 text-sm border border-gray-200 px-4 py-1.5 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            {testing === "llm" ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />}
            Test all LLM connections
          </button>
        </div>
      </Section>

      {/* ── STT ── */}
      <Section icon={Mic} title="Speech-to-Text (STT)" active={active?.stt}>
        <ProviderCard
          label="Ollama Whisper (local)"
          active={active?.stt === "ollama"}
          badge={<StatusBadge configured={status?.stt.ollama_whisper.configured} ok={status?.stt.ollama_whisper.ok ?? testResults.stt?.ollama?.ok} />}
        >
          <InfoRow label="STT URL" value={status?.stt.ollama_whisper.url} />
          <InfoRow label="STT model" value={status?.stt.ollama_whisper.model} />
          <InfoRow label="LLM URL" value={status?.stt.ollama_whisper.llm_url} />
          <InfoRow label="LLM model" value={status?.stt.ollama_whisper.llm_model} />
          {status?.stt.ollama_whisper.available_models && (
            <div className="text-xs text-gray-500 pt-1">
              Available: {status.stt.ollama_whisper.available_models.slice(0, 5).join(", ")}
            </div>
          )}
          {(testResults.stt?.ollama?.error ?? status?.stt.ollama_whisper.error) && (
            <p className="text-xs text-red-500">{testResults.stt?.ollama?.error ?? status?.stt.ollama_whisper.error}</p>
          )}
          <div className="pt-2 space-y-2 border-t border-gray-100">
            <Field label="STT URL" value={config.ollama_url ?? ""} onChange={set("ollama_url")}
              placeholder="http://host.docker.internal:11434" />
            <Field label="STT model" value={config.ollama_stt_model ?? ""} onChange={set("ollama_stt_model")}
              placeholder="whisper" />
            <Field label="LLM URL (turn formatter)" value={config.ollama_llm_url ?? ""} onChange={set("ollama_llm_url")}
              placeholder="http://host.docker.internal:11434" />
            <Field label="LLM model" value={config.ollama_llm_model ?? ""} onChange={set("ollama_llm_model")}
              placeholder="llama3.2" />
          </div>
        </ProviderCard>

        <div className="flex items-end">
          <button
            onClick={() => handleTest("stt")}
            disabled={testing === "stt"}
            className="flex items-center gap-2 text-sm border border-gray-200 px-4 py-1.5 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            {testing === "stt" ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />}
            Test STT
          </button>
        </div>
      </Section>

      {/* ── TTS ── */}
      <Section icon={Volume2} title="Text-to-Speech (TTS)" active={active?.tts}>
        <ProviderCard
          label="Local TTS server"
          active={active?.tts === "local"}
          badge={<StatusBadge configured={status?.tts.local.configured} ok={status?.tts.local.reachable ?? testResults.tts?.local?.ok} />}
        >
          <InfoRow label="URL" value={status?.tts.local.url} />
          <InfoRow label="Model" value={status?.tts.local.model} />
          <InfoRow label="Voice" value={status?.tts.local.voice} />
          <p className="text-xs text-gray-400 pt-1">
            Compatible with openedai-speech, kokoro-fastapi, or any OpenAI /v1/audio/speech endpoint.
          </p>
          <div className="pt-2 space-y-2 border-t border-gray-100">
            <Field label="URL" value={config.local_tts_url ?? ""} onChange={set("local_tts_url")}
              placeholder="http://host.docker.internal:8880" />
            <Field label="Voice" value={config.local_tts_voice ?? ""} onChange={set("local_tts_voice")}
              placeholder="alloy / af_bella / etc." />
          </div>
        </ProviderCard>

        <ProviderCard
          label="Sarvam AI"
          active={active?.tts === "sarvam"}
          badge={<StatusBadge configured={status?.tts.sarvam.configured} ok={status?.tts.sarvam.ok ?? testResults.tts?.sarvam?.ok} />}
        >
          <InfoRow label="Key" value={status?.tts.sarvam.configured ? "●●●●●●●● (set)" : "Not set"} />
          <p className="text-xs text-gray-400">Best for Indian languages — supports all P0/P1 languages natively.</p>
        </ProviderCard>

        <ProviderCard
          label="Azure Neural TTS"
          active={active?.tts === "azure"}
          badge={<StatusBadge configured={status?.tts.azure.configured} ok={status?.tts.azure.ok ?? testResults.tts?.azure?.ok} />}
        >
          <InfoRow label="Region" value={(status?.tts.azure as any)?.region} />
          <InfoRow label="Key" value={status?.tts.azure.configured ? "●●●●●●●● (set)" : "Not set"} />
          <p className="text-xs text-gray-400">Enterprise fallback — supports all languages via Neural TTS.</p>
        </ProviderCard>

        <div className="md:col-span-2 xl:col-span-3 flex justify-end">
          <button
            onClick={() => handleTest("tts")}
            disabled={testing === "tts"}
            className="flex items-center gap-2 text-sm border border-gray-200 px-4 py-1.5 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            {testing === "tts" ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />}
            Test all TTS connections
          </button>
        </div>
      </Section>

      {/* ── Save ── */}
      {hasChanges && (
        <div className="sticky bottom-4 flex justify-end">
          <div className="bg-white border border-gray-200 rounded-xl shadow-lg p-4 flex items-center gap-4">
            <span className="text-sm text-gray-600">
              {Object.keys(config).filter((k) => config[k as keyof ProviderConfig]).length} field(s) changed
            </span>
            <button
              onClick={() => setConfig({})}
              className="text-sm text-gray-500 hover:text-gray-700 px-3 py-1.5 border border-gray-200 rounded-lg"
            >
              Discard
            </button>
            <button
              onClick={() => updateMutation.mutate(config)}
              disabled={updateMutation.isPending}
              className="flex items-center gap-2 text-sm bg-brand-600 hover:bg-brand-500 text-white px-4 py-1.5 rounded-lg font-medium disabled:opacity-50"
            >
              {updateMutation.isPending
                ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                : <Save className="w-3.5 h-3.5" />}
              Apply changes
            </button>
          </div>
        </div>
      )}
      {updateMutation.isSuccess && (
        <div className="text-sm text-green-600 bg-green-50 border border-green-200 rounded-xl p-3">
          ✓ Changes applied. To persist across restarts, add the values to your <code>.env</code> file.
        </div>
      )}

      {/* ── .env help ── */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <button
          className="w-full flex items-center justify-between px-5 py-4 text-sm font-medium hover:bg-gray-50"
          onClick={() => setShowEnvHelp((v) => !v)}
        >
          <span>Environment variable reference</span>
          {showEnvHelp ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
        {showEnvHelp && (
          <div className="px-5 pb-5 space-y-3 text-xs border-t border-gray-100">
            <p className="text-gray-500 pt-3">
              Set these in <code className="bg-gray-100 px-1 rounded">vyuha/.env</code> to persist across container restarts.
            </p>
            <pre className="bg-gray-50 rounded-lg p-4 overflow-x-auto text-gray-700 leading-relaxed">{`# LLM Judges
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
LOCAL_LLM_URL=http://host.docker.internal:11434/v1
LOCAL_LLM_MODEL=llama3.2

# STT (Ollama Whisper)
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_STT_MODEL=whisper
OLLAMA_LLM_URL=http://host.docker.internal:11434
OLLAMA_LLM_MODEL=llama3.2

# TTS
SARVAM_API_KEY=...
AZURE_SPEECH_KEY=...
AZURE_SPEECH_REGION=eastus
LOCAL_TTS_URL=http://host.docker.internal:8880
LOCAL_TTS_VOICE=alloy`}</pre>
            <p className="text-gray-400">
              On Mac, <code className="bg-gray-100 px-1 rounded">host.docker.internal</code> resolves to your Mac&apos;s IP
              from inside Docker containers — use this to reach locally-running Ollama.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
