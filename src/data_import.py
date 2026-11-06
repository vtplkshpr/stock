"""Merge manually entered or CSV data into the stock tables, cell by cell.

Each record is matched by its key columns. A non-empty value overwrites the
stored cell (or fills it on a new record); an empty or missing value leaves the
stored cell untouched. Companies are referenced by ticker, never by id.
"""

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class Category:
    table: str
    label: str
    keys: tuple[str, ...]
    values: tuple[str, ...]
    required: tuple[str, ...] = ()
    nullable_keys: tuple[str, ...] = ()

    @property
    def columns(self) -> tuple[str, ...]:
        return self.keys + self.values


CATEGORIES = {
    category.table: category
    for category in (
        Category(
            "companies",
            "Basic information",
            ("ticker",),
            (
                "company_name", "exchange", "industry", "tax_code", "charter_capital",
                "listed_shares", "outstanding_shares", "initial_listed_shares",
                "first_trading_date", "established_date", "listed_date",
                "company_history", "headquarters_addresses", "phone_numbers", "fax",
                "email", "website", "description", "fiscal_year_start_month",
                "business_registration_amendment", "business_registration_date",
                "listing_license",
            ),
            required=("company_name",),
        ),
        Category(
            "stock_prices",
            "Share prices",
            ("ticker", "price_date"),
            (
                "open_price", "high_price", "low_price", "close_price",
                "adjusted_close", "price_change", "change_percentage", "trading_volume",
                "trading_value", "negotiated_volume", "negotiated_value",
            ),
            required=("close_price",),
        ),
        Category(
            "foreign_trades",
            "Foreign investor trading",
            ("ticker", "trade_date"),
            (
                "buy_volume", "buy_value", "sell_volume", "sell_value", "net_volume",
                "net_value", "room_remaining", "ownership_percentage", "source_url",
            ),
        ),
        Category(
            "proprietary_trades",
            "Proprietary trading",
            ("ticker", "trade_date"),
            (
                "buy_volume", "buy_value", "sell_volume", "sell_value", "net_volume",
                "net_value", "source_url",
            ),
        ),
        Category(
            "order_statistics",
            "Order statistics",
            ("ticker", "trade_date"),
            (
                "buy_orders", "buy_volume", "avg_buy_order_volume", "sell_orders",
                "sell_volume", "avg_sell_order_volume", "net_volume", "source_url",
            ),
        ),
        Category(
            "intraday_trades",
            "Intraday matched trades",
            ("ticker", "trade_date", "seq"),
            (
                "trade_time", "price", "price_change", "lot_volume", "cumulative_volume",
                "weight_percentage", "source_url",
            ),
            required=("trade_time",),
        ),
        Category(
            "insider_trades",
            "Insider & major shareholder trades",
            ("ticker", "trader_name", "registration_start"),
            (
                "trader_position", "related_person_name", "related_person_position",
                "shares_before", "registered_buy", "registered_sell", "registration_end",
                "executed_buy", "executed_sell", "execution_date", "shares_after",
                "ownership_after_percentage", "source_url",
            ),
        ),
        Category(
            "stock_holders",
            "Shareholders",
            ("ticker", "holder_name", "snapshot_date"),
            ("holder_type", "shares_owned", "ownership_percentage", "source_url"),
        ),
        Category(
            "finance_reports",
            "Financial reports",
            ("ticker", "report_type", "report_scope", "fiscal_year", "fiscal_quarter"),
            (
                "period_start", "period_end", "audit_status", "auditor", "audit_opinion",
                "audit_report_date", "currency",
                "revenue", "net_revenue", "cost_of_goods_sold", "gross_profit",
                "financial_income", "financial_expense", "interest_expense",
                "selling_expense", "admin_expense", "operating_profit", "other_profit",
                "profit_before_tax", "income_tax_expense", "net_income",
                "net_income_parent", "earnings_per_share", "cash_and_equivalents",
                "short_term_investments", "short_term_receivables", "inventory",
                "current_assets", "total_assets", "current_liabilities",
                "total_liabilities", "short_term_debt", "long_term_debt",
                "share_capital", "equity", "operating_cash_flow", "investing_cash_flow",
                "financing_cash_flow", "employee_count", "other_metrics",
                "document_storage_path", "published_at", "source_url",
            ),
            nullable_keys=("report_scope", "fiscal_quarter"),
        ),
        Category(
            "finance_report_items",
            "Financial statement lines",
            (
                "ticker", "report_type", "report_scope", "fiscal_year", "fiscal_quarter",
                "statement", "item_code",
            ),
            ("item_name", "value", "comparative_value", "ytd_value", "ytd_comparative_value"),
            nullable_keys=("report_scope", "fiscal_quarter"),
        ),
        Category(
            "supply_chain_relations",
            "Supply chain",
            ("supplier_ticker", "customer_ticker", "product_category"),
            ("percentage_revenue", "source_url"),
        ),
        Category(
            "company_news",
            "News",
            ("ticker", "title"),
            (
                "content_text", "media_type", "media_url", "storage_path",
                "published_at", "source_name", "source_url",
            ),
        ),
        Category(
            "company_leaders",
            "Leadership",
            ("ticker", "person_name", "position"),
            (
                "leader_group", "birth_year", "appointed_date", "dismissed_date",
                "status", "is_legal_representative", "source_url",
            ),
        ),
        Category(
            "company_investments",
            "Subsidiaries, associates & investments",
            ("ticker", "investee_name"),
            (
                "investee_ticker", "relation_type", "is_direct", "shares_owned",
                "ownership_percentage", "voting_percentage", "investment_cost",
                "charter_capital", "contributed_capital", "business_line",
                "operating_status", "as_of_date", "note", "source_url",
            ),
            required=("relation_type",),
        ),
        Category(
            "related_party_transactions",
            "Related-party transactions",
            (
                "ticker", "report_scope", "counterparty_name", "transaction_type", "description",
                "period_start", "period_end",
            ),
            (
                "counterparty_ticker", "relationship", "amount",
                "currency", "document_storage_path", "source_url",
            ),
            nullable_keys=("report_scope", "description"),
        ),
        Category(
            "company_tiers",
            "Tiers",
            ("ticker", "tier_name"),
            ("tier_description",),
        ),
    )
}

