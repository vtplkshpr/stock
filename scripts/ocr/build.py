"""Validate parsed statements of one report and write import CSVs.

usage: build.py <ocr dir> <out dir> <json overrides>
overrides: {"meta": {...}, "fix": {"statement": {"wrong_code@page": "right_code"}}, "drop": [...]}
"""
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parse_reports import fold, parse_report  # noqa: E402
from vas_tt200 import CASH_FLOW, NAMES  # noqa: E402
import vas_tt99  # noqa: E402

NAMES99 = {"balance_sheet": vas_tt99.BALANCE_SHEET, "income_statement": vas_tt99.INCOME_STATEMENT,
           "cash_flow": CASH_FLOW}
BS99_RULES = {
    "100": ["110", "120", "130", "140", "150", "160"], "200": ["210", "220", "230", "240", "250", "260", "270"],
    "280": ["100", "200"], "300": ["310", "330"], "400": ["410", "430"], "440": ["300", "400"],
    "220": ["221", "224", "227"], "221": ["222", "223"], "224": ["225", "226"], "227": ["228", "229"],
    "240": ["241", "242"], "140": ["141", "142"], "411": ["411a", "411b"], "420": ["420a", "420b"],
}
BS99_RANGES = {"110": (111, 119), "120": (121, 129), "130": (131, 139), "150": (151, 159), "160": (161, 169),
               "210": (211, 219), "250": (251, 259), "260": (261, 269), "270": (271, 279), "310": (311, 329),
               "330": (331, 343), "410": (411, 429), "430": (431, 439)}
IS99_RULES = {"10": ["01", "02"], "20": ["10", "11"], "30": ["20", "22", "23", "25", "26", "27"],
              "40": ["31", "32"], "50": ["30", "40"], "60": ["50", "51", "52"], "60b": ["61", "62"]}
TT99 = False

BS_RULES = {
    "100": ["110", "120", "130", "140", "150"], "200": ["210", "220", "230", "240", "250", "260"],
    "270": ["100", "200"], "300": ["310", "330"], "400": ["410", "430"], "440": ["300", "400"],
    "220": ["221", "224", "227"], "221": ["222", "223"], "224": ["225", "226"], "227": ["228", "229"],
    "230": ["231", "232"], "240": ["241", "242"], "140": ["141", "149"], "411": ["411a", "411b"],
    "421": ["421a", "421b"],
}
BS_RANGES = {"110": (111, 119), "120": (121, 129), "130": (131, 139), "150": (151, 159),
             "210": (211, 219), "250": (251, 259), "260": (261, 269), "310": (311, 329),
             "330": (331, 343), "410": (411, 429), "430": (431, 439)}
IS_RULES = {"10": ["01", "02"], "20": ["10", "11"], "30": ["20", "21", "22", "24", "25", "26"],
            "40": ["31", "32"], "50": ["30", "40"], "60": ["50", "51", "52"]}
CF_RULES = {"08": ["01", "02", "03", "04", "05", "06", "07"],
            "20": ["08", "09", "10", "11", "12", "13", "14", "15", "16", "17"],
            "30": ["21", "22", "23", "24", "25", "26", "27"],
            "40": ["31", "32", "33", "34", "35", "36"], "50": ["20", "30", "40"], "70": ["50", "60", "61"]}


def rules_for(statement, codes):
    if TT99 and statement == "balance_sheet":
        rules = dict(BS99_RULES)
        for parent, (lo, hi) in BS99_RANGES.items():
            rules[parent] = [c for c in codes if c.isdigit() and lo <= int(c) <= hi]
        return rules
    if TT99 and statement == "income_statement":
        return IS99_RULES
    if statement == "balance_sheet":
        rules = dict(BS_RULES)
        for parent, (lo, hi) in BS_RANGES.items():
            rules[parent] = [c for c in codes if c.isdigit() and lo <= int(c) <= hi]
        return rules
    if statement == "income_statement":
        rules = dict(IS_RULES)
        if "61" in codes:
            rules["60b"] = ["61", "62"]
        return rules
    return CF_RULES


