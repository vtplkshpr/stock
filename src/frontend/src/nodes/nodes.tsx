// Node components. Every node carries hidden handles on all four sides; edges pick the pair that
// matches the direction the branch grows in (see edgeHandles in Diagram.tsx).
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Fragment, type ReactNode } from "react";
import { ContentView } from "../components/ContentView";
import { useActions } from "../context";
import { date, money, relationship, trend } from "../format";
import { store, type TNode } from "../store";
import { SectionIcon } from "./icons";

export type DiagramNode = Node<{ node: TNode }>;

const HANDLE_SIDES: [string, Position][] = [
  ["top", Position.Top], ["bottom", Position.Bottom], ["left", Position.Left], ["right", Position.Right],
];

function Handles() {
  return (
    <>
      {HANDLE_SIDES.map(([id, position]) => (
        <Fragment key={id}>
          <Handle type="source" id={`s-${id}`} position={position} className="handle" isConnectable={false} />
          <Handle type="target" id={`t-${id}`} position={position} className="handle" isConnectable={false} />
        </Fragment>
      ))}
    </>
  );
}

/** Ticker that identifies the company a node stands for (for highlighting its other copies). */
export function companyOf(node: TNode): string | null {
  if (node.kind === "company") return node.ticker;
  if (node.kind === "partner" || node.kind === "loop") return node.partner?.ref ?? null;
  return null;
}

function Shell({ node, className, children, title }: {
  node: TNode; className: string; children: ReactNode; title?: string;
}) {
  const actions = useActions();
  const company = companyOf(node);
  const expandable = store.isExpandable(node) || node.kind === "more" || node.kind === "loop";
  const classes = [
    "dnode", className, `dir-${node.dir}`,
    node.expanded ? "is-open" : "",
    expandable ? "is-expandable" : "is-disabled",
    node.loading ? "is-loading" : "",
    actions.selectedId === node.id ? "is-selected" : "",
    company && actions.hoveredTicker === company ? "is-same-company" : "",
  ].join(" ");
  return (
    <div
      className={classes}
      title={title}
      role="button"
      tabIndex={0}
      aria-expanded={expandable ? node.expanded : undefined}
      onClick={() => actions.toggle(node.id)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          actions.toggle(node.id);
        }
      }}
      onMouseEnter={() => company && actions.setHoveredTicker(company)}
      onMouseLeave={() => company && actions.setHoveredTicker(null)}
    >
      <Handles />
      {children}
      {node.loading && <span className="spinner" aria-label="Loading" />}
      {node.error && <p className="node-error">{node.error}</p>}
    </div>
  );
}

function Toggle({ node, open, closed }: { node: TNode; open: string; closed: string }) {
  if (!store.isExpandable(node)) return null;
  return <span className="toggle-hint">{node.expanded ? open : closed}</span>;
}

export function CompanyNode({ data }: NodeProps<DiagramNode>) {
  const node = data.node;
  const summary = node.summary!;
  const price = summary.price;
  const sections = summary.sections.length;
  const listed = summary.entity === "company";
  return (
    <Shell node={node} className={`company-node ${listed ? "" : "is-organization"}`}>
      <div className="company-head">
        <span className="company-ticker">{listed ? summary.ticker : summary.name}</span>
        {summary.exchange && <span className="chip">{summary.exchange}</span>}
        {!listed && <span className="chip">{[summary.kind, "unlisted"].filter(Boolean).join(" · ")}</span>}
      </div>
      <div className="company-name">{listed ? summary.name : summary.full_name}</div>
      {summary.industry && <div className="muted">{summary.industry}</div>}
      {price && (
        <div className="company-price">
          <b>{money(price.close_price)}</b>
          <span className={`change ${trend(price.change_percentage)}`}>
            {price.change_percentage !== null ? `${price.change_percentage > 0 ? "+" : ""}${price.change_percentage}%` : ""}
          </span>
          <span className="muted">{date(price.price_date)}</span>
        </div>
      )}
      <span className="toggle-hint">{node.expanded ? "▾ Hide information" : `▴ Show information (${sections})`}</span>
    </Shell>
  );
}

export function SectionNode({ data }: NodeProps<DiagramNode>) {
  const node = data.node;
  const section = node.section!;
  const category = section.key.split(".")[0];
  const empty = section.count === 0;
  return (
    <Shell node={node} className={`section-node cat-${category} ${section.group ? "is-group" : "is-leaf"}`}
           title={empty ? "No data yet" : section.count_label}>
      <SectionIcon category={category} />
      <span className="section-label">{section.label}</span>
      <span className={`badge ${empty ? "badge-empty" : ""}`}>
        {section.group ? `${section.count}/${section.children.length}` : empty ? "no data" : section.count}
      </span>
      {!empty && <span className="caret" aria-hidden>{node.expanded ? "−" : "+"}</span>}
    </Shell>
  );
}

