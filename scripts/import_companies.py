"""Prepare table-specific CSV files and import their rows into MySQL."""

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any


MODULE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = MODULE_DIR / "raw_data"
DEFAULT_OUTPUT_DIR = MODULE_DIR / "processed_data"
TABLE_FIELDS = {
    "companies": (
        "ticker", "company_name", "exchange", "industry", "tax_code",
        "charter_capital", "listed_shares", "outstanding_shares",
        "initial_listed_shares", "first_trading_date", "company_history",
        "headquarters_addresses", "phone_numbers", "fax", "email", "website",
        "description", "established_date", "listed_date",
    ),
    "tiers": ("tier_name", "description"),
    "stock_holders": (
        "company_id", "holder_name", "holder_type", "shares_owned",
        "ownership_percentage", "snapshot_date", "source_url",
    ),
    "stock_prices": (
        "company_id", "price_date", "open_price", "high_price", "low_price",
        "close_price", "adjusted_close", "trading_volume",
    ),
    "finance_reports": (
        "company_id", "report_type", "fiscal_year", "fiscal_quarter", "currency",
        "revenue", "gross_profit", "operating_profit", "net_income", "total_assets",
        "total_liabilities", "equity", "operating_cash_flow", "earnings_per_share",
        "other_metrics", "document_storage_path", "published_at", "source_url",
    ),
    "company_tiers": ("company_id", "tier_id"),
    "supply_chain_relations": (
        "supplier_id", "customer_id", "product_category", "percentage_revenue",
        "source_url",
    ),
    "company_news": (
        "company_id", "title", "content_text", "media_type", "media_url",
        "storage_path", "published_at", "source_name", "source_url",
    ),
}
REQUIRED_FIELDS = {
    "companies": {"ticker", "company_name"},
    "tiers": {"tier_name"},
    "stock_holders": {"company_id", "holder_name", "snapshot_date"},
    "stock_prices": {"company_id", "price_date", "close_price"},
    "finance_reports": {"company_id", "report_type", "fiscal_year"},
    "company_tiers": {"company_id", "tier_id"},
    "supply_chain_relations": {"supplier_id", "customer_id", "product_category"},
    "company_news": {"company_id", "title"},
}


def clean(value: str | None) -> str:
    return (value or "").strip()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def parse_reported_volume(value: str) -> str:
    normalized = clean(value).replace(",", "").replace(" ", "")
    if not normalized or normalized == "-":
        return ""
    if not normalized.isdigit():
        raise ValueError(f"Invalid reported volume: {value!r}")
    return str(int(normalized))


def prepare_csv(output_dir: Path) -> int:
    market_rows = read_rows(RAW_DIR / "24hmoney.csv")
    disclosure_rows = read_rows(RAW_DIR / "congbothongtin.csv")

    market_by_ticker = {
        clean(row.get("Code")).upper(): row
        for row in market_rows
        if clean(row.get("Code"))
    }
    disclosure_by_ticker = {
        clean(row.get("Mã chứng khoán3")).upper(): row
        for row in disclosure_rows
        if clean(row.get("Mã chứng khoán3"))
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    companies_path = output_dir / "companies.csv"
    with companies_path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=TABLE_FIELDS["companies"])
        writer.writeheader()
        for ticker in sorted(market_by_ticker.keys() | disclosure_by_ticker.keys()):
            market = market_by_ticker.get(ticker, {})
            disclosure = disclosure_by_ticker.get(ticker, {})
            industry_url = clean(market.get("company-info href 2"))
            if "/recommend/business/" not in industry_url:
                industry_url = ""

            metadata = {
                key: value
                for key, value in {
                    "profile_url": clean(market.get("company info")),
                    "industry_url": industry_url,
                    "reported_volume": parse_reported_volume(
                        clean(market.get("volumes"))
                    ),
                    "disclosure_company_name": clean(disclosure.get("company name")),
                }.items()
                if value
            }
            writer.writerow({
                "ticker": ticker,
                "company_name": clean(market.get("company name"))
                or clean(disclosure.get("company name")),
                "exchange": clean(market.get("Market place"))
                or clean(disclosure.get("Sàn niêm yết")),
                "industry": clean(market.get("company fields"))
                if clean(market.get("company fields")) != "-"
                else "",
                "tax_code": clean(disclosure.get("Mã số doanh nghiệp")),
                "charter_capital": "",
                "listed_shares": "",
                "outstanding_shares": "",
                "initial_listed_shares": "",
                "first_trading_date": "",
                "company_history": "",
                "headquarters_addresses": "",
                "phone_numbers": "",
                "fax": "",
                "email": "",
                "website": "",
                "description": json.dumps(metadata, ensure_ascii=False) if metadata else "",
                "established_date": "",
                "listed_date": "",
            })

    for table_name, fields in TABLE_FIELDS.items():
        if table_name == "companies":
            continue
        with (output_dir / f"{table_name}.csv").open(
            "w", encoding="utf-8", newline=""
        ) as destination:
            csv.writer(destination).writerow(fields)

    return len(market_by_ticker.keys() | disclosure_by_ticker.keys())


def load_database_config() -> dict[str, Any]:
    env_path = MODULE_DIR / ".env"
    file_config: dict[str, str] = {}
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.startswith("MYSQL_"):
                file_config[key] = value.strip().strip("\"'")

    return {
        "host": os.environ.get("MYSQL_HOST", file_config.get("MYSQL_HOST", "localhost")),
        "port": int(os.environ.get("MYSQL_PORT", file_config.get("MYSQL_PORT", "3306"))),
        "user": os.environ.get("MYSQL_USER", file_config.get("MYSQL_USER", "stock_app")),
        "password": os.environ.get(
            "MYSQL_PASSWORD", file_config.get("MYSQL_PASSWORD", "")
        ),
        "database": os.environ.get(
            "MYSQL_DATABASE", file_config.get("MYSQL_DATABASE", "stock_market")
        ),
        "charset": "utf8mb4",
    }


