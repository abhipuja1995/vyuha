"use client";

import { useCallback, useState } from "react";
import ReactFlow, {
  addEdge,
  Background,
  Connection,
  Controls,
  Edge,
  MiniMap,
  Node,
  NodeChange,
  EdgeChange,
  applyNodeChanges,
  applyEdgeChanges,
  Handle,
  Position,
  NodeProps,
} from "reactflow";
import "reactflow/dist/style.css";
import { Plus, Trash2 } from "lucide-react";
import { ConversationGraph } from "@/lib/api";

// ─── Custom node ─────────────────────────────────────────────────────────────

function UtteranceNode({ data, selected }: NodeProps) {
  return (
    <div className={`min-w-48 max-w-64 bg-white border-2 rounded-xl shadow-sm px-4 py-3 ${
      data.is_terminal
        ? "border-green-400"
        : selected
        ? "border-brand-500"
        : "border-gray-200"
    }`}>
      <Handle type="target" position={Position.Top} className="!bg-gray-400" />
      <p className="text-xs font-mono text-gray-400 mb-1">{data.node_id}</p>
      <p className="text-sm text-gray-800 leading-snug">{data.utterance_template}</p>
      {data.is_terminal && (
        <span className="inline-block mt-2 text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded">terminal</span>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-gray-400" />
    </div>
  );
}

const nodeTypes = { utterance: UtteranceNode };

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  value: ConversationGraph;
  onChange: (graph: ConversationGraph) => void;
}

export function ConversationGraphEditor({ value, onChange }: Props) {
  const [nodes, setNodes] = useState<Node[]>(
    value.nodes.map((n, i) => ({
      id: n.node_id,
      type: "utterance",
      position: { x: i * 280, y: 0 },
      data: { ...n },
    }))
  );
  const [edges, setEdges] = useState<Edge[]>(
    value.edges.map((e, i) => ({
      id: `e${i}`,
      source: e.from_node,
      target: e.to_node,
      label: e.condition,
      labelStyle: { fontSize: 10 },
      type: "smoothstep",
    }))
  );

  const [newUtterance, setNewUtterance] = useState("");
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [edgeConditions, setEdgeConditions] = useState<Record<string, string>>(
    Object.fromEntries(value.edges.map((e) => [`${e.from_node}->${e.to_node}`, e.condition]))
  );

  const emitChange = useCallback(
    (nextNodes: Node[], nextEdges: Edge[]) => {
      const graph: ConversationGraph = {
        start_node: nextNodes[0]?.id ?? "",
        nodes: nextNodes.map((n) => ({
          node_id: n.id,
          utterance_template: n.data.utterance_template,
          is_terminal: n.data.is_terminal ?? false,
          audio_file: n.data.audio_file ?? null,
        })),
        edges: nextEdges.map((e) => ({
          from_node: e.source,
          to_node: e.target,
          condition: typeof e.label === "string" ? e.label : "",
        })),
      };
      onChange(graph);
    },
    [onChange]
  );

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const next = applyNodeChanges(changes, nodes);
      setNodes(next);
      emitChange(next, edges);
    },
    [nodes, edges, emitChange]
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      const next = applyEdgeChanges(changes, edges);
      setEdges(next);
      emitChange(nodes, next);
    },
    [nodes, edges, emitChange]
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      const conditionKey = `${connection.source}->${connection.target}`;
      const condition = prompt("Edge condition (what does the agent say/do to trigger this?)") ?? "";
      const newEdge: Edge = {
        ...connection,
        id: conditionKey,
        label: condition,
        type: "smoothstep",
        source: connection.source ?? "",
        target: connection.target ?? "",
      };
      const next = addEdge(newEdge, edges);
      setEdges(next);
      setEdgeConditions((prev) => ({ ...prev, [conditionKey]: condition }));
      emitChange(nodes, next);
    },
    [nodes, edges, emitChange]
  );

  const addNode = () => {
    if (!newUtterance.trim()) return;
    const id = `n${nodes.length + 1}`;
    const newNode: Node = {
      id,
      type: "utterance",
      position: { x: (nodes.length % 3) * 280, y: Math.floor(nodes.length / 3) * 160 },
      data: { node_id: id, utterance_template: newUtterance.trim(), is_terminal: false },
    };
    const next = [...nodes, newNode];
    setNodes(next);
    setNewUtterance("");
    emitChange(next, edges);
  };

  const toggleTerminal = (nodeId: string) => {
    const next = nodes.map((n) =>
      n.id === nodeId ? { ...n, data: { ...n.data, is_terminal: !n.data.is_terminal } } : n
    );
    setNodes(next);
    emitChange(next, edges);
  };

  return (
    <div className="space-y-3">
      {/* Add node form */}
      <div className="flex gap-2">
        <input
          value={newUtterance}
          onChange={(e) => setNewUtterance(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addNode()}
          placeholder="Type a caller utterance and press Enter…"
          className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2"
        />
        <button
          onClick={addNode}
          className="flex items-center gap-1.5 bg-brand-600 hover:bg-brand-500 text-white text-sm px-3 py-2 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" /> Add node
        </button>
      </div>

      {/* Graph canvas */}
      <div className="h-96 border border-gray-200 rounded-xl overflow-hidden bg-gray-50">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
        >
          <Background />
          <Controls />
          <MiniMap nodeColor={() => "#4f6ef7"} />
        </ReactFlow>
      </div>

      {/* Node list for toggling terminal */}
      <div className="flex flex-wrap gap-2">
        {nodes.map((n) => (
          <button
            key={n.id}
            onClick={() => toggleTerminal(n.id)}
            className={`text-xs px-2 py-1 rounded-full border transition-colors ${
              n.data.is_terminal
                ? "bg-green-100 border-green-400 text-green-700"
                : "bg-gray-100 border-gray-200 text-gray-600 hover:border-gray-400"
            }`}
          >
            {n.id} {n.data.is_terminal ? "✓ terminal" : ""}
          </button>
        ))}
      </div>

      <p className="text-xs text-gray-400">
        Drag to reposition nodes · Connect nodes by dragging between handles · Click node label to mark as terminal
      </p>
    </div>
  );
}
