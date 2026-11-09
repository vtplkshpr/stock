"""Interactive terminal browser for listed-company data."""

import argparse
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

try:
    from . import data_import, metrics, organizations, screening
except ImportError:
    import data_import
    import metrics
    import organizations
    import screening

# Display name of the organisation linked as `org`, e.g. "Công ty TNHH MTV Thành Công Xanh"
# (structure word + canonical name, see organizations.py); NULL when the row has no organisation.
ORG_NAME = organizations.display_sql("org")


def load_database_config() -> dict[str, str]:
    config: dict[str, str] = {}
    config_path = Path(__file__).resolve().parents[1] / ".env"
    if config_path.is_file():
        for line in config_path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.startswith("MYSQL_"):
                config[key] = value.strip().strip("\"'")

    return {
        "host": os.environ.get("MYSQL_HOST", config.get("MYSQL_HOST", "localhost")),
        "port": os.environ.get("MYSQL_PORT", config.get("MYSQL_PORT", "3306")),
        "user": os.environ.get("MYSQL_USER", config.get("MYSQL_USER", "stock_app")),
        "password": os.environ.get("MYSQL_PASSWORD", config.get("MYSQL_PASSWORD", "")),
        "database": os.environ.get("MYSQL_DATABASE", config.get("MYSQL_DATABASE", "stock_market")),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Browse listed companies in the stock database.")
    parser.add_argument("--query", help="Ticker or company name to search for on start.")
    parser.add_argument("--page-size", type=int, default=10, help="Rows per page (1-100, default 10).")
    args = parser.parse_args(argv)
    if not 1 <= args.page_size <= 100:
        parser.error("--page-size must be between 1 and 100.")
    return args


def display_value(value: Any, limit: int = 42) -> str:
    if value is None:
        return "-"
    if isinstance(value, Decimal):
        # 135829154.0000 -> 135,829,154 and 14.530000 -> 14.53
        value = value.normalize()
        text = f"{value:,f}" if value != value.to_integral() else f"{int(value):,}"
        return text
    text = str(value).replace("\n", " ").replace("\r", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def print_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    values = [[display_value(value) for value in row] for row in rows]
    widths = [min(42, max(len(headers[i]), *(len(row[i]) for row in values))) for i in range(len(headers))]
    print("  ".join(header.ljust(widths[i]) for i, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in values:
        print("  ".join(value.ljust(widths[i]) for i, value in enumerate(row)))


def browse_pages(
    connection: Any,
    title: str,
    select_sql: str,
    count_sql: str,
    params: Sequence[Any],
    headers: Sequence[str],
    page_size: int,
    start_page: int = 0,
    hide_id: bool = False,
) -> tuple[tuple[Any, ...], int] | None:
    cursor = connection.cursor()
    cursor.execute(count_sql, params)
    total = cursor.fetchone()[0]
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(start_page, total_pages - 1)

    while True:
        offset = page * page_size
        cursor.execute(select_sql, (*params, page_size, offset))
        rows = cursor.fetchall()
        print(f"\n{title} | {total} result{"" if total == 1 else "s"} | Page {page + 1}/{total_pages}")
        if rows:
            # Number rows by the value to type; hide_id drops the internal id column.
            skip = 1 if hide_id else 0
            print_table(
                ("#", *headers),
                [(index, *row[skip:]) for index, row in enumerate(rows, start=1)],
            )
            print("Enter a row number to select, n: next page, p: previous page, b: back.")
        else:
            print("No data.")
            cursor.close()
            return None

        try:
            choice = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            cursor.close()
            return None

        if choice == "b":
            cursor.close()
            return None
        if choice == "n":
            if page + 1 < total_pages:
                page += 1
            else:
                print("Already on the last page.")
            continue
        if choice == "p":
            if page > 0:
                page -= 1
            else:
                print("Already on the first page.")
            continue
        if choice.isdigit() and 1 <= int(choice) <= len(rows):
            cursor.close()
            return rows[int(choice) - 1], page
        print("Invalid choice.")


def browse_company_search(
    connection: Any, query: str, page_size: int, start_page: int
) -> tuple[tuple[Any, ...], int] | None:
    pattern = f"%{query}%"
    return browse_pages(
        connection,
        f"Companies matching '{query}'",
        """SELECT company_id, ticker, company_name, exchange, industry
           FROM companies
           WHERE ticker LIKE %s OR company_name LIKE %s
           ORDER BY ticker, company_id LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM companies WHERE ticker LIKE %s OR company_name LIKE %s",
        (pattern, pattern),
        ("Ticker", "Company", "Exchange", "Industry"),
        page_size,
        start_page,
        hide_id=True,
    )


def browse_company_catalog(
    connection: Any, page_size: int, start_page: int
) -> tuple[tuple[Any, ...], int] | None:
    return browse_pages(
        connection,
        "Listed companies",
        """SELECT company_id, ticker, company_name, exchange, industry
           FROM companies
           ORDER BY ticker, company_id LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM companies",
        (),
        ("Ticker", "Company", "Exchange", "Industry"),
        page_size,
        start_page,
        hide_id=True,
    )


def show_company(connection: Any, company_id: int) -> None:
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT * FROM companies WHERE company_id = %s", (company_id,))
    company = cursor.fetchone()
    cursor.close()
    if company is None:
        print("Company not found.")
        return

    print("\n" + "=" * 72)
    print(f"{company['ticker']} - {company['company_name']}")
    for label, key in (
        ("Exchange", "exchange"),
        ("Industry", "industry"),
        ("Tax code", "tax_code"),
        ("Charter capital", "charter_capital"),
        ("Listed shares", "listed_shares"),
        ("Outstanding shares", "outstanding_shares"),
        ("Initially listed shares", "initial_listed_shares"),
        ("First trading date", "first_trading_date"),
        ("Established", "established_date"),
        ("Listing date", "listed_date"),
        ("Listing licence", "listing_license"),
        ("Fiscal year starts in month", "fiscal_year_start_month"),
        ("Business registration amendment no.", "business_registration_amendment"),
        ("Latest business registration date", "business_registration_date"),
        ("Fax", "fax"),
        ("Email", "email"),
        ("Website", "website"),
    ):
        value = company.get(key)
        if value is not None and value != "":
            if key.endswith("_shares") and str(value).isdigit():
                value = f"{int(value):,}"
            elif isinstance(value, Decimal):
                value = display_value(value)
            print(f"{label}: {value}")

    for label, key in (
        ("Addresses", "headquarters_addresses"),
        ("Phone", "phone_numbers"),
    ):
        value = company.get(key)
        if not value:
            continue
        try:
            entries = json.loads(value) if isinstance(value, str) else value
        except json.JSONDecodeError:
            entries = []
        if entries:
            print(f"{label}:")
            for entry in entries:
                if isinstance(entry, list) and len(entry) == 2:
                    print(f"  - {entry[0]}: {entry[1]}")
                else:
                    print(f"  - {entry}")

    print_leaders(connection, company_id)

    history = company.get("company_history")
    if history:
        print("History:")
        print(history)

    description = company.get("description")
    if description:
        try:
            source_data = json.loads(description)
        except (json.JSONDecodeError, TypeError):
            source_data = description
        print("Source data:")
        if isinstance(source_data, dict):
            for key, value in source_data.items():
                print(f"  {key}: {value}")
        else:
            print(source_data)


LEADER_GROUPS = (
    ("board", "Board of directors"),
    ("audit_committee", "Audit committee"),
    ("management", "Management / chief accountant"),
    ("other", "Other positions"),
    (None, "Unclassified"),
)


def leader_line(name: str, position: str, birth_year: Any, appointed: Any,
                dismissed: Any, legal_rep: Any) -> str:
    notes = []
    if birth_year:
        notes.append(f"born {birth_year}")
    if appointed:
        notes.append(f"appointed {appointed:%d/%m/%Y}")
    if dismissed:
        notes.append(f"left {dismissed:%d/%m/%Y}")
    if legal_rep:
        notes.append("legal representative")
    suffix = f" ({', '.join(notes)})" if notes else ""
    return f"    - {name}: {position}{suffix}"


def print_leaders(connection: Any, company_id: int) -> None:
    cursor = connection.cursor()
    cursor.execute(
        """SELECT leader_group, status, person_name, position, birth_year,
                  appointed_date, dismissed_date, is_legal_representative
           FROM company_leaders WHERE company_id = %s ORDER BY leader_id""",
        (company_id,),
    )
    leaders = cursor.fetchall()
    cursor.close()
    if not leaders:
        return

    print("Leadership:")
    current = [leader for leader in leaders if leader[1] != "former"]
    for group, label in LEADER_GROUPS:
        members = [leader[2:] for leader in current if leader[0] == group]
        if members:
            print(f"  {label}:")
            for member in members:
                print(leader_line(*member))
    former = [leader[2:] for leader in leaders if leader[1] == "former"]
    if former:
        print("  Former officers:")
        for member in former:
            print(leader_line(*member))


def browse_prices(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Share prices {ticker}",
        """SELECT price_date, open_price, high_price, low_price, close_price,
                  adjusted_close, price_change, change_percentage, trading_volume,
                  ROUND(trading_value / 1e9, 2), negotiated_volume, ROUND(negotiated_value / 1e9, 2)
           FROM stock_prices WHERE company_id = %s
           ORDER BY price_date DESC LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM stock_prices WHERE company_id = %s",
        (company_id,),
        ("Date", "Open", "High", "Low", "Close", "Adjusted", "Change", "Change %", "Volume",
         "Value (bn)", "Negotiated vol.", "Negotiated (bn)"),
        page_size,
    )


def browse_foreign_trades(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Foreign investor trading {ticker} - values: VND billion",
        """SELECT trade_date, buy_volume, ROUND(buy_value / 1e9, 2), sell_volume,
                  ROUND(sell_value / 1e9, 2), net_volume, ROUND(net_value / 1e9, 2),
                  room_remaining, ownership_percentage
           FROM foreign_trades WHERE company_id = %s
           ORDER BY trade_date DESC LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM foreign_trades WHERE company_id = %s",
        (company_id,),
        ("Date", "Buy vol.", "Buy value", "Sell vol.", "Sell value", "Net vol.", "Net value",
         "Room left", "Foreign owned %"),
        page_size,
    )


def browse_proprietary_trades(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Proprietary trading {ticker} - values: VND billion",
        """SELECT trade_date, buy_volume, ROUND(buy_value / 1e9, 2), sell_volume,
                  ROUND(sell_value / 1e9, 2), net_volume, ROUND(net_value / 1e9, 2)
           FROM proprietary_trades WHERE company_id = %s
           ORDER BY trade_date DESC LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM proprietary_trades WHERE company_id = %s",
        (company_id,),
        ("Date", "Buy vol.", "Buy value", "Sell vol.", "Sell value", "Net vol.", "Net value"),
        page_size,
    )


def browse_order_statistics(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Order statistics {ticker}",
        """SELECT trade_date, buy_orders, buy_volume, avg_buy_order_volume, sell_orders,
                  sell_volume, avg_sell_order_volume, net_volume
           FROM order_statistics WHERE company_id = %s
           ORDER BY trade_date DESC LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM order_statistics WHERE company_id = %s",
        (company_id,),
        ("Date", "Buy orders", "Buy vol.", "Avg/buy order", "Sell orders", "Sell vol.",
         "Avg/sell order", "Net vol."),
        page_size,
    )


def browse_intraday_trades(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Intraday matched trades {ticker} (as exported by the source)",
        """SELECT trade_date, trade_time, price, price_change, lot_volume, cumulative_volume,
                  weight_percentage
           FROM intraday_trades WHERE company_id = %s
           ORDER BY trade_date DESC, seq LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM intraday_trades WHERE company_id = %s",
        (company_id,),
        ("Date", "Time", "Price", "Change", "Lot", "Cumulative", "Weight %"),
        page_size,
    )


# Executed share of the registered amount, and whether a result has been reported yet.
INSIDER_STATUS_SQL = """
    CASE WHEN execution_date IS NOT NULL OR COALESCE(executed_buy, 0) + COALESCE(executed_sell, 0) > 0
              THEN 'reported'
         WHEN registration_end >= CURDATE() THEN 'in progress'
         ELSE 'awaiting result' END"""
INSIDER_EXECUTED_SQL = """
    ROUND(100 * (COALESCE(executed_buy, 0) + COALESCE(executed_sell, 0))
          / NULLIF(COALESCE(registered_buy, 0) + COALESCE(registered_sell, 0), 0), 1)"""


def browse_insider_trades(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Insider & major shareholder trades {ticker}",
        f"""SELECT trader_name, trader_position,
                   CONCAT_WS(' - ', related_person_name, related_person_position),
                   shares_before, registered_buy, registered_sell,
                   registration_start, registration_end,
                   executed_buy, executed_sell, execution_date, {INSIDER_EXECUTED_SQL},
                   shares_after, ownership_after_percentage, {INSIDER_STATUS_SQL}
            FROM insider_trades WHERE company_id = %s
            ORDER BY registration_start DESC, trader_name LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM insider_trades WHERE company_id = %s",
        (company_id,),
        ("Trader", "Position / relation", "Related insider", "Shares before", "Reg. buy",
         "Reg. sell", "Reg. from", "Reg. to", "Bought", "Sold", "Exec. date", "Done %", "Shares after",
         "Owned %", "Status"),
        page_size,
    )


TRADING_VIEWS = (
    ("Foreign investors", browse_foreign_trades),
    ("Proprietary trading", browse_proprietary_trades),
    ("Order statistics", browse_order_statistics),
    ("Insider & major shareholder trades", browse_insider_trades),
    ("Intraday matched trades", browse_intraday_trades),
)


def trading_menu(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    while True:
        print(f"\nTrading activity {ticker}")
        print("   ".join(f"{i}. {label}" for i, (label, _) in enumerate(TRADING_VIEWS, start=1)))
        print("b. Back")
        choice = (prompt("> ") or "b").lower()
        if choice == "b":
            return
        if choice.isdigit() and 1 <= int(choice) <= len(TRADING_VIEWS):
            TRADING_VIEWS[int(choice) - 1][1](connection, company_id, ticker, page_size)
        else:
            print("Invalid choice.")


def browse_holders(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Shareholders {ticker}",
        f"""SELECT COALESCE({ORG_NAME}, holder.holder_name), holder.holder_type, holder.shares_owned,
                   holder.ownership_percentage, holder.snapshot_date, holder.source_url
            FROM stock_holders AS holder LEFT JOIN organizations AS org ON org.org_id = holder.holder_org_id
            WHERE holder.company_id = %s
            ORDER BY holder.snapshot_date DESC, holder.ownership_percentage DESC LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM stock_holders WHERE company_id = %s",
        (company_id,),
        ("Shareholder", "Type", "Shares", "Ownership %", "As of", "Source"),
        page_size,
    )


PURCHASE_TYPES = "'purchase_goods', 'purchase_materials', 'purchase_services'"
SALE_TYPES = "'sale_goods', 'sale_services', 'sale_other'"


def browse_supply_chain(
    connection: Any, company_id: int, ticker: str, direction: str, page_size: int
) -> None:
    """List partners from supply_chain_relations and from related-party trades.

    Upstream partners are those the company buys from, or that report selling to it.
    """
    if direction == "upstream":
        title = f"Suppliers of {ticker} (upstream)"
        own_side, other_side = "customer_id", "supplier_id"
        own_types, reverse_types = PURCHASE_TYPES, SALE_TYPES
    else:
        title = f"Customers of {ticker} (downstream)"
        own_side, other_side = "supplier_id", "customer_id"
        own_types, reverse_types = SALE_TYPES, PURCHASE_TYPES

    # Names are shown in their standard form when the organisation register knows them. The other
    # side of a supply relation may be a listed company or an unlisted organisation; sales the
    # company reports to others count when they name its ticker or its organisation record.
    other_org = other_side.replace("_id", "_org_id")
    union_sql = f"""
        SELECT COALESCE(partner.ticker, org.ticker) AS partner_ticker,
               COALESCE({ORG_NAME}, partner.company_name) AS partner_name,
               relation.product_category AS content, relation.percentage_revenue AS share,
               NULL AS amount, NULL AS period_end, NULL AS scope, relation.source_url AS source
        FROM supply_chain_relations AS relation
        LEFT JOIN companies AS partner ON partner.company_id = relation.{other_side}
        LEFT JOIN organizations AS org
          ON org.org_id = COALESCE(relation.{other_org},
                                   (SELECT o.org_id FROM organizations AS o WHERE o.ticker = partner.ticker LIMIT 1))
        WHERE relation.{own_side} = %s
        UNION ALL
        SELECT COALESCE(trade.counterparty_ticker, org.ticker), COALESCE({ORG_NAME}, trade.counterparty_name),
               trade.description, NULL, trade.amount, trade.period_end, trade.report_scope,
               COALESCE(trade.document_storage_path, trade.source_url)
        FROM related_party_transactions AS trade
        LEFT JOIN organizations AS org ON org.org_id = trade.counterparty_org_id
        WHERE trade.company_id = %s AND trade.transaction_type IN ({own_types})
        UNION ALL
        SELECT seller.ticker, COALESCE({ORG_NAME}, seller.company_name), trade.description,
               NULL, trade.amount, trade.period_end, trade.report_scope,
               COALESCE(trade.document_storage_path, trade.source_url)
        FROM related_party_transactions AS trade
        JOIN companies AS seller ON seller.company_id = trade.company_id
        LEFT JOIN organizations AS org ON org.org_id =
            (SELECT o.org_id FROM organizations AS o WHERE o.ticker = seller.ticker LIMIT 1)
        WHERE trade.company_id <> %s AND trade.transaction_type IN ({reverse_types})
          AND (trade.counterparty_ticker = %s OR trade.counterparty_org_id IN
               (SELECT o.org_id FROM organizations AS o WHERE o.ticker = %s))"""
    browse_pages(
        connection,
        title,
        f"""SELECT * FROM ({union_sql}) AS partners
            ORDER BY period_end DESC, amount DESC, partner_name
            LIMIT %s OFFSET %s""",
        f"SELECT COUNT(*) FROM ({union_sql}) AS partners",
        (company_id, company_id, company_id, ticker, ticker),
        ("Ticker", "Company", "Description", "Share %", "Amount", "Period end", "Scope", "Source"),
        page_size,
    )


def browse_reports(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Financial reports {ticker}",
        """SELECT fiscal_year, fiscal_quarter, report_type, report_scope, period_end,
                  net_revenue, profit_before_tax, net_income, total_assets, equity,
                  document_storage_path
           FROM finance_reports WHERE company_id = %s
           ORDER BY period_end DESC, fiscal_year DESC, fiscal_quarter DESC, report_id DESC
           LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM finance_reports WHERE company_id = %s",
        (company_id,),
        (
            "Fiscal year", "Quarter", "Type", "Scope", "Period end", "Net revenue", "Profit before tax",
            "Net income", "Total assets", "Equity", "File",
        ),
        page_size,
    )


def browse_investments(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Subsidiaries, associates & investments of {ticker}",
        f"""SELECT inv.relation_type,
                   CASE inv.is_direct WHEN 1 THEN 'direct' WHEN 0 THEN 'indirect' END,
                   COALESCE({ORG_NAME}, inv.investee_name), COALESCE(inv.investee_ticker, org.ticker),
                   inv.shares_owned, inv.ownership_percentage, inv.voting_percentage,
                   inv.investment_cost, inv.as_of_date
            FROM company_investments AS inv LEFT JOIN organizations AS org ON org.org_id = inv.investee_org_id
            WHERE inv.company_id = %s
            ORDER BY FIELD(inv.relation_type, 'subsidiary', 'associate', 'shareholding'),
                     inv.is_direct DESC, inv.investment_cost DESC, inv.ownership_percentage DESC,
                     inv.investment_id
            LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM company_investments WHERE company_id = %s",
        (company_id,),
        ("Type", "Holding", "Company", "Ticker", "Shares", "Ownership %", "Voting %", "Cost", "As of"),
        page_size,
    )


def browse_related_parties(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Related-party transactions of {ticker}",
        f"""SELECT trade.period_end, trade.report_scope, COALESCE({ORG_NAME}, trade.counterparty_name) AS party,
                   trade.relationship, trade.transaction_type, trade.description, trade.amount
            FROM related_party_transactions AS trade
            LEFT JOIN organizations AS org ON org.org_id = trade.counterparty_org_id
            WHERE trade.company_id = %s
            ORDER BY trade.period_end DESC, trade.report_scope, party, trade.transaction_type
            LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM related_party_transactions WHERE company_id = %s",
        (company_id,),
        ("Period end", "Scope", "Related party", "Relationship", "Type", "Description", "Amount"),
        page_size,
    )


def flag_sql() -> str:
    return "CONCAT_WS(', ', " + ", ".join(
        f"IF({column}, '{label}', NULL)" for column, label in metrics.FLAG_LABELS.items()) + ")"


def browse_metrics(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    print("\nScope: 1. Consolidated  2. Separate   |   Period: a. TTM  b. Year  c. Quarter (Enter = consolidated, TTM)")
    answer = (prompt("> ") or "").lower()
    scope = "separate" if "2" in answer else "consolidated"
    period = {"b": "year", "c": "quarter"}.get(next((ch for ch in answer if ch in "abc"), "a"), "ttm")
    browse_pages(
        connection,
        f"Financial metrics {ticker} ({scope}, {period}) "
        "- amounts: VND billion, ratios: %",
        f"""SELECT CONCAT('FY', fiscal_year, ' Q', fiscal_quarter), period_end,
                   CASE flow_source WHEN 'derived' THEN 'derived' WHEN 'mixed' THEN 'partly derived' ELSE 'reported' END,
                   ROUND(cfo / 1e9, 1), ROUND(cfi / 1e9, 1), ROUND(cff / 1e9, 1), ROUND(free_cash_flow / 1e9, 1),
                   cash_flow_pattern, lifecycle_stage, ROUND(net_margin * 100, 1), ROUND(roe * 100, 1),
                   ROUND(debt_to_equity, 2), ROUND(net_debt_to_ebitda, 1), ROUND(interest_coverage, 2),
                   ROUND(cfo_to_net_income, 2), ROUND(current_ratio, 2), {flag_sql()}
            FROM financial_metrics
            WHERE company_id = %s AND report_scope = %s AND period_type = %s
            ORDER BY period_end DESC LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM financial_metrics WHERE company_id = %s AND report_scope = %s AND period_type = %s",
        (company_id, scope, period),
        ("Period", "Period end", "Source", "CFO", "CFI", "CFF", "FCF", "Pattern", "Life cycle", "Net margin %", "ROE %",
         "Debt/Equity", "Net debt/EBITDA", "EBIT/interest", "CFO/NI", "Current ratio", "Warnings"),
        page_size,
    )


def browse_valuations(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Daily valuation {ticker} (uses only reports published before each price date)",
        """SELECT price_date, close_price, ROUND(market_cap / 1e9, 0), ROUND(pe_ttm, 1), ROUND(pb, 2),
                  ROUND(ps_ttm, 2), ROUND(ev_ebitda, 1), ROUND(dividend_yield * 100, 2),
                  ROUND(fcf_yield * 100, 2), report_scope
           FROM valuation_metrics WHERE company_id = %s
           ORDER BY price_date DESC LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM valuation_metrics WHERE company_id = %s",
        (company_id,),
        ("Date", "Price", "Market cap (bn)", "P/E", "P/B", "P/S", "EV/EBITDA", "Dividend %", "FCF yield %", "Scope"),
        page_size,
    )


def browse_news(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    result = browse_pages(
        connection,
        f"News {ticker}",
        """SELECT news_id, title, media_type, published_at, source_name,
                  media_url, storage_path
           FROM company_news WHERE company_id = %s
           ORDER BY published_at DESC, news_id DESC LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM company_news WHERE company_id = %s",
        (company_id,),
        ("Title", "Media", "Published", "Source", "Media URL", "File"),
        page_size,
        hide_id=True,
    )
    if result is None:
        return
    selected, _ = result

    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """SELECT title, content_text, media_type, media_url, storage_path,
                  published_at, source_name, source_url
           FROM company_news WHERE news_id = %s AND company_id = %s""",
        (selected[0], company_id),
    )
    news = cursor.fetchone()
    cursor.close()
    if news:
        print(f"\n{news['title']} [{news['media_type']}]")
        print(f"Published: {news['published_at'] or '-'} | Source: {news['source_name'] or '-'}")
        print(f"Source URL: {news['source_url'] or '-'}")
        print(f"URL media: {news['media_url'] or '-'}")
        print(f"Stored file: {news['storage_path'] or '-'}")
        print("\n" + (news["content_text"] or "(No text content.)"))
        input("\nPress Enter to go back...")


def prompt(message: str) -> str | None:
    try:
        return input(message).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def confirm_and_commit(connection: Any, results: dict[str, data_import.ImportStats]) -> None:
    print("\nResult:")
    print(data_import.format_report(results))
    if any(stats.errors for stats in results.values()):
        connection.rollback()
        print("Errors found; nothing was saved. Fix the data and try again.")
        return
    if not any(stats.inserted or stats.updated for stats in results.values()):
        connection.rollback()
        print("Nothing to change.")
        return
    answer = prompt("Save changes? (y/N): ")
    if answer is not None and answer.lower() in {"y", "yes"}:
        organisation_summary = data_import.refresh_organizations(connection, results)
        if organisation_summary:
            print(organisation_summary)
        if data_import.METRIC_SOURCES & set(results):
            print(metrics.format_summary(metrics.recompute(connection)))
        connection.commit()
        print("Changes saved.")
    else:
        connection.rollback()
        print("Cancelled; nothing was saved.")


def choose_categories(multiple: bool) -> list[data_import.Category]:
    categories = list(data_import.CATEGORIES.values())
    print()
    for index, category in enumerate(categories, start=1):
        print(f"{index}. {category.label}")
    hint = "Choose categories (e.g. 1,3 or a = all)" if multiple else "Choose a category"
    answer = prompt(f"{hint}, b to go back: ")
    if answer is None or answer.lower() == "b":
        return []
    if multiple and answer.lower() == "a":
        return categories

    chosen: list[data_import.Category] = []
    for part in answer.split(","):
        part = part.strip()
        if not part.isdigit() or not 1 <= int(part) <= len(categories):
            print("Invalid choice.")
            return []
        if categories[int(part) - 1] not in chosen:
            chosen.append(categories[int(part) - 1])
    if not chosen or (not multiple and len(chosen) != 1):
        print("Invalid choice.")
        return []
    return chosen


def manual_entry(connection: Any, ticker: str) -> None:
    categories = choose_categories(multiple=False)
    if not categories:
        return
    category = categories[0]
    print(f"\nEnter {category.label} for {ticker}. Press Enter to leave a field blank (keeps the stored value).")

    raw: dict[str, str] = {}
    for column in category.keys:
        if column == "ticker":
            raw[column] = ticker
            continue
        hint = f" (Enter = {ticker})" if column in data_import.COMPANY_REFS else ""
        value = prompt(f"{column}{hint}: ")
        if value is None:
            return
        raw[column] = value

    cursor = connection.cursor()
    try:
        row = data_import.normalize_row(category, raw, ticker)
        existing = data_import.fetch_existing(cursor, category, row)
        choices = data_import.enum_choices(cursor, category.table)
    except ValueError as exc:
        print(f"Invalid: {exc}")
        return
    finally:
        cursor.close()

    if existing is None:
        print("New record. Current values are shown in [ ].")
    else:
        print("Existing record. Current values are shown in [ ].")
    for column in category.values:
        current = display_value(existing.get(column)) if existing else "-"
        required = " (required)" if existing is None and column in category.required else ""
        options = choices.get(column)
        if options:
            print(f"{column}: " + "   ".join(f"{i}. {o}" for i, o in enumerate(options, start=1)))
            value = prompt(f"Choose a number or type a value{required} [{current}]: ")
        else:
            value = prompt(f"{column}{required} [{current}]: ")
        if value is None:
            return
        if options and value.isdigit():
            if not 1 <= int(value) <= len(options):
                print("Invalid choice.")
                return
            value = options[int(value) - 1]
        raw[column] = value

    stats = data_import.merge_rows(connection, category, [("manual entry", raw)], [ticker])
    confirm_and_commit(connection, {category.table: stats})


def csv_import(connection: Any, tickers: list[str] | None) -> None:
    categories = choose_categories(multiple=True)
    if not categories:
        return
    print("\nSupported CSV columns (first row = column names, blank cell = keep the stored value):")
    for category in categories:
        print(f"  {category.table}.csv: {','.join(category.columns)}")
    if tickers is None or len(tickers) > 1:
        print("Every row needs a ticker column (ticker / supplier_ticker / customer_ticker) to identify the company.")
    else:
        print(f"Rows without a ticker column apply to {tickers[0]}.")

    files: dict[str, Path] = {}
    if len(categories) > 1:
        folder = prompt("Folder with <category>.csv files (Enter to give each file): ")
        if folder is None:
            return
        if folder:
            directory = Path(folder).expanduser()
            for category in categories:
                path = directory / f"{category.table}.csv"
                if path.is_file():
                    files[category.table] = path
                else:
                    print(f"{path} not found; skipping {category.label}.")
    if not files:
        for category in categories:
            path = prompt(f"CSV file for {category.label} (Enter to skip): ")
            if path is None:
                return
            if path:
                files[category.table] = Path(path).expanduser()
    if not files:
        print("No files to import.")
        return

    confirm_and_commit(connection, data_import.import_files(connection, files, tickers))


def data_entry_menu(connection: Any, tickers: list[str] | None) -> None:
    label = ", ".join(tickers) if tickers else "every ticker in the files"
    while True:
        print(f"\n=== ENTER / UPDATE DATA: {label} ===")
        print("1. Manual entry   2. Import CSV files   b. Back")
        choice = prompt("> ")
        if choice is None or choice.lower() == "b":
            return
        if choice == "1":
            if tickers is None or len(tickers) != 1:
                print("Manual entry works for one company at a time.")
            else:
                manual_entry(connection, tickers[0])
        elif choice == "2":
            csv_import(connection, tickers)
        else:
            print("Invalid choice.")


def run_data_entry(connection: Any) -> None:
    answer = prompt(
        "\nTickers (e.g. HPG or HPG,VNM; * = every ticker in the files; b to go back): "
    )
    if not answer or answer.lower() == "b":
        return
    tickers = data_import.parse_tickers(answer)
    if tickers:
        cursor = connection.cursor()
        cursor.execute(
            f"SELECT ticker FROM companies WHERE ticker IN ({', '.join(['%s'] * len(tickers))})",
            tickers,
        )
        found = {row[0] for row in cursor.fetchall()}
        cursor.close()
        missing = [ticker for ticker in tickers if ticker not in found]
        if missing:
            print(f"Not in the database yet: {', '.join(missing)} (only Basic information can create them).")
    data_entry_menu(connection, tickers)


def company_menu(connection: Any, selected: tuple[Any, ...], page_size: int) -> None:
    company_id, ticker, company_name, _, _ = selected
    while True:
        show_company(connection, company_id)
        print("\n1. Share prices   2. Shareholders   3. Suppliers (upstream)")
        print("4. Customers (downstream)   5. Financial reports   6. News")
        print("7. Subsidiaries, associates & investments   8. Enter / update data")
        print("9. Related-party transactions   10. Financial metrics   11. Valuation")
        print("12. Trading activity (foreign, proprietary, orders, insiders, intraday)")
        print("b. Back to search")
        try:
            choice = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if choice == "b":
            return
        if choice == "1":
            browse_prices(connection, company_id, ticker, page_size)
        elif choice == "2":
            browse_holders(connection, company_id, ticker, page_size)
        elif choice == "3":
            browse_supply_chain(connection, company_id, ticker, "upstream", page_size)
        elif choice == "4":
            browse_supply_chain(connection, company_id, ticker, "downstream", page_size)
        elif choice == "5":
            browse_reports(connection, company_id, ticker, page_size)
        elif choice == "6":
            browse_news(connection, company_id, ticker, page_size)
        elif choice == "7":
            browse_investments(connection, company_id, ticker, page_size)
        elif choice == "8":
            data_entry_menu(connection, [ticker])
        elif choice == "9":
            browse_related_parties(connection, company_id, ticker, page_size)
        elif choice == "10":
            browse_metrics(connection, company_id, ticker, page_size)
        elif choice == "11":
            browse_valuations(connection, company_id, ticker, page_size)
        elif choice == "12":
            trading_menu(connection, company_id, ticker, page_size)
        else:
            print("Invalid choice.")


def browse_list(title: str, headers: Sequence[str], rows: list[Sequence[Any]], page_size: int) -> int | None:
    """Page through in-memory rows; return the index of the chosen row, or None."""
    page, total_pages = 0, max(1, (len(rows) + page_size - 1) // page_size)
    while True:
        chunk = rows[page * page_size:(page + 1) * page_size]
        print(f"\n{title} | {len(rows)} result{"" if len(rows) == 1 else "s"} | Page {page + 1}/{total_pages}")
        if not chunk:
            print("No data.")
            return None
        print_table(("#", *headers), [(i, *row) for i, row in enumerate(chunk, start=1)])
        print("Enter a row number to open the company, n: next page, p: previous page, b: back.")
        choice = (prompt("> ") or "b").lower()
        if choice == "b":
            return None
        if choice == "n" and page + 1 < total_pages:
            page += 1
        elif choice == "p" and page > 0:
            page -= 1
        elif choice.isdigit() and 1 <= int(choice) <= len(chunk):
            return page * page_size + int(choice) - 1
        else:
            print("Invalid choice.")


def open_company(connection: Any, company_id: int, page_size: int) -> None:
    cursor = connection.cursor()
    cursor.execute("SELECT company_id, ticker, company_name, exchange, industry FROM companies WHERE company_id = %s",
                   (company_id,))
    selected = cursor.fetchone()
    cursor.close()
    if selected:
        company_menu(connection, selected, page_size)


def pct(value: Any, digits: int = 1) -> str:
    return "-" if value is None else f"{float(value) * 100:.{digits}f}"


def num(value: Any, digits: int = 2) -> str:
    return "-" if value is None else f"{float(value):.{digits}f}"


def screening_row(result: "screening.Result") -> tuple:
    s = result.snapshot
    roe_change = (s.get("roe") - s.before("roe")) * 100 if s.get("roe") is not None and s.before("roe") is not None else None
    failed = [c.label for c, o in zip(result.group.criteria, result.outcomes) if c.required and o is not True]
    return (s.ticker, s.name, f"FY{s.now['fiscal_year']} Q{s.now['fiscal_quarter']}",
            "Consolidated" if s.now["report_scope"] == "consolidated" else "Separate", s.now.get("cash_flow_pattern") or "-",
            pct(s.get("roe")), num(roe_change, 1), num(s.get("cfo_to_net_income")), num(s.get("debt_to_equity")),
            f"{result.met}/{len(result.required)}", "; ".join(failed) or "-")


SCREEN_HEADERS = ("Ticker", "Company", "TTM period", "Scope", "Pattern", "ROE %", "ΔROE (pts)", "CFO/NI",
                  "Debt/Equity", "Met", "Not met / no data")


def show_group(connection: Any, group: "screening.Group", results: list, page_size: int) -> None:
    print(f"\n=== {group.name.upper()} ===\n{group.meaning}\nConditions:")
    for criterion in group.criteria:
        print(f"  - {criterion.label}{'' if criterion.required else ' (for reference)'}")
    matched = [r for r in results if r.matched]
    near = [r for r in results if not r.matched and r.near]
    rows = [("MATCH", *screening_row(r)) for r in matched] + [("near match", *screening_row(r)) for r in near]
    while True:
        index = browse_list(f"{group.name}: {len(matched)} match{"" if len(matched) == 1 else "es"}, {len(near)} near match{"" if len(near) == 1 else "es"} (one condition short)",
                            ("Result", *SCREEN_HEADERS), rows, page_size)
        if index is None:
            return
        open_company(connection, (matched + near)[index].snapshot.company_id, page_size)


def show_warnings(connection: Any, snapshots: list, page_size: int) -> None:
    rows, targets = [], []
    for s in snapshots:
        active = [label for column, label in metrics.FLAG_LABELS.items() if s.now.get(column)]
        if active:
            rows.append((len(active), s.ticker, s.name, f"FY{s.now['fiscal_year']} Q{s.now['fiscal_quarter']}",
                         num(s.get("interest_coverage")), num(s.get("net_debt_to_ebitda"), 1),
                         num(s.get("cfo_to_net_income")), num(s.get("current_ratio")), ", ".join(active)))
            targets.append(s.company_id)
    order = sorted(range(len(rows)), key=lambda i: -rows[i][0])
    rows, targets = [rows[i] for i in order], [targets[i] for i in order]
    while True:
        index = browse_list("Early warnings (flags on the latest TTM period, most flags first)",
                            ("Flags", "Ticker", "Company", "TTM period", "EBIT/interest", "Net debt/EBITDA", "CFO/NI",
                             "Current ratio", "Warnings"), rows, page_size)
        if index is None:
            return
        open_company(connection, targets[index], page_size)


def run_screening(connection: Any, page_size: int) -> None:
    cursor = connection.cursor()
    try:
        results = screening.screen(cursor)
    finally:
        cursor.close()
    snapshots = list({id(r.snapshot): r.snapshot for r in results}.values())
    while True:
        print(f"\n=== STOCK SCREENING & EARLY WARNINGS === (latest TTM period of {len(snapshots)} compan{"y" if len(snapshots) == 1 else "ies"} with reports)")
        for index, group in enumerate(screening.GROUPS, start=1):
            group_results = [r for r in results if r.group is group]
            print(f"{index}. {group.name}: {sum(r.matched for r in group_results)} matches, "
                  f"{sum((not r.matched) and r.near for r in group_results)} near matches")
        flagged = sum(1 for s in snapshots if any(s.now.get(c) for c in metrics.FLAG_LABELS))
        print(f"{len(screening.GROUPS) + 1}. Early warnings: {flagged} compan{"y" if flagged == 1 else "ies"} flagged")
        print(f"{len(screening.GROUPS) + 2}. Overview of every company")
        print("b. Back")
        choice = (prompt("> ") or "b").lower()
        if choice == "b":
            return
        if choice.isdigit() and 1 <= int(choice) <= len(screening.GROUPS):
            group = screening.GROUPS[int(choice) - 1]
            show_group(connection, group, [r for r in results if r.group is group], page_size)
        elif choice == str(len(screening.GROUPS) + 1):
            show_warnings(connection, snapshots, page_size)
        elif choice == str(len(screening.GROUPS) + 2):
            rows = []
            for s in snapshots:
                own = [r for r in results if r.snapshot is s]
                rows.append((s.ticker, s.name, f"FY{s.now['fiscal_year']} Q{s.now['fiscal_quarter']}",
                             s.now.get("cash_flow_pattern") or "-", s.now.get("lifecycle_stage") or "-",
                             *[("✓ " if r.matched else "") + f"{r.met}/{len(r.required)}" for r in own]))
            index = browse_list("Conditions met per group (✓ = match)",
                                ("Ticker", "Company", "TTM period", "Pattern", "Life cycle",
                                 *[g.name for g in screening.GROUPS]), rows, page_size)
            if index is not None:
                open_company(connection, snapshots[index].company_id, page_size)
        else:
            print("Invalid choice.")


def run_search(connection: Any, page_size: int, initial_query: str | None = None) -> None:
    query = initial_query
    while True:
        if query is None:
            try:
                query = input("\nTicker or company name (b to go back): ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
        if query.lower() in {"b", "q", "quit", "exit"}:
            return
        if not query:
            query = None
            continue

        search_page = 0
        while True:
            result = browse_company_search(connection, query, page_size, search_page)
            if result is None:
                break
            selected, search_page = result
            company_menu(connection, selected, page_size)
        query = None


def run_company_catalog(connection: Any, page_size: int) -> None:
    page = 0
    while True:
        result = browse_company_catalog(connection, page_size, page)
        if result is None:
            return
        selected, page = result
        company_menu(connection, selected, page_size)


def browser_view_notice() -> str:
    """One line pointing to the browser diagram (src/backend/server.py), which runs separately."""
    import urllib.request

    values: dict[str, str] = {}
    config_path = Path(__file__).resolve().parents[1] / ".env"
    if config_path.is_file():
        for line in config_path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.startswith("WEB_"):
                values[key.strip()] = value.strip().strip("\"'")
    host = os.environ.get("WEB_HOST", values.get("WEB_HOST", "127.0.0.1"))
    port = os.environ.get("WEB_PORT", values.get("WEB_PORT", "8765"))
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = os.environ.get("WEB_PUBLIC_URL", values.get("WEB_PUBLIC_URL", f"http://{probe_host}:{port}"))
    try:  # only the diagram's own health check counts, not any program on that port
        with urllib.request.urlopen(f"http://{probe_host}:{int(port)}/api/health", timeout=0.5) as response:
            running = json.load(response).get("status") == "ok"
    except (OSError, ValueError):
        running = False
    if running:
        return f"Browser view (company diagram) is running: {url}"
    return f"Browser view (company diagram) is also supported: start it with `python src/backend/server.py`, then open {url}"


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        import mysql.connector
    except ImportError:
        print("MySQL connector is missing. Run scripts/setup_database.sh first.", file=sys.stderr)
        return 1

    config = load_database_config()
    try:
        connection = mysql.connector.connect(
            host=config["host"],
            port=int(config["port"]),
            user=config["user"],
            password=config["password"],
            database=config["database"],
            autocommit=True,
        )
    except Exception as exc:
        print(f"Cannot connect to the database: {exc}", file=sys.stderr)
        print("Run scripts/setup_database.sh to set it up, or check .env.", file=sys.stderr)
        return 1

    print(browser_view_notice())
    try:
        if args.query:
            run_search(connection, args.page_size, args.query)
        else:
            while True:
                print("\n=== STOCK: LISTED COMPANIES ===")
                print("1. Search companies")
                print("2. Browse the company list")
                print("3. Enter / update data (manual / CSV)")
                print("4. Stock screening & early warnings")
                print("q. Quit")
                try:
                    choice = input("> ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if choice in {"q", "quit", "exit"}:
                    break
                if choice == "1":
                    run_search(connection, args.page_size)
                elif choice == "2":
                    run_company_catalog(connection, args.page_size)
                elif choice == "3":
                    run_data_entry(connection)
                elif choice == "4":
                    run_screening(connection, args.page_size)
                else:
                    print("Invalid choice.")
    except Exception as exc:
        print(f"Database query failed: {exc}", file=sys.stderr)
        connection.close()
        return 1

    connection.close()
    print("Goodbye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())