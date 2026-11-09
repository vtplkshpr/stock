import { getNodesBounds, getViewportForBounds, useReactFlow } from "@xyflow/react";
import { toPng, toSvg } from "html-to-image";
import { useMemo, useState } from "react";
import { diagramControl } from "../Diagram";
import { store, useDiagram } from "../store";

const EXPORT_PADDING = 40;
const EXPORT_MAX = 8000;

/** Find on the diagram, fit, re-arrange, collapse and export. */
export function Toolbar({ onFocus }: { onFocus: (id: string) => void }) {
  const { tree } = useDiagram();
  const flow = useReactFlow();
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [busy, setBusy] = useState(false);

  const matches = useMemo(() => {
    const text = query.trim().toLowerCase();
    if (!text) return [];
    return store.visible().filter((node) => [node.label, node.partner?.name, node.content?.title, node.summary?.name]
      .some((value) => value?.toLowerCase().includes(text))).map((node) => node.id);
  }, [query, tree]);

  const next = () => {
    if (!matches.length) return;
    const index = cursor % matches.length;
    onFocus(matches[index]);
    setCursor(index + 1);
  };

  const exportImage = async (kind: "png" | "svg") => {
    const element = document.querySelector<HTMLElement>(".react-flow__viewport");
    const nodes = flow.getNodes();
    if (!element || !nodes.length) return;
    setBusy(true);
    try {
      const bounds = getNodesBounds(nodes);
      const scale = Math.min(1, EXPORT_MAX / Math.max(bounds.width, bounds.height));
      const width = Math.ceil((bounds.width + EXPORT_PADDING * 2) * scale);
      const height = Math.ceil((bounds.height + EXPORT_PADDING * 2) * scale);
      const viewport = getViewportForBounds(bounds, width, height, scale, scale, 0);
      const background = getComputedStyle(document.body).getPropertyValue("--canvas").trim() || "#ffffff";
      const options = {
        backgroundColor: background, width, height,
        style: { width: `${width}px`, height: `${height}px`,
                 transform: `translate(${viewport.x + EXPORT_PADDING * scale}px, ${viewport.y + EXPORT_PADDING * scale}px) scale(${viewport.zoom})` },
      };
      const url = kind === "png" ? await toPng(element, { ...options, pixelRatio: 1.5 }) : await toSvg(element, options);
      const link = document.createElement("a");
      const root = store.tree[store.rootId ?? ""];
      link.download = `${root ? store.label(root.ticker).replace(/[^\p{L}\p{N}]+/gu, "-") : "diagram"}-diagram.${kind}`;
      link.href = url;
      link.click();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="toolbar">
      <div className="find">
        <input type="search" placeholder="Find on diagram…" value={query} aria-label="Find on diagram"
               onChange={(e) => {
                 setQuery(e.target.value);
                 setCursor(0);
               }}
               onKeyDown={(e) => e.key === "Enter" && next()} />
        {query && <span className="find-count">{matches.length ? `${(cursor % matches.length) || matches.length}/${matches.length}` : "0"}</span>}
      </div>
      <button onClick={() => diagramControl.fitAll()} title="Fit the whole diagram on screen">Fit</button>
      <button onClick={() => diagramControl.rearrange()} title="Undo manual moves and re-arrange">Re-arrange</button>
      <button onClick={() => store.collapseAll()} title="Close every branch">Collapse all</button>
      <button disabled={busy} onClick={() => exportImage("png")} title="Download the diagram as PNG">PNG</button>
      <button disabled={busy} onClick={() => exportImage("svg")} title="Download the diagram as SVG">SVG</button>
    </div>
  );
}
