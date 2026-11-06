"""Extract related-party transaction rows (current period) from OCR pages with coordinates."""
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parse_reports import fold, parse_value  # noqa: E402

# Standard wording of transaction descriptions and their type; OCR text is matched to these.
VOCABULARY = [
    ("Bán hàng hóa", "sale_goods"), ("Bán thành phẩm, hàng hóa", "sale_goods"),
    ("Bán hàng hóa, thành phẩm", "sale_goods"), ("Bán thành phẩm", "sale_goods"),
    ("Bán nguyên liệu", "sale_goods"), ("Bán phân bón", "sale_goods"), ("Bán dụng cụ", "sale_other"),
    ("Bán máy móc, thiết bị", "sale_other"), ("Bán khác", "sale_other"), ("Bán dịch vụ", "sale_services"),
    ("Cung cấp dịch vụ", "sale_services"), ("Mua hàng hóa", "purchase_goods"),
    ("Mua hàng hóa, nguyên liệu", "purchase_goods"), ("Mua hàng hóa, tài sản, nguyên vật liệu", "purchase_goods"),
    ("Mua phân bón", "purchase_goods"), ("Mua dụng cụ", "purchase_goods"),
    ("Mua nguyên liệu", "purchase_materials"), ("Mua nguyên vật liệu", "purchase_materials"),
    ("Mua nguyên liệu, hàng hóa", "purchase_materials"), ("Mua vật liệu", "purchase_materials"),
    ("Mua dịch vụ", "purchase_services"), ("Nhận cung cấp dịch vụ", "purchase_services"),
    ("Mua tài sản cố định", "other"), ("Mua thêm cổ phiếu", "other"),
    ("Thu nhập lãi", "interest_income"), ("Thu nhập lãi vay", "interest_income"),
    ("Chi phí lãi vay", "interest_expense"), ("Chi phí lãi", "interest_expense"),
    ("Chi phí lãi vay/ứng", "interest_expense"), ("Thu nhập khác", "other_income"),
    ("Lợi nhuận hợp tác đầu tư", "other_income"), ("Thanh lý tài sản", "asset_disposal"),
    ("Thanh lý tài sản cố định", "asset_disposal"), ("Cho vay", "lending"),
    ("Thu cho vay", "loan_collection"), ("Thu hồi khoản cho vay", "loan_collection"),
    ("Tiền thu từ cho vay", "loan_collection"), ("Đi vay", "borrowing"), ("Vay", "borrowing"),
    ("Trả nợ vay", "loan_repayment"), ("Trả gốc vay", "loan_repayment"), ("Cổ tức", "dividend_received"),
    ("Cổ tức được chia", "dividend_received"), ("Đặt cọc", "other"), ("Hoàn ký quỹ", "other"),
    ("Nhận hoàn đặt cọc", "other"),
    # Wording used in the reviewed semi-annual reports.
    ("Doanh thu cung cấp dịch vụ", "sale_services"), ("Doanh thu khác", "sale_other"),
    ("Thu nhập lãi cho vay", "interest_income"), ("Nhận lại tiền cho vay", "loan_collection"),
    ("Mua khác", "purchase_goods"), ("Bán máy móc, công cụ", "sale_other"),
    ("Mua hàng hóa, dịch vụ", "purchase_goods"), ("Mua hàng hóa, tài sản", "purchase_goods"), ("Trả vay", "loan_repayment"), ("Bán đường", "sale_goods"),
]

TYPE_RULES = [
    (r"\bnh\w{0,2}n\b.*c\w{0,2}ng c", "purchase_services"), (r"c\w{0,2}ng c\w{0,3} d\w{0,2}ch", "sale_services"),
    (r"mua (ng|v\w{0,2}t|nvl)", "purchase_materials"), (r"mua d\w{0,2}ch", "purchase_services"),
    (r"mua th\w{0,2}m c|mua t\w{0,2}i s", "other"), (r"mua (h|th|ph|d)", "purchase_goods"),
    (r"b\w{0,2}n (kh|d\w{0,2}ng|m)", "sale_other"),
    (r"b\w{0,2}n (h|th|ng|v|ph)", "sale_goods"), (r"thu nh\w{0,2}p? l|l\w{0,2}i ti\w{0,2}n g", "interest_income"),
    (r"chi ph\w{0,2} l", "interest_expense"), (r"thu nh\w{0,2}p? kh|h\w{0,2}p t\w{0,2}c", "other_income"),
    (r"thanh l", "asset_disposal"),
    (r"thu h\w{0,2}i|thu (t\w{0,2} )?cho vay", "loan_collection"), (r"\bcho vay", "lending"),
    (r"\bd?i vay|^vay\b", "borrowing"),
    (r"tr\w{0,2} (n|g)", "loan_repayment"), (r"c\w{0,2} t\w{0,2}c", "dividend_received"),
]


