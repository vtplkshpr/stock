import { ReactFlowProvider } from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { CompanySearch } from "./components/CompanySearch";
import { Legend } from "./components/Legend";
import { SidePanel } from "./components/SidePanel";
import { Toolbar } from "./components/Toolbar";
import { ActionsContext, type DiagramActions, type Panel } from "./context";
import { Diagram, diagramControl } from "./Diagram";
import { SIDE_LABEL, store, useDiagram, type TNode } from "./store";
import type { SearchHit } from "./types";

export function App() {
  return (
    <ReactFlowProvider>
      <Workspace />
    </ReactFlowProvider>
  );
}

function crumbLabel(node: TNode): string {
  switch (node.kind) {
    case "company":
      return store.label(node.ticker);
    case "side":
      return `${SIDE_LABEL[node.side!]} of ${store.label(node.ticker)}`;
    case "partner":
      return node.partner?.ticker ?? node.partner?.name ?? node.label;
    case "content":
      return node.content?.title ?? node.label;
    default:
      return node.label;
  }
}

/** Read ?ticker=SBT&open=id1,id2 (the diagram state shared by a link). */
function linkState(): { ticker: string | null; open: string[] } {
  const params = new URLSearchParams(window.location.search);
  return { ticker: params.get("ticker"), open: (params.get("open") ?? "").split(",").filter(Boolean) };
}

function Workspace() {
  const { rootId, rootError, rootLoading, version } = useDiagram();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredTicker, setHoveredTicker] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel | null>(null);
  const restoring = useRef(false);

  const restore = useCallback(async (ticker: string, open: string[]) => {
    restoring.current = true;
    setSelectedId(null);
    setPanel(null);
    await store.open(ticker);
    for (const id of open) await store.expand(id);
    restoring.current = false;
    if (open.length) window.setTimeout(() => diagramControl.fitAll(), 600);
  }, []);

  useEffect(() => {
    const { ticker, open } = linkState();
    if (ticker) restore(ticker, open);
    const onPop = () => {
      const state = linkState();
      if (state.ticker) restore(state.ticker, state.open);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [restore]);

  // Keep the URL in step with the open branches, so the current view can be bookmarked or shared.
  useEffect(() => {
    if (restoring.current || !rootId) return;
    const url = new URL(window.location.href);
    url.searchParams.set("ticker", store.tree[rootId].ticker);
    const open = store.openIds();
    if (open.length) url.searchParams.set("open", open.join(","));
    else url.searchParams.delete("open");
    window.history.replaceState(null, "", url);
    document.title = `${store.label(store.tree[rootId].ticker)} · Company Diagram`;
  }, [version, rootId]);

  const openCompany = useCallback((ticker: string) => {
    const url = new URL(window.location.href);
    url.search = `?ticker=${encodeURIComponent(ticker)}`;
    window.history.pushState(null, "", url);
    restore(ticker, []);
  }, [restore]);

  const actions = useMemo<DiagramActions>(() => ({
    toggle: (id) => {
      setSelectedId(id);
      const node = store.tree[id];
      if (!node) return;
      if (node.kind === "loop" && node.targetId) {
        setSelectedId(node.targetId);
        diagramControl.focus(node.targetId);
        return;
      }
      const wasOpen = node.expanded;
      store.toggle(id).then(() => {
        const after = store.tree[id];
        if (!wasOpen && (after?.expanded || after?.kind === "more")) diagramControl.focusAfterLayout(after.kind === "more" ? after.parent! : id);
      });
    },
    focus: (id) => {
      setSelectedId(id);
      diagramControl.focus(id);
    },
    openPanel: setPanel,
    selectedId,
    hoveredTicker,
    setHoveredTicker,
  }), [selectedId, hoveredTicker]);

  const path = selectedId && store.tree[selectedId] ? store.path(selectedId) : rootId ? store.path(rootId) : [];

  return (
    <ActionsContext.Provider value={actions}>
      <div className="app">
        <header className="topbar">
          <div className="brand" title="Company diagram">◎ <span>Company Diagram</span></div>
          <CompanySearch onSelect={openCompany} />
          <nav className="breadcrumb" aria-label="Path to the selected node">
            {path.map((node, index) => (
              <span key={node.id}>
                {index > 0 && <span className="sep">›</span>}
                <button onClick={() => actions.focus(node.id)}>{crumbLabel(node)}</button>
              </span>
            ))}
          </nav>
          {rootId && <Toolbar onFocus={actions.focus} />}
        </header>
        <main className="canvas">
          {rootId ? (
            <>
              <Diagram />
              <Legend />
            </>
          ) : (
            <Welcome loading={rootLoading} error={rootError} onSelect={openCompany} />
          )}
        </main>
        {panel && <SidePanel panel={panel} onClose={() => setPanel(null)} />}
      </div>
    </ActionsContext.Provider>
  );
}

function Welcome({ loading, error, onSelect }: { loading: boolean; error: string | null; onSelect: (t: string) => void }) {
  const [featured, setFeatured] = useState<SearchHit[]>([]);
  useEffect(() => {
    api.featured().then(setFeatured).catch(() => setFeatured([]));
  }, []);
  return (
    <section className="welcome">
      <h1>Company diagram</h1>
      <p>
        Pick a company. Its information opens upwards, its suppliers to the right and its customers to the
        left; every supplier or customer can be opened in turn.
      </p>
      <CompanySearch onSelect={onSelect} autoFocus />
      {loading && <p className="muted">Loading…</p>}
      {error && <p className="node-error">{error}</p>}
      {featured.length > 0 && (
        <div className="featured">
          <span className="muted">Companies with detailed data:</span>
          {featured.map((hit) => (
            <button key={hit.ref} className="chip-button" onClick={() => onSelect(hit.ref)} title={hit.company_name}>
              {hit.ticker}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
