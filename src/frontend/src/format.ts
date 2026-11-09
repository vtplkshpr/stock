import type { ColumnType } from "./types";

const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const decimal = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

/** VND amounts: 1,234.5 bn / 12.3 m / 950,000. */
export function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${decimal.format(value / 1e12)} tn`;
  if (abs >= 1e9) return `${decimal.format(value / 1e9)} bn`;
  if (abs >= 1e6) return `${decimal.format(value / 1e6)} m`;
  return integer.format(value);
}

export function date(value: unknown): string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}/.test(value)) return value ? String(value) : "–";
  const [y, m, d] = value.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

export function format(value: unknown, type: ColumnType): string {
  if (value === null || value === undefined || value === "") return "–";
  const n = typeof value === "number" ? value : Number(value);
  switch (type) {
    case "money":
      return money(n);
    case "price":
    case "number":
      return Number.isFinite(n) ? (Number.isInteger(n) ? integer.format(n) : decimal.format(n)) : String(value);
    case "percent":
    case "percent_bar":
      return Number.isFinite(n) ? `${decimal.format(n)}%` : String(value);
    case "fraction":
      return Number.isFinite(n) ? `${decimal.format(n * 100)}%` : String(value);
    case "date":
      return date(value);
    case "bool":
      return value ? "Yes" : "No";
    default:
      return String(value);
  }
}

/** Sign class for coloured changes. */
export function trend(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return "flat";
  return value > 0 ? "up" : "down";
}

const RELATIONSHIPS: Record<string, string> = {
  subsidiary: "Subsidiary",
  indirect_subsidiary: "Indirect subsidiary",
  associate: "Associate",
  major_shareholder: "Major shareholder",
  co_owner: "Co-owner",
  group_company: "Group company",
  key_management: "Key management",
  parent: "Parent company",
  indirect_parent: "Indirect parent",
  investor: "Investor (associate of it)",
  investee: "Investee (it is a major shareholder)",
  other: "Other",
};

export const relationship = (value: string) => RELATIONSHIPS[value] ?? value;
