"""Stock screening: sort companies into financial-state groups from their latest TTM metrics.

Each company is judged on its newest TTM row in financial_metrics (consolidated when available)
against the TTM row one year earlier, so "rising" and "falling" mean year-on-year changes.
A group matches when all of its required criteria hold; criteria without data count as unknown,
never as passed. Thresholds are analyst rules of thumb, collected in RULES so they can be tuned.
"""

from dataclasses import dataclass, field
from typing import Any, Callable

RULES = {
    "roe_min": 0.15,               # ROE above 15%: the usual bar for a high-quality business
    "fcf_margin_min": 0.05,        # FCF at least 5% of revenue counts as "large" free cash flow
    "profit_jump": 0.20,           # net income up 20% or more year on year
    "cfo_to_net_income_max": 0.5,  # less than half of the profit arrives as operating cash
    "working_capital_jump": 0.20,  # receivables or inventory up 20% more than revenue
    "leverage_jump": 0.20,         # debt/equity up 20% or more year on year
    "interest_jump": 0.20,         # interest expense up 20% or more year on year
    "roe_drop": 0.03,              # ROE down 3 percentage points or more
    "cfo_interest_cover_min": 1.5, # operating cash below 1.5x interest paid cannot carry the debt
    "pe_jump": 0.30,               # P/E up 30% or more while profit falls
}


@dataclass
class Snapshot:
    """Latest TTM metrics of one company plus the same period a year earlier."""
    company_id: int
    ticker: str
    name: str
    now: dict[str, Any]
    prior: dict[str, Any] | None
    pe_now: float | None = None
    pe_prior: float | None = None

    def get(self, key: str) -> float | None:
        value = self.now.get(key)
        return float(value) if value is not None and not isinstance(value, str) else value

    def before(self, key: str) -> float | None:
        if not self.prior or self.prior.get(key) is None:
            return None
        value = self.prior[key]
        return float(value) if not isinstance(value, str) else value


def change(now: float | None, before: float | None) -> float | None:
    if now is None or before in (None, 0):
        return None
    return (now - before) / abs(before)


def both(a: bool | None, b: bool | None) -> bool | None:
    if a is False or b is False:
        return False
    return None if a is None or b is None else True


def either(a: bool | None, b: bool | None) -> bool | None:
    if a or b:
        return True
    return None if a is None or b is None else False


def gt(value: float | None, limit: float) -> bool | None:
    return None if value is None else value > limit


def lt(value: float | None, limit: float) -> bool | None:
    return None if value is None else value < limit


def working_capital_outgrows_sales(s: Snapshot) -> bool | None:
    sales = change(s.get("revenue"), s.before("revenue"))
    if sales is None:
        return None
    gaps = [change(s.get(k), s.before(k)) for k in ("receivables", "inventory")]
    known = [g for g in gaps if g is not None]
    if not known:
        return None
    return any(g - sales > RULES["working_capital_jump"] for g in known)


@dataclass
class Criterion:
    label: str
    test: Callable[[Snapshot], bool | None]
    required: bool = True


@dataclass
class Group:
    key: str
    name: str
    meaning: str
    criteria: list[Criterion] = field(default_factory=list)


