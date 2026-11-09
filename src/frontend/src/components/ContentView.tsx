import { useState } from "react";
import { format } from "../format";
import type { Content, Row } from "../types";
import { Chart } from "./Chart";
import { DataTable } from "./DataTable";

export interface ContentHandlers {
  onPage: (page: number) => void;
  onOption: (key: string, value: string) => void;
  onRowClick?: (row: Row) => void;
  onText?: (label: string, text: string) => void;
}

/** Options, fields, chart, table and pager of one content payload (used in nodes and the panel). */
export function ContentView({ content, handlers, compact, loading }: {
  content: Content;
  handlers: ContentHandlers;
  compact: boolean;
  loading?: boolean;
}) {
  // Payloads that hold every row at once (no server paging) are paged here.
  const [localPage, setLocalPage] = useState(1);
  const allRows = content.rows ?? [];
  const limit = compact ? 10 : 50;
  const clientPaged = allRows.length > limit && allRows.length >= (content.total ?? 0);
  const total = content.total ?? allRows.length;
  const pageSize = clientPaged ? limit : content.page_size ?? (total || 1);
  const page = clientPaged ? localPage : content.page ?? 1;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const rows = clientPaged ? allRows.slice((page - 1) * limit, page * limit) : allRows;
  const goTo = clientPaged ? setLocalPage : handlers.onPage;
  const fields = compact ? content.fields?.slice(0, 8) : content.fields;

  return (
    <div className={`content-view ${loading ? "is-loading" : ""}`}>
      {content.options && Object.keys(content.options).length > 0 && (
        <div className="options nodrag">
          {Object.entries(content.options).map(([key, option]) =>
            option.choices.length > 1 ? (
              <label key={key}>
                <span>{option.label ?? key}</span>
                <select value={option.value ?? ""} onChange={(e) => handlers.onOption(key, e.target.value)}>
                  {option.choices.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
            ) : null,
          )}
        </div>
      )}
      {fields && fields.length > 0 && (
        <dl className="fields">
          {fields.map((field, index) => (
            <div key={index}>
              <dt>{field.label}</dt>
              <dd>{field.type === "link" && field.value
                ? <a href={String(field.value).startsWith("http") ? String(field.value) : `https://${field.value}`}
                     target="_blank" rel="noreferrer">{String(field.value)}</a>
                : format(field.value, field.type)}</dd>
            </div>
          ))}
        </dl>
      )}
      {content.texts?.map((text) => (
        <div key={text.label} className="text-block">
          <h4>{text.label}</h4>
          <p className={compact ? "clamp" : ""}>{text.text}</p>
          {compact && handlers.onText && text.text.length > 180 && (
            <button className="link nodrag" onClick={() => handlers.onText!(text.label, text.text)}>Read all</button>
          )}
        </div>
      ))}
      {content.chart && <Chart chart={content.chart} width={compact ? 440 : 620} />}
      {content.columns && content.rows && (
        <div className={`table-scroll ${compact ? "nowheel" : ""}`}>
          <DataTable columns={content.columns} rows={rows}
                     onRowClick={content.row_action ? handlers.onRowClick : undefined} />
        </div>
      )}
      {content.columns && pages > 1 && (
        <div className="pager nodrag">
          <button disabled={page <= 1} onClick={() => goTo(page - 1)} aria-label="Previous page">‹</button>
          <span>{page} / {pages} <small>({total} rows)</small></span>
          <button disabled={page >= pages} onClick={() => goTo(page + 1)} aria-label="Next page">›</button>
        </div>
      )}
      {content.note && <p className="note">{content.note}</p>}
    </div>
  );
}
