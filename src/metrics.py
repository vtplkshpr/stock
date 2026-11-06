"""Derive per-period financial metrics and price-based valuations from the reported statements.

financial_metrics and valuation_metrics are computed tables: every run deletes and rebuilds the
rows of the companies it processes from finance_reports, finance_report_items and stock_prices.
Never edit them by hand; re-run this module (it also runs after imports and restores).

Periods follow each company's fiscal year (companies.fiscal_year_start_month). Vietnamese
quarterly cash-flow statements are year-to-date, so a stand-alone quarter is derived as
YTD(q) - YTD(q-1); such rows are marked flow_source = 'derived'.
"""

import argparse
import sys
from datetime import date, timedelta
from typing import Any, Sequence

FORMULA_VERSION = "1.1"
PAR_VALUE = 10_000  # VND per share, the statutory par value of Vietnamese listed shares
DEFAULT_TAX_RATE = 0.20  # Vietnamese corporate income tax rate, used when the effective rate is unusable

# Line codes per statement and circular. Circular 99 (fiscal years from 2026) renumbered several lines.
ITEMS = {
    "tt200": {
        "income_statement": {
            "revenue": "10", "cogs": "11", "gross_profit": "20", "financial_income": "21",
            "financial_expense": "22", "interest_expense": "23", "associates": "24", "selling": "25",
            "admin": "26", "operating_profit": "30", "profit_before_tax": "50", "tax_current": "51",
            "tax_deferred": "52", "net_income": "60", "net_income_parent": "61",
        },
        "cash_flow": {
            "cfo": "20", "cfi": "30", "cff": "40", "capex": "21", "depreciation": "02",
            "interest_paid": "14", "tax_paid": "15", "dividends_paid": "36",
        },
        "balance_sheet": {
            "current_assets": "100", "cash": "110", "short_term_investments": "120",
            "receivables_trade": "131", "inventory": "140", "total_assets": "270",
            "total_liabilities": "300", "current_liabilities": "310", "payables_trade": "311",
            "short_term_debt": "320", "long_term_debt": "338", "convertible_bonds": "339",
            "equity": "400", "common_share_capital": "411a", "minority_interest": "429",
        },
    },
}
ITEMS["tt99"] = {
    "income_statement": {**ITEMS["tt200"]["income_statement"], "financial_income": "22",
                         "financial_expense": "23", "interest_expense": "24", "associates": "27"},
    "cash_flow": dict(ITEMS["tt200"]["cash_flow"]),
    "balance_sheet": {**ITEMS["tt200"]["balance_sheet"], "total_assets": "280", "short_term_debt": "321",
                      "long_term_debt": "339", "convertible_bonds": "340"},
}
FLOW_STATEMENTS = ("income_statement", "cash_flow")
# Lines that are legitimately absent (no minority interest in separate reports, no bonds, ...).
OPTIONAL = {"associates", "minority_interest", "convertible_bonds", "short_term_debt", "long_term_debt",
            "dividends_paid", "short_term_investments", "tax_deferred", "interest_paid", "tax_paid"}

# Cash-flow pattern -> life-cycle stage (Dickinson, 2011, "Cash Flow Patterns as a Proxy for Firm
# Life Cycle", The Accounting Review). Signs are (CFO, CFI, CFF).
LIFECYCLE = {
    (-1, -1, 1): "introduction", (1, -1, 1): "growth", (1, -1, -1): "mature",
    (-1, -1, -1): "shake_out", (1, 1, 1): "shake_out", (1, 1, -1): "shake_out",
    (-1, 1, 1): "decline", (-1, 1, -1): "decline",
}
# Flows smaller than this share of total assets count as zero when reading the pattern.
SIGN_MATERIALITY = 0.005