def check(statement, items):
    by_code = {i["code"]: i for i in items}
    problems = []
    width = max((len(i["values"]) for i in items), default=0)
    for parent, children in rules_for(statement, by_code).items():
        target = by_code.get(parent.rstrip("b"))
        present = [by_code[c] for c in children if c in by_code]
        if not target or not present:
            continue
        for col in range(width):
            if col >= len(target["values"]):
                continue
            if target["values"][col] is None:
                continue
            total = sum(i["values"][col] or 0 for i in present if col < len(i["values"]))
            if abs(total - target["values"][col]) == 1:
                print(f"note: {statement} {parent} col{col} off by 1 VND (rounding in the source)")
            elif total != target["values"][col]:
                problems.append(f"{statement} {parent} col{col}: {target['values'][col]:,} != sum{children} {total:,}")
    return problems


def name_for(statement, code, ocr_label):
    canonical = (NAMES99 if TT99 else NAMES)[statement].get(code)
    if canonical is None:
        return ocr_label
    a = {w for w in re.findall(r"[a-z]{3,}", fold(canonical))}
    b = {w for w in re.findall(r"[a-z]{3,}", fold(ocr_label))}
    return canonical if not a or len(a & b) / len(a) >= 0.25 or not b else ocr_label


def main():
    ocr_dir, out_dir, overrides = Path(sys.argv[1]), Path(sys.argv[2]), json.loads(sys.argv[3])
    report = parse_report(ocr_dir, set(overrides.get("deskew", [])))
    # OCR habitually reads cash-flow codes 08 as "80" and 09 as "60" (60 proper comes after 50).
    cash = report["statements"].get("cash_flow", [])
    seen_ten = False
    for item in cash:
        if item["code"] == "80":
            item["code"] = "08"
        elif item["code"] == "60" and not seen_ten:
            item["code"] = "09"
        seen_ten = seen_ten or item["code"] in ("10", "11", "20")
    for statement, fixes in overrides.get("fix", {}).items():
        seen = {}
        for item in report["statements"].get(statement, []):
            key = f"{item['code']}@{item['page']}"
            seen[key] = seen.get(key, 0) + 1
            nth = f"{key}#{seen[key]}"
            if nth in fixes or key in fixes:
                item["code"] = fixes.get(nth, fixes.get(key))
    # Values that OCR merged into labels, derived from their totals and checked against the residue.
    for statement, values in overrides.get("set", {}).items():
        items = report["statements"].setdefault(statement, [])
        present = {i["code"] for i in items}
        for item in items:
            if item["code"] in values:
                item["values"] = values[item["code"]]
        for code, vals in values.items():
            if code not in present:  # a line OCR missed entirely, read from the page image
                items.append({"code": code, "label": "", "values": vals, "page": items[0]["page"] if items else 0})
        items.sort(key=lambda i: (i["page"], i["code"].zfill(4)))
    global TT99
    TT99 = any(i["code"] == "280" for i in report["statements"].get("balance_sheet", []))
    statements = {s: [i for i in items if any(v is not None for v in i["values"]) and i["code"] not in overrides.get("drop", [])]
                  for s, items in report["statements"].items()}
    problems = [p for s, items in statements.items() for p in check(s, items)]
    print(json.dumps(report["meta"], ensure_ascii=False))
    print("\n".join(problems) or "ALL CHECKS PASS")
    meta = {**report["meta"], **overrides.get("meta", {})}
    quarterly = meta.get("quarter") is not None
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "finance_report_items.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "report_type", "report_scope", "fiscal_year", "fiscal_quarter", "statement",
                    "item_code", "item_name", "value", "comparative_value", "ytd_value", "ytd_comparative_value"])
        for statement, items in statements.items():
            for item in items:
                v = item["values"] + [None] * 4
                if statement == "income_statement" and quarterly:
                    cols = (v[0], v[1], v[2], v[3])
                elif statement == "cash_flow" and quarterly:
                    cols = (v[0] if meta["quarter"] == 1 else None, v[1] if meta["quarter"] == 1 else None, v[0], v[1])
                else:
                    cols = (v[0], v[1], None, None)
                w.writerow(["SBT", meta["report_type"], meta["scope"], meta["fiscal_year"], meta.get("quarter") or "",
                            statement, item["code"], name_for(statement, item["code"], item["label"]),
                            *("" if c is None else c for c in cols)])
    (out_dir / "statements.json").write_text(json.dumps(statements, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
