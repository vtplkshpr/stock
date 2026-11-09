// The diagram as a tree of nodes, and the actions that open, close and load them.
//
// Layout directions: the centre company's information branches grow up, its suppliers to the
// right and its customers to the left. Everything under a side keeps growing outwards on that
// side (a partner's information, suppliers and customers included), so the tree never folds
// back over itself.
import { useSyncExternalStore } from "react";
import { api } from "./api";
import type { CompanySummary, Content, Partner, SectionInfo, Side } from "./types";

export type Dir = "up" | "left" | "right";
export type Kind = "company" | "section" | "content" | "side" | "partner" | "info" | "more" | "loop";

export type ContentSource =
  | { kind: "section"; ticker: string; key: string }
  | { kind: "partnerTx"; ticker: string; side: Side; key: string };

export interface TNode {
  id: string;
  kind: Kind;
  parent: string | null;
  dir: Dir;
  label: string;
  ticker: string; // entity this node belongs to: a ticker, or "org:<id>" for an unlisted organisation
  expanded: boolean;
  loading?: boolean;
  error?: string;
  children: string[];
  ancestors: [string, string][]; // [entity ref, node id] of every company on the path, nearest last
  section?: SectionInfo;
  summary?: CompanySummary;
  side?: Side;
  partner?: Partner;
  partnerTotal?: number;
  source?: ContentSource;
  content?: Content;
  page?: number;
  pageSize?: number;
  options?: Record<string, string>;
  targetId?: string;
}

export type Tree = Record<string, TNode>;

const PARTNER_PAGE = 10;
export const CONTENT_PAGE = 10;
const SIDE_DIR: Record<Side, Dir> = { suppliers: "right", customers: "left" };
export const SIDE_LABEL: Record<Side, string> = { suppliers: "Suppliers", customers: "Customers" };

type Listener = () => void;

class DiagramStore {
  tree: Tree = {};
  rootId: string | null = null;
  rootError: string | null = null;
  rootLoading = false;
  version = 0;
  /** Display name of every entity ref met so far (ticker for listed companies). */
  names: Record<string, string> = {};
  private listeners = new Set<Listener>();
  private snapshot = { tree: this.tree, rootId: this.rootId, version: 0, rootError: null as string | null, rootLoading: false };

  subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = () => this.snapshot;

  private emit() {
    this.version += 1;
    this.snapshot = {
      tree: this.tree, rootId: this.rootId, version: this.version,
      rootError: this.rootError, rootLoading: this.rootLoading,
    };
    this.listeners.forEach((listener) => listener());
  }

  private patch(id: string, changes: Partial<TNode>) {
    const node = this.tree[id];
    if (!node) return;
    this.tree = { ...this.tree, [id]: { ...node, ...changes } };
  }

  private add(nodes: TNode[], parentId: string, before?: string) {
    const parent = this.tree[parentId];
    const next = { ...this.tree };
    const ids = nodes.map((n) => n.id).filter((id) => !parent.children.includes(id));
    for (const node of nodes) next[node.id] = node;
    const children = [...parent.children];
    const at = before ? children.indexOf(before) : -1;
    if (at >= 0) children.splice(at, 0, ...ids);
    else children.push(...ids);
    next[parentId] = { ...parent, children };
    this.tree = next;
  }

  // --- loading the centre company -----------------------------------------------------------

  async open(ticker: string) {
    this.rootLoading = true;
    this.rootError = null;
    this.emit();
    try {
      const summary = await api.company(ticker);
      this.remember(summary);
      const id = `c:${summary.ref}`;
      const root: TNode = {
        id, kind: "company", parent: null, dir: "up", label: this.label(summary.ref), ticker: summary.ref,
        expanded: false, children: [], ancestors: [[summary.ref, id]], summary,
      };
      this.tree = { [id]: root };
      this.rootId = id;
      this.add(this.sideNodes(root, summary, "right-and-left"), id);
    } catch (error) {
      this.tree = {};
      this.rootId = null;
      this.rootError = (error as Error).message;
    }
    this.rootLoading = false;
    this.emit();
  }

  remember(summary: CompanySummary) {
    this.names[summary.ref] = summary.ticker ?? summary.name;
  }

  /** Short display name of an entity ref. */
  label(ref: string): string {
    return this.names[ref] ?? ref;
  }

  private sideNodes(owner: TNode, summary: CompanySummary, mode: "right-and-left" | Dir): TNode[] {
    return (["suppliers", "customers"] as Side[]).map((side) => ({
      id: `${owner.id}/${side}`, kind: "side" as Kind, parent: owner.id,
      dir: mode === "right-and-left" ? SIDE_DIR[side] : mode,
      label: SIDE_LABEL[side], ticker: summary.ref, expanded: false, children: [],
      ancestors: owner.ancestors, side, partnerTotal: summary.partners[side],
    }));
  }

