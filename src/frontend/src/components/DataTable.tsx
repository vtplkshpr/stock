import { format } from "../format";
import type { Column, ColumnType, Row } from "../types";

const NUMERIC: ColumnType[] = ["number", "money", "price", "percent", "fraction", "percent_bar"];

function cellType(column: Column, row: Row): ColumnType {
  return column.type === "auto" ? ((row._type as ColumnType) ?? "text") : column.type;
}

function Cell({ column, row }: { column: Column; row: Row }) {
  const value = row[column.key];
  const type = cellType(column, row);
  if (type === "ticker" && value) {
    return (
      <a className="ticker-link" href={`?ticker=${encodeURIComponent(String(value))}`} target="_blank"
         rel="noreferrer" title={`Open ${value} in a new diagram`}>{String(value)}</a>
    );
  }
  if (type === "link" && value) {
    const href = String(value).startsWith("http") ? String(value) : `https://${value}`;
    return <a href={href} target="_blank" rel="noreferrer">{String(value)}</a>;
  }
  if (type === "percent_bar" && typeof value === "number") {
    return (
      <span className="bar-cell">
        <span className="bar" style={{ width: `${Math.max(2, Math.min(100, value))}%` }} />
        <span className="bar-value">{format(value, "percent")}</span>
      </span>
    );
  }
  if (type === "bool" && value !== null && value !== undefined) {
    return <span className={value ? "flag-on" : "flag-off"}>{value ? "Yes" : "No"}</span>;
  }
  const text = format(value, type);
  const sign = NUMERIC.includes(type) && typeof value === "number" && value < 0 ? "negative" : "";
  return <span className={sign} title={text.length > 40 ? text : undefined}>{text}</span>;
}

export function DataTable({ columns, rows, onRowClick }: {
  columns: Column[];
  rows: Row[];
  onRowClick?: (row: Row) => void;
}) {
  if (!rows.length) return <p className="empty">No data.</p>;
  return (
    <table className="data-table">
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column.key} className={NUMERIC.includes(column.type) || column.type === "auto" ? "num" : ""}>
              {column.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={index} className={onRowClick ? "clickable" : ""} onClick={onRowClick ? () => onRowClick(row) : undefined}>
            {columns.map((column) => {
              const numeric = NUMERIC.includes(cellType(column, row));
              return (
                <td key={column.key} className={numeric ? "num" : column.key === "item_name" || column.key === "metric" ? "wrap" : ""}>
                  <Cell column={column} row={row} />
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
