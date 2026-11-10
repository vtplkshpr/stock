// Shapes returned by the diagram API (src/backend/app.py).

export interface SearchHit {
  ref: string; // ticker, or "org:<id>" for an unlisted organisation
  ticker: string | null;
  kind?: string | null;
  company_name: string;
  exchange: string | null;
  has_data: boolean;
}

export interface SectionInfo {
  key: string;
  label: string;
  count: number;
  count_label: string;
  group: boolean;
  children: SectionInfo[];
}

export interface CompanySummary {
  ref: string; // ticker, or "org:<id>" for an unlisted organisation
  entity: "company" | "organization";
  ticker: string | null;
  name: string;
  kind: string | null;
  legal_form: string | null;
  full_name: string | null;
  exchange: string | null;
  industry: string | null;
  price: { price_date: string; close_price: number; change_percentage: number | null } | null;
  sections: SectionInfo[];
  partners: { suppliers: number; customers: number };
  /** Smart-money signal ("Dòng tiền lớn"), listed companies only. */
  signal: SmartMoneySignal | null;
}

export interface SmartMoneySignal {
  level: -2 | -1 | 0 | 1 | 2;
  label: string;
  message: string;
  as_of: string | null;
  reasons: string[];
}

export type Side = "suppliers" | "customers";

export interface Partner {
  key: string;
  ref: string | null; // how to open it (ticker or "org:<id>"); null = transactions only
  expandable: boolean;
  name: string;
  ticker: string | null;
  listed: boolean;
  kind: string | null;
  legal_form: string | null;
  relationships: string[];
  products: string[];
  /** What is traded in the latest period, as worded in the report; share = % of that direction's total. */
  items: { description: string; amount: number | null; share: number | null }[];
  latest_document: string | null;
  latest_reported_by: string[];
  latest_amount: number | null;
  latest_period_start: string | null;
  latest_period_end: string | null;
  latest_scope: string | null;
  lines: number;
  sources: string[];
}

export interface PartnerPage {
  side: Side;
  total: number;
  offset: number;
  items: Partner[];
}

export type ColumnType =
  | "text" | "number" | "money" | "price" | "percent" | "fraction" | "date" | "ticker"
  | "bool" | "percent_bar" | "link" | "auto";

export interface Column {
  key: string;
  label: string;
  type: ColumnType;
}

export interface Field {
  label: string;
  value: string | number | null;
  type: ColumnType;
}

export interface OptionChoice {
  value: string | null;
  label?: string;
  choices: [string, string][];
}

export interface ChartData {
  type: "line" | "bar";
  unit: "money" | "price" | "number";
  series: { name: string; points: [string, number | null][] }[];
}

export type Row = Record<string, unknown>;

export interface Content {
  key?: string;
  title: string;
  fields?: Field[];
  texts?: { label: string; text: string }[];
  chart?: ChartData;
  columns?: Column[];
  rows?: Row[];
  total?: number;
  page?: number;
  page_size?: number;
  options?: Record<string, OptionChoice>;
  note?: string;
  row_action?: "news";
}

export interface NewsItem {
  title: string;
  content_text: string | null;
  media_type: string;
  media_url: string | null;
  published_at: string | null;
  source_name: string | null;
  source_url: string | null;
  ticker: string;
}