  private sectionNodes(owner: TNode, sections: SectionInfo[], ticker: string, dir: Dir): TNode[] {
    return sections.map((section) => ({
      id: `${owner.id}/s:${section.key}`, kind: "section" as Kind, parent: owner.id, dir,
      label: section.label, ticker, expanded: false, children: [], ancestors: owner.ancestors, section,
    }));
  }

  // --- opening and closing ------------------------------------------------------------------

  isExpandable(node: TNode): boolean {
    switch (node.kind) {
      case "section":
        return (node.section?.count ?? 0) > 0;
      case "side":
        return (node.partnerTotal ?? 0) > 0;
      case "content":
      case "loop":
      case "more":
        return false;
      default:
        return true;
    }
  }

  /** Open or close a node; resolves once its children are loaded. */
  async toggle(id: string): Promise<void> {
    const node = this.tree[id];
    if (!node || node.loading) return;
    if (node.kind === "more") return this.loadMore(node);
    if (!this.isExpandable(node)) return;
    if (node.expanded) {
      this.patch(id, { expanded: false });
      this.emit();
      return;
    }
    if (this.hasLoadedChildren(node)) {
      this.patch(id, { expanded: true, error: undefined });
      this.emit();
      return;
    }
    this.patch(id, { loading: true, error: undefined });
    this.emit();
    try {
      await this.loadChildren(this.tree[id]);
      this.patch(id, { expanded: true, loading: false });
    } catch (error) {
      this.patch(id, { loading: false, error: (error as Error).message });
    }
    this.emit();
  }

  /** Make sure a node is open (used when restoring a shared link). A partner beyond the first
   *  page of its group is reached by loading further pages. */
  async expand(id: string) {
    const at = id.lastIndexOf("/p:");
    if (!this.tree[id] && at > 0) {
      const moreId = `${id.slice(0, at)}/more`;
      while (!this.tree[id] && this.tree[moreId] && !this.tree[moreId].error) {
        await this.loadMore(this.tree[moreId]);
      }
    }
    const node = this.tree[id];
    if (node && !node.expanded) await this.toggle(id);
  }

  private hasLoadedChildren(node: TNode): boolean {
    if (node.kind === "company") return node.children.some((c) => this.tree[c]?.kind === "section");
    return node.children.length > 0;
  }

  /** Children of the centre company that are only shown while it is open (its information). */
  visibleChildren(node: TNode): string[] {
    if (node.kind === "company") {
      return node.children.filter((c) => node.expanded || this.tree[c]?.kind !== "section");
    }
    return node.expanded ? node.children : [];
  }

  private async loadChildren(node: TNode) {
    switch (node.kind) {
      case "company":
        this.add(this.sectionNodes(node, node.summary!.sections, node.ticker, "up"), node.id, node.children[0]);
        return;
      case "info":
        this.add(this.sectionNodes(node, node.summary!.sections, node.ticker, node.dir), node.id);
        return;
      case "section": {
        const section = node.section!;
        if (section.group) {
          this.add(this.sectionNodes(node, section.children, node.ticker, node.dir), node.id);
        } else {
          await this.addContent(node, { kind: "section", ticker: node.ticker, key: section.key }, section.label);
        }
        return;
      }
      case "side":
        await this.loadPartners(node, 0);
        return;
      case "partner": {
        const partner = node.partner!;
        if (partner.expandable && partner.ref) {
          const summary = await api.company(partner.ref);
          this.remember(summary);
          const ancestors: [string, string][] = [...node.ancestors, [summary.ref, node.id]];
          const owner = { ...node, ancestors };
          this.patch(node.id, { summary, ancestors });
          const info: TNode = {
            id: `${node.id}/info`, kind: "info", parent: node.id, dir: node.dir, label: "Information",
            ticker: summary.ref, expanded: false, children: [], ancestors, summary,
          };
          this.add([info, ...this.sideNodes(owner, summary, node.dir)], node.id);
        } else {
          await this.addContent(node, { kind: "partnerTx", ticker: node.ticker, side: node.side!, key: partner.key },
            "Transactions");
        }
        return;
      }
      default:
        return;
    }
  }

  private async addContent(parent: TNode, source: ContentSource, label: string) {
    const content = await fetchContent(source, 1, CONTENT_PAGE, {});
    this.add([{
      id: `${parent.id}/data`, kind: "content", parent: parent.id, dir: parent.dir, label: content.title || label,
      ticker: source.ticker, expanded: true, children: [], ancestors: parent.ancestors, source, content,
      page: 1, pageSize: CONTENT_PAGE, options: {},
    }], parent.id);
  }

