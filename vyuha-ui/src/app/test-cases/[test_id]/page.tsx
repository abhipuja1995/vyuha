"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, ConversationNode, TestCase } from "@/lib/api";
import { ArrowLeft, Mic, Trash2, Upload } from "lucide-react";

export default function TestCaseDetailPage() {
  const { test_id } = useParams<{ test_id: string }>();
  const router = useRouter();
  const [tc, setTc] = useState<TestCase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState<string | null>(null); // node_id being uploaded

  useEffect(() => {
    api.testCases.get(test_id).then(setTc).catch((e) => setError(String(e)));
  }, [test_id]);

  const refresh = () => api.testCases.get(test_id).then(setTc);

  if (error) return <div className="p-8 text-red-600">{error}</div>;
  if (!tc) return <div className="p-8 text-gray-400">Loading…</div>;

  return (
    <div className="max-w-3xl mx-auto px-6 py-10 space-y-8">
      <button
        onClick={() => router.push("/test-cases")}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" /> Back to test cases
      </button>

      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-1">
          <span className="text-xs font-mono bg-gray-100 px-2 py-0.5 rounded text-gray-500">{tc.test_id}</span>
          <span className="text-xs font-medium bg-brand-50 text-brand-700 border border-brand-200 px-2 py-0.5 rounded">{tc.category}</span>
        </div>
        <h1 className="text-2xl font-semibold text-gray-900">{tc.title}</h1>
        <p className="text-sm text-gray-500 mt-1">{tc.user_goal}</p>
      </div>

      {/* Persona */}
      <section className="border border-gray-200 rounded-xl p-5 space-y-2">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">Persona</h2>
        <div className="grid grid-cols-3 gap-3 text-sm">
          <Chip label="Language" value={tc.persona_config.language} />
          <Chip label="Emotion" value={tc.persona_config.emotion} />
          <Chip label="Noise" value={tc.persona_config.noise_profile} />
        </div>
        {tc.persona_config.backstory && (
          <p className="text-xs text-gray-500 mt-2">{tc.persona_config.backstory}</p>
        )}
      </section>

      {/* Conversation nodes with audio upload */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
          Conversation Nodes
          <span className="ml-2 text-xs font-normal text-gray-400 normal-case">
            Upload a voice file per node to use instead of TTS
          </span>
        </h2>
        {tc.conversation_graph.nodes.map((node) => (
          <NodeAudioRow
            key={node.node_id}
            testId={tc.test_id}
            node={node}
            uploading={uploading === node.node_id}
            onUploadStart={() => setUploading(node.node_id)}
            onUploadDone={() => { setUploading(null); refresh(); }}
            onDelete={() => refresh()}
          />
        ))}
      </section>

      {/* Pass criteria */}
      <section className="border border-gray-200 rounded-xl p-5">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">Pass Criteria</h2>
        <p className="text-sm text-gray-700">{tc.pass_criteria}</p>
      </section>

      {/* Tags */}
      {tc.tags.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {tc.tags.map((tag) => (
            <span key={tag} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{tag}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50 rounded-lg px-3 py-2">
      <p className="text-xs text-gray-400">{label}</p>
      <p className="font-medium text-gray-800">{value}</p>
    </div>
  );
}

function NodeAudioRow({
  testId,
  node,
  uploading,
  onUploadStart,
  onUploadDone,
  onDelete,
}: {
  testId: string;
  node: ConversationNode;
  uploading: boolean;
  onUploadStart: () => void;
  onUploadDone: () => void;
  onDelete: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const audioUrl = node.audio_file ? api.audio.url(testId, node.node_id) : null;

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    onUploadStart();
    try {
      await api.audio.upload(testId, node.node_id, file);
      onUploadDone();
    } catch (err) {
      alert(`Upload failed: ${err}`);
      onUploadDone();
    }
    if (fileRef.current) fileRef.current.value = "";
  };

  const handleDelete = async () => {
    setDeleteLoading(true);
    try {
      await api.audio.delete(testId, node.node_id);
      onDelete();
    } finally {
      setDeleteLoading(false);
    }
  };

  return (
    <div className={`border rounded-xl p-4 transition-colors ${
      node.is_terminal ? "border-green-300 bg-green-50" : "border-gray-200 bg-white"
    }`}>
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono text-gray-400">{node.node_id}</span>
            {node.is_terminal && (
              <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded">terminal</span>
            )}
            {node.audio_file && (
              <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded flex items-center gap-1">
                <Mic className="w-3 h-3" /> audio
              </span>
            )}
          </div>
          <p className="text-sm text-gray-800">{node.utterance_template}</p>

          {/* Audio player */}
          {audioUrl && (
            <audio controls src={audioUrl} className="mt-2 h-8 w-full max-w-xs" />
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <input
            ref={fileRef}
            type="file"
            accept=".wav,.mp3,.ogg,.flac,.m4a"
            className="hidden"
            onChange={handleFile}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-1 text-xs bg-brand-50 hover:bg-brand-100 text-brand-700 border border-brand-200 px-2.5 py-1.5 rounded-lg transition-colors disabled:opacity-50"
          >
            <Upload className="w-3.5 h-3.5" />
            {uploading ? "Uploading…" : node.audio_file ? "Replace" : "Upload audio"}
          </button>
          {node.audio_file && (
            <button
              onClick={handleDelete}
              disabled={deleteLoading}
              className="text-xs text-red-500 hover:text-red-700 p-1.5 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
