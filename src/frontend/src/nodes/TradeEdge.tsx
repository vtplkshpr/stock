// Edge between a "Suppliers/Customers of X" group and one partner. Its label lists what is traded
// in the partner's latest reported period, in the report's own wording, with each item's share
// of the total traded in that direction; the tooltip names the period, report and source file.
import { BaseEdge, EdgeLabelRenderer, getBezierPath, Position, type Edge, type EdgeProps } from "@xyflow/react";
import { date, format, money } from "../format";
import { TRADE_GAP } from "../layout";
import type { Partner, Side } from "../types";

export type TradeEdgeData = { partner: Partner; side: Side; owner: string };
export type TradeEdgeType = Edge<TradeEdgeData, "trade">;

const ITEMS_SHOWN = 3;

function tooltip({ partner, side, owner }: TradeEdgeData): string {
  const verb = side === "suppliers" ? `${owner} buys from ${partner.name}` : `${owner} sells to ${partner.name}`;
  const lines = [verb];
  if (partner.latest_period_end) {
    const scope = partner.latest_scope ? `${partner.latest_scope} report` : "report";
    const by = partner.latest_reported_by.length ? ` of ${partner.latest_reported_by.join(", ")}` : "";
    lines.push(`Period ${date(partner.latest_period_start)} – ${date(partner.latest_period_end)} (${scope}${by})`);
  }
  for (const item of partner.items) {
    const amount = item.amount !== null ? money(item.amount) : "amount not disclosed";
    const share = item.share !== null ? ` · ${format(item.share, "percent")}` : "";
    lines.push(`• ${item.description}: ${amount}${share}`);
  }
  if (partner.latest_document) lines.push(`Source: ${partner.latest_document}`);
  lines.push("Items as worded in the report; shares are of the total traded in this direction.");
  return lines.join("\n");
}

export function TradeEdge(props: EdgeProps<TradeEdgeType>) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, data } = props;
  const [path] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  if (!data) return <BaseEdge id={id} path={path} style={style} />;
  const { partner } = data;
  const items = partner.items ?? [];
  const hasLabel = partner.latest_amount !== null || items.length > 0;
  // The label sits on the straight end of the edge, in the gap just before the partner node.
  const growsLeft = targetPosition === Position.Right;
  const x = targetX + (growsLeft ? TRADE_GAP / 2 : -TRADE_GAP / 2);
  return (
    <>
      <BaseEdge id={id} path={path} style={style} />
      {hasLabel && (
        <EdgeLabelRenderer>
          <div className={`trade-label side-${data.side} nodrag nopan`} title={tooltip(data)}
               style={{ transform: `translate(-50%, -50%) translate(${x}px, ${targetY}px)` }}>
            {partner.latest_amount !== null && <div className="trade-amount">{money(partner.latest_amount)}</div>}
            {items.slice(0, ITEMS_SHOWN).map((item) => (
              <div key={item.description} className="trade-item">
                <span className="trade-name">{item.description}</span>
                <span className="trade-share">{item.share !== null ? format(item.share, "percent") : ""}</span>
              </div>
            ))}
            {items.length > ITEMS_SHOWN && <div className="trade-more">+{items.length - ITEMS_SHOWN} more</div>}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const edgeTypes = { trade: TradeEdge };