  private async loadPartners(group: TNode, offset: number) {
    const page = await api.partners(group.ticker, group.side!, offset, PARTNER_PAGE);
    const nodes: TNode[] = page.items.map((partner) => {
      const id = `${group.id}/p:${partner.key}`;
      if (partner.ref) this.names[partner.ref] ??= partner.ticker ?? partner.name;
      const loop = partner.ref ? group.ancestors.find(([ref]) => ref === partner.ref) : undefined;
      if (loop) {
        return {
          id, kind: "loop" as Kind, parent: group.id, dir: group.dir, label: partner.ticker ?? partner.name,
          ticker: group.ticker,
          expanded: false, children: [], ancestors: group.ancestors, partner, side: group.side, targetId: loop[1],
        };
      }
      return {
        id, kind: "partner" as Kind, parent: group.id, dir: group.dir, label: partner.ticker ?? partner.name,
        ticker: group.ticker, expanded: false, children: [], ancestors: group.ancestors, partner, side: group.side,
      };
    });
    const moreId = `${group.id}/more`;
    this.add(nodes, group.id, moreId);
    const loaded = offset + page.items.length;
    if (loaded < page.total) {
      const more: TNode = {
        id: moreId, kind: "more", parent: group.id, dir: group.dir, label: `${page.total - loaded} more`,
        ticker: group.ticker, expanded: false, children: [], ancestors: group.ancestors, side: group.side,
        page: loaded,
      };
      if (this.tree[moreId]) this.patch(moreId, { label: more.label, page: loaded, loading: false });
      else this.add([more], group.id);
    } else if (this.tree[moreId]) {
      const parent = this.tree[group.id];
      const next = { ...this.tree };
      delete next[moreId];
      next[group.id] = { ...parent, children: parent.children.filter((c) => c !== moreId) };
      this.tree = next;
    }
  }

  private async loadMore(node: TNode) {
    this.patch(node.id, { loading: true, error: undefined });
    this.emit();
    try {
      await this.loadPartners(this.tree[node.parent!], node.page ?? 0);
    } catch (error) {
      this.patch(node.id, { loading: false, error: (error as Error).message });
    }
    this.emit();
  }

  /** Reload a content node with another page or option (scope, period...). */
  async updateContent(id: string, page: number, options: Record<string, string>) {
    const node = this.tree[id];
    if (!node?.source) return;
    this.patch(id, { loading: true, error: undefined });
    this.emit();
    try {
      const content = await fetchContent(node.source, page, node.pageSize ?? CONTENT_PAGE, options);
      this.patch(id, { content, page, options, loading: false });
    } catch (error) {
      this.patch(id, { loading: false, error: (error as Error).message });
    }
    this.emit();
  }

  collapseAll() {
    const next: Tree = {};
    for (const [id, node] of Object.entries(this.tree)) {
      next[id] = node.kind === "content" ? node : { ...node, expanded: false };
    }
    this.tree = next;
    this.emit();
  }

  /** Ids of open nodes, parents first (for the shareable URL). */
  openIds(): string[] {
    return Object.values(this.tree)
      .filter((node) => node.expanded && node.kind !== "content" && this.isShown(node.id))
      .map((node) => node.id)
      .sort((a, b) => a.split("/").length - b.split("/").length);
  }

  isShown(id: string): boolean {
    let node = this.tree[id];
    while (node?.parent) {
      const parent = this.tree[node.parent];
      if (!parent || !this.visibleChildren(parent).includes(node.id)) return false;
      node = parent;
    }
    return Boolean(node);
  }

  /** Visible nodes in depth-first order. */
  visible(): TNode[] {
    const result: TNode[] = [];
    const walk = (id: string) => {
      const node = this.tree[id];
      if (!node) return;
      result.push(node);
      this.visibleChildren(node).forEach(walk);
    };
    if (this.rootId) walk(this.rootId);
    return result;
  }

  path(id: string): TNode[] {
    const result: TNode[] = [];
    let node = this.tree[id];
    while (node) {
      result.unshift(node);
      node = node.parent ? this.tree[node.parent] : (undefined as unknown as TNode);
    }
    return result;
  }
}

export function fetchContent(source: ContentSource, page: number, pageSize: number,
                             options: Record<string, string>): Promise<Content> {
  return source.kind === "section"
    ? api.section(source.ticker, source.key, page, pageSize, options)
    : api.partnerTransactions(source.ticker, source.side, source.key);
}

export const store = new DiagramStore();

export function useDiagram() {
  return useSyncExternalStore(store.subscribe, store.getSnapshot);
}
