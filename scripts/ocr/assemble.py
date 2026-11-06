"""Turn one report's OCR output plus a hand-checked config into import CSVs.

usage: assemble.py <config.json>   (normally called by process.py; see README.md for the config fields)
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import difflib  # noqa: E402
import re  # noqa: E402
from parse_reports import fold  # noqa: E402
from rpt import clean_description, extract as extract_rows, relation_of, transaction_type  # noqa: E402
from rpt2 import extract as extract_tokens  # noqa: E402

CLEAN = {
    "sale_goods": "Bán hàng hóa, thành phẩm", "sale_services": "Cung cấp dịch vụ", "sale_other": "Bán khác",
    "purchase_goods": "Mua hàng hóa", "purchase_materials": "Mua nguyên vật liệu",
    "purchase_services": "Nhận cung cấp dịch vụ", "interest_income": "Thu nhập lãi",
    "interest_expense": "Chi phí lãi vay", "other_income": "Thu nhập khác", "asset_disposal": "Thanh lý tài sản",
    "lending": "Cho vay", "loan_collection": "Thu hồi khoản cho vay", "borrowing": "Đi vay",
    "loan_repayment": "Trả nợ vay", "dividend_received": "Cổ tức được chia",
}
TT200 = {
    "income_statement": {
        "revenue": "01", "net_revenue": "10", "cost_of_goods_sold": "-11", "gross_profit": "20",
        "financial_income": "21", "financial_expense": "-22", "interest_expense": "-23",
        "selling_expense": "-25", "admin_expense": "-26", "operating_profit": "30", "other_profit": "40",
        "profit_before_tax": "50", "net_income": "60", "net_income_parent": "61",
    },
    "balance_sheet": {
        "cash_and_equivalents": "110", "short_term_investments": "120", "short_term_receivables": "130",
        "inventory": "140", "current_assets": "100", "total_assets": "270", "current_liabilities": "310",
        "total_liabilities": "300", "short_term_debt": "320", "long_term_debt": "338",
        "share_capital": "411", "equity": "400",
    },
    "cash_flow": {"operating_cash_flow": "20", "investing_cash_flow": "30", "financing_cash_flow": "40"},
}


def main():
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    meta, out = config["meta"], Path(config["out_dir"])
    overrides = {"meta": {"report_type": meta["report_type"], "scope": meta["scope"],
                          "fiscal_year": meta["fiscal_year"], "quarter": meta.get("quarter")},
                 "fix": config.get("statement_fix", {}), "set": config.get("set", {}),
                 "deskew": config.get("deskew", [])}
    result = subprocess.run([sys.executable, str(HERE / "build.py"), config["ocr_dir"], str(out),
                             json.dumps(overrides)], capture_output=True, text=True, check=True)
    print(result.stdout.strip().splitlines()[-1] if "PASS" in result.stdout else result.stdout)
    statements = json.loads((out / "statements.json").read_text(encoding="utf-8"))
    values = {s: {i["code"]: i["values"] for i in items} for s, items in statements.items()}
    quarterly = meta.get("quarter") is not None

    row = {"ticker": "SBT", "report_type": meta["report_type"], "report_scope": meta["scope"],
           "fiscal_year": meta["fiscal_year"], "fiscal_quarter": meta.get("quarter") or "",
           "period_start": meta["period_start"], "period_end": meta["period_end"], "currency": "VND",
           "document_storage_path": meta["document"], "published_at": meta["published_at"],
           "audit_status": meta.get("audit_status", ""), "auditor": meta.get("auditor", ""),
           "audit_opinion": meta.get("audit_opinion", ""), "audit_report_date": meta.get("audit_report_date", "")}
    mappings = TT200
    if "280" in values.get("balance_sheet", {}):  # Circular 99 layout
        mappings = json.loads(json.dumps(TT200))
        mappings["income_statement"].update({"financial_income": "22", "financial_expense": "-23",
                                             "interest_expense": "-24"})
        mappings["balance_sheet"].update({"total_assets": "280", "short_term_debt": "321",
                                          "long_term_debt": "339"})
    for statement, mapping in mappings.items():
        if statement == "cash_flow" and quarterly and meta["quarter"] != 1:
            continue  # quarterly cash flows are year-to-date; kept in finance_report_items
        for column, code in mapping.items():
            sign = -1 if code.startswith("-") else 1
            found = values.get(statement, {}).get(code.lstrip("-"))
            if found and found[0] is not None:
                row[column] = sign * found[0]
    tax = [values.get("income_statement", {}).get(c, [0])[0] or 0 for c in ("51", "52")]
    row["income_tax_expense"] = -sum(tax)
    eps = values.get("income_statement", {}).get("70")
    if eps:
        row["earnings_per_share"] = eps[0]
    other = {}
    for key, (statement, code, col) in {
        "associates_profit": ("income_statement", "27" if "280" in values.get("balance_sheet", {}) else "24", 0), "net_income_minority": ("income_statement", "62", 0),
        "minority_interest": ("balance_sheet", "429", 0), "ytd_net_revenue": ("income_statement", "10", 2),
        "ytd_profit_before_tax": ("income_statement", "50", 2), "ytd_net_income": ("income_statement", "60", 2),
        "ytd_operating_cash_flow": ("cash_flow", "20", 0),
    }.items():
        found = values.get(statement, {}).get(code)
        if found and len(found) > col and found[col] is not None and (quarterly or not key.startswith("ytd")):
            other[key] = found[col]
    if config.get("employees"):
        row["employee_count"] = config["employees"]["total"]
        other.update({k: v for k, v in config["employees"].items() if k != "total"})
    row["other_metrics"] = json.dumps(other, ensure_ascii=False)
    with (out / "finance_reports.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)

    pages = {int(p.stem[1:]): json.loads(p.read_text(encoding="utf-8")) for p in Path(config["ocr_dir"]).glob("p*.json")}
    trades = extract_tokens(pages) if any("tokens" in p for p in pages.values()) else \
        extract_rows({n: p for n, p in pages.items() if "rows" in p})
    parties, missing = config.get("parties", {}), set()
    # Canonical counterparty names live next to the company's configs.
    registry_path = Path(config.get("registry", Path(sys.argv[1]).parent / "registry.json"))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    folded = {fold(name): name for name in registry}
    matched = {}
    rpt_rows = []
    for name, kind, description, amount in config.get("extra_rows", []):
        rpt_rows.append([name, kind, "", "other", description, amount])
    skip = {tuple(x) for x in config.get("skip_rows", [])}
    for trade in trades:
        if (trade["page"], trade["amount"]) in skip:
            continue
        party = parties.get(trade["counterparty"])
        if party is None and trade["counterparty"] not in matched:
            # Fuzzy-match OCR'd names to the canonical registry; weak matches are reported.
            ocr = re.sub(r"\(t\w{0,2}n c\w{0,2} .*|\*+", "", fold(trade["counterparty"])).strip()
            best = max(folded, key=lambda f: difflib.SequenceMatcher(None, ocr, f).ratio())
            ratio = difflib.SequenceMatcher(None, ocr, best).ratio()
            matched[trade["counterparty"]] = (folded[best], ratio)
            print(f"  match {ratio:.2f}: {trade['counterparty'][:60]} -> {folded[best]}")
        if party is None and matched.get(trade["counterparty"], (None, 0))[1] >= config.get("min_ratio", 0.8):
            name = matched[trade["counterparty"]][0]
            relation = relation_of(trade.get("relation", "")) if trade.get("relation") else None
            party = [name, relation if relation and relation != "other" else registry[name]["relationship"],
                     registry[name]["ticker"]]
        if party is None:
            missing.add(trade["counterparty"])
            continue
        description = config.get("description_fix", {}).get(trade["description"], clean_description(trade["description"]))
        kind = transaction_type(description)
        rpt_rows.append([party[0], kind, party[2], party[1], description,
                         trade["amount"]])
    for name, description, amount in config.get("remuneration", []):
        rpt_rows.append([name, "remuneration", "", "key_management", description, amount])
    if missing:
        print("UNMAPPED PARTIES:", sorted(missing))
    keys = [(r[0].lower(), r[1], r[4]) for r in rpt_rows]
    duplicates = {k for k in keys if keys.count(k) > 1}
    if duplicates:
        print("DUPLICATE KEYS (merge or retype):", duplicates)
    with (out / "related_party_transactions.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "report_scope", "counterparty_name", "transaction_type", "period_start",
                         "period_end", "counterparty_ticker", "relationship", "description", "amount", "currency",
                         "document_storage_path"])
        for name, kind, ticker, relationship, description, amount in rpt_rows:
            writer.writerow(["SBT", meta["scope"], name, kind, meta["period_start"], meta["period_end"], ticker,
                             relationship, description, amount, "VND", meta["document"]])
    if config.get("leaders"):
        with (out / "company_leaders.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ticker", "person_name", "position", "leader_group", "appointed_date",
                             "dismissed_date", "status"])
            for leader in config["leaders"]:
                writer.writerow(["SBT", *leader])
    print(f"finance_reports 1, items {sum(len(v) for v in statements.values())}, related party {len(rpt_rows)}, "
          f"leaders {len(config.get('leaders', []))}")
    for key in ("net_revenue", "profit_before_tax", "net_income", "total_assets", "equity"):
        print(f"  {key}: {row.get(key, 0):,}")


if __name__ == "__main__":
    main()
