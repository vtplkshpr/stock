import { useState } from "react";
import { date, format } from "../format";
import type { ChartData } from "../types";

/** Small dependency-free SVG chart: a line (prices) or bars around zero (net flows). */
export function Chart({ chart, width = 480, height = 130 }: { chart: ChartData; width?: number; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const points = chart.series[0]?.points.filter((p): p is [string, number] => p[1] !== null) ?? [];
  if (points.length < 2) return null;

  const pad = { left: 8, right: 8, top: 10, bottom: 18 };
  const values = points.map((p) => p[1]);
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (chart.type === "bar") {
    min = Math.min(min, 0);
    max = Math.max(max, 0);
  }
  if (min === max) max = min + 1;
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const x = (i: number) => pad.left + (points.length === 1 ? innerW / 2 : (i / (points.length - 1)) * innerW);
  const y = (v: number) => pad.top + (1 - (v - min) / (max - min)) * innerH;
  const type = chart.unit === "money" ? "money" : chart.unit === "price" ? "price" : "number";

  const onMove = (event: React.MouseEvent<SVGRectElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    setHover(Math.max(0, Math.min(points.length - 1, Math.round(ratio * (points.length - 1)))));
  };

  const barWidth = Math.max(1, innerW / points.length - 1);
  const shown = hover ?? points.length - 1;
  return (
    <div className="chart">
      <div className="chart-caption">
        <span>{chart.series[0].name}</span>
        <span className={points[shown][1] < 0 ? "negative" : ""}>
          {date(points[shown][0])}: <b>{format(points[shown][1], type)}</b>
        </span>
      </div>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img"
           aria-label={`${chart.series[0].name} chart`}>
        {chart.type === "bar" ? (
          <>
            <line x1={pad.left} x2={width - pad.right} y1={y(0)} y2={y(0)} className="axis" />
            {points.map(([, v], i) => (
              <rect key={i} x={x(i) - barWidth / 2} width={barWidth} y={Math.min(y(v), y(0))}
                    height={Math.max(1, Math.abs(y(v) - y(0)))}
                    className={`${v < 0 ? "bar-down" : "bar-up"} ${hover === i ? "active" : ""}`} />
            ))}
          </>
        ) : (
          <>
            <polyline className="line-area" points={[
              `${x(0)},${pad.top + innerH}`,
              ...points.map(([, v], i) => `${x(i)},${y(v)}`),
              `${x(points.length - 1)},${pad.top + innerH}`,
            ].join(" ")} />
            <polyline className="line" points={points.map(([, v], i) => `${x(i)},${y(v)}`).join(" ")} />
            {hover !== null && <circle cx={x(hover)} cy={y(points[hover][1])} r={3.5} className="dot" />}
          </>
        )}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={pad.top + innerH} className="cursor" />}
        <text x={pad.left} y={height - 4} className="tick">{date(points[0][0])}</text>
        <text x={width - pad.right} y={height - 4} className="tick" textAnchor="end">{date(points[points.length - 1][0])}</text>
        <rect x={0} y={0} width={width} height={height} fill="transparent" onMouseMove={onMove}
              onMouseLeave={() => setHover(null)} />
      </svg>
    </div>
  );
}
