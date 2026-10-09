"""Initialize the MySQL schema used by the stock module."""

import argparse
import os
import re
import sys
from typing import Any


TABLES = (
    """
    CREATE TABLE IF NOT EXISTS companies (
        company_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        ticker VARCHAR(16) NOT NULL,
        company_name VARCHAR(255) NOT NULL,
        exchange VARCHAR(32) NULL,
        industry VARCHAR(128) NULL,
        tax_code VARCHAR(32) NULL,
        website VARCHAR(512) NULL,
        description TEXT NULL,
        established_date DATE NULL,
        listed_date DATE NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (company_id),
        UNIQUE KEY uq_companies_ticker (ticker),
        KEY ix_companies_name (company_name),
        KEY ix_companies_exchange (exchange)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS tiers (
        tier_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        tier_name VARCHAR(100) NOT NULL,
        description TEXT NULL,
        PRIMARY KEY (tier_id),
        UNIQUE KEY uq_tiers_name (tier_name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS stock_holders (
        holder_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        company_id BIGINT UNSIGNED NOT NULL,
        holder_name VARCHAR(255) NOT NULL,
        holder_type VARCHAR(64) NULL,
        shares_owned DECIMAL(24, 4) NULL,
        ownership_percentage DECIMAL(9, 6) NULL,
        snapshot_date DATE NOT NULL,
        source_url VARCHAR(1024) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (holder_id),
        KEY ix_stock_holders_company_date (company_id, snapshot_date),
        CONSTRAINT fk_stock_holders_company FOREIGN KEY (company_id)
            REFERENCES companies (company_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS stock_prices (
        company_id BIGINT UNSIGNED NOT NULL,
        price_date DATE NOT NULL,
        open_price DECIMAL(20, 4) NULL,
        high_price DECIMAL(20, 4) NULL,
        low_price DECIMAL(20, 4) NULL,
        close_price DECIMAL(20, 4) NOT NULL,
        adjusted_close DECIMAL(20, 4) NULL,
        trading_volume BIGINT UNSIGNED NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (company_id, price_date),
        KEY ix_stock_prices_date (price_date),
        CONSTRAINT fk_stock_prices_company FOREIGN KEY (company_id)
            REFERENCES companies (company_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS finance_reports (
        report_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        company_id BIGINT UNSIGNED NOT NULL,
        report_type VARCHAR(64) NOT NULL,
        fiscal_year SMALLINT UNSIGNED NOT NULL,
        fiscal_quarter TINYINT UNSIGNED NULL,
        currency CHAR(3) NOT NULL DEFAULT 'VND',
        revenue DECIMAL(24, 4) NULL,
        gross_profit DECIMAL(24, 4) NULL,
        operating_profit DECIMAL(24, 4) NULL,
        net_income DECIMAL(24, 4) NULL,
        total_assets DECIMAL(24, 4) NULL,
        total_liabilities DECIMAL(24, 4) NULL,
        equity DECIMAL(24, 4) NULL,
        operating_cash_flow DECIMAL(24, 4) NULL,
        earnings_per_share DECIMAL(20, 4) NULL,
        other_metrics JSON NULL,
        document_storage_path VARCHAR(1024) NULL,
        published_at DATE NULL,
        source_url VARCHAR(1024) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (report_id),
        KEY ix_finance_reports_company_period (company_id, fiscal_year, fiscal_quarter),
        CONSTRAINT fk_finance_reports_company FOREIGN KEY (company_id)
            REFERENCES companies (company_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS company_tiers (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        company_id BIGINT UNSIGNED NOT NULL,
        tier_id BIGINT UNSIGNED NOT NULL,
        assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uq_company_tiers_pair (company_id, tier_id),
        CONSTRAINT fk_company_tiers_company FOREIGN KEY (company_id)
            REFERENCES companies (company_id) ON DELETE CASCADE,
        CONSTRAINT fk_company_tiers_tier FOREIGN KEY (tier_id)
            REFERENCES tiers (tier_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS supply_chain_relations (
        relation_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        supplier_id BIGINT UNSIGNED NOT NULL,
        customer_id BIGINT UNSIGNED NOT NULL,
        product_category VARCHAR(255) NOT NULL,
        percentage_revenue DECIMAL(9, 6) NULL,
        source_url VARCHAR(1024) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (relation_id),
        KEY ix_supply_chain_supplier (supplier_id),
        KEY ix_supply_chain_customer (customer_id),
        CONSTRAINT fk_supply_chain_supplier FOREIGN KEY (supplier_id)
            REFERENCES companies (company_id) ON DELETE CASCADE,
        CONSTRAINT fk_supply_chain_customer FOREIGN KEY (customer_id)
            REFERENCES companies (company_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS company_news (
        news_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        company_id BIGINT UNSIGNED NOT NULL,
        title VARCHAR(512) NOT NULL,
        content_text LONGTEXT NULL,
        media_type ENUM('text', 'video', 'audio', 'image', 'document', 'other')
            NOT NULL DEFAULT 'text',
        media_url VARCHAR(1024) NULL,
        storage_path VARCHAR(1024) NULL,
        published_at DATETIME NULL,
        source_name VARCHAR(255) NULL,
        source_url VARCHAR(1024) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (news_id),
        KEY ix_company_news_company_date (company_id, published_at),
        KEY ix_company_news_media_type (media_type),
        CONSTRAINT fk_company_news_company FOREIGN KEY (company_id)
            REFERENCES companies (company_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the stock module MySQL schema.")
    parser.add_argument("--host", default=os.getenv("MYSQL_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    parser.add_argument("--user", default=os.getenv("MYSQL_USER", "root"))
    parser.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "stock_market"))
    parser.add_argument(
        "--skip-create-database",
        action="store_true",
        help="Do not create the database; connect to an existing database instead.",
    )
    return parser.parse_args()


def validate_database_name(database: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", database):
        raise ValueError("Database name may contain only letters, digits, and underscores.")
    return database


def initialize_database(config: argparse.Namespace) -> None:
    try:
        import mysql.connector
    except ImportError as exc:
        raise RuntimeError(
            "Missing MySQL driver. Install it with: pip install mysql-connector-python"
        ) from exc

    database = validate_database_name(config.database)
    connection_options: dict[str, Any] = {
        "host": config.host,
        "port": config.port,
        "user": config.user,
        "password": config.password,
        "charset": "utf8mb4",
    }

    if not config.skip_create_database:
        with mysql.connector.connect(**connection_options) as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )

    with mysql.connector.connect(database=database, **connection_options) as connection:
        cursor = connection.cursor()
        for statement in TABLES:
            cursor.execute(statement)
        connection.commit()


def main() -> int:
    config = parse_args()
    try:
        initialize_database(config)
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Database initialization failed: {exc}", file=sys.stderr)
        return 1

    print(f"MySQL schema initialized successfully in database '{config.database}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())