def clean_description(text: str) -> str:
    """Map OCR'd wording to the closest standard phrase (unchanged if nothing is close)."""
    import difflib
    # OCR sometimes glues the relation cell ("Cong ty con", "Co dong lon") onto the description.
    text = re.sub(r"^(C\S* \S*ng l\S*n|C\S*ng ty (con( gi\S*n ti\S*p)?|c\S*ng T\S*p \S*))\s*(?=\S)", "", text.strip())
    target = fold(text).strip()
    best = max(VOCABULARY, key=lambda v: difflib.SequenceMatcher(None, target, fold(v[0])).ratio())
    ratio = difflib.SequenceMatcher(None, target, fold(best[0])).ratio()
    return best[0] if ratio >= 0.72 else text


RELATIONS = [
    (r"con gian tiep", "indirect_subsidiary"), (r"cong ty con", "subsidiary"), (r"lien ket", "associate"),
    (r"co dong lon", "major_shareholder"), (r"dong chu so huu", "co_owner"),
    (r"cung tap doan", "group_company"),
]


def transaction_type(description: str) -> str:
    standard = {phrase: kind for phrase, kind in VOCABULARY}
    if description in standard:
        return standard[description]
    text = fold(description)
    for pattern, kind in TYPE_RULES:
        if re.search(pattern, text):
            return kind
    return "other"


def relation_of(text: str) -> str:
    text = fold(text)
    for pattern, kind in RELATIONS:
        if re.search(pattern, text):
            return kind
    return "other"


def canonical(name: str, known: list[str]) -> tuple[str, float]:
    folded = {fold(k): k for k in known}
    match = difflib.get_close_matches(fold(name), list(folded), n=1, cutoff=0.0)
    if not match:
        return name, 0.0
    return folded[match[0]], difflib.SequenceMatcher(None, fold(name), match[0]).ratio()


def extract(pages: dict[int, dict]) -> list[dict]:
    rows_out = []
    for number, page in sorted(pages.items()):
        text = fold(" ".join(page["lines"]))
        if "nghi" not in text or re.search(r"s\w? du cac kh|thu lao", text):
            continue
        header = next((r for r in page["rows"] if any("dung nghi" in fold(t) for _, _, t in r)), None)
        if header is None:
            continue
        desc_x = next(x1 for x1, _, t in header if "dung nghi" in fold(t))
        # Balance tables head their value columns "Ngay 31 thang ..."; transaction tables do not.
        if re.search(r"ngay \d", fold(" ".join(t for x1, _, t in header if x1 >= desc_x))):
            continue
        value_cols = sorted(x2 for x1, x2, t in header if x1 > desc_x + 60)
        if len(value_cols) < 1:
            continue
        current_right = value_cols[0]
        counterparty, relation = None, None
        start = page["rows"].index(header) + 1
        for row in page["rows"][start:]:
            names = [t for x1, x2, t in row if x2 < desc_x - 20]
            descs = [t for x1, x2, t in row if x1 >= desc_x - 120 and parse_value(t) is None and x2 < current_right - 120]
            values = [(x2, parse_value(t)) for x1, x2, t in row if parse_value(t) is not None]
            if names:
                joined = " ".join(names)
                if descs or values:
                    counterparty = joined
                elif counterparty and not rows_out or (rows_out and rows_out[-1]["counterparty"] == counterparty and len(joined) < 30):
                    counterparty = f"{counterparty} {joined}"
                    for r in rows_out:
                        if r["counterparty"] == counterparty.rsplit(" ", len(joined.split()))[0]:
                            r["counterparty"] = counterparty
                else:
                    counterparty = joined
            for x2, value in values:
                if abs(x2 - current_right) < 80 and descs:
                    rows_out.append({"page": number, "counterparty": counterparty,
                                     "description": " ".join(descs), "amount": value})
    return rows_out


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    pages = {int(p.stem[1:]): json.loads(p.read_text(encoding="utf-8")) for p in directory.glob("p*.json")}
    pages = {n: p for n, p in pages.items() if "rows" in p}
    for row in extract(pages):
        print(row)
