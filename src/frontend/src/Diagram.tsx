// The zoomable canvas. Nodes are rendered first (at their parent's position, invisible), measured
// by React Flow, then placed by layout() and animated into position.
import {
  Background, BackgroundVariant, Controls, MiniMap, ReactFlow, useNodesState, useReactFlow,
  type Edge, type NodeChange,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { layout, type Box, type Size } from "./layout";
import { companyOf, nodeTypes, type DiagramNode } from "./nodes/nodes";
import { edgeTypes } from "./nodes/TradeEdge";
import { store, useDiagram, type Dir, type TNode } from "./store";

/** Imperative controls used by the toolbar and actions (set while the canvas is mounted). */
export const diagramControl = {
  focusAfterLayout: (_id: string) => {},
  focus: (_id: string) => {},
  fitAll: () => {},
  rearrange: () => {},
};

const EDGE_HANDLES: Record<Dir, [string, string]> = {
  up: ["s-top", "t-bottom"],
  right: ["s-right", "t-left"],
  left: ["s-left", "t-right"],
};

function edgeWidth(amount: number | null | undefined): number {
  if (!amount || amount <= 0) return 1.5;
  return Math.min(7, 1.5 + Math.max(0, Math.log10(amount) - 8) * 1.3); // ~1.5 px at 100 m, ~7 px at 1 tn+
}

const MINIMAP_COLORS: Record<string, string> = {
  company: "#2563eb", section: "#94a3b8", info: "#94a3b8", content: "#cbd5e1",
  side: "#64748b", partner: "#0f766e", more: "#e2e8f0", loop: "#e2e8f0",
};

export function Diagram() {
  const { tree, rootId } = useDiagram();
  const [nodes, setNodes, onNodesChangeBase] = useNodesState<DiagramNode>([]);
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;
  const visible = useMemo(() => (rootId ? store.visible() : []), [tree, rootId]);
  const visibleRef = useRef(visible);
  visibleRef.current = visible;

  const boxes = useRef(new Map<string, Box>());
  const offsets = useRef(new Map<string, { x: number; y: number }>());
  const pendingFocus = useRef<string | null>(null);
  const frame = useRef(0);
  const animationTimer = useRef(0);
  const [animating, setAnimating] = useState(false);
  const flow = useReactFlow();

  const runLayout = useCallback(() => {
    const current = nodesRef.current;
    const root = store.rootId;
    if (!root || !current.length) return;
    const sizes = new Map<string, Size>();
    for (const node of current) {
      if (!node.measured?.width || !node.measured?.height) return; // wait for React Flow to measure
      sizes.set(node.id, { width: node.measured.width, height: node.measured.height });
    }
    boxes.current = layout(root, visibleRef.current, sizes, (n) => store.visibleChildren(n));
    let moved = false;
    const next = current.map((node) => {
      const box = boxes.current.get(node.id);
      if (!box) return node;
      const offset = offsets.current.get(node.id);
      const position = { x: box.x + (offset?.x ?? 0), y: box.y + (offset?.y ?? 0) };
      const wasHidden = node.className === "unplaced";
      if (!wasHidden && Math.abs(position.x - node.position.x) < 0.5 && Math.abs(position.y - node.position.y) < 0.5) {
        return node;
      }
      moved = true;
      return { ...node, position, className: undefined };
    });
    if (moved) {
      setAnimating(true);
      window.clearTimeout(animationTimer.current);
      animationTimer.current = window.setTimeout(() => setAnimating(false), 450);
      setNodes(next);
    }
    const focusId = pendingFocus.current;
    if (focusId) {
      pendingFocus.current = null;
      const target = store.tree[focusId];
      const ids = target ? [focusId, ...store.visibleChildren(target)] : [focusId];
      window.setTimeout(() => {
        flow.fitView({ nodes: ids.map((id) => ({ id })), padding: 0.2, duration: 550, maxZoom: 1, minZoom: 0.2 });
      }, 30);
    }
  }, [flow, setNodes]);

  const schedule = useCallback(() => {
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(runLayout);
  }, [runLayout]);

  // Mirror the visible tree into React Flow nodes, keeping positions and measurements.
  useEffect(() => {
    setNodes((previous) => {
      const byId = new Map(previous.map((node) => [node.id, node]));
      return visible.map((t): DiagramNode => {
        const old = byId.get(t.id);
        if (old) return { ...old, data: { node: t } };
        const parent = t.parent ? byId.get(t.parent) : undefined;
        return {
          id: t.id,
          type: t.kind,
          data: { node: t },
          position: parent ? { ...parent.position } : { x: 0, y: 0 },
          className: "unplaced",
          zIndex: t.kind === "content" ? 2 : 1,
        };
      });
    });
    schedule();
  }, [visible, setNodes, schedule]);

  // A new centre company: forget manual moves and frame it.
  useEffect(() => {
    offsets.current.clear();
    if (rootId) pendingFocus.current = rootId;
  }, [rootId]);

  const onNodesChange = useCallback((changes: NodeChange<DiagramNode>[]) => {
    onNodesChangeBase(changes);
    if (changes.some((change) => change.type === "dimensions")) schedule();
  }, [onNodesChangeBase, schedule]);

  const onNodeDragStop = useCallback((_: unknown, node: DiagramNode) => {
    const box = boxes.current.get(node.id);
    if (box) offsets.current.set(node.id, { x: node.position.x - box.x, y: node.position.y - box.y });
  }, []);

  useEffect(() => {
    diagramControl.focusAfterLayout = (id) => {
      pendingFocus.current = id;
      schedule();
    };
    diagramControl.focus = (id) => {
      flow.fitView({ nodes: [{ id }], padding: 0.6, duration: 500, maxZoom: 1.1 });
    };
    diagramControl.fitAll = () => flow.fitView({ padding: 0.1, duration: 500 });
    diagramControl.rearrange = () => {
      offsets.current.clear();
      schedule();
    };
  }, [flow, schedule]);

  const edges = useMemo<Edge[]>(() => visible.filter((t) => t.parent).map((t: TNode) => {
    const [sourceHandle, targetHandle] = EDGE_HANDLES[t.dir];
    const partner = t.kind === "partner" || t.kind === "loop" ? t.partner : undefined;
    return {
      id: `e:${t.id}`,
      source: t.parent!,
      target: t.id,
      sourceHandle,
      targetHandle,
      className: `edge edge-${t.side ?? (t.dir === "up" ? "info" : "plain")} ${t.kind === "loop" ? "edge-loop" : ""}`,
      style: partner ? { strokeWidth: edgeWidth(partner.latest_amount) } : undefined,
      ...(partner && t.side
        ? { type: "trade", data: { partner, side: t.side, owner: store.label(t.ticker) } }
        : {}),
    };
  }), [visible]);

  return (
    <ReactFlow
      className={animating ? "animating" : ""}
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodesChange={onNodesChange}
      onNodeDragStop={onNodeDragStop}
      nodesConnectable={false}
      edgesFocusable={false}
      elementsSelectable={false}
      minZoom={0.05}
      maxZoom={2.5}
      zoomOnDoubleClick={false}
      onlyRenderVisibleElements={nodes.length > 150}
      proOptions={{ hideAttribution: true }}
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} />
      <Controls showInteractive={false} position="bottom-left" />
      <MiniMap pannable zoomable position="bottom-right"
               nodeColor={(node) => {
                 const t = (node.data as DiagramNode["data"]).node;
                 if (t.kind === "side" || t.kind === "partner") return t.side === "suppliers" ? "#0f766e" : "#b45309";
                 return companyOf(t) && t.kind === "company" ? MINIMAP_COLORS.company : MINIMAP_COLORS[t.kind] ?? "#94a3b8";
               }} />
    </ReactFlow>
  );
}