GROUPS = [
    Group("healthy_growth", "Khỏe mạnh & tăng trưởng",
          "Làm ăn ra tiền thật, tự tài trợ đầu tư và trả bớt nợ.",
          [Criterion("Mẫu dòng tiền +,−,− (CFO dương, CFI âm, CFF âm)",
                     lambda s: None if s.now.get("cash_flow_pattern") is None else s.now["cash_flow_pattern"] == "+--"),
           Criterion(f"ROE > {RULES['roe_min']:.0%}", lambda s: gt(s.get("roe"), RULES["roe_min"])),
           Criterion("ROE không giảm so với cùng kỳ", lambda s: None if s.before("roe") is None or s.get("roe") is None
                     else s.get("roe") >= s.before("roe")),
           Criterion(f"FCF dương và ≥ {RULES['fcf_margin_min']:.0%} doanh thu",
                     lambda s: gt((s.get("free_cash_flow") / s.get("revenue"))
                                  if s.get("free_cash_flow") is not None and s.get("revenue") else None,
                                  RULES["fcf_margin_min"]))]),
    Group("paper_profit", "Đột biến trên giấy",
          "Báo lãi tăng nhưng không thu được tiền: tiền kẹt ở phải thu, tồn kho.",
          [Criterion(f"LNST tăng ≥ {RULES['profit_jump']:.0%} so với cùng kỳ",
                     lambda s: None if s.get("net_income_yoy") is None else s.get("net_income_yoy") >= RULES["profit_jump"]),
           Criterion(f"CFO/LNST < {RULES['cfo_to_net_income_max']} (gồm cả CFO âm)",
                     lambda s: None if s.get("cfo") is None or s.get("net_income") in (None, 0)
                     else s.get("cfo") / s.get("net_income") < RULES["cfo_to_net_income_max"]),
           Criterion(f"Phải thu hoặc tồn kho tăng nhanh hơn doanh thu > {RULES['working_capital_jump']:.0%}",
                     working_capital_outgrows_sales)]),
    Group("cash_burn_expansion", "Đốt tiền bành trướng",
          "Kinh doanh chưa ra tiền, đầu tư lớn và sống bằng tiền vay.",
          [Criterion("Mẫu dòng tiền −,−,+ (CFO âm, CFI âm, CFF dương)",
                     lambda s: None if s.now.get("cash_flow_pattern") is None else s.now["cash_flow_pattern"] == "--+"),
           Criterion(f"Nợ/VCSH tăng ≥ {RULES['leverage_jump']:.0%} hoặc chi phí lãi vay tăng ≥ {RULES['interest_jump']:.0%}",
                     lambda s: either(gt(change(s.get("debt_to_equity"), s.before("debt_to_equity")), RULES["leverage_jump"] - 1e-12),
                                      gt(change(s.get("interest_expense"), s.before("interest_expense")), RULES["interest_jump"] - 1e-12)))]),
    Group("declining", "Khủng hoảng thoái trào",
          "Hiệu quả kinh doanh và dòng tiền cùng đi xuống.",
          [Criterion(f"ROE giảm ≥ {RULES['roe_drop'] * 100:.0f} điểm % so với cùng kỳ",
                     lambda s: None if s.get("roe") is None or s.before("roe") is None
                     else s.before("roe") - s.get("roe") >= RULES["roe_drop"]),
           Criterion(f"CFO âm hoặc < {RULES['cfo_interest_cover_min']}x lãi vay đã trả",
                     lambda s: either(lt(s.get("cfo"), 0), lt(s.get("cfo_interest_coverage"), RULES["cfo_interest_cover_min"]))),
           Criterion("CFF âm (đang trả nợ cũ)", lambda s: None if s.get("cff_sign") is None else s.get("cff_sign") < 0),
           Criterion(f"P/E tăng ≥ {RULES['pe_jump']:.0%} (khi có dữ liệu giá)",
                     lambda s: gt(change(s.pe_now, s.pe_prior), RULES["pe_jump"] - 1e-12), required=False)]),
]


@dataclass
class Result:
    snapshot: Snapshot
    group: Group
    outcomes: list[bool | None]

    @property
    def required(self) -> list[bool | None]:
        return [o for o, c in zip(self.outcomes, self.group.criteria) if c.required]

    @property
    def matched(self) -> bool:
        return all(o is True for o in self.required)

    @property
    def met(self) -> int:
        return sum(1 for o in self.required if o is True)

    @property
    def near(self) -> bool:
        """Exactly one required criterion is not met (failed or without data)."""
        failed = [o for o in self.required if o is not True]
        return len(failed) == 1


def load_snapshots(cursor: Any) -> list[Snapshot]:
    cursor.execute(
        """SELECT m.*, c.ticker, c.company_name
           FROM financial_metrics m JOIN companies c USING (company_id)
           WHERE m.period_type = 'ttm'
           ORDER BY m.company_id, (m.report_scope = 'consolidated') DESC, m.period_end DESC"""
    )
    columns = [d[0] for d in cursor.description]
    rows = [dict(zip(columns, r)) for r in cursor.fetchall()]
    by_company: dict[int, list[dict]] = {}
    for row in rows:
        by_company.setdefault(row["company_id"], []).append(row)
    snapshots = []
    for company_id, company_rows in by_company.items():
        now = company_rows[0]  # consolidated first, newest first
        prior = next((r for r in company_rows if r["report_scope"] == now["report_scope"]
                      and r["fiscal_year"] == now["fiscal_year"] - 1
                      and r["fiscal_quarter"] == now["fiscal_quarter"]), None)
        snapshot = Snapshot(company_id, now["ticker"], now["company_name"], now, prior)
        # Valuation on the latest price day, and about a year before it.
        cursor.execute(
            """SELECT price_date, pe_ttm FROM valuation_metrics
               WHERE company_id = %s AND pe_ttm IS NOT NULL ORDER BY price_date DESC LIMIT 1""",
            (company_id,),
        )
        latest = cursor.fetchone()
        if latest:
            snapshot.pe_now = float(latest[1])
            cursor.execute(
                """SELECT pe_ttm FROM valuation_metrics
                   WHERE company_id = %s AND pe_ttm IS NOT NULL AND price_date <= %s - INTERVAL 1 YEAR
                   ORDER BY price_date DESC LIMIT 1""",
                (company_id, latest[0]),
            )
            year_ago = cursor.fetchone()
            snapshot.pe_prior = float(year_ago[0]) if year_ago else None
        snapshots.append(snapshot)
    return snapshots


def screen(cursor: Any) -> list[Result]:
    results = []
    for snapshot in load_snapshots(cursor):
        for group in GROUPS:
            results.append(Result(snapshot, group, [c.test(snapshot) for c in group.criteria]))
    return results
