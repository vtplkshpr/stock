import { useEffect, useState } from "react";
import { api } from "../api";
import type { Panel } from "../context";
import { date } from "../format";
import { fetchContent, store } from "../store";
import type { Content, NewsItem } from "../types";
import { ContentView } from "./ContentView";

const PANEL_PAGE = 50;

/** Full-size view of a table (50 rows a page), a news item or a long text. */
export function SidePanel({ panel, onClose }: { panel: Panel; onClose: () => void }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside className="side-panel" aria-label="Details">
      <button className="icon-button panel-close" onClick={onClose} aria-label="Close panel" title="Close (Esc)">×</button>
      {panel.kind === "content" && <ContentPanel nodeId={panel.nodeId} />}
      {panel.kind === "news" && <NewsPanel id={panel.id} title={panel.title} />}
      {panel.kind === "text" && (
        <div className="panel-body">
          <h2>{panel.title}</h2>
          <p className="long-text">{panel.text}</p>
        </div>
      )}
    </aside>
  );
}

function ContentPanel({ nodeId }: { nodeId: string }) {
  const node = store.tree[nodeId];
  const [page, setPage] = useState(1);
  const [options, setOptions] = useState<Record<string, string>>(node?.options ?? {});
  const [content, setContent] = useState<Content | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!node?.source) return;
    let cancelled = false;
    setLoading(true);
    fetchContent(node.source, page, PANEL_PAGE, options)
      .then((result) => !cancelled && (setContent(result), setError(null)))
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [node?.source, page, options]);

  if (!node) return <p className="panel-body">This item is no longer on the diagram.</p>;
  return (
    <div className="panel-body">
      <p className="eyebrow">{store.label(node.ticker)}</p>
      <h2>{content?.title ?? node.label}</h2>
      {error && <p className="node-error">{error}</p>}
      {content && (
        <ContentView
          content={content}
          compact={false}
          loading={loading}
          handlers={{
            onPage: setPage,
            onOption: (key, value) => {
              setPage(1);
              setOptions((current) => ({ ...current, [key]: value }));
            },
          }}
        />
      )}
      {!content && !error && <p className="muted">Loading…</p>}
    </div>
  );
}

function NewsPanel({ id, title }: { id: number; title: string }) {
  const [news, setNews] = useState<NewsItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.news(id).then(setNews).catch((e: Error) => setError(e.message));
  }, [id]);
  return (
    <div className="panel-body">
      <p className="eyebrow">{news?.ticker ?? "News"}</p>
      <h2>{news?.title ?? title}</h2>
      {error && <p className="node-error">{error}</p>}
      {news && (
        <>
          <p className="muted">
            {date(news.published_at)} {news.source_name ? `· ${news.source_name}` : ""}
            {news.source_url && <> · <a href={news.source_url} target="_blank" rel="noreferrer">Source</a></>}
          </p>
          <p className="long-text">{news.content_text ?? "No text content."}</p>
        </>
      )}
    </div>
  );
}