# Warning thresholds commonly used in international credit and equity analysis.
THRESHOLDS = {
    "earnings_quality": 1.0,   # CFO / net income below 1: profit not backed by operating cash
    "accrual_ratio": 0.10,     # (net income - CFO) / average assets above 10% (Sloan, 1996)
    "interest_coverage": 1.5,  # EBIT / interest expense below 1.5x: weak, speculative-grade territory
    "net_debt_to_ebitda": 4.0, # above 4x: highly leveraged (rating-agency and covenant convention)
    "current_ratio": 1.0,      # below 1: current liabilities exceed current assets
}
FLAG_LABELS = {
    "flag_negative_cfo": "CFO<0", "flag_negative_fcf": "FCF<0", "flag_low_earnings_quality": "CFO/LN<1",
    "flag_high_accruals": "dồn tích>10%", "flag_weak_interest_coverage": "EBIT/lãi<1.5",
    "flag_high_leverage": "nợ ròng/EBITDA>4", "flag_low_liquidity": "thanh toán<1",
}
REPORT_RANK = {"quarterly": 1, "semi_annual": 2, "annual": 3}
AUDIT_RANK = {None: 0, "unaudited": 0, "reviewed": 1, "audited": 2}


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    return date(day.year + month // 12, month % 12 + 1, 1)


def quarter_bounds(fiscal_year: int, quarter: int, start_month: int) -> tuple[date, date]:
    """First and last day of a fiscal quarter; fiscal_year is the year in which the fiscal year ends."""
    fiscal_start = date(fiscal_year - (1 if start_month > 1 else 0), start_month, 1)
    start = add_months(fiscal_start, 3 * (quarter - 1))
    return start, add_months(start, 3) - timedelta(days=1)


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def sign(value: float | None, materiality: float) -> int | None:
    if value is None:
        return None
    return 0 if abs(value) < materiality else (1 if value > 0 else -1)


class CompanyFacts:
    """Every reported figure of one company, indexed by scope, period kind, fiscal year and quarter.

    kinds: 'qtr' (stand-alone quarter flow), 'ytd' (year-to-date flow), 'bal' (balance at quarter end).
    """

    def __init__(self, start_month: int):
        self.start_month = start_month
        self.facts: dict[tuple, dict[str, tuple[float, int, int]]] = {}
        self.reports: dict[int, dict] = {}

    def put(self, key: tuple, name: str, value: Any, rank: int, report_id: int) -> None:
        if value is None:
            return
        slot = self.facts.setdefault(key, {})
        if name not in slot or rank > slot[name][1]:
            slot[name] = (float(value), rank, report_id)

    def get(self, scope: str, kind: str, year: int, quarter: int, name: str) -> tuple[float, int] | None:
        found = self.facts.get((scope, kind, year, quarter), {}).get(name)
        return (found[0], found[2]) if found else None

    def add_report(self, report: dict, items: dict[tuple[str, str], tuple]) -> None:
        self.reports[report["report_id"]] = report
        circular = "tt99" if ("balance_sheet", "280") in items else "tt200"
        kind = report["report_type"]
        year, scope, rid = report["fiscal_year"], report["report_scope"], report["report_id"]
        quarter = {"annual": 4, "semi_annual": 2}.get(kind, report["fiscal_quarter"])
        rank = REPORT_RANK.get(kind, 1) * 10 + AUDIT_RANK.get(report["audit_status"], 0)
        # Comparative columns of later reports fill earlier periods, below any direct figure.
        comparative_rank = -10
        for statement in FLOW_STATEMENTS:
            for name, code in ITEMS[circular][statement].items():
                row = items.get((statement, code))
                if row is None:
                    continue
                value, comparative, ytd, ytd_comparative = row
                if kind == "quarterly":
                    if statement == "income_statement":
                        self.put((scope, "qtr", year, quarter), name, value, rank, rid)
                        self.put((scope, "qtr", year - 1, quarter), name, comparative, comparative_rank, rid)
                    first = quarter == 1
                    self.put((scope, "ytd", year, quarter), name, ytd if ytd is not None or not first else value,
                             rank, rid)
                    self.put((scope, "ytd", year - 1, quarter), name,
                             ytd_comparative if ytd_comparative is not None or not first else comparative,
                             comparative_rank, rid)
                else:
                    self.put((scope, "ytd", year, quarter), name, value, rank, rid)
                    self.put((scope, "ytd", year - 1, quarter), name, comparative, comparative_rank, rid)
        for name, code in ITEMS[circular]["balance_sheet"].items():
            row = items.get(("balance_sheet", code))
            if row is None:
                continue
            self.put((scope, "bal", year, quarter), name, row[0], rank, rid)
            # The comparative balance is the end of the previous fiscal year.
            self.put((scope, "bal", year - 1, 4), name, row[1], comparative_rank, rid)

    def periods(self) -> set[tuple[str, int, int]]:
        return {(scope, year, quarter) for scope, _, year, quarter in self.facts}


class PeriodValues:
    """Flows and balances of one period, remembering which reports supplied them."""

    def __init__(self):
        self.values: dict[str, float] = {}
        self.report_ids: set[int] = set()
        self.derived = False
        self.reported = False

    def set(self, name: str, value: float | None, report_ids: Sequence[int], derived: bool) -> None:
        if value is None:
            return
        self.values[name] = value
        self.report_ids.update(report_ids)
        self.derived |= derived
        self.reported |= not derived

    def get(self, name: str) -> float | None:
        value = self.values.get(name)
        return 0.0 if value is None and name in OPTIONAL else value


def flow_names() -> set[str]:
    return {name for circular in ITEMS.values() for st in FLOW_STATEMENTS for name in circular[st]}


def balance_names() -> set[str]:
    return {name for circular in ITEMS.values() for name in circular["balance_sheet"]}


def flows_for(facts: CompanyFacts, scope: str, period_type: str, year: int, quarter: int) -> PeriodValues:
    out = PeriodValues()
    for name in flow_names():
        def ytd(y: int, q: int):
            return facts.get(scope, "ytd", y, q, name)
        if period_type == "year" or (period_type == "ttm" and quarter == 4):
            found = ytd(year, 4)
            if found:
                out.set(name, found[0], [found[1]], False)
        elif period_type == "ttm":
            parts = [ytd(year, quarter), ytd(year - 1, 4), ytd(year - 1, quarter)]
            if all(parts):
                out.set(name, parts[0][0] + parts[1][0] - parts[2][0], [p[1] for p in parts], True)
        else:
            direct = facts.get(scope, "qtr", year, quarter, name)
            if direct:
                out.set(name, direct[0], [direct[1]], False)
            elif quarter == 1:
                found = ytd(year, 1)
                if found:
                    out.set(name, found[0], [found[1]], False)
            else:
                now, before = ytd(year, quarter), ytd(year, quarter - 1)
                if now and before:
                    out.set(name, now[0] - before[0], [now[1], before[1]], True)
    return out


def balances_for(facts: CompanyFacts, scope: str, year: int, quarter: int) -> PeriodValues:
    out = PeriodValues()
    for name in balance_names():
        found = facts.get(scope, "bal", year, quarter, name)
        if found:
            out.set(name, found[0], [found[1]], False)
    return out


def average(*values: float | None) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def compute_row(flows: PeriodValues, end: PeriodValues, start: PeriodValues, prior: PeriodValues | None,
                period_type: str) -> dict[str, Any]:
    f, b = flows.get, end.get
    row: dict[str, Any] = {}
    revenue, cfo, cfi, cff = f("revenue"), f("cfo"), f("cfi"), f("cff")
    net_income = f("net_income")
    net_income_parent = flows.values.get("net_income_parent", net_income)
    interest = abs(f("interest_expense")) if f("interest_expense") is not None else None
    pbt = f("profit_before_tax")
    ebit = pbt + interest if pbt is not None and interest is not None else None
    depreciation = f("depreciation")
    ebitda = ebit + depreciation if ebit is not None and depreciation is not None else None
    capex = f("capex")
    fcf = cfo + capex if cfo is not None and capex is not None else None
    debt = None
    if b("total_assets") is not None:
        debt = (b("short_term_debt") or 0) + (b("long_term_debt") or 0) + (b("convertible_bonds") or 0)
    liquid = (b("cash") or 0) + (b("short_term_investments") or 0) if b("cash") is not None else None
    net_debt = debt - liquid if debt is not None and liquid is not None else None
    equity = b("equity")
    equity_parent = equity - (b("minority_interest") or 0) if equity is not None else None
    row.update(revenue=revenue, gross_profit=f("gross_profit"), ebit=ebit, ebitda=ebitda,
               interest_expense=interest, receivables=b("receivables_trade"), inventory=b("inventory"),
               net_income=net_income, net_income_parent=net_income_parent, cfo=cfo, cfi=cfi, cff=cff,
               capex=capex, free_cash_flow=fcf, dividends_paid=f("dividends_paid"),
               total_assets=b("total_assets"), equity_parent=equity_parent,
               interest_bearing_debt=debt, net_debt=net_debt)

    materiality = abs(b("total_assets") or 0) * SIGN_MATERIALITY
    signs = tuple(sign(v, materiality) for v in (cfo, cfi, cff))
    if None not in signs:
        row.update(cfo_sign=signs[0], cfi_sign=signs[1], cff_sign=signs[2],
                   cash_flow_pattern="".join({1: "+", -1: "-", 0: "0"}[s] for s in signs),
                   lifecycle_stage=LIFECYCLE.get(signs))

    row.update(gross_margin=ratio(f("gross_profit"), revenue), ebit_margin=ratio(ebit, revenue),
               net_margin=ratio(net_income, revenue),
               cfo_to_net_income=ratio(cfo, net_income) if net_income and net_income > 0 else None,
               debt_to_equity=ratio(debt, equity),
               interest_coverage=ratio(ebit, interest),
               current_ratio=ratio(b("current_assets"), b("current_liabilities")),
               quick_ratio=ratio(b("current_assets") - b("inventory")
                                 if b("current_assets") is not None and b("inventory") is not None else None,
                                 b("current_liabilities")),
               cash_ratio=ratio(liquid, b("current_liabilities")))
    interest_paid, tax_paid = abs(f("interest_paid") or 0), abs(f("tax_paid") or 0)
    if cfo is not None and interest_paid:
        row["cfo_interest_coverage"] = (cfo + interest_paid + tax_paid) / interest_paid
    shares = round(b("common_share_capital") / PAR_VALUE) if b("common_share_capital") else None
    row["shares_outstanding"] = shares
    row["bvps"] = ratio(equity_parent, shares)

    if period_type != "quarter":
        s = start.get
        avg_assets = average(b("total_assets"), s("total_assets"))
        start_equity = s("equity")
        avg_equity_parent = average(equity_parent, start_equity - (s("minority_interest") or 0)
                                    if start_equity is not None else None)
        start_debt = None
        if s("total_assets") is not None:
            start_debt = (s("short_term_debt") or 0) + (s("long_term_debt") or 0) + (s("convertible_bonds") or 0)
        avg_capital = average(debt + equity if debt is not None and equity is not None else None,
                              start_debt + start_equity if start_debt is not None and start_equity is not None else None)
        tax = -((f("tax_current") or 0) + (f("tax_deferred") or 0))
        tax_rate = tax / pbt if pbt and pbt > 0 and 0 <= tax / pbt <= 0.5 else DEFAULT_TAX_RATE
        cogs = abs(f("cogs")) if f("cogs") is not None else None
        days = 365
        row.update(
            roe=ratio(net_income_parent, avg_equity_parent),
            roa=ratio(net_income, avg_assets),
            roic=ratio(ebit * (1 - tax_rate) if ebit is not None else None, avg_capital),
            accrual_ratio=ratio(net_income - cfo if net_income is not None and cfo is not None else None, avg_assets),
            net_debt_to_ebitda=ratio(net_debt, ebitda) if ebitda and ebitda > 0 else None,
            dso=ratio(average(b("receivables_trade"), s("receivables_trade")), revenue),
            dio=ratio(average(b("inventory"), s("inventory")), cogs),
            dpo=ratio(average(b("payables_trade"), s("payables_trade")), cogs),
            asset_turnover=ratio(revenue, avg_assets),
            eps=ratio(net_income_parent, shares), cfo_per_share=ratio(cfo, shares),
        )
        for key in ("dso", "dio", "dpo"):
            if row[key] is not None:
                row[key] *= days
        if None not in (row["dso"], row["dio"], row["dpo"]):
            row["cash_conversion_cycle"] = row["dso"] + row["dio"] - row["dpo"]

        def flag(condition: bool | None, *inputs: Any) -> int | None:
            return None if any(i is None for i in inputs) else int(bool(condition))
        row.update(
            flag_negative_cfo=flag(cfo is not None and cfo < 0, cfo),
            flag_negative_fcf=flag(fcf is not None and fcf < 0, fcf),
            flag_low_earnings_quality=flag(
                net_income is not None and net_income > 0 and cfo is not None
                and cfo / net_income < THRESHOLDS["earnings_quality"], net_income, cfo),
            flag_high_accruals=flag((row["accrual_ratio"] or 0) > THRESHOLDS["accrual_ratio"], row["accrual_ratio"]),
            flag_weak_interest_coverage=flag(
                row["interest_coverage"] is not None and row["interest_coverage"] < THRESHOLDS["interest_coverage"],
                row["interest_coverage"]),
            flag_high_leverage=flag(
                (row["net_debt_to_ebitda"] or 0) > THRESHOLDS["net_debt_to_ebitda"]
                or (ebitda is not None and ebitda <= 0 and (net_debt or 0) > 0), net_debt, ebitda),
            flag_low_liquidity=flag(
                row["current_ratio"] is not None and row["current_ratio"] < THRESHOLDS["current_ratio"],
                row["current_ratio"]),
        )

    if prior is not None:
        def growth(name: str) -> float | None:
            now, before = flows.get(name), prior.get(name)
            return (now - before) / abs(before) if now is not None and before not in (None, 0) else None
        row.update(revenue_yoy=growth("revenue"), net_income_yoy=growth("net_income"), cfo_yoy=growth("cfo"))
    return row


def load_company(cursor: Any, company_id: int) -> CompanyFacts:
    cursor.execute("SELECT COALESCE(fiscal_year_start_month, 1) FROM companies WHERE company_id = %s", (company_id,))
    facts = CompanyFacts(int(cursor.fetchone()[0]))
    cursor.execute(
        """SELECT report_id, report_type, report_scope, fiscal_year, fiscal_quarter, period_start,
                  period_end, audit_status, published_at
           FROM finance_reports WHERE company_id = %s AND report_scope IS NOT NULL""",
        (company_id,),
    )
    columns = [d[0] for d in cursor.description]
    reports = [dict(zip(columns, row)) for row in cursor.fetchall()]
    cursor.execute(
        """SELECT report_type, report_scope, fiscal_year, fiscal_quarter, statement, item_code,
                  value, comparative_value, ytd_value, ytd_comparative_value
           FROM finance_report_items WHERE company_id = %s""",
        (company_id,),
    )
    items: dict[tuple, dict] = {}
    for kind, scope, year, quarter, statement, code, *values in cursor.fetchall():
        items.setdefault((kind, scope, year, quarter), {})[(statement, code)] = tuple(values)
    # Annual and semi-annual reports first, so equal-rank ties keep the more authoritative figure.
    for report in sorted(reports, key=lambda r: -REPORT_RANK.get(r["report_type"], 1)):
        found = items.get((report["report_type"], report["report_scope"], report["fiscal_year"],
                           report["fiscal_quarter"]))
        if found:
            facts.add_report(report, found)
    return facts


def company_rows(facts: CompanyFacts, company_id: int) -> list[dict[str, Any]]:
    rows = []
    for scope, year, quarter in sorted(facts.periods()):
        for period_type in ("quarter", "ttm", "year"):
            if period_type == "year" and quarter != 4:
                continue
            flows = flows_for(facts, scope, period_type, year, quarter)
            if flows.get("cfo") is None and flows.get("revenue") is None:
                continue
            end = balances_for(facts, scope, year, quarter)
            start = balances_for(facts, scope, year - 1, quarter)
            prior = flows_for(facts, scope, period_type, year - 1, quarter)
            period_start, period_end = quarter_bounds(year, quarter, facts.start_month)
            if period_type != "quarter":
                period_start = quarter_bounds(year if period_type == "year" else year - 1,
                                              1 if period_type == "year" else quarter + 1 if quarter < 4 else 1,
                                              facts.start_month)[0]
                if period_type == "ttm" and quarter == 4:
                    period_start = quarter_bounds(year, 1, facts.start_month)[0]
            row = compute_row(flows, end, start, prior if prior.values else None, period_type)
            sources = [facts.reports[r] for r in flows.report_ids | end.report_ids]
            published = [r["published_at"] for r in sources if r["published_at"]]
            audit = min((AUDIT_RANK.get(r["audit_status"], 0) for r in sources), default=0)
            row.update(
                company_id=company_id, report_scope=scope, period_type=period_type, fiscal_year=year,
                fiscal_quarter=quarter, period_start=period_start, period_end=period_end,
                flow_source="mixed" if flows.derived and flows.reported else ("derived" if flows.derived else "reported"),
                audit_status={0: "unaudited", 1: "reviewed", 2: "audited"}[audit],
                available_from=max(published) if published else None,
                source_report_ids=",".join(str(r) for r in sorted(flows.report_ids | end.report_ids)),
                formula_version=FORMULA_VERSION,
            )
            rows.append(row)
    return rows


def insert_rows(cursor: Any, table: str, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        columns = ", ".join(f"`{c}`" for c in row)
        cursor.execute(f"INSERT INTO `{table}` ({columns}) VALUES ({', '.join(['%s'] * len(row))})",
                       tuple(round(v, 6) if isinstance(v, float) else v for v in row.values()))


def valuation_rows(cursor: Any, company_id: int) -> list[dict[str, Any]]:
    """One row per price day, using the latest TTM metrics already published on that day."""
    cursor.execute(
        """SELECT metric_id, report_scope, available_from, shares_outstanding, net_income_parent,
                  equity_parent, revenue, ebitda, net_debt, dividends_paid, free_cash_flow
           FROM financial_metrics
           WHERE company_id = %s AND period_type = 'ttm' AND available_from IS NOT NULL
           ORDER BY available_from""",
        (company_id,),
    )
    columns = [d[0] for d in cursor.description]
    metrics = [dict(zip(columns, row)) for row in cursor.fetchall()]
    preferred = "consolidated" if any(m["report_scope"] == "consolidated" for m in metrics) else "separate"
    metrics = [m for m in metrics if m["report_scope"] == preferred]
    cursor.execute("SELECT price_date, close_price FROM stock_prices WHERE company_id = %s ORDER BY price_date",
                   (company_id,))
    rows = []
    for price_date, close in cursor.fetchall():
        known = [m for m in metrics if m["available_from"] <= price_date]
        if not known:
            continue
        m = {k: (float(v) if hasattr(v, "is_finite") else v) for k, v in known[-1].items()}
        close = float(close)
        shares = m["shares_outstanding"]
        market_cap = close * shares if shares else None
        enterprise_value = market_cap + m["net_debt"] if market_cap is not None and m["net_debt"] is not None else None
        positive = lambda v: v if v and v > 0 else None  # noqa: E731 - multiples are undefined below zero
        rows.append(dict(
            company_id=company_id, price_date=price_date, close_price=close, metric_id=m["metric_id"],
            report_scope=preferred, shares_outstanding=shares, market_cap=market_cap,
            enterprise_value=enterprise_value,
            pe_ttm=ratio(market_cap, positive(m["net_income_parent"])),
            pb=ratio(market_cap, positive(m["equity_parent"])),
            ps_ttm=ratio(market_cap, positive(m["revenue"])),
            ev_ebitda=ratio(enterprise_value, positive(m["ebitda"])),
            dividend_yield=ratio(abs(m["dividends_paid"]) if m["dividends_paid"] is not None else None, market_cap),
            fcf_yield=ratio(m["free_cash_flow"], market_cap),
            formula_version=FORMULA_VERSION,
        ))
    return rows


def recompute(connection: Any, tickers: Sequence[str] | None = None) -> dict[str, tuple[int, int]]:
    """Rebuild both computed tables for the given tickers (default: every company with reports).

    Runs inside the caller's transaction; returns {ticker: (metric rows, valuation rows)}.
    """
    cursor = connection.cursor()
    try:
        query = """SELECT DISTINCT c.company_id, c.ticker FROM companies c
                   WHERE c.company_id IN (SELECT company_id FROM finance_report_items)
                      OR c.company_id IN (SELECT company_id FROM stock_prices)"""
        params: tuple = ()
        if tickers:
            query += f" AND c.ticker IN ({', '.join(['%s'] * len(tickers))})"
            params = tuple(t.upper() for t in tickers)
        cursor.execute(query, params)
        companies = cursor.fetchall()
        summary = {}
        for company_id, ticker in companies:
            cursor.execute("DELETE FROM valuation_metrics WHERE company_id = %s", (company_id,))
            cursor.execute("DELETE FROM financial_metrics WHERE company_id = %s", (company_id,))
            rows = company_rows(load_company(cursor, company_id), company_id)
            insert_rows(cursor, "financial_metrics", rows)
            valuations = valuation_rows(cursor, company_id)
            insert_rows(cursor, "valuation_metrics", valuations)
            summary[ticker] = (len(rows), len(valuations))
        return summary
    finally:
        cursor.close()


def format_summary(summary: dict[str, tuple[int, int]]) -> str:
    if not summary:
        return "Không có doanh nghiệp nào có báo cáo tài chính hoặc giá để tính chỉ số."
    return "\n".join(f"- {ticker}: {m} dòng chỉ số tài chính, {v} dòng định giá" for ticker, (m, v) in summary.items())


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tính lại bảng chỉ số tài chính và định giá.")
    parser.add_argument("--tickers", default="", help="Các mã cần tính, cách nhau bởi dấu phẩy (mặc định: tất cả).")
    parser.add_argument("--dry-run", action="store_true", help="Tính thử rồi hoàn tác.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        from . import stock_cli
    except ImportError:
        import stock_cli
    import mysql.connector

    config = stock_cli.load_database_config()
    config["port"] = int(config["port"])
    connection = mysql.connector.connect(**config)
    try:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] or None
        print(format_summary(recompute(connection, tickers)))
        if args.dry_run:
            connection.rollback()
            print("Chạy thử: không lưu thay đổi.")
        else:
            connection.commit()
            print("Đã lưu chỉ số.")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
