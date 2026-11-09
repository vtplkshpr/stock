"""Suppliers and customers of a listed company or an organisation of the register.

Sources, for side="suppliers" (customers is the mirror image):
  1. the company's own related-party purchases (the counterparty sold to it);
  2. sales that other listed companies report to it (counterparty linked to its organisation
     record, or naming its ticker);
  3. supply_chain_relations rows where it is the customer (as a company or an organisation).

A counterparty is identified by its organisation record (src/organizations.py), so every
spelling of one name lands on one partner; a listed partner is addressed by its ticker, an
unlisted one by "org:<id>", and both can be opened further. Names without a record (people,
placeholder lines) are grouped by normalised name and only show their transactions.

The same transaction is usually disclosed in both the separate and the consolidated report, and
reporting periods overlap (quarter, year to date, full year), so a partner's amount is the figure
of its latest period in one scope (consolidated when available), never a sum.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from . import db
from .names import normalize
from .sections import Company, col

PURCHASE_TYPES = ("purchase_goods", "purchase_materials", "purchase_services")
SALE_TYPES = ("sale_goods", "sale_services", "sale_other")
SIDES = ("suppliers", "customers")
# A relationship is disclosed from the reporter's point of view ("X is our subsidiary"). When the
# partner is the reporter, the partner's role towards the company is the reverse one.
REVERSED = {
    "subsidiary": "parent", "indirect_subsidiary": "indirect_parent", "associate": "investor",
    "major_shareholder": "investee", "key_management": "other",
}


@dataclass
class Partner:
    key: str
    ref: str | None  # ticker or "org:<id>" when the partner can be opened
    name: str
    ticker: str | None
    kind: str | None = None
    legal_form: str | None = None


@dataclass
class Line:
    partner: Partner
    relationship: str | None
    transaction_type: str
    description: str | None
    amount: Any
    period_start: date | None
    period_end: date | None
    scope: str | None
    reported_by: str
    source: str


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class _Directory:
    """Organisation and listed-company lookups for one request."""

    def __init__(self) -> None:
        self.orgs = {row["org_id"]: row for row in db.rows(
            """SELECT o.org_id, o.canonical_name, o.kind, o.legal_form, c.ticker
               FROM organizations AS o LEFT JOIN companies AS c ON c.ticker = o.ticker""")}
        self.org_of_ticker = {row["ticker"]: org_id for org_id, row in self.orgs.items() if row["ticker"]}

    def by_org(self, org_id: int) -> Partner:
        row = self.orgs[org_id]
        if row["ticker"]:
            return Partner(f"t:{row['ticker']}", row["ticker"], row["canonical_name"], row["ticker"],
                           row["kind"], row["legal_form"])
        return Partner(f"o:{org_id}", f"org:{org_id}", row["canonical_name"], None, row["kind"], row["legal_form"])

    def by_company(self, ticker: str, name: str) -> Partner:
        org_id = self.org_of_ticker.get(ticker)
        if org_id is not None:
            return self.by_org(org_id)
        return Partner(f"t:{ticker}", ticker, name, ticker)

    def resolve(self, org_id: int | None, ticker: str | None, name: str) -> Partner:
        if org_id is not None and org_id in self.orgs:
            return self.by_org(org_id)
        if ticker:
            return Partner(f"t:{ticker}", ticker, name, ticker)
        return Partner(f"n:{normalize(name)}", None, name, None)


def own_org_ids(company: Company, directory: _Directory) -> list[int]:
    if company.org_id is not None:
        return [company.org_id]
    org_id = directory.org_of_ticker.get(company.ticker or "")
    return [org_id] if org_id is not None else []


def lines(company: Company, side: str) -> list[Line]:
    directory = _Directory()
    own_types, reverse_types = (PURCHASE_TYPES, SALE_TYPES) if side == "suppliers" else (SALE_TYPES, PURCHASE_TYPES)
    org_ids = own_org_ids(company, directory)
    result: list[Line] = []

    if company.listed:
        for row in db.rows(
            f"""SELECT counterparty_name, counterparty_ticker, counterparty_org_id, relationship, transaction_type,
                       description, amount, period_start, period_end, report_scope
                FROM related_party_transactions
                WHERE company_id = %(cid)s AND transaction_type IN ({_in(own_types)})""",
            {"cid": company.company_id},
        ):
            partner = directory.resolve(row["counterparty_org_id"], row["counterparty_ticker"], row["counterparty_name"])
            if partner.ticker and partner.ticker == company.ticker:
                continue
            result.append(Line(partner, row["relationship"], row["transaction_type"], row["description"],
                               row["amount"], row["period_start"], row["period_end"], row["report_scope"],
                               company.ticker or "", "own report"))

    org_filter = f"t.counterparty_org_id IN ({', '.join(str(i) for i in org_ids)})" if org_ids else "FALSE"
    for row in db.rows(
        f"""SELECT reporter.ticker, reporter.company_name, t.relationship, t.transaction_type, t.description,
                   t.amount, t.period_start, t.period_end, t.report_scope
            FROM related_party_transactions AS t
            JOIN companies AS reporter ON reporter.company_id = t.company_id
            WHERE NOT (t.company_id <=> %(cid)s) AND t.transaction_type IN ({_in(reverse_types)})
              AND ({org_filter} OR (%(ticker)s IS NOT NULL AND t.counterparty_ticker = %(ticker)s))""",
        {"cid": company.company_id, "ticker": company.ticker},
    ):
        relationship = REVERSED.get(row["relationship"], row["relationship"])
        result.append(Line(directory.by_company(row["ticker"], row["company_name"]), relationship,
                           row["transaction_type"], row["description"], row["amount"], row["period_start"],
                           row["period_end"], row["report_scope"], row["ticker"], "partner's report"))

    own, other = ("customer", "supplier") if side == "suppliers" else ("supplier", "customer")
    own_org_filter = f"r.{own}_org_id IN ({', '.join(str(i) for i in org_ids)})" if org_ids else "FALSE"
    for row in db.rows(
        f"""SELECT c.ticker, c.company_name, r.{other}_org_id AS org_id, r.product_category
            FROM supply_chain_relations AS r LEFT JOIN companies AS c ON c.company_id = r.{other}_id
            WHERE r.{own}_id <=> %(cid)s AND %(cid)s IS NOT NULL OR {own_org_filter}""",
        {"cid": company.company_id},
    ):
        partner = directory.resolve(row["org_id"], row["ticker"], row["company_name"] or "")
        result.append(Line(partner, None, "supply_chain", row["product_category"], None, None, None, None,
                           "", "supply chain"))
    return result


def _latest(group: list[Line]) -> tuple[list[Line], str | None]:
    """Lines of the partner's latest period, in one scope (consolidated first), longest period first."""
    dated = [line for line in group if line.period_end]
    if not dated:
        return [], None
    scopes = {line.scope for line in dated}
    scope = "consolidated" if "consolidated" in scopes else ("separate" if "separate" in scopes else None)
    dated = [line for line in dated if line.scope == scope]
    end = max(line.period_end for line in dated)
    starts = [line.period_start for line in dated if line.period_end == end and line.period_start]
    start = min(starts) if starts else None
    chosen = [line for line in dated if line.period_end == end and line.period_start == start]
    return chosen, scope