# Categories that feed the computed financial_metrics / valuation_metrics tables (see metrics.py).
METRIC_SOURCES = {"finance_reports", "finance_report_items", "stock_prices"}

# CSV ticker columns and the company id column each one resolves to.
COMPANY_REFS = {
    "ticker": "company_id",
    "supplier_ticker": "supplier_id",
    "customer_ticker": "customer_id",
}
DATE_COLUMNS = {
    "price_date", "snapshot_date", "published_at", "first_trading_date", "as_of_date",
    "established_date", "listed_date", "period_start", "period_end", "appointed_date",
    "dismissed_date", "business_registration_date", "audit_report_date", "trade_date",
    "registration_start", "registration_end", "execution_date",
}
JSON_COLUMNS = {"headquarters_addresses", "phone_numbers", "other_metrics"}
DMY_PATTERN = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})(.*)")


@dataclass
class ImportStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def enum_choices(cursor: Any, table: str) -> dict[str, tuple[str, ...]]:
    """Return the allowed values of each ENUM column in table, read from the schema."""
    cursor.execute(
        """SELECT column_name, column_type FROM information_schema.columns
           WHERE table_schema = DATABASE() AND table_name = %s AND data_type = 'enum'""",
        (table,),
    )
    choices = {}
    for name, column_type in cursor.fetchall():
        if isinstance(column_type, bytes):
            column_type = column_type.decode()
        choices[name] = tuple(re.findall(r"'([^']*)'", column_type))
    return choices


def normalize_value(column: str, value: str) -> str:
    if column in COMPANY_REFS or column in ("investee_ticker", "counterparty_ticker"):
        return value.upper()
    if column in DATE_COLUMNS:
        match = DMY_PATTERN.fullmatch(value)
        if match:
            day, month, year, rest = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}{rest}"
    if column in JSON_COLUMNS:
        try:
            return json.dumps(json.loads(value), ensure_ascii=False)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{column} must be valid JSON.") from exc
    return value


