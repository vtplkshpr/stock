"""Position-based extraction of current-period related-party transactions (needs OCR 'tokens')."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parse_reports import fold, parse_value  # noqa: E402
from rpt import RELATIONS, relation_of  # noqa: E402,F401

RELATION_TEXT = re.compile(r"c\w{0,2}ng ty|c\w{0,2} d\w{0,2}ng|b\w{0,2}n li|d\w{0,2}ng ch")


def mid(token):
    return (token[2] + token[3]) / 2


def split_merged(tokens):
    """Split cells like '152.200.500.000 358.746.207.886' (two adjacent numbers) in two."""
    out = []
    for t in tokens:
        parts = t[4].split()
        if len(parts) == 2 and all(parse_value(p) is not None for p in parts):
            cut = t[0] + (t[1] - t[0]) * len(parts[0]) / len(t[4])
            out += [[t[0], round(cut), t[2], t[3], parts[0]], [round(cut) + 8, t[1], t[2], t[3], parts[1]]]
        else:
            out.append(t)
    return out


def extract_page(number, page):
    tokens = split_merged(page["tokens"])
    text = fold(" ".join(page["lines"]))
    if "nghi" not in text:
        return []
    # Remuneration and balance tables may share the page; keep only what lies above them.
    stops = [t[2] for t in tokens if re.search(r"giao d\w{0,2}ch v\w{0,2}i (c\w{0,2}c )?b\w{0,2}n li\w{0,2}n quan kh|th\w{0,2} lao c|s\w? du cac kh",
                                              fold(t[4]))]
    if stops:
        tokens = [t for t in tokens if t[2] < min(stops) - 5]
    desc_head = next((t for t in sorted(tokens, key=mid) if len(t[4]) <= 26 and t[0] > 500
                      and re.match(r"n\w{0,2}i dung|giao d\w{0,2}ch$", fold(t[4]).strip())), None)
    if desc_head is None:
        return []
    header_y = desc_head[3] + 5
    above = [t for t in tokens if t[2] < header_y + 40 and t[2] > desc_head[2] - 200]
    if not re.search(r"cho k|\bk\w? k\w? to|n\w{0,2}m nay|n\w{0,2}m tr|\bk\w? n\w{0,2}y\b|\bk\w? tr\w{0,2}\w?c\b", fold(" ".join(t[4] for t in above if t[0] > desc_head[1]))):
        return []  # balance tables head their columns with dates, not "Cho ky ke toan"
    rel_head = next((t for t in above if "quan h" in fold(t[4]) and t[0] < desc_head[0]), None)
    body = [t for t in tokens if t[2] > header_y]
    values = [t for t in body if parse_value(t[4]) is not None and t[0] > desc_head[0]]
    if not values:
        return []
    # Value columns are right-edge clusters holding at least two numbers (drops stamp noise).
    clusters = {}
    for t in values:
        clusters.setdefault(round(t[1] / 25) * 25, []).append(t)
    columns = sorted(c for c, members in clusters.items() if len(members) >= 2) or sorted(clusters)
    current_right = columns[0]
    values = [t for t in values if any(abs(round(t[1] / 25) * 25 - c) <= 25 for c in columns)]
    value_left = min(t[0] for t in values) - 15
    if rel_head:
        # Relation cells are right-aligned under their header, so the name column ends just
        # before the leftmost of them.
        starts = [t[0] for t in body if t[0] > 500 and t[0] < rel_head[1] and RELATION_TEXT.search(fold(t[4]))]
        name_limit = (min(starts) if starts else rel_head[0] - 100) - 5
        names = [t for t in body if t[1] <= name_limit + 40 and t[0] < name_limit]
    else:
        # Without a relation column, names are the cells left-aligned under "Ben lien quan".
        name_head = next((t for t in above if re.search(r"b\w{0,2}n li\w{0,2}n quan", fold(t[4]))), None)
        left = name_head[0] if name_head else min(t[0] for t in body)
        names = [t for t in body if abs(t[0] - left) < 80 and parse_value(t[4]) is None
                 and t[1] < desc_head[1] - 40]
        name_limit = max((t[1] for t in names), default=desc_head[0] - 60) + 5
    relations = [t for t in body if rel_head and t[0] >= name_limit and t[1] <= desc_head[0] + 30
                 and RELATION_TEXT.search(fold(t[4]))]
    # Description cells; OCR sometimes merges the relation cell into the description, so any
    # cell reaching into the description column counts.
    descs = [t for t in body if t[1] > desc_head[0] - 30 and t[0] > name_limit - 10
             and t[1] < value_left + 30 and parse_value(t[4]) is None
             and not re.fullmatch(r"\d{1,3}", t[4].strip())]
    # Group name lines into counterparty blocks: a block starts at a line opening with a company
    # word ("Cong ty", "CT", "Vien", "Cac ben") or after a vertical gap.
    blocks = []
    for n in sorted(names, key=mid):
        opener = re.match(r"(\w{0,3}ng ty\b|ct\b|cty|vi\w{0,2}n\b|c\w{0,2}c b\w{0,2}n|ng\w{0,2}n h)", fold(n[4]).strip())
        if not blocks or opener or n[2] - blocks[-1]["bottom"] > 60:
            blocks.append({"top": n[2], "bottom": n[3], "names": [n[4]], "spans": [(n[2], n[3])]})
        else:
            blocks[-1]["names"].append(n[4])
            blocks[-1]["spans"].append((n[2], n[3]))
            blocks[-1]["bottom"] = n[3]
    for block in blocks:
        centre = (block["top"] + block["bottom"]) / 2
        near = min(relations, key=lambda r: abs(mid(r) - centre), default=None)
        block["relation"] = near[4] if near is not None and abs(mid(near) - centre) < 80 else ""
    # Relation cells also mark their block's rows (they may sit level with the first description).
    if blocks:
        for r in relations:
            owner = min(blocks, key=lambda b: abs((b["top"] + b["bottom"]) / 2 - mid(r)))
            if abs((owner["top"] + owner["bottom"]) / 2 - mid(r)) < 80:
                owner["spans"].append((r[2], r[3]))

    # Group description lines; a larger vertical gap starts a new group.
    ordered = sorted(descs, key=mid)
    gaps = [mid(b) - mid(a) for a, b in zip(ordered, ordered[1:])]
    typical = sorted(gaps)[len(gaps) // 5] if gaps else 0  # spacing of lines within one block
    group_of, groups = {}, []
    for index, d in enumerate(ordered):
        if index == 0 or gaps[index - 1] > typical * 1.45:
            groups.append([])
        groups[-1].append(d)
        group_of[id(d)] = len(groups) - 1

    # A name line level with a description (vertical overlap) starts that block there; later
    # lines of the same group stay with it.
    def overlap(span, d):
        return min(span[1], d[3]) - max(span[0], d[2])

    switched = {}
    for group in groups:
        current = None
        for d in group:
            level = [(max(overlap(sp, d) for sp in b["spans"]), b) for b in blocks]
            level = [(o, b) for o, b in level if o > 10]
            if level:
                current = max(level, key=lambda x: x[0])[1]
            if current is not None:
                switched[id(d)] = current

    def owner_of(desc):
        if id(desc) in switched:
            return switched[id(desc)]
        # The group belongs to the last name block starting no more than ~40px below the
        # group's first line (names are top-aligned or centred against their group).
        group_top = groups[group_of[id(desc)]][0][2]
        started = [b for b in blocks if b["top"] <= group_top + 30]
        if started:
            return started[-1]
        return blocks[0] if blocks else {"names": ["?"], "relation": ""}

    rows = []
    carried = [t for t in tokens if parse_value(t[4]) is not None and t[0] > desc_head[0]
               and desc_head[2] - 420 < t[2] < desc_head[2] - 60
               and min(columns, key=lambda c: abs(c - t[1])) == current_right]
    for v in carried:
        near = min((t for t in tokens if t[1] < v[0] and t[0] > desc_head[0] - 250 and abs(mid(t) - mid(v)) < 30),
                   key=lambda t: abs(mid(t) - mid(v)), default=None)
        if near is not None:
            rows.append({"page": number, "counterparty": "<previous>", "relation": "", "description": near[4],
                         "amount": parse_value(v[4])})
    for v in values:
        if abs(round(v[1] / 25) * 25 - current_right) > 40:
            continue
        near = min(descs, key=lambda d: abs(mid(d) - mid(v)), default=None)
        if near is None or abs(mid(near) - mid(v)) > 45:
            continue
        block = owner_of(near)
        rows.append({"page": number, "counterparty": " ".join(block["names"]), "relation": block["relation"],
                     "description": near[4], "amount": parse_value(v[4])})
    return rows


def extract(pages):
    rows = []
    for number, page in sorted(pages.items()):
        if "tokens" in page:
            for row in extract_page(number, page):
                if row["counterparty"] == "<previous>":
                    row["counterparty"] = rows[-1]["counterparty"] if rows else "?"
                rows.append(row)
    return rows


if __name__ == "__main__":
    import json
    from rpt import transaction_type
    directory = Path(sys.argv[1])
    pages = {int(p.stem[1:]): json.loads(p.read_text(encoding="utf-8")) for p in directory.glob("p*.json")}
    for r in extract(pages):
        print(f"p{r['page']} {transaction_type(r['description']):18} {r['amount']:>18,}  {r['counterparty'][:45]:45} | {r['relation'][:22]:22} | {r['description']}")
