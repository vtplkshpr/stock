"""Parse OCR'd SBT financial reports: report metadata and statement line items."""
import json
import re
import sys
import unicodedata
from pathlib import Path

VALUE = re.compile(r"^\(?-?\d{1,3}(?:[.,]\d{3})+\)?$")
CODE = re.compile(r"^(\d{2,3}[a-z]?)$")
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "1": 1, "2": 2, "3": 3, "4": 4}
# OCR drops accented letters, so allow up to two missing/odd characters per syllable.
def fuzzy(phrase: str) -> re.Pattern:
    return re.compile(r"\s*".join(r"\w{0,2}".join(re.escape(ch) for ch in word) for word in phrase.split()))


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn").lower()


def load_pages(directory: Path) -> list[list[str]]:
    pages = []
    for path in sorted(directory.glob("p*.json")):
        pages.append(json.loads(path.read_text(encoding="utf-8"))["lines"])
    return pages


def parse_value(token: str) -> int | None:
    token = token.strip()
    if not VALUE.match(token):
        return None
    negative = token.startswith("(") or token.startswith("-")
    number = int(re.sub(r"\D", "", token))
    return -number if negative else number


def metadata(pages: list[list[str]]) -> dict:
    head = fold(" ".join(" ".join(p) for p in pages[:3]))
    scope = "consolidated" if re.search(r"h\w{0,2}p nh\w{0,2}t", head) else "separate"
    meta = {"scope": scope}
    if "rieng" in head and "hop nhat" not in head:
        meta["scope"] = "separate"
    dates = re.findall(r"ngay (\d{1,2}) thang (\d{1,2}) nam (\d{4})", head)
    meta["dates"] = dates[:6]
    quarter = re.search(r"\bqu\w{0,2} ([ivl1]{1,3}|\d)\b", head)
    meta["quarter"] = ROMAN.get(quarter.group(1).replace("l", "i")) if quarter else None
    fiscal = re.search(r"ni\w{0,2}n d\w{0,2} (\d{4}) ?- ?(\d{4})", head)
    meta["fiscal_year"] = int(fiscal.group(2)) if fiscal else None
    meta["annual"] = bool(re.search(r"nam tai chinh ket thuc|bao cao kiem toan|da duoc kiem toan", head)) and not meta["quarter"]
    meta["title"] = " ".join(pages[0][:4])
    return meta


STATEMENTS = (
    ("balance_sheet", (fuzzy("bang can doi ke toan"), fuzzy("tinh hinh tai chinh"))),
    ("income_statement", (fuzzy("ket qua hoat dong kinh doanh"),)),
    ("cash_flow", (fuzzy("luu chuyen tien te"),)),
)


FORM_CODES = {"1": "balance_sheet", "2": "income_statement", "3": "cash_flow", "9": None}


def statement_of(page: list[str]) -> str | None:
    head = fold(" ".join(page[:6]))
    form = re.search(r"\bb\s?0?([1239])[a-z]?\s?-\s?dn", head)
    if form:
        return FORM_CODES[form.group(1)]
    if fuzzy("thuyet minh").search(head):
        return None
    for name, keys in STATEMENTS:
        if any(k.search(head) for k in keys):
            return name
    return None


def parse_items(lines: list[str]) -> list[dict]:
    items = []
    pending = None
    for line in lines:
        tokens = [t.strip() for t in line.split("|") if t.strip()]
        if not tokens:
            continue
        first = tokens[0].split(" ", 1)
        code = CODE.match(first[0])
        values = []
        for t in (tokens[1:] if code else tokens):
            v = parse_value(t)
            if v is not None:
                values.append(v)
            elif t in ("-", "_", "–") and values is not None:
                values.append(0)
        if code and code.group(1) in ("70", "71") and not values:
            values = [float(t.replace(".", "").replace(",", ".")) for t in re.findall(r"\(?\d[\d.]*,\d+\)?", line)]
        dashes = [t for t in tokens if t in ("-", "_", "–")]
        label_parts = [t for t in tokens[1:] if parse_value(t) is None and t not in ("-", "_", "–")]
        if code:
            label = " ".join(([first[1]] if len(first) > 1 else []) + label_parts)
            pending = {"code": code.group(1), "label": label, "values": values, "dashes": len(dashes)}
            items.append(pending)
        elif pending is not None and not pending["values"]:
            pending["label"] += " " + " ".join(label_parts)
            pending["values"] = values
    for item in items:
        item["label"] = re.sub(r"\s+\d{1,2}(?:[.,]\d)?(?:,\d+)*$", "", item["label"]).strip()
    return items