def normalize_row(
    category: Category,
    raw: Mapping[str, Any],
    default_ticker: str | None,
    choices: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, str]:
    row = {}
    for column in category.columns:
        value = str(raw.get(column) or "").strip()
        if not value:
            continue
        if choices and column in choices:
            value = value.lower()
            if value not in choices[column]:
                raise ValueError(f"{column} must be one of: {', '.join(choices[column])}")
        row[column] = normalize_value(column, value)

    # A row may omit its single missing company reference when one company is selected.
    missing_refs = [c for c in category.keys if c in COMPANY_REFS and c not in row]
    if default_ticker and len(missing_refs) == 1:
        row[missing_refs[0]] = default_ticker.upper()

    missing_keys = [
        c for c in category.keys if c not in row and c not in category.nullable_keys
    ]
    if missing_keys:
        raise ValueError(f"missing key values: {', '.join(missing_keys)}")
    return row


def company_id_for(cursor: Any, ticker: str) -> int:
    cursor.execute("SELECT company_id FROM companies WHERE ticker = %s", (ticker,))
    found = cursor.fetchone()
    if found is None:
        raise ValueError(f"ticker {ticker} is not in the companies table")
    return found[0]


def key_filter(cursor: Any, category: Category, row: Mapping[str, str]) -> dict[str, Any]:
    keys = {}
    for column in category.keys:
        if column in COMPANY_REFS and category.table != "companies":
            keys[COMPANY_REFS[column]] = company_id_for(cursor, row[column])
        else:
            keys[column] = row.get(column)
    return keys


def fetch_existing(
    cursor: Any, category: Category, row: Mapping[str, str]
) -> dict[str, Any] | None:
    """Return the stored values of the record matching row's keys, if any."""
    if category.table == "company_tiers":
        return None
    keys = key_filter(cursor, category, row)
    where = " AND ".join(f"`{column}` <=> %s" for column in keys)
    columns = ", ".join(f"`{column}`" for column in category.values)
    cursor.execute(
        f"SELECT {columns} FROM `{category.table}` WHERE {where} LIMIT 1",
        tuple(keys.values()),
    )
    found = cursor.fetchone()
    return dict(zip(category.values, found)) if found else None


def merge_company_tier(cursor: Any, row: Mapping[str, str]) -> str:
    company_id = company_id_for(cursor, row["ticker"])
    description = row.get("tier_description")
    tier_changed = False
    cursor.execute(
        "SELECT tier_id FROM tiers WHERE tier_name = %s", (row["tier_name"],)
    )
    found = cursor.fetchone()
    if found is None:
        cursor.execute(
            "INSERT INTO tiers (tier_name, description) VALUES (%s, %s)",
            (row["tier_name"], description),
        )
        tier_id = cursor.lastrowid
        tier_changed = True
    else:
        tier_id = found[0]
        if description:
            cursor.execute(
                "UPDATE tiers SET description = %s WHERE tier_id = %s",
                (description, tier_id),
            )
            tier_changed = cursor.rowcount > 0

    cursor.execute(
        "INSERT IGNORE INTO company_tiers (company_id, tier_id) VALUES (%s, %s)",
        (company_id, tier_id),
    )
    if cursor.rowcount:
        return "inserted"
    return "updated" if tier_changed else "unchanged"


def merge_row(cursor: Any, category: Category, row: Mapping[str, str]) -> str:
    """Apply one normalized row; return 'inserted', 'updated' or 'unchanged'."""
    if category.table == "company_tiers":
        return merge_company_tier(cursor, row)

    keys = key_filter(cursor, category, row)
    values = {column: row[column] for column in category.values if column in row}
    where = " AND ".join(f"`{column}` <=> %s" for column in keys)
    cursor.execute(
        f"SELECT COUNT(*) FROM `{category.table}` WHERE {where}", tuple(keys.values())
    )
    if cursor.fetchone()[0]:
        if not values:
            return "unchanged"
        assignments = ", ".join(f"`{column}` = %s" for column in values)
        cursor.execute(
            f"UPDATE `{category.table}` SET {assignments} WHERE {where}",
            (*values.values(), *keys.values()),
        )
        return "updated" if cursor.rowcount else "unchanged"

    missing = [column for column in category.required if column not in values]
    if missing:
        raise ValueError(f"new record lacks required values: {', '.join(missing)}")
    data = {**keys, **values}
    columns = ", ".join(f"`{column}`" for column in data)
    placeholders = ", ".join("%s" for _ in data)
    cursor.execute(
        f"INSERT INTO `{category.table}` ({columns}) VALUES ({placeholders})",
        tuple(data.values()),
    )
    return "inserted"