def summary(company: Company, side: str) -> list[dict[str, Any]]:
    groups: dict[str, list[Line]] = defaultdict(list)
    for line in lines(company, side):
        groups[line.partner.key].append(line)

    partners = []
    for key, group in groups.items():
        partner = group[0].partner
        latest, scope = _latest(group)
        amount = sum((line.amount for line in latest if line.amount is not None), start=0) if latest else None
        products: dict[str, Any] = defaultdict(int)
        for line in latest or group:
            if line.description:
                products[line.description] += line.amount or 0
        partners.append({
            "key": key,
            "ref": partner.ref,
            "expandable": partner.ref is not None,
            "name": partner.name,
            "ticker": partner.ticker,
            "listed": partner.ticker is not None,
            "kind": partner.kind,
            "legal_form": partner.legal_form,
            "relationships": sorted({line.relationship for line in group if line.relationship}),
            "products": [p for p, _ in sorted(products.items(), key=lambda item: -item[1])][:3],
            "latest_amount": amount,
            "latest_period_start": latest[0].period_start if latest else None,
            "latest_period_end": latest[0].period_end if latest else None,
            "latest_scope": scope,
            "lines": len(group),
            "sources": sorted({line.source for line in group}),
        })
    # Amounts of different periods (a quarter vs a full year) are not comparable, so partners are
    # ranked by how recent their latest figure is, then by its size.
    partners.sort(key=lambda p: (p["latest_period_end"] or date.min, p["latest_amount"] or 0, p["name"]),
                  reverse=True)
    return partners


def transactions(company: Company, side: str, key: str) -> dict[str, Any]:
    found = [line for line in lines(company, side) if line.partner.key == key]
    found.sort(key=lambda line: (line.period_end or date.min, line.amount or 0), reverse=True)
    name = found[0].partner.name if found else key
    return {
        "title": f"{'Purchases from' if side == 'suppliers' else 'Sales to'} {name}",
        "columns": [col("period", "Period"), col("scope", "Scope"), col("reported_by", "Reported by"),
                    col("transaction_type", "Type"), col("description", "Description"),
                    col("amount", "Amount", "money")],
        "rows": [{
            "period": (f"{line.period_start:%d/%m/%Y} – {line.period_end:%d/%m/%Y}"
                       if line.period_start and line.period_end else ""),
            "scope": line.scope, "reported_by": line.reported_by or line.source,
            "transaction_type": line.transaction_type, "description": line.description,
            "amount": line.amount,
        } for line in found],
        "total": len(found), "page": 1, "page_size": max(len(found), 1),
        "note": "The same transaction often appears in both the separate and consolidated reports.",
    }