def import_csv(input_dir: Path) -> dict[str, int]:
    try:
        import mysql.connector
    except ImportError as exc:
        raise RuntimeError(
            "Missing MySQL driver. Install it with: "
            "pip install mysql-connector-python"
        ) from exc

    batch: dict[str, tuple[tuple[str, ...], list[tuple[str | None, ...]]]] = {}
    for table_name, columns in TABLE_FIELDS.items():
        path = input_dir / f"{table_name}.csv"
        if not path.is_file():
            raise ValueError(f"Missing CSV for table '{table_name}': {path}")
        with path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if tuple(reader.fieldnames or ()) != columns:
                raise ValueError(
                    f"CSV header does not match table '{table_name}': {path}"
                )
            rows = list(reader)
        if not rows:
            continue

        values: list[tuple[str | None, ...]] = []
        for row_number, row in enumerate(rows, start=2):
            normalized = {column: clean(row.get(column)) for column in columns}
            missing = [
                column for column in REQUIRED_FIELDS[table_name]
                if not normalized[column]
            ]
            if missing:
                raise ValueError(
                    f"{path}:{row_number} missing required values: {', '.join(missing)}"
                )
            if table_name == "companies":
                normalized["ticker"] = normalized["ticker"].upper()
                for json_column in ("headquarters_addresses", "phone_numbers"):
                    if normalized[json_column]:
                        try:
                            json_value = json.loads(normalized[json_column])
                        except json.JSONDecodeError as exc:
                            raise ValueError(
                                f"{path}:{row_number} {json_column} must contain JSON."
                            ) from exc
                        if not isinstance(json_value, list) or any(
                            not isinstance(item, list)
                            or len(item) != 2
                            or not all(isinstance(part, str) for part in item)
                            for item in json_value
                        ):
                            raise ValueError(
                                f"{path}:{row_number} {json_column} must be an array "
                                "of two-string arrays."
                            )
                        normalized[json_column] = json.dumps(
                            json_value, ensure_ascii=False
                        )
            values.append(tuple(normalized[column] or None for column in columns))
        batch[table_name] = (columns, values)

    if not batch:
        print("No data rows found in table CSV files.")
        return {}

    statements = {}
    for table_name, columns in TABLE_FIELDS.items():
        column_list = ", ".join(f"`{column}`" for column in columns)
        placeholders = ", ".join("%s" for _ in columns)
        statement = (
            f"INSERT INTO `{table_name}` ({column_list}) "
            f"VALUES ({placeholders})"
        )
        if table_name == "companies":
            statement += """
                ON DUPLICATE KEY UPDATE
                    company_name = VALUES(company_name),
                    exchange = COALESCE(VALUES(exchange), exchange),
                    industry = COALESCE(VALUES(industry), industry),
                    tax_code = COALESCE(VALUES(tax_code), tax_code),
                    website = COALESCE(VALUES(website), website),
                    description = COALESCE(NULLIF(description, ''), VALUES(description)),
                    established_date = COALESCE(VALUES(established_date), established_date),
                        listed_date = COALESCE(VALUES(listed_date), listed_date),
                        charter_capital = COALESCE(VALUES(charter_capital), charter_capital),
                        listed_shares = COALESCE(VALUES(listed_shares), listed_shares),
                        outstanding_shares = COALESCE(VALUES(outstanding_shares), outstanding_shares),
                        initial_listed_shares = COALESCE(VALUES(initial_listed_shares), initial_listed_shares),
                        first_trading_date = COALESCE(VALUES(first_trading_date), first_trading_date),
                        company_history = COALESCE(VALUES(company_history), company_history),
                        headquarters_addresses = COALESCE(VALUES(headquarters_addresses), headquarters_addresses),
                        phone_numbers = COALESCE(VALUES(phone_numbers), phone_numbers),
                        fax = COALESCE(VALUES(fax), fax),
                        email = COALESCE(VALUES(email), email)
            """
        elif table_name == "tiers":
            statement += " ON DUPLICATE KEY UPDATE description = COALESCE(VALUES(description), description)"
        elif table_name == "stock_prices":
            updates = ", ".join(
                f"`{column}` = COALESCE(VALUES(`{column}`), `{column}`)"
                for column in columns[2:]
            )
            statement += f" ON DUPLICATE KEY UPDATE {updates}"
        elif table_name == "company_tiers":
            statement = statement.replace("INSERT INTO", "INSERT IGNORE INTO", 1)
        statements[table_name] = statement

    connection = mysql.connector.connect(**load_database_config())
    imported: dict[str, int] = {}
    try:
        cursor = connection.cursor()
        for table_name, (columns, values) in batch.items():
            cursor.executemany(statements[table_name], values)
            imported[table_name] = len(values)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return imported


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare table-specific CSVs and/or import them into MySQL."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory containing one CSV per table (default: {DEFAULT_OUTPUT_DIR})",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--prepare",
        action="store_true",
        help="Regenerate all table CSVs, then import their data rows.",
    )
    mode.add_argument(
        "--prepare-only",
        action="store_true",
        help="Regenerate all table CSVs without connecting to MySQL.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.prepare or args.prepare_only:
            count = prepare_csv(args.data_dir)
            print(f"Prepared {count} company rows and table CSVs in {args.data_dir}")
        if args.prepare_only:
            return 0

        imported = import_csv(args.data_dir)
        for table_name, count in imported.items():
            print(f"Imported {count} rows into {table_name}.")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Database import failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())