export function InfoNode({ data }: NodeProps<DiagramNode>) {
  const node = data.node;
  return (
    <Shell node={node} className="section-node info-node">
      <SectionIcon category="profile" />
      <span className="section-label">{store.label(node.ticker)} information</span>
      <span className="badge">{node.summary?.sections.length ?? 0}</span>
      <span className="caret" aria-hidden>{node.expanded ? "−" : "+"}</span>
    </Shell>
  );
}

export function SideNode({ data }: NodeProps<DiagramNode>) {
  const node = data.node;
  const total = node.partnerTotal ?? 0;
  const one = total === 1;
  const relation = node.side === "suppliers" ? `${one ? "supplies" : "supply"} to it` : `${one ? "buys" : "buy"} from it`;
  return (
    <Shell node={node} className={`side-node side-${node.side}`}
           title={node.side === "suppliers" ? `Companies that sell to ${store.label(node.ticker)}` : `Companies that buy from ${store.label(node.ticker)}`}>
      <div className="side-title">{node.label} <span className="muted">of {store.label(node.ticker)}</span></div>
      <div className="side-count">{total ? `${total} ${one ? "company" : "companies"} that ${relation}` : "None recorded yet"}</div>
      <Toggle node={node} open="− Hide" closed="+ Show" />
    </Shell>
  );
}

export function PartnerNode({ data }: NodeProps<DiagramNode>) {
  const node = data.node;
  const partner = node.partner!;
  const period = partner.latest_period_end
    ? `${date(partner.latest_period_start)} – ${date(partner.latest_period_end)}`
    : "";
  return (
    <Shell node={node} className={`partner-node side-${node.side} ${partner.listed ? "is-listed" : "is-unlisted"}`}>
      <div className="partner-head">
        {partner.ticker ? <span className="chip chip-strong">{partner.ticker}</span> : <span className="chip">Unlisted</span>}
        {!partner.ticker && partner.kind && partner.kind !== "Công ty" && <span className="chip chip-soft">{partner.kind}</span>}
        {partner.relationships.slice(0, 2).map((r) => <span key={r} className="chip chip-soft">{relationship(r)}</span>)}
      </div>
      <div className="partner-name">{partner.name}</div>
      {partner.latest_amount !== null && (
        <div className="partner-amount">
          <b>{money(partner.latest_amount)}</b> <span className="muted">{period}</span>
        </div>
      )}
      {partner.products.length > 0 && <div className="partner-products">{partner.products.join(" · ")}</div>}
      <Toggle node={node} open="− Close"
              closed={partner.expandable ? "+ Information · suppliers · customers" : "+ Transactions"} />
    </Shell>
  );
}

export function ContentNode({ data }: NodeProps<DiagramNode>) {
  const node = data.node;
  const actions = useActions();
  const content = node.content!;
  return (
    <div className={`dnode content-node dir-${node.dir} ${actions.selectedId === node.id ? "is-selected" : ""}`}>
      <Handles />
      <div className="content-head">
        <span className="chip chip-strong chip-name">{store.label(node.ticker)}</span>
        <h3>{content.title}</h3>
        <button className="icon-button nodrag" title="Open in the side panel" aria-label="Open in the side panel"
                onClick={() => actions.openPanel({ kind: "content", nodeId: node.id })}>⤢</button>
      </div>
      <ContentView
        content={content}
        compact
        loading={node.loading}
        handlers={{
          onPage: (page) => store.updateContent(node.id, page, node.options ?? {}),
          onOption: (key, value) => store.updateContent(node.id, 1, { ...(node.options ?? {}), [key]: value }),
          onRowClick: (row) => actions.openPanel({ kind: "news", id: Number(row._id), title: String(row.title ?? "") }),
          onText: (title, text) => actions.openPanel({ kind: "text", title, text }),
        }}
      />
      {node.error && <p className="node-error">{node.error}</p>}
    </div>
  );
}

export function MoreNode({ data }: NodeProps<DiagramNode>) {
  const node = data.node;
  return (
    <Shell node={node} className="more-node" title="Load the next companies">
      + {node.label}
    </Shell>
  );
}

export function LoopNode({ data }: NodeProps<DiagramNode>) {
  const node = data.node;
  return (
    <Shell node={node} className="loop-node" title="This company is already on the diagram; click to go there">
      <span>↩ {node.partner?.ticker ?? node.partner?.name}</span>
      <span className="muted">already shown – go to it</span>
    </Shell>
  );
}

export const nodeTypes = {
  company: CompanyNode,
  section: SectionNode,
  info: InfoNode,
  side: SideNode,
  partner: PartnerNode,
  content: ContentNode,
  more: MoreNode,
  loop: LoopNode,
};
