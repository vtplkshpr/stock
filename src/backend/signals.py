"""Smart-money signal ("Dòng tiền lớn") of a listed company.

Four groups that tend to trade on better information than the crowd are compared with their own
habits: foreign investors, proprietary desks of securities firms, the order book, and insiders.

For the three daily groups, the average daily net flow of the last WINDOW sessions is compared
with the HISTORY sessions before them:  z = (mean_recent - mean_before) / sd_before  (missing
days count as 0, e.g. days without proprietary trades). |z| >= 1 is unusual (score ±1),
|z| >= 2 strong (±2); with fewer than MIN_HISTORY earlier sessions the group is left out.

Insiders: an executed buy/sell in the last INSIDER_DAYS days scores ±2; a registration whose
window is still open scores ±1; a window that ended without a reported result scores 0. Trades
below MATERIAL_SHARE of the company's shares are ignored (shares from companies, else from the
financial metrics, else derived from insider reports as shares after / ownership %).

Level (agreed with the user):
  -2  Cảnh báo cao   two or more groups strongly negative, or foreign strongly negative with
                     insiders selling
  -1  Cảnh báo       some group unusually negative, none positive
   0  Trung lập      nothing unusual / Trái chiều: groups point in opposite directions
  +1  Tích cực       some group unusually positive, none negative
  +2  Tích cực mạnh  two or more groups strongly positive, or insiders registered and bought
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean, pstdev
from typing import Any

from . import db

WINDOW = 20
HISTORY = 60
MIN_HISTORY = 40
INSIDER_DAYS = 60
MATERIAL_SHARE = 0.0002  # insider trades below 0.02% of the shares are too small to count

LEVELS = {
    -2: ("Cảnh báo cao", "Dòng tiền lớn rút mạnh và đồng thuận. Không nên mua mới; nếu đang nắm giữ, "
                          "cân nhắc giảm tỷ trọng."),
    -1: ("Cảnh báo", "Dòng tiền lớn nghiêng về bán. Thận trọng, chờ tín hiệu cải thiện rồi mới mua."),
    0: ("Trung lập", "Chưa có tín hiệu rõ. Tiếp tục theo dõi."),
    1: ("Tích cực", "Dòng tiền lớn nghiêng về mua. Có thể đưa vào danh sách theo dõi."),
    2: ("Tích cực mạnh", "Dòng tiền lớn gom mạnh và đồng thuận. Có thể cân nhắc mua thăm dò."),
}
MIXED = ("Trái chiều", "Các nhóm dòng tiền lớn ngược chiều nhau. Tiếp tục theo dõi.")


@dataclass
class Component:
    key: str
    label: str
    score: int | None  # None: not enough data
    z: float | None = None
    recent: str = ""
    usual: str = ""
    detail: str = ""


@dataclass
class Signal:
    level: int
    label: str
    message: str
    as_of: date | None
    components: list[Component] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level, "label": self.label, "message": self.message, "as_of": self.as_of,
            "window": WINDOW, "history": HISTORY,
            "components": [c.__dict__ for c in self.components], "reasons": self.reasons,
        }


def _bn(value: float) -> str:
    return f"{value / 1e9:+,.2f} tỷ"


def _shares(value: float) -> str:
    return f"{value:+,.0f} cp"


def _score(z: float | None) -> int | None:
    if z is None:
        return None
    if z >= 2:
        return 2
    if z >= 1:
        return 1
    if z <= -2:
        return -2
    if z <= -1:
        return -1
    return 0


def _calendar(company_id: int) -> list[date]:
    """Trading days of the company, newest first (prices and foreign trades cover every session)."""
    rows = db.rows(
        """SELECT d FROM (SELECT price_date AS d FROM stock_prices WHERE company_id = %(cid)s
                          UNION SELECT trade_date FROM foreign_trades WHERE company_id = %(cid)s
                          UNION SELECT trade_date FROM order_statistics WHERE company_id = %(cid)s) AS days
           ORDER BY d DESC LIMIT %(n)s""",
        {"cid": company_id, "n": WINDOW + HISTORY})
    return [row["d"] for row in rows]


def _daily(company_id: int, days: list[date], table: str, column: str, key: str, label: str,
           fmt) -> Component:
    if len(days) < WINDOW + MIN_HISTORY:
        return Component(key, label, None, detail="Chưa đủ dữ liệu (cần ít nhất "
                                                   f"{WINDOW + MIN_HISTORY} phiên)")
    rows = db.rows(f"SELECT trade_date, {column} AS v FROM {table} WHERE company_id = %(cid)s "
                   "AND trade_date BETWEEN %(a)s AND %(b)s", {"cid": company_id, "a": days[-1], "b": days[0]})
    if not rows:
        return Component(key, label, None, detail="Không có dữ liệu")
    by_day = {row["trade_date"]: float(row["v"] or 0) for row in rows}
    series = [by_day.get(day, 0.0) for day in days]  # newest first
    recent, before = series[:WINDOW], series[WINDOW:]
    sd = pstdev(before)
    z = (mean(recent) - mean(before)) / sd if sd > 0 else None
    sign_days = sum(1 for v in recent if v < 0)
    return Component(
        key, label, _score(z), round(z, 2) if z is not None else None,
        recent=f"{fmt(sum(recent))} ({fmt(mean(recent))}/phiên)",
        usual=f"{fmt(mean(before))}/phiên",
        detail=f"{sign_days}/{WINDOW} phiên bán ròng, {WINDOW - sign_days}/{WINDOW} phiên mua ròng hoặc cân bằng",
    )


def _shares_outstanding(company_id: int) -> float | None:
    row = db.one(
        """SELECT COALESCE(c.outstanding_shares, c.listed_shares,
                           (SELECT m.shares_outstanding FROM financial_metrics AS m WHERE m.company_id = c.company_id
                            ORDER BY m.period_end DESC LIMIT 1),
                           (SELECT MAX(i.shares_after * 100 / i.ownership_after_percentage) FROM insider_trades AS i
                            WHERE i.company_id = c.company_id AND i.ownership_after_percentage >= 0.1)) AS shares
           FROM companies AS c WHERE c.company_id = %(cid)s""", {"cid": company_id})
    return float(row["shares"]) if row and row["shares"] else None


def _insiders(company_id: int, as_of: date) -> Component:
    rows = db.rows(
        """SELECT trader_name, related_person_name, registered_buy, registered_sell, registration_start,
                  registration_end, executed_buy, executed_sell, execution_date
           FROM insider_trades WHERE company_id = %(cid)s
             AND (COALESCE(execution_date, registration_end, registration_start) >= %(since)s
                  OR registration_end >= %(today)s)
           ORDER BY registration_start DESC""",
        {"cid": company_id, "since": as_of - timedelta(days=INSIDER_DAYS), "today": as_of})
    if not rows:
        return Component("insiders", "Người nội bộ", 0, detail=f"Không có đăng ký/giao dịch trong {INSIDER_DAYS} ngày")
    shares = _shares_outstanding(company_id)
    threshold = shares * MATERIAL_SHARE if shares else 0
    scores, notes = [], []
    for row in rows:
        who = row["trader_name"] + (f" (liên quan {row['related_person_name']})" if row["related_person_name"] else "")
        bought, sold = row["executed_buy"] or 0, row["executed_sell"] or 0
        size = max(bought, sold, row["registered_buy"] or 0, row["registered_sell"] or 0)
        if threshold and size < threshold:
            notes.append(f"{who}: {size:,} cp, dưới ngưỡng trọng yếu ({MATERIAL_SHARE:.2%} = {threshold:,.0f} cp), bỏ qua")
            scores.append(0)
            continue
        if bought or sold:
            direction = 2 if bought >= sold else -2
            notes.append(f"{who}: đã {'mua' if direction > 0 else 'bán'} {max(bought, sold):,} cp")
        elif row["registration_end"] and row["registration_end"] >= as_of:
            direction = 1 if (row["registered_buy"] or 0) >= (row["registered_sell"] or 0) else -1
            amount = row["registered_buy"] if direction > 0 else row["registered_sell"]
            notes.append(f"{who}: đang đăng ký {'mua' if direction > 0 else 'bán'} {amount or 0:,} cp "
                         f"đến {row['registration_end']:%d/%m/%Y}")
        else:
            direction = 0
            ended = f"{row['registration_end']:%d/%m/%Y}" if row["registration_end"] else "?"
            notes.append(f"{who}: hết hạn đăng ký {ended}, chưa có kết quả thực hiện")
        scores.append(direction)
    strongest = max(scores, key=abs)
    mixed = any(s > 0 for s in scores) and any(s < 0 for s in scores)
    return Component("insiders", "Người nội bộ", 0 if mixed else strongest,
                     recent="; ".join(notes[:3]), usual="", detail="Trái chiều giữa các người nội bộ" if mixed else "")


def compute(company_id: int) -> Signal | None:
    days = _calendar(company_id)
    has_insiders = db.scalar("SELECT COUNT(*) FROM insider_trades WHERE company_id = %(cid)s", {"cid": company_id})
    if not days and not has_insiders:
        return None
    as_of = days[0] if days else date.today()
    components = [
        _daily(company_id, days, "foreign_trades", "net_value", "foreign", "Khối ngoại", _bn),
        _daily(company_id, days, "proprietary_trades", "net_value", "proprietary", "Tự doanh", _bn),
        _daily(company_id, days, "order_statistics", "net_volume", "orders", "Lệnh đặt (mua − bán)", _shares),
        _insiders(company_id, as_of),
    ]
    scored = [c for c in components if c.score is not None]
    negative = [c for c in scored if c.score < 0]
    positive = [c for c in scored if c.score > 0]
    insider = next(c for c in components if c.key == "insiders")
    foreign = next(c for c in components if c.key == "foreign")
    reasons = [f"{c.label}: {'bất thường mạnh' if abs(c.score) == 2 else 'bất thường'} theo chiều "
               f"{'mua' if c.score > 0 else 'bán'}" + (f" (z = {c.z:+.2f})" if c.z is not None else "")
               for c in negative + positive]

    if negative and positive:
        label, message = MIXED
        return Signal(0, label, message, as_of, components, reasons)
    if negative:
        strong = sum(1 for c in negative if c.score <= -2)
        level = -2 if strong >= 2 or ((foreign.score or 0) <= -2 and (insider.score or 0) <= -1) else -1
    elif positive:
        strong = sum(1 for c in positive if c.score >= 2)
        level = 2 if strong >= 2 or (insider.score or 0) >= 2 else 1
    else:
        level = 0
        reasons = ["Không nhóm nào lệch đáng kể so với thói quen của chính nó"]
    missing = [c.label for c in components if c.score is None]
    if missing:
        reasons.append("Thiếu dữ liệu: " + ", ".join(missing))
    label, message = LEVELS[level]
    return Signal(level, label, message, as_of, components, reasons)
