"""The information branches of a company node and the content behind each of them.

A section is either a group (its children are further branches) or a leaf (it opens one content
panel). Leaf content is returned in one shape the frontend renders generically:

  {title, fields?, texts?, chart?, columns?, rows?, total?, page?, page_size?, options?, note?}

Column types: text, number, money (VND), price (VND/share), percent (already in %), fraction
(0.15 = 15%), date, ticker (opens that company), bool, percent_bar (percent drawn as a bar).
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from . import db

Payload = dict[str, Any]
Options = dict[str, str]


@dataclass
class Company:
    """The entity a diagram node stands for: a listed company (company_id, ticker) or an
    organisation of the register without a listing (org_id only). `ref` is how the API and the
    frontend address it: the ticker, or "org:<org_id>"."""
    company_id: int | None
    ticker: str | None
    name: str
    org_id: int | None = None

    @property
    def ref(self) -> str:
        return self.ticker if self.company_id else f"org:{self.org_id}"

    @property
    def listed(self) -> bool:
        return self.company_id is not None


@dataclass
class Section:
    key: str
    label: str
    count: Callable[[Company], int] | None = None
    fetch: Callable[[Company, Options, int, int], Payload] | None = None
    children: list["Section"] = field(default_factory=list)
    description: str = ""


# --- helpers ---------------------------------------------------------------------------------

def col(key: str, label: str, type_: str = "text") -> dict[str, str]:
    return {"key": key, "label": label, "type": type_}


def count_sql(sql: str) -> Callable[[Company], int]:
    return lambda company: int(db.scalar(sql, {"cid": company.company_id, "ticker": company.ticker,
                                                 "oid": company.org_id}) or 0)


def page_rows(sql: str, params: dict[str, Any], page: int, page_size: int) -> tuple[list[dict], int]:
    """Run sql (without LIMIT) for one page; return (rows, total)."""
    total = int(db.scalar(f"SELECT COUNT(*) AS n FROM ({sql}) AS counted", params) or 0)
    found = db.rows(
        f"{sql} LIMIT %(limit)s OFFSET %(offset)s",
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    )
    return found, total


def table(title: str, columns: list[dict], sql: str, company: Company, page: int, page_size: int,
          **extra: Any) -> Payload:
    found, total = page_rows(sql, {"cid": company.company_id, "ticker": company.ticker, "oid": company.org_id,
                                   **extra.pop("params", {})}, page, page_size)
    return {"title": title, "columns": columns, "rows": found, "total": total,
            "page": page, "page_size": page_size, **extra}


def choice(options: Options, key: str, choices: list[tuple[str, str]], default: str | None = None) -> dict:
    values = [value for value, _ in choices]
    selected = options.get(key)
    if selected not in values:
        selected = default if default in values else (values[0] if values else None)
    return {"value": selected, "choices": [list(c) for c in choices]}


# --- profile ---------------------------------------------------------------------------------

def fetch_profile(company: Company, options: Options, page: int, page_size: int) -> Payload:
    import json

    row = db.one("SELECT * FROM companies WHERE company_id = %(cid)s", {"cid": company.company_id}) or {}
    fields = [
        {"label": "Company name", "value": row.get("company_name"), "type": "text"},
        {"label": "Exchange", "value": row.get("exchange"), "type": "text"},
        {"label": "Industry", "value": row.get("industry"), "type": "text"},
        {"label": "Tax code", "value": row.get("tax_code"), "type": "text"},
        {"label": "Charter capital", "value": row.get("charter_capital"), "type": "money"},
        {"label": "Listed shares", "value": row.get("listed_shares"), "type": "number"},
        {"label": "Outstanding shares", "value": row.get("outstanding_shares"), "type": "number"},
        {"label": "Established", "value": row.get("established_date"), "type": "date"},
        {"label": "Listed", "value": row.get("listed_date"), "type": "date"},
        {"label": "First trading day", "value": row.get("first_trading_date"), "type": "date"},
        {"label": "Fiscal year starts (month)", "value": row.get("fiscal_year_start_month"), "type": "number"},
        {"label": "Listing licence", "value": row.get("listing_license"), "type": "text"},
        {"label": "Website", "value": row.get("website"), "type": "link"},
        {"label": "Email", "value": row.get("email"), "type": "text"},
        {"label": "Fax", "value": row.get("fax"), "type": "text"},
    ]
    for column in ("headquarters_addresses", "phone_numbers"):
        try:
            pairs = json.loads(row.get(column) or "[]")
        except (TypeError, ValueError):
            pairs = []
        for pair in pairs:
            if isinstance(pair, list) and len(pair) == 2:
                fields.append({"label": pair[0], "value": pair[1], "type": "text"})
    texts = [
        {"label": label, "text": row[column]}
        for column, label in (("description", "Description"), ("company_history", "History"))
        if row.get(column)
    ]
    return {"title": "Company profile", "fields": [f for f in fields if f["value"] not in (None, "")],
            "texts": texts}


# --- leadership ------------------------------------------------------------------------------

LEADER_GROUPS = (
    ("board", "Board of directors"),
    ("management", "Management"),
    ("audit_committee", "Audit committee"),
    ("other", "Other officers"),
)
CURRENT = "COALESCE(status, 'current') = 'current'"


def leader_section(group: str, label: str) -> Section:
    where = f"company_id = %(cid)s AND leader_group = '{group}' AND {CURRENT}"
    return Section(
        f"leaders.{group}", label,
        count=count_sql(f"SELECT COUNT(*) FROM company_leaders WHERE {where}"),
        fetch=lambda c, o, p, s: table(
            label,
            [col("person_name", "Name"), col("position", "Position"),
             col("birth_year", "Born", "number"), col("appointed_date", "Appointed", "date"),
             col("is_legal_representative", "Legal rep.", "bool")],
            f"""SELECT person_name, position, birth_year, appointed_date, is_legal_representative
                FROM company_leaders WHERE {where} ORDER BY appointed_date IS NULL, appointed_date, person_name""",
            c, p, s),
    )


FORMER_WHERE = "company_id = %(cid)s AND status = 'former'"
LEADERS = Section("leaders", "Leadership", children=[
    *(leader_section(group, label) for group, label in LEADER_GROUPS),
    Section(
        "leaders.former", "Former officers",
        count=count_sql(f"SELECT COUNT(*) FROM company_leaders WHERE {FORMER_WHERE}"),
        fetch=lambda c, o, p, s: table(
            "Former officers",
            [col("person_name", "Name"), col("position", "Position"),
             col("appointed_date", "Appointed", "date"), col("dismissed_date", "Left", "date")],
            f"""SELECT person_name, position, appointed_date, dismissed_date FROM company_leaders
                WHERE {FORMER_WHERE} ORDER BY dismissed_date DESC, person_name""",
            c, p, s),
    ),
])


# --- shareholders ----------------------------------------------------------------------------

def fetch_holders(company: Company, options: Options, page: int, page_size: int) -> Payload:
    dates = [r["snapshot_date"] for r in db.rows(
        "SELECT DISTINCT snapshot_date FROM stock_holders WHERE company_id = %(cid)s "
        "ORDER BY snapshot_date DESC", {"cid": company.company_id})]
    snapshot = choice(options, "snapshot", [(d.isoformat(), d.isoformat()) for d in dates])
    return table(
        "Shareholders",
        [col("holder_name", "Shareholder"), col("holder_type", "Type"),
         col("shares_owned", "Shares", "number"), col("ownership_percentage", "Ownership", "percent_bar")],
        """SELECT holder_name, holder_type, shares_owned, ownership_percentage FROM stock_holders
           WHERE company_id = %(cid)s AND snapshot_date = %(snapshot)s
           ORDER BY ownership_percentage DESC, holder_name""",
        company, page, page_size, params={"snapshot": snapshot["value"]},
        options={"snapshot": {**snapshot, "label": "As of"}},
    )


HOLDERS = Section(
    "holders", "Shareholders",
    count=count_sql("""SELECT COUNT(*) FROM stock_holders WHERE company_id = %(cid)s AND snapshot_date =
                       (SELECT MAX(snapshot_date) FROM stock_holders WHERE company_id = %(cid)s)"""),
    fetch=fetch_holders,
)


# --- subsidiaries, associates, investments ---------------------------------------------------

INVESTMENT_KINDS = (
    ("direct", "Direct subsidiaries", "relation_type = 'subsidiary' AND COALESCE(is_direct, 1) = 1"),
    ("indirect", "Indirect subsidiaries", "relation_type = 'subsidiary' AND is_direct = 0"),
    ("associates", "Associates", "relation_type = 'associate'"),
    ("shareholdings", "Other shareholdings", "relation_type = 'shareholding'"),
)


def investment_section(kind: str, label: str, condition: str) -> Section:
    where = f"company_id = %(cid)s AND {condition}"
    return Section(
        f"investments.{kind}", label,
        count=count_sql(f"SELECT COUNT(*) FROM company_investments WHERE {where}"),
        fetch=lambda c, o, p, s: table(
            label,
            [col("investee_name", "Company"), col("investee_ticker", "Ticker", "ticker"),
             col("ownership_percentage", "Ownership", "percent_bar"),
             col("voting_percentage", "Voting %", "percent"),
             col("charter_capital", "Charter capital", "money"),
             col("investment_cost", "Cost", "money"), col("business_line", "Business"),
             col("operating_status", "Status"), col("as_of_date", "As of", "date")],
            f"""SELECT investee_name, investee_ticker, ownership_percentage, voting_percentage,
                       charter_capital, investment_cost, business_line, operating_status, as_of_date
                FROM company_investments WHERE {where}
                ORDER BY ownership_percentage DESC, investee_name""",
            c, p, s),
    )


INVESTMENTS = Section("investments", "Subsidiaries & investments", children=[
    investment_section(*kind) for kind in INVESTMENT_KINDS
])


# --- price & valuation -----------------------------------------------------------------------

def fetch_price(company: Company, options: Options, page: int, page_size: int) -> Payload:
    params = {"cid": company.company_id}
    latest = db.one("""SELECT p.*, v.market_cap, v.pe_ttm, v.pb, v.ps_ttm, v.ev_ebitda,
                              v.dividend_yield, v.fcf_yield
                       FROM stock_prices AS p LEFT JOIN valuation_metrics AS v
                         ON v.company_id = p.company_id AND v.price_date = p.price_date
                       WHERE p.company_id = %(cid)s ORDER BY p.price_date DESC LIMIT 1""", params) or {}
    fields = [
        {"label": "Date", "value": latest.get("price_date"), "type": "date"},
        {"label": "Close", "value": latest.get("close_price"), "type": "price"},
        {"label": "Change", "value": latest.get("change_percentage"), "type": "percent"},
        {"label": "Volume", "value": latest.get("trading_volume"), "type": "number"},
        {"label": "Value", "value": latest.get("trading_value"), "type": "money"},
        {"label": "Market cap", "value": latest.get("market_cap"), "type": "money"},
        {"label": "P/E (TTM)", "value": latest.get("pe_ttm"), "type": "number"},
        {"label": "P/B", "value": latest.get("pb"), "type": "number"},
        {"label": "P/S (TTM)", "value": latest.get("ps_ttm"), "type": "number"},
        {"label": "EV/EBITDA", "value": latest.get("ev_ebitda"), "type": "number"},
        {"label": "Dividend yield", "value": latest.get("dividend_yield"), "type": "fraction"},
        {"label": "FCF yield", "value": latest.get("fcf_yield"), "type": "fraction"},
    ]
    series = db.rows("""SELECT price_date, close_price FROM stock_prices WHERE company_id = %(cid)s
                        AND price_date >= DATE_SUB((SELECT MAX(price_date) FROM stock_prices
                                                    WHERE company_id = %(cid)s), INTERVAL 1 YEAR)
                        ORDER BY price_date""", params)
    result = table(
        "Price & valuation",
        [col("price_date", "Date", "date"), col("open_price", "Open", "price"),
         col("high_price", "High", "price"), col("low_price", "Low", "price"),
         col("close_price", "Close", "price"), col("change_percentage", "Change", "percent"),
         col("trading_volume", "Volume", "number"), col("trading_value", "Value", "money"),
         col("negotiated_volume", "Negotiated vol.", "number"),
         col("pe_ttm", "P/E", "number"), col("pb", "P/B", "number")],
        """SELECT p.price_date, p.open_price, p.high_price, p.low_price, p.close_price,
                  p.change_percentage, p.trading_volume, p.trading_value, p.negotiated_volume,
                  v.pe_ttm, v.pb
           FROM stock_prices AS p LEFT JOIN valuation_metrics AS v
             ON v.company_id = p.company_id AND v.price_date = p.price_date
           WHERE p.company_id = %(cid)s ORDER BY p.price_date DESC""",
        company, page, page_size,
    )
    result["fields"] = [f for f in fields if f["value"] is not None]
    if series:
        result["chart"] = {"type": "line", "unit": "price", "series": [{
            "name": "Close", "points": [[r["price_date"], r["close_price"]] for r in series]}]}
    return result


PRICE = Section(
    "price", "Price & valuation",
    count=count_sql("SELECT COUNT(*) FROM stock_prices WHERE company_id = %(cid)s"),
    fetch=fetch_price,
)


# --- financial statements --------------------------------------------------------------------

STATEMENTS = (
    ("income_statement", "Income statement"),
    ("balance_sheet", "Balance sheet"),
    ("cash_flow", "Cash flow"),
)
PERIODS_SHOWN = 6


def period_label(report_type: str, fiscal_year: int, fiscal_quarter: int | None) -> str:
    if report_type == "annual":
        return f"FY{fiscal_year}"
    if report_type == "semi_annual":
        return f"H1 FY{fiscal_year}"
    return f"Q{fiscal_quarter} FY{fiscal_year}"


def scope_choice(options: Options, table_name: str, company: Company) -> dict:
    scopes = [r["report_scope"] for r in db.rows(
        f"SELECT DISTINCT report_scope FROM {table_name} WHERE company_id = %(cid)s "
        "AND report_scope IS NOT NULL ORDER BY report_scope", {"cid": company.company_id})]
    labels = {"consolidated": "Consolidated", "separate": "Separate"}
    return {**choice(options, "scope", [(s, labels.get(s, s)) for s in scopes], "consolidated"),
            "label": "Scope"}


def statement_section(statement: str, label: str) -> Section:
    def fetch(company: Company, options: Options, page: int, page_size: int) -> Payload:
        scope = scope_choice(options, "finance_report_items", company)
        types = [r["report_type"] for r in db.rows(
            "SELECT DISTINCT report_type FROM finance_reports WHERE company_id = %(cid)s",
            {"cid": company.company_id})]
        period_choices = [(v, l) for v, l in (("quarterly", "Quarters"), ("annual", "Years"))
                          if v in types or (v == "annual" and "semi_annual" in types)]
        period = {**choice(options, "period", period_choices, "quarterly"), "label": "Periods"}
        report_types = ("annual", "semi_annual") if period["value"] == "annual" else ("quarterly",)
        params = {"cid": company.company_id, "scope": scope["value"], "statement": statement,
                  "t1": report_types[0], "t2": report_types[-1]}
        # Circular 99 renumbered many lines, so periods are only set side by side within one
        # circular (detected as in metrics.py: its balance sheet has total assets on line 280).
        all_periods = db.rows(
            """SELECT r.report_type, r.fiscal_year, r.fiscal_quarter, MAX(r.period_end) AS period_end,
                      MAX(EXISTS (SELECT 1 FROM finance_report_items AS i
                                  WHERE i.company_id = r.company_id AND i.report_scope = r.report_scope
                                    AND i.report_type = r.report_type AND i.fiscal_year = r.fiscal_year
                                    AND i.fiscal_quarter <=> r.fiscal_quarter
                                    AND i.statement = 'balance_sheet' AND i.item_code = '280')) AS tt99
               FROM finance_reports AS r WHERE r.company_id = %(cid)s AND r.report_scope = %(scope)s
                 AND r.report_type IN (%(t1)s, %(t2)s)
               GROUP BY r.report_type, r.fiscal_year, r.fiscal_quarter
               ORDER BY period_end DESC""", params)
        circulars = list(dict.fromkeys("tt99" if p["tt99"] else "tt200" for p in all_periods))
        circular = {**choice(options, "circular", [(c, {"tt99": "Circular 99", "tt200": "Circular 200"}[c])
                                                   for c in circulars]), "label": "Standard"}
        periods = [p for p in all_periods
                   if ("tt99" if p["tt99"] else "tt200") == circular["value"]][:PERIODS_SHOWN]
        columns = [col("item_code", "Code"), col("item_name", "Item")]
        keys = {}
        for index, p in enumerate(periods):
            key = f"p{index}"
            keys[(p["report_type"], p["fiscal_year"], p["fiscal_quarter"])] = key
            columns.append(col(key, period_label(p["report_type"], p["fiscal_year"], p["fiscal_quarter"]), "money"))
        items: dict[str, dict] = {}
        if periods:
            for row in db.rows(
                """SELECT item_code, item_name, report_type, fiscal_year, fiscal_quarter, value
                   FROM finance_report_items WHERE company_id = %(cid)s AND report_scope = %(scope)s
                     AND statement = %(statement)s AND report_type IN (%(t1)s, %(t2)s)""", params):
                key = keys.get((row["report_type"], row["fiscal_year"], row["fiscal_quarter"]))
                if key is None:
                    continue
                item = items.setdefault(row["item_code"], {"item_code": row["item_code"],
                                                           "item_name": row["item_name"]})
                item[key] = row["value"]
        ordered = sorted(items.values(), key=lambda r: (len(r["item_code"]), r["item_code"]))
        start = (page - 1) * page_size
        note = "Amounts in VND."
        if len(circulars) > 1:
            note += " Circular 99 renumbered many lines, so its periods are shown apart from Circular 200 ones."
        return {"title": label, "columns": columns, "rows": ordered[start:start + page_size],
                "total": len(ordered), "page": page, "page_size": page_size,
                "options": {"scope": scope, "period": period, "circular": circular}, "note": note}

    return Section(
        f"reports.{statement}", label,
        count=count_sql(f"""SELECT COUNT(DISTINCT report_type, COALESCE(report_scope, ''), fiscal_year,
                                                  COALESCE(fiscal_quarter, 0))
                            FROM finance_report_items WHERE company_id = %(cid)s
                              AND statement = '{statement}'"""),
        fetch=fetch,
        description="Number of reports",
    )


REPORTS = Section("reports", "Financial statements", children=[
    statement_section(*statement) for statement in STATEMENTS
])


# --- financial metrics -----------------------------------------------------------------------

METRIC_GROUPS = (
    ("cash_flow", "Cash flow", [
        ("cfo", "Operating cash flow (CFO)", "money"), ("cfi", "Investing cash flow (CFI)", "money"),
        ("cff", "Financing cash flow (CFF)", "money"), ("capex", "Capex", "money"),
        ("free_cash_flow", "Free cash flow", "money"), ("dividends_paid", "Dividends paid", "money"),
        ("cash_flow_pattern", "Pattern (CFO/CFI/CFF)", "text"), ("lifecycle_stage", "Life-cycle stage", "text"),
    ]),
    ("profitability", "Profitability", [
        ("revenue", "Revenue", "money"), ("net_income", "Net income", "money"),
        ("gross_margin", "Gross margin", "fraction"), ("ebit_margin", "EBIT margin", "fraction"),
        ("net_margin", "Net margin", "fraction"), ("roe", "ROE", "fraction"),
        ("roa", "ROA", "fraction"), ("roic", "ROIC", "fraction"),
    ]),
    ("quality", "Earnings quality", [
        ("cfo_to_net_income", "CFO / net income", "number"), ("accrual_ratio", "Accrual ratio", "fraction"),
    ]),
    ("leverage", "Leverage", [
        ("interest_bearing_debt", "Interest-bearing debt", "money"), ("net_debt", "Net debt", "money"),
        ("debt_to_equity", "Debt / equity", "number"), ("net_debt_to_ebitda", "Net debt / EBITDA", "number"),
        ("interest_coverage", "EBIT / interest", "number"),
        ("cfo_interest_coverage", "CFO interest coverage", "number"),
    ]),
    ("liquidity", "Liquidity & efficiency", [
        ("current_ratio", "Current ratio", "number"), ("quick_ratio", "Quick ratio", "number"),
        ("cash_ratio", "Cash ratio", "number"), ("dso", "Receivable days (DSO)", "number"),
        ("dio", "Inventory days (DIO)", "number"), ("dpo", "Payable days (DPO)", "number"),
        ("cash_conversion_cycle", "Cash conversion cycle", "number"),
        ("asset_turnover", "Asset turnover", "number"),
    ]),
    ("growth", "Growth & per share", [
        ("revenue_yoy", "Revenue YoY", "fraction"), ("net_income_yoy", "Net income YoY", "fraction"),
        ("cfo_yoy", "CFO YoY", "fraction"), ("eps", "EPS", "price"), ("bvps", "Book value / share", "price"),
        ("cfo_per_share", "CFO / share", "price"),
    ]),
    ("warnings", "Warning flags", [
        ("flag_negative_cfo", "Negative CFO", "bool"), ("flag_negative_fcf", "Negative FCF", "bool"),
        ("flag_low_earnings_quality", "CFO / net income < 1", "bool"),
        ("flag_high_accruals", "Accruals > 10%", "bool"),
        ("flag_weak_interest_coverage", "EBIT / interest < 1.5x", "bool"),
        ("flag_high_leverage", "Net debt / EBITDA > 4x", "bool"),
        ("flag_low_liquidity", "Current ratio < 1", "bool"),
    ]),
)


def metric_section(group: str, label: str, metrics: list[tuple[str, str, str]]) -> Section:
    def fetch(company: Company, options: Options, page: int, page_size: int) -> Payload:
        scope = scope_choice(options, "financial_metrics", company)
        period = {**choice(options, "period", [("ttm", "TTM"), ("year", "Years"), ("quarter", "Quarters")],
                           "ttm"), "label": "Periods"}
        selected = ", ".join(column for column, _, _ in metrics)
        periods = db.rows(
            f"""SELECT fiscal_year, fiscal_quarter, period_end, {selected} FROM financial_metrics
                WHERE company_id = %(cid)s AND report_scope = %(scope)s AND period_type = %(period)s
                ORDER BY period_end DESC LIMIT {PERIODS_SHOWN}""",
            {"cid": company.company_id, "scope": scope["value"], "period": period["value"]})
        columns = [col("metric", "Metric")]
        for index, p in enumerate(periods):
            name = f"FY{p['fiscal_year']}" if period["value"] == "year" else f"Q{p['fiscal_quarter']} FY{p['fiscal_year']}"
            columns.append(col(f"p{index}", name, "auto"))
        rows = []
        for column, metric_label, type_ in metrics:
            row = {"metric": metric_label, "_type": type_}
            for index, p in enumerate(periods):
                row[f"p{index}"] = p[column]
            rows.append(row)
        note = "TTM: twelve months to the quarter end." if period["value"] == "ttm" else ""
        if period["value"] == "quarter" and group in ("profitability", "quality", "warnings"):
            note = "Return ratios and flags are only computed for TTM and full years."
        return {"title": label, "columns": columns, "rows": rows, "total": len(rows), "page": 1,
                "page_size": len(rows) or 1, "options": {"scope": scope, "period": period}, "note": note}

    return Section(
        f"metrics.{group}", label,
        count=count_sql("SELECT COUNT(*) FROM financial_metrics WHERE company_id = %(cid)s AND period_type = 'ttm'"),
        fetch=fetch,
        description="TTM periods",
    )


METRICS = Section("metrics", "Financial metrics", children=[
    metric_section(*group) for group in METRIC_GROUPS
])


# --- trading activity ------------------------------------------------------------------------

def daily_chart(sql: str, company: Company, name: str, unit: str) -> dict | None:
    points = db.rows(sql, {"cid": company.company_id})
    if not points:
        return None
    return {"type": "bar", "unit": unit, "series": [{
        "name": name, "points": [[p["trade_date"], p["value"]] for p in reversed(points)]}]}


def trade_section(key: str, label: str, table_name: str, columns: list[dict], select: str,
                  chart: tuple[str, str, str] | None = None) -> Section:
    def fetch(company: Company, options: Options, page: int, page_size: int) -> Payload:
        result = table(label, columns,
                       f"SELECT {select} FROM {table_name} WHERE company_id = %(cid)s ORDER BY trade_date DESC",
                       company, page, page_size)
        if chart:
            column, name, unit = chart
            drawn = daily_chart(
                f"""SELECT trade_date, {column} AS value FROM {table_name} WHERE company_id = %(cid)s
                    ORDER BY trade_date DESC LIMIT 60""", company, name, unit)
            if drawn:
                result["chart"] = drawn
        return result

    return Section(
        f"trading.{key}", label,
        count=count_sql(f"SELECT COUNT(*) FROM {table_name} WHERE company_id = %(cid)s"),
        fetch=fetch,
    )


INSIDER_STATUS = """CASE WHEN execution_date IS NOT NULL
                              OR COALESCE(executed_buy, 0) + COALESCE(executed_sell, 0) > 0 THEN 'reported'
                         WHEN registration_end >= CURDATE() THEN 'in progress'
                         ELSE 'awaiting result' END"""
INSIDER_DONE = """100 * (COALESCE(executed_buy, 0) + COALESCE(executed_sell, 0))
                  / NULLIF(COALESCE(registered_buy, 0) + COALESCE(registered_sell, 0), 0)"""


def fetch_insiders(company: Company, options: Options, page: int, page_size: int) -> Payload:
    return table(
        "Insider & major shareholder trades",
        [col("trader_name", "Trader"), col("trader_position", "Position / relation"),
         col("related", "Related insider"), col("shares_before", "Shares before", "number"),
         col("registered_buy", "Reg. buy", "number"), col("registered_sell", "Reg. sell", "number"),
         col("registration_start", "From", "date"), col("registration_end", "To", "date"),
         col("executed_buy", "Bought", "number"), col("executed_sell", "Sold", "number"),
         col("execution_date", "Executed", "date"), col("done", "Done", "percent"),
         col("shares_after", "Shares after", "number"),
         col("ownership_after_percentage", "Owned after", "percent"), col("status", "Status")],
        f"""SELECT trader_name, trader_position,
                   CONCAT_WS(' - ', related_person_name, related_person_position) AS related,
                   shares_before, registered_buy, registered_sell, registration_start, registration_end,
                   executed_buy, executed_sell, execution_date, {INSIDER_DONE} AS done,
                   shares_after, ownership_after_percentage, {INSIDER_STATUS} AS status
            FROM insider_trades WHERE company_id = %(cid)s
            ORDER BY registration_start DESC, trader_name""",
        company, page, page_size,
    )


def fetch_intraday(company: Company, options: Options, page: int, page_size: int) -> Payload:
    dates = [r["trade_date"] for r in db.rows(
        "SELECT DISTINCT trade_date FROM intraday_trades WHERE company_id = %(cid)s ORDER BY trade_date DESC",
        {"cid": company.company_id})]
    day = {**choice(options, "date", [(d.isoformat(), d.isoformat()) for d in dates]), "label": "Session"}
    return table(
        "Intraday matched trades",
        [col("trade_time", "Time"), col("price", "Price", "price"), col("price_change", "Change", "price"),
         col("lot_volume", "Lot", "number"), col("cumulative_volume", "Cumulative", "number"),
         col("weight_percentage", "Weight", "percent")],
        """SELECT trade_time, price, price_change, lot_volume,
                  cumulative_volume, weight_percentage
           FROM intraday_trades WHERE company_id = %(cid)s AND trade_date = %(day)s ORDER BY seq""",
        company, page, page_size, params={"day": day["value"]}, options={"date": day},
        note="Columns as exported by the source; lot and cumulative figures are not reliable volumes.",
    )


TRADING = Section("trading", "Trading activity", children=[
    trade_section(
        "foreign", "Foreign investors", "foreign_trades",
        [col("trade_date", "Date", "date"), col("buy_volume", "Buy vol.", "number"),
         col("buy_value", "Buy value", "money"), col("sell_volume", "Sell vol.", "number"),
         col("sell_value", "Sell value", "money"), col("net_volume", "Net vol.", "number"),
         col("net_value", "Net value", "money"), col("room_remaining", "Room left", "number"),
         col("ownership_percentage", "Foreign owned", "percent")],
        "trade_date, buy_volume, buy_value, sell_volume, sell_value, net_volume, net_value, "
        "room_remaining, ownership_percentage",
        chart=("net_value", "Net value", "money"),
    ),
    trade_section(
        "proprietary", "Proprietary trading", "proprietary_trades",
        [col("trade_date", "Date", "date"), col("buy_volume", "Buy vol.", "number"),
         col("buy_value", "Buy value", "money"), col("sell_volume", "Sell vol.", "number"),
         col("sell_value", "Sell value", "money"), col("net_volume", "Net vol.", "number"),
         col("net_value", "Net value", "money")],
        "trade_date, buy_volume, buy_value, sell_volume, sell_value, net_volume, net_value",
        chart=("net_value", "Net value", "money"),
    ),
    trade_section(
        "orders", "Order statistics", "order_statistics",
        [col("trade_date", "Date", "date"), col("buy_orders", "Buy orders", "number"),
         col("buy_volume", "Buy vol.", "number"), col("avg_buy_order_volume", "Avg buy order", "number"),
         col("sell_orders", "Sell orders", "number"), col("sell_volume", "Sell vol.", "number"),
         col("avg_sell_order_volume", "Avg sell order", "number"), col("net_volume", "Net vol.", "number")],
        "trade_date, buy_orders, buy_volume, avg_buy_order_volume, sell_orders, sell_volume, "
        "avg_sell_order_volume, net_volume",
        chart=("net_volume", "Net volume", "number"),
    ),
    Section("trading.insiders", "Insider trades",
            count=count_sql("SELECT COUNT(*) FROM insider_trades WHERE company_id = %(cid)s"),
            fetch=fetch_insiders),
    Section("trading.intraday", "Intraday trades",
            count=count_sql("SELECT COUNT(*) FROM intraday_trades WHERE company_id = %(cid)s"),
            fetch=fetch_intraday),
])


# --- related parties and news ----------------------------------------------------------------

def fetch_related(company: Company, options: Options, page: int, page_size: int) -> Payload:
    return table(
        "Related-party transactions",
        [col("counterparty_name", "Related party"), col("counterparty_ticker", "Ticker", "ticker"),
         col("relationship", "Relationship"), col("transaction_type", "Type"),
         col("transactions", "Lines", "number"), col("amount", "Total amount", "money"),
         col("latest_period", "Latest period", "date")],
        """SELECT counterparty_name, MAX(counterparty_ticker) AS counterparty_ticker,
                  MAX(relationship) AS relationship, transaction_type, COUNT(*) AS transactions,
                  SUM(amount) AS amount, MAX(period_end) AS latest_period
           FROM related_party_transactions WHERE company_id = %(cid)s
           GROUP BY counterparty_name, transaction_type
           ORDER BY latest_period DESC, amount DESC""",
        company, page, page_size,
        note="Summed over every reported period and both report scopes.",
    )


def fetch_news(company: Company, options: Options, page: int, page_size: int) -> Payload:
    return table(
        "News",
        [col("title", "Title"), col("published_at", "Published", "date"), col("source_name", "Source"),
         col("media_type", "Media")],
        """SELECT news_id AS _id, title, published_at, source_name, media_type FROM company_news
           WHERE company_id = %(cid)s ORDER BY published_at DESC, news_id DESC""",
        company, page, page_size, row_action="news",
    )


def fetch_signals(company: Company, options: Options, page: int, page_size: int) -> Payload:
    from . import signals

    signal = signals.compute(company.company_id)
    if signal is None:
        return {"title": "Dòng tiền lớn", "fields": [], "note": "Chưa có dữ liệu giao dịch."}
    data = signal.as_dict()
    rows = [{"group": c["label"], "recent": c["recent"], "usual": c["usual"], "z": c["z"],
             "assessment": {None: "Thiếu dữ liệu", 2: "Mua mạnh bất thường", 1: "Mua bất thường", 0: "Bình thường",
                            -1: "Bán bất thường", -2: "Bán mạnh bất thường"}[c["score"]],
             "detail": c["detail"]} for c in data["components"]]
    return {
        "title": "Dòng tiền lớn",
        "signal": {k: data[k] for k in ("level", "label", "message")},
        "fields": [
            {"label": "Cấp độ", "value": data["label"], "type": "text"},
            {"label": "Tính đến phiên", "value": data["as_of"], "type": "date"},
            {"label": "Kết luận", "value": data["message"], "type": "text"},
        ],
        "texts": [{"label": "Lý do", "text": "\n".join(data["reasons"])}],
        "columns": [col("group", "Nhóm"), col("assessment", "Đánh giá"), col("recent", f"{data['window']} phiên gần nhất"),
                    col("usual", f"Thói quen {data['history']} phiên trước"), col("z", "Độ lệch (z)", "number"),
                    col("detail", "Chi tiết")],
        "rows": rows, "total": len(rows), "page": 1, "page_size": len(rows),
        "note": (f"Mỗi nhóm so {data['window']} phiên gần nhất với thói quen {data['history']} phiên trước đó của chính mã này: "
                 "|z| ≥ 1 là bất thường, ≥ 2 là mạnh. Người nội bộ: đã giao dịch = mạnh, đang đăng ký = bất thường; "
                 "giao dịch dưới 0,02% số cổ phiếu bị bỏ qua."),
    }


SIGNALS = Section(
    "signals", "Dòng tiền lớn",
    count=count_sql("""SELECT (EXISTS (SELECT 1 FROM foreign_trades WHERE company_id = %(cid)s))
                            + (EXISTS (SELECT 1 FROM proprietary_trades WHERE company_id = %(cid)s))
                            + (EXISTS (SELECT 1 FROM order_statistics WHERE company_id = %(cid)s))
                            + (EXISTS (SELECT 1 FROM insider_trades WHERE company_id = %(cid)s))"""),
    fetch=fetch_signals,
    description="groups with data",
)


SECTIONS: list[Section] = [
    Section("profile", "Company profile", count=lambda c: 1, fetch=fetch_profile),
    LEADERS,
    HOLDERS,
    INVESTMENTS,
    PRICE,
    SIGNALS,
    REPORTS,
    METRICS,
    TRADING,
    Section("related", "Related-party transactions",
            count=count_sql("SELECT COUNT(*) FROM related_party_transactions WHERE company_id = %(cid)s"),
            fetch=fetch_related),
    Section("news", "News", count=count_sql("SELECT COUNT(*) FROM company_news WHERE company_id = %(cid)s"),
            fetch=fetch_news),
]


# --- unlisted organisations (organizations register) -------------------------------------------

def fetch_org_profile(company: Company, options: Options, page: int, page_size: int) -> Payload:
    row = db.one("""SELECT o.*, p.canonical_name AS parent_name FROM organizations AS o
                    LEFT JOIN organizations AS p ON p.org_id = o.parent_org_id
                    WHERE o.org_id = %(oid)s""", {"oid": company.org_id}) or {}
    aliases = [r["alias"] for r in db.rows(
        "SELECT alias FROM organization_aliases WHERE org_id = %(oid)s ORDER BY alias", {"oid": company.org_id})]
    fields = [
        {"label": "Name", "value": row.get("canonical_name"), "type": "text"},
        {"label": "Full name", "value": row.get("full_name"), "type": "text"},
        {"label": "Structure", "value": row.get("kind"), "type": "text"},
        {"label": "Legal form", "value": row.get("legal_form"), "type": "text"},
        {"label": "Tax code", "value": row.get("tax_code"), "type": "text"},
        {"label": "Country", "value": row.get("country"), "type": "text"},
        {"label": "Industry", "value": row.get("industry"), "type": "text"},
        {"label": "Address", "value": row.get("address"), "type": "text"},
        {"label": "Website", "value": row.get("website"), "type": "link"},
        {"label": "Parent", "value": row.get("parent_name"), "type": "text"},
        {"label": "Record", "value": "reviewed" if row.get("status") == "reviewed" else "matched automatically",
         "type": "text"},
    ]
    texts = [{"label": "Names used in the sources", "text": "\n".join(aliases)}] if aliases else []
    if row.get("note"):
        texts.append({"label": "Note", "text": row["note"]})
    return {"title": "Organisation profile", "fields": [f for f in fields if f["value"] not in (None, "")],
            "texts": texts}


ORG_SECTIONS: list[Section] = [
    Section("org.profile", "Profile", count=lambda c: 1, fetch=fetch_org_profile),
    Section(
        "org.owners", "Owned by",
        count=count_sql("SELECT COUNT(*) FROM company_investments WHERE investee_org_id = %(oid)s"),
        fetch=lambda c, o, p, s: table(
            "Owned by (from listed companies' reports)",
            [col("owner", "Owner", "ticker"), col("relation_type", "Relation"),
             col("is_direct", "Direct", "bool"), col("ownership_percentage", "Ownership", "percent_bar"),
             col("voting_percentage", "Voting %", "percent"), col("investment_cost", "Cost", "money"),
             col("as_of_date", "As of", "date")],
            """SELECT owner.ticker AS owner, i.relation_type, i.is_direct, i.ownership_percentage,
                      i.voting_percentage, i.investment_cost, i.as_of_date
               FROM company_investments AS i JOIN companies AS owner USING (company_id)
               WHERE i.investee_org_id = %(oid)s ORDER BY i.ownership_percentage DESC""",
            c, p, s),
    ),
    Section(
        "org.holdings", "Holds shares in",
        count=count_sql("SELECT COUNT(*) FROM stock_holders WHERE holder_org_id = %(oid)s"),
        fetch=lambda c, o, p, s: table(
            "Shareholdings in listed companies",
            [col("ticker", "Company", "ticker"), col("shares_owned", "Shares", "number"),
             col("ownership_percentage", "Ownership", "percent_bar"), col("snapshot_date", "As of", "date")],
            """SELECT c.ticker, h.shares_owned, h.ownership_percentage, h.snapshot_date
               FROM stock_holders AS h JOIN companies AS c USING (company_id)
               WHERE h.holder_org_id = %(oid)s ORDER BY h.snapshot_date DESC, h.ownership_percentage DESC""",
            c, p, s),
    ),
    Section(
        "org.related", "Disclosed transactions",
        count=count_sql("SELECT COUNT(*) FROM related_party_transactions WHERE counterparty_org_id = %(oid)s"),
        fetch=lambda c, o, p, s: table(
            "Transactions disclosed by listed companies",
            [col("reporter", "Reported by", "ticker"), col("relationship", "Relationship"),
             col("transaction_type", "Type"), col("transactions", "Lines", "number"),
             col("amount", "Total amount", "money"), col("latest_period", "Latest period", "date")],
            """SELECT c.ticker AS reporter, MAX(t.relationship) AS relationship, t.transaction_type,
                      COUNT(*) AS transactions, SUM(t.amount) AS amount, MAX(t.period_end) AS latest_period
               FROM related_party_transactions AS t JOIN companies AS c USING (company_id)
               WHERE t.counterparty_org_id = %(oid)s
               GROUP BY c.ticker, t.transaction_type ORDER BY latest_period DESC, amount DESC""",
            c, p, s, note="Summed over every reported period and both report scopes."),
    ),
]


def _index(sections: list[Section]) -> dict[str, Section]:
    found = {}
    for section in sections:
        found[section.key] = section
        found.update(_index(section.children))
    return found


BY_KEY = {**_index(SECTIONS), **_index(ORG_SECTIONS)}


def describe(company: Company, sections: list[Section] | None = None) -> list[dict]:
    """The section tree with counts: records for a leaf, branches holding data for a group."""
    if sections is None:
        sections = SECTIONS if company.listed else ORG_SECTIONS
    result = []
    for section in sections:
        children = describe(company, section.children) if section.children else []
        if children:
            count = sum(1 for child in children if child["count"])
            count_label = f"{count}/{len(children)} branches with data"
        else:
            count = section.count(company)
            count_label = f"{count} {(section.description or 'records').lower()}"
        result.append({"key": section.key, "label": section.label, "count": count,
                       "group": bool(children), "children": children, "count_label": count_label})
    return result