DASHES = ("-", "_", "–")


def parse_rows(rows: list[list]) -> list[dict]:
    """Like parse_items, but places each number in the column whose right edge is nearest."""
    edges = []
    for row in rows:
        xs = sorted(x2 for _, x2, t in row if parse_value(t) is not None)
        if len(xs) > len(edges):
            edges = xs
    # Codes live in the leftmost "Ma so" column; a short number further right is a note reference.
    code_x = min((x1 for row in rows for x1, _, t in row if CODE.match(t.strip().split(" ", 1)[0])), default=0)
    items, pending, orphan = [], None, None
    loose = None  # a values-only line not yet claimed by any item
    for row in rows:
        texts = [t.strip() for _, _, t in row if t.strip()]
        if not texts:
            continue
        first = texts[0].split(" ", 1)
        code = CODE.match(first[0]) if row[0][0] < code_x + 60 else None
        if code and len(texts) == 1 and len(first) == 1 and orphan is not None:
            # The code sits on the line below its label and values.
            orphan["code"] = code.group(1)
            orphan = None
            continue
        cells = [None] * len(edges)
        for _, x2, t in (row[1:] if code else row):
            value = parse_value(t)
            if value is not None and edges:
                cells[min(range(len(edges)), key=lambda i: abs(edges[i] - x2))] = value
        if code and code.group(1) in ("70", "71") and not any(c is not None for c in cells):
            cells = [float(t.replace(".", "").replace(",", ".")) for t in re.findall(r"\(?\d[\d.]*,\d+\)?", " | ".join(texts))]
        eps_row = re.search(r"l\w{0,2}i (c\w{0,2} b|suy)", fold(" ".join(texts))) or (
            not code and pending is not None and pending["code"] in ("70", "71") and not pending["values"])
        if not any(c is not None for c in cells) and eps_row:
            # Earnings per share are small decimals such as 255,79.
            cells = [float(t.replace(".", "").replace(",", ".")) for t in texts if re.fullmatch(r"\(?\d[\d.]*,\d+\)?", t)]
        labels = [t for t in (texts[1:] if code else texts) if parse_value(t) is None and t not in DASHES
                  and not re.fullmatch(r"\(?\d[\d.]*,\d+\)?|\d{1,2}\.\d", t)]
        labels = [t for t in labels if not CODE.match(t)]
        has_values = any(c is not None for c in cells)
        orphan = None
        consumed = False
        if code:
            label = " ".join(([first[1]] if len(first) > 1 else []) + labels)
            if not has_values and loose is not None:
                # Values printed on the line just above the code line.
                cells, has_values = loose, True
            consumed = True
            pending = {"code": code.group(1), "label": label, "values": cells if has_values else []}
            items.append(pending)
        elif pending is not None and not pending["values"]:
            pending["label"] += " " + " ".join(labels)
            if has_values:
                pending["values"] = cells
                consumed = True
        elif (pending is not None and has_values and len(cells) == len(pending["values"])
              and all(p is None for p, c in zip(pending["values"], cells) if c is not None)
              and any(p is None for p in pending["values"])):
            # The rest of a partly read line, printed one row lower: fill only the empty cells.
            pending["values"] = [p if p is not None else c for p, c in zip(pending["values"], cells)]
            consumed = True
        elif has_values and labels and re.match(r"\d{1,2}\.", labels[0]):
            # A numbered line ("15. ...") with values but no code yet; the code may follow.
            orphan = {"code": None, "label": " ".join(labels), "values": cells}
            items.append(orphan)
            pending = orphan
            consumed = True
        real_labels = [t for t in labels if len(re.sub(r"\W", "", t)) > 3]  # ignore stamp fragments
        loose = cells if (has_values and not consumed and not real_labels) else None
    items = [i for i in items if i["code"]]
    for item in items:
        item["label"] = re.sub(r"\s+\d{1,2}(?:[.,]\d)?(?:,\d+)*$", "", item["label"]).strip()
    return items