def merge_rows(
    connection: Any,
    category: Category,
    rows: Iterable[tuple[str, Mapping[str, Any]]],
    tickers: Sequence[str] | None,
) -> ImportStats:
    """Merge (location, row) pairs; tickers limits rows to those companies (None = all).

    Changes are left uncommitted so the caller can commit or roll back.
    """
    stats = ImportStats()
    selected = {ticker.upper() for ticker in tickers} if tickers else None
    default_ticker = tickers[0] if tickers and len(tickers) == 1 else None
    if not connection.in_transaction:
        connection.start_transaction()
    cursor = connection.cursor()
    try:
        choices = enum_choices(cursor, category.table)
        for location, raw in rows:
            try:
                row = normalize_row(category, raw, default_ticker, choices)
                refs = {row[c] for c in category.keys if c in COMPANY_REFS}
                if selected is not None and not refs & selected:
                    stats.skipped += 1
                    continue
                outcome = merge_row(cursor, category, row)
            except Exception as exc:
                stats.errors.append(f"{location}: {exc}")
                continue
            setattr(stats, outcome, getattr(stats, outcome) + 1)
    finally:
        cursor.close()
    return stats


def read_csv(path: Path) -> tuple[list[str], list[tuple[str, dict[str, str]]]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        header = [(name or "").strip().lower() for name in reader.fieldnames or ()]
        reader.fieldnames = header
        rows = [(f"{path.name}:{reader.line_num}", row) for row in reader]
    return header, rows


def import_files(
    connection: Any, files: Mapping[str, Path], tickers: Sequence[str] | None
) -> dict[str, ImportStats]:
    """Merge one CSV per category; the caller commits only if no stats have errors."""
    results = {}
    for table, path in files.items():
        category = CATEGORIES[table]
        try:
            header, rows = read_csv(path)
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            results[table] = ImportStats(errors=[f"{path}: {exc}"])
            continue

        unknown = [column for column in header if column not in category.columns]
        if unknown and len(unknown) == len(header):
            results[table] = ImportStats(errors=[
                f"{path.name}: the first row must hold the column names, e.g. "
                f"{','.join(category.columns)}"
            ])
            continue
        if unknown:
            results[table] = ImportStats(errors=[
                f"{path.name}: unknown columns {', '.join(unknown)}. "
                f"Supported columns: {', '.join(category.columns)}"
            ])
            continue
        results[table] = merge_rows(connection, category, rows, tickers)
    return results


def export_rows(cursor: Any, category: Category) -> list[list[str]]:
    """Read a category back out in its CSV layout, oldest record first."""
    if category.table == "company_tiers":
        cursor.execute(
            """SELECT company.ticker, tier.tier_name, tier.description
               FROM company_tiers AS link
               JOIN companies AS company ON company.company_id = link.company_id
               JOIN tiers AS tier ON tier.tier_id = link.tier_id
               ORDER BY link.id"""
        )
    else:
        selects, joins = [], []
        for column in category.columns:
            if column in COMPANY_REFS and category.table != "companies":
                alias = f"ref{len(joins)}"
                joins.append(
                    f"JOIN companies AS {alias} "
                    f"ON {alias}.company_id = t.`{COMPANY_REFS[column]}`"
                )
                selects.append(f"{alias}.ticker")
            else:
                selects.append(f"t.`{column}`")
        cursor.execute(f"SHOW KEYS FROM `{category.table}` WHERE Key_name = 'PRIMARY'")
        order = ", ".join(f"t.`{key[4]}`" for key in cursor.fetchall())
        cursor.execute(
            f"SELECT {', '.join(selects)} FROM `{category.table}` AS t "
            f"{' '.join(joins)} ORDER BY {order}"
        )

    rows = []
    for record in cursor.fetchall():
        rows.append([
            "" if value is None
            else value.decode() if isinstance(value, bytes)
            else str(value)
            for value in record
        ])
    return rows


def export_backup(connection: Any, directory: Path) -> dict[str, int]:
    """Write every category as <table>.csv plus manifest.json; return row counts."""
    directory.mkdir(parents=True, exist_ok=True)
    counts = {}
    cursor = connection.cursor()
    try:
        for category in CATEGORIES.values():
            rows = export_rows(cursor, category)
            with (directory / f"{category.table}.csv").open(
                "w", encoding="utf-8", newline=""
            ) as destination:
                writer = csv.writer(destination)
                writer.writerow(category.columns)
                writer.writerows(rows)
            counts[category.table] = len(rows)
    finally:
        cursor.close()

    manifest = {"created_at": date.today().isoformat(), "row_counts": counts}
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return counts


def backup_files(directory: Path) -> dict[str, Path]:
    """Map each category to its CSV in a backup folder, in import order."""
    return {
        table: directory / f"{table}.csv"
        for table in CATEGORIES
        if (directory / f"{table}.csv").is_file()
    }


def format_report(results: Mapping[str, ImportStats], max_errors: int = 20) -> str:
    lines = []
    for table, stats in results.items():
        lines.append(
            f"- {CATEGORIES[table].label} ({table}): inserted {stats.inserted}, "
            f"updated {stats.updated}, unchanged {stats.unchanged}, "
            f"skipped (other tickers) {stats.skipped}, errors {len(stats.errors)}"
        )
        lines.extend(f"    ! {error}" for error in stats.errors[:max_errors])
        if len(stats.errors) > max_errors:
            lines.append(f"    ! ... and {len(stats.errors) - max_errors} more errors")
    return "\n".join(lines)


def parse_tickers(text: str) -> list[str] | None:
    """Parse 'HPG, VNM'; '*' or blank means every ticker in the data."""
    tickers = [part.strip().upper() for part in text.replace(";", ",").split(",")]
    tickers = [ticker for ticker in tickers if ticker]
    return None if not tickers or tickers == ["*"] else tickers


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge CSV data into the stock database, cell by cell.",
        epilog="Categories: " + ", ".join(CATEGORIES),
    )
    parser.add_argument(
        "files", nargs="*", metavar="CATEGORY=FILE.csv",
        help="One or more category=path.csv pairs.",
    )
    parser.add_argument(
        "--tickers", default="*",
        help="Comma-separated tickers to apply (default *: every ticker in the files).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run without saving.")
    parser.add_argument(
        "--list", action="store_true", help="List the categories and their CSV columns."
    )
    parser.add_argument(
        "--export", type=Path, metavar="DIR",
        help="Export all data to a backup folder (one CSV per category).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list or not (args.files or args.export):
        for category in CATEGORIES.values():
            print(f"{category.table} ({category.label}): {','.join(category.columns)}")
        return 0

    files = {}
    for item in args.files:
        table, separator, path = item.partition("=")
        if not separator or table not in CATEGORIES:
            print(f"Invalid argument: {item}", file=sys.stderr)
            return 2
        files[table] = Path(path).expanduser()

    try:
        from . import stock_cli
    except ImportError:
        import stock_cli
    import mysql.connector

    config = stock_cli.load_database_config()
    config["port"] = int(config["port"])
    connection = mysql.connector.connect(**config)
    if args.export:
        try:
            counts = export_backup(connection, args.export.expanduser())
        finally:
            connection.close()
        for table, count in counts.items():
            print(f"- {CATEGORIES[table].label} ({table}): {count} rows")
        print(f"Backup exported to {args.export}")
        return 0
    try:
        results = import_files(connection, files, parse_tickers(args.tickers))
        print(format_report(results))
        if any(stats.errors for stats in results.values()):
            connection.rollback()
            print("Errors found; nothing was saved.", file=sys.stderr)
            return 1
        if METRIC_SOURCES & set(files):
            try:
                from . import metrics
            except ImportError:
                import metrics
            print("Recomputing financial metrics:")
            print(metrics.format_summary(metrics.recompute(connection, parse_tickers(args.tickers))))
        if args.dry_run:
            connection.rollback()
            print("Dry run: nothing was saved.")
        else:
            connection.commit()
            print("Changes saved.")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