MERGED = re.compile(r"^\(?\d{1,3}(?:\.\d{3})+\)?")


def split_numbers(text: str) -> list[str]:
    """Split '14.258.223.051.15014.789.631.162.803' (two numbers run together) into both parts."""
    if parse_value(text) is not None or not re.fullmatch(r"[\d.()\s-]+", text) or text.count(".") < 4:
        return [text]
    parts = text.split()
    if len(parts) == 2 and all(parse_value(p) is not None for p in parts):
        return parts
    compact = text.replace(" ", "")
    best = None
    for cut in range(4, len(compact) - 4):
        a, b = compact[:cut], compact[cut:]
        if parse_value(a) is not None and parse_value(b) is not None:
            score = abs(len(a) - len(b))
            if best is None or score < best[0]:
                best = (score, a, b)
    return [best[1], best[2]] if best else [text]


def regroup(tokens: list[list]) -> list[list]:
    """Rebuild table rows from OCR tokens, undoing a slight page skew first."""
    pieces = []
    for x1, x2, y1, y2, text in tokens:
        parts = split_numbers(text.strip())
        width = (x2 - x1) / max(1, len(text))
        cursor = x1
        for part in parts:
            end = cursor + width * len(part)
            pieces.append([cursor, end, (y1 + y2) / 2, part])
            cursor = end + width
    def rows_for(slope):
        rows = []
        for x1, x2, y, text in sorted(pieces, key=lambda p: p[2] - slope * p[0]):
            yc = y - slope * x1
            if rows and abs(rows[-1][0] - yc) < 14:
                rows[-1][1].append([round(x1), round(x2), text])
            else:
                rows.append([yc, [[round(x1), round(x2), text]]])
        return [sorted(r[1]) for r in rows]
    def score(rows):
        total = 0
        for r in rows:
            codes = sum(1 for x1, _, t in r if x1 < 320 and CODE.match(t.split(" ", 1)[0]))
            values = sum(1 for _, _, t in r if parse_value(t) is not None)
            if codes == 1 and 1 <= values <= 4:
                total += 1
            elif codes > 1 or values > 4:
                total -= 2  # two table lines merged into one
        return total
    candidates = [(score(rows_for(k / 1000)), -abs(k), k) for k in range(-30, 31, 2)]
    return rows_for(max(candidates)[2] / 1000)


def parse_report(directory: Path, deskew: set = frozenset()) -> dict:
    pages = load_pages(directory)
    report = {"file": directory.name, "meta": metadata(pages), "statements": {}}
    previous = None
    for index, page in enumerate(pages[:16]):
        name = statement_of(page)
        head = fold(" ".join(page[:4]))
        if name is None and previous and re.search(r"ti\w{0,2}p th", head) and not fuzzy("thuyet minh").search(head):
            name = previous
        previous = name
        if name:
            raw = json.loads((directory / f"p{index + 1:02d}.json").read_text(encoding="utf-8"))
            if "tokens" in raw and index + 1 in deskew:
                parsed = parse_rows(regroup(raw["tokens"]))
            else:
                parsed = parse_rows(raw["rows"]) if "rows" in raw else parse_items(page)
            report["statements"].setdefault(name, []).extend({**item, "page": index + 1} for item in parsed)
    return report


if __name__ == "__main__":
    for directory in sorted(Path(sys.argv[1]).iterdir()):
        if directory.is_dir():
            report = parse_report(directory)
            print(json.dumps(report["meta"], ensure_ascii=False))
            for name, items in report["statements"].items():
                print("  ", name, len(items), "items")
