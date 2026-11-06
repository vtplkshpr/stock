"""Initialize the MySQL schema used by the stock module."""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any


HOLDER_TYPES = (
    "individual",
    "institution",
    "state",
    "foreign_individual",
    "foreign_institution",
    "other",
)
HOLDER_TYPE_DEFINITION = (
    "ENUM(" + ", ".join(f"'{value}'" for value in HOLDER_TYPES) + ") NULL"
)

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
        charter_capital DECIMAL(24, 4) NULL,
        listed_shares BIGINT UNSIGNED NULL,
        outstanding_shares BIGINT UNSIGNED NULL,
        initial_listed_shares BIGINT UNSIGNED NULL,
        first_trading_date DATE NULL,
        company_history LONGTEXT NULL,
        headquarters_addresses JSON NULL,
        phone_numbers JSON NULL,
        fax VARCHAR(64) NULL,
        email VARCHAR(255) NULL,
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
    f"""
    CREATE TABLE IF NOT EXISTS stock_holders (
        holder_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        company_id BIGINT UNSIGNED NOT NULL,
        holder_name VARCHAR(255) NOT NULL,
        holder_type {HOLDER_TYPE_DEFINITION},
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
    """
    CREATE TABLE IF NOT EXISTS company_leaders (
        leader_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        company_id BIGINT UNSIGNED NOT NULL,
        person_name VARCHAR(255) NOT NULL,
        position VARCHAR(255) NOT NULL,
        leader_group ENUM('board', 'management', 'audit_committee', 'other') NULL,
        birth_year SMALLINT UNSIGNED NULL,
        source_url VARCHAR(1024) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (leader_id),
        UNIQUE KEY uq_company_leaders_person_position (company_id, person_name, position),
        CONSTRAINT fk_company_leaders_company FOREIGN KEY (company_id)
            REFERENCES companies (company_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS finance_report_items (
        item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        company_id BIGINT UNSIGNED NOT NULL,
        report_type VARCHAR(64) NOT NULL,
        report_scope ENUM('separate', 'consolidated') NULL,
        fiscal_year SMALLINT UNSIGNED NOT NULL,
        fiscal_quarter TINYINT UNSIGNED NULL,
        statement ENUM('balance_sheet', 'income_statement', 'cash_flow') NOT NULL,
        item_code VARCHAR(8) NOT NULL,
        item_name VARCHAR(255) NULL,
        value DECIMAL(24, 4) NULL,
        comparative_value DECIMAL(24, 4) NULL,
        ytd_value DECIMAL(24, 4) NULL,
        ytd_comparative_value DECIMAL(24, 4) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (item_id),
        KEY ix_finance_report_items_report (company_id, fiscal_year, fiscal_quarter, statement),
        CONSTRAINT fk_finance_report_items_company FOREIGN KEY (company_id)
            REFERENCES companies (company_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS financial_metrics (
        metric_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        company_id BIGINT UNSIGNED NOT NULL,
        report_scope ENUM('separate', 'consolidated') NOT NULL,
        period_type ENUM('quarter', 'year', 'ttm') NOT NULL,
        fiscal_year SMALLINT UNSIGNED NOT NULL,
        fiscal_quarter TINYINT UNSIGNED NOT NULL,
        period_start DATE NULL,
        period_end DATE NOT NULL,
        flow_source ENUM('reported', 'derived', 'mixed') NULL,
        audit_status ENUM('unaudited', 'reviewed', 'audited') NULL,
        available_from DATE NULL,
        source_report_ids VARCHAR(255) NULL,
        revenue DECIMAL(24, 4) NULL,
        gross_profit DECIMAL(24, 4) NULL,
        ebit DECIMAL(24, 4) NULL,
        ebitda DECIMAL(24, 4) NULL,
        net_income DECIMAL(24, 4) NULL,
        net_income_parent DECIMAL(24, 4) NULL,
        cfo DECIMAL(24, 4) NULL,
        cfi DECIMAL(24, 4) NULL,
        cff DECIMAL(24, 4) NULL,
        capex DECIMAL(24, 4) NULL,
        free_cash_flow DECIMAL(24, 4) NULL,
        dividends_paid DECIMAL(24, 4) NULL,
        total_assets DECIMAL(24, 4) NULL,
        equity_parent DECIMAL(24, 4) NULL,
        interest_bearing_debt DECIMAL(24, 4) NULL,
        net_debt DECIMAL(24, 4) NULL,
        cfo_sign TINYINT NULL,
        cfi_sign TINYINT NULL,
        cff_sign TINYINT NULL,
        cash_flow_pattern CHAR(3) NULL,
        lifecycle_stage ENUM('introduction', 'growth', 'mature', 'shake_out', 'decline') NULL,
        gross_margin DECIMAL(18, 6) NULL,
        ebit_margin DECIMAL(18, 6) NULL,
        net_margin DECIMAL(18, 6) NULL,
        roe DECIMAL(18, 6) NULL,
        roa DECIMAL(18, 6) NULL,
        roic DECIMAL(18, 6) NULL,
        cfo_to_net_income DECIMAL(18, 6) NULL,
        accrual_ratio DECIMAL(18, 6) NULL,
        debt_to_equity DECIMAL(18, 6) NULL,
        net_debt_to_ebitda DECIMAL(18, 6) NULL,
        interest_coverage DECIMAL(18, 6) NULL,
        cfo_interest_coverage DECIMAL(18, 6) NULL,
        current_ratio DECIMAL(18, 6) NULL,
        quick_ratio DECIMAL(18, 6) NULL,
        cash_ratio DECIMAL(18, 6) NULL,
        dso DECIMAL(18, 6) NULL,
        dio DECIMAL(18, 6) NULL,
        dpo DECIMAL(18, 6) NULL,
        cash_conversion_cycle DECIMAL(18, 6) NULL,
        asset_turnover DECIMAL(18, 6) NULL,
        revenue_yoy DECIMAL(18, 6) NULL,
        net_income_yoy DECIMAL(18, 6) NULL,
        cfo_yoy DECIMAL(18, 6) NULL,
        shares_outstanding BIGINT UNSIGNED NULL,
        eps DECIMAL(24, 4) NULL,
        bvps DECIMAL(24, 4) NULL,
        cfo_per_share DECIMAL(24, 4) NULL,
        flag_negative_cfo TINYINT(1) NULL,
        flag_negative_fcf TINYINT(1) NULL,
        flag_low_earnings_quality TINYINT(1) NULL,
        flag_high_accruals TINYINT(1) NULL,
        flag_weak_interest_coverage TINYINT(1) NULL,
        flag_high_leverage TINYINT(1) NULL,
        flag_low_liquidity TINYINT(1) NULL,
        formula_version VARCHAR(16) NOT NULL,
        calculated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (metric_id),
        UNIQUE KEY uq_financial_metrics_period (
            company_id, report_scope, period_type, fiscal_year, fiscal_quarter
        ),
        KEY ix_financial_metrics_end (company_id, period_end),
        CONSTRAINT fk_financial_metrics_company FOREIGN KEY (company_id)
            REFERENCES companies (company_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS valuation_metrics (
        company_id BIGINT UNSIGNED NOT NULL,
        price_date DATE NOT NULL,
        close_price DECIMAL(20, 4) NOT NULL,
        metric_id BIGINT UNSIGNED NULL,
        report_scope ENUM('separate', 'consolidated') NULL,
        shares_outstanding BIGINT UNSIGNED NULL,
        market_cap DECIMAL(24, 4) NULL,
        enterprise_value DECIMAL(24, 4) NULL,
        pe_ttm DECIMAL(18, 6) NULL,
        pb DECIMAL(18, 6) NULL,
        ps_ttm DECIMAL(18, 6) NULL,
        ev_ebitda DECIMAL(18, 6) NULL,
        dividend_yield DECIMAL(18, 6) NULL,
        fcf_yield DECIMAL(18, 6) NULL,
        formula_version VARCHAR(16) NOT NULL,
        calculated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (company_id, price_date),
        CONSTRAINT fk_valuation_metrics_company FOREIGN KEY (company_id)
            REFERENCES companies (company_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS related_party_transactions (
        transaction_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        company_id BIGINT UNSIGNED NOT NULL,
        counterparty_name VARCHAR(255) NOT NULL,
        counterparty_ticker VARCHAR(16) NULL,
        report_scope ENUM('separate', 'consolidated') NULL,
        relationship ENUM(
            'subsidiary', 'indirect_subsidiary', 'associate', 'major_shareholder',
            'co_owner', 'group_company', 'key_management', 'other'
        ) NULL,
        transaction_type ENUM(
            'sale_goods', 'sale_services', 'sale_other', 'purchase_goods',
            'purchase_materials', 'purchase_services', 'interest_income',
            'interest_expense', 'other_income', 'asset_disposal', 'lending',
            'loan_collection', 'borrowing', 'loan_repayment', 'dividend_received',
            'remuneration', 'other'
        ) NOT NULL,
        description VARCHAR(255) NULL,
        period_start DATE NOT NULL,
        period_end DATE NOT NULL,
        amount DECIMAL(24, 4) NULL,
        currency CHAR(3) NOT NULL DEFAULT 'VND',
        document_storage_path VARCHAR(1024) NULL,
        source_url VARCHAR(1024) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (transaction_id),
        UNIQUE KEY uq_related_party_transactions_item (
            company_id, report_scope, counterparty_name, transaction_type, description,
            period_start, period_end
        ),
        KEY ix_related_party_transactions_counterparty (counterparty_ticker),
        CONSTRAINT fk_related_party_transactions_company FOREIGN KEY (company_id)
            REFERENCES companies (company_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS company_investments (
        investment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        company_id BIGINT UNSIGNED NOT NULL,
        investee_name VARCHAR(255) NOT NULL,
        investee_ticker VARCHAR(16) NULL,
        relation_type ENUM('subsidiary', 'associate', 'shareholding') NOT NULL,
        shares_owned BIGINT UNSIGNED NULL,
        ownership_percentage DECIMAL(9, 6) NULL,
        charter_capital DECIMAL(24, 4) NULL,
        contributed_capital DECIMAL(24, 4) NULL,
        as_of_date DATE NULL,
        note TEXT NULL,
        source_url VARCHAR(1024) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (investment_id),
        UNIQUE KEY uq_company_investments_investee (company_id, investee_name),
        KEY ix_company_investments_ticker (investee_ticker),
        CONSTRAINT fk_company_investments_company FOREIGN KEY (company_id)
            REFERENCES companies (company_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
)


# Columns added after a table was first created; missing ones are added on every run.
ADDITIONAL_COLUMNS = {
    "companies": {
        "charter_capital": "DECIMAL(24, 4) NULL",
        "listed_shares": "BIGINT UNSIGNED NULL",
        "outstanding_shares": "BIGINT UNSIGNED NULL",
        "initial_listed_shares": "BIGINT UNSIGNED NULL",
        "first_trading_date": "DATE NULL",
        "company_history": "LONGTEXT NULL",
        "headquarters_addresses": "JSON NULL",
        "phone_numbers": "JSON NULL",
        "fax": "VARCHAR(64) NULL",
        "email": "VARCHAR(255) NULL",
        "fiscal_year_start_month": "TINYINT UNSIGNED NULL",
        "business_registration_amendment": "SMALLINT UNSIGNED NULL",
        "business_registration_date": "DATE NULL",
        "listing_license": "VARCHAR(255) NULL",
    },
    "finance_reports": {
        "report_scope": "ENUM('separate', 'consolidated') NULL",
        "period_start": "DATE NULL",
        "period_end": "DATE NULL",
        "audit_status": "ENUM('unaudited', 'reviewed', 'audited') NULL",
        "auditor": "VARCHAR(255) NULL",
        "audit_opinion": "ENUM('unqualified', 'qualified', 'adverse', 'disclaimer') NULL",
        "audit_report_date": "DATE NULL",
        "employee_count": "INT UNSIGNED NULL",
        "net_revenue": "DECIMAL(24, 4) NULL",
        "cost_of_goods_sold": "DECIMAL(24, 4) NULL",
        "financial_income": "DECIMAL(24, 4) NULL",
        "financial_expense": "DECIMAL(24, 4) NULL",
        "interest_expense": "DECIMAL(24, 4) NULL",
        "selling_expense": "DECIMAL(24, 4) NULL",
        "admin_expense": "DECIMAL(24, 4) NULL",
        "other_profit": "DECIMAL(24, 4) NULL",
        "profit_before_tax": "DECIMAL(24, 4) NULL",
        "income_tax_expense": "DECIMAL(24, 4) NULL",
        "net_income_parent": "DECIMAL(24, 4) NULL",
        "cash_and_equivalents": "DECIMAL(24, 4) NULL",
        "short_term_investments": "DECIMAL(24, 4) NULL",
        "short_term_receivables": "DECIMAL(24, 4) NULL",
        "inventory": "DECIMAL(24, 4) NULL",
        "current_assets": "DECIMAL(24, 4) NULL",
        "current_liabilities": "DECIMAL(24, 4) NULL",
        "short_term_debt": "DECIMAL(24, 4) NULL",
        "long_term_debt": "DECIMAL(24, 4) NULL",
        "share_capital": "DECIMAL(24, 4) NULL",
        "investing_cash_flow": "DECIMAL(24, 4) NULL",
        "financing_cash_flow": "DECIMAL(24, 4) NULL",
    },
    "company_leaders": {
        "appointed_date": "DATE NULL",
        "dismissed_date": "DATE NULL",
        "status": "ENUM('current', 'former') NULL",
        "is_legal_representative": "TINYINT(1) NULL",
    },
    "related_party_transactions": {
        "report_scope": "ENUM('separate', 'consolidated') NULL AFTER counterparty_ticker",
    },
    "company_investments": {
        "is_direct": "TINYINT(1) NULL",
        "voting_percentage": "DECIMAL(9, 6) NULL",
        "investment_cost": "DECIMAL(24, 4) NULL",
        "business_line": "TEXT NULL",
        "operating_status": "VARCHAR(64) NULL",
    },
}
# ENUM columns whose value list grew after creation (only additions are safe here).
ENUM_COLUMNS = {
    ("company_leaders", "leader_group"):
        "ENUM('board', 'management', 'audit_committee', 'other') NULL",
}


def load_env_config() -> dict[str, str]:
    config: dict[str, str] = {}
    config_path = Path(__file__).resolve().parents[1] / ".env"
    if config_path.is_file():
        for line in config_path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.startswith("MYSQL_"):
                config[key] = value.strip().strip("\"'")
    return config


def parse_args() -> argparse.Namespace:
    file_config = load_env_config()

    def setting(key: str, default: str) -> str:
        return os.environ.get(key, file_config.get(key, default))

    parser = argparse.ArgumentParser(description="Create the stock module MySQL schema.")
    parser.add_argument("--host", default=setting("MYSQL_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(setting("MYSQL_PORT", "3306")))
    parser.add_argument("--user", default=setting("MYSQL_USER", "stock_app"))
    parser.add_argument("--password", default=setting("MYSQL_PASSWORD", ""))
    parser.add_argument("--database", default=setting("MYSQL_DATABASE", "stock_market"))
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


def migrate_stock_holders_table(cursor: Any) -> None:
    cursor.execute("SHOW COLUMNS FROM stock_holders LIKE 'holder_type'")
    column_type = cursor.fetchone()[1]
    if isinstance(column_type, bytes):
        column_type = column_type.decode()
    if column_type == HOLDER_TYPE_DEFINITION.removesuffix(" NULL").lower():
        return
    # Free-text values outside the list would block the conversion, so map them to 'other'.
    placeholders = ", ".join("%s" for _ in HOLDER_TYPES)
    cursor.execute(
        f"UPDATE stock_holders SET holder_type = 'other' "
        f"WHERE holder_type IS NOT NULL AND LOWER(holder_type) NOT IN ({placeholders})",
        HOLDER_TYPES,
    )
    cursor.execute(
        f"ALTER TABLE stock_holders MODIFY COLUMN holder_type {HOLDER_TYPE_DEFINITION}"
    )


def migrate_additional_columns(cursor: Any) -> None:
    for table, columns in ADDITIONAL_COLUMNS.items():
        cursor.execute(f"SHOW COLUMNS FROM `{table}`")
        existing_columns = {row[0] for row in cursor.fetchall()}
        for column_name, definition in columns.items():
            if column_name not in existing_columns:
                cursor.execute(
                    f"ALTER TABLE `{table}` ADD COLUMN `{column_name}` {definition}"
                )


def migrate_related_party_key(cursor: Any) -> None:
    """Separate and consolidated reports disclose the same period, and one counterparty can have
    several lines of the same type (e.g. selling tools and selling materials), so the scope and
    the description are part of the key."""
    cursor.execute(
        "SHOW INDEX FROM related_party_transactions WHERE Key_name = 'uq_related_party_transactions_item'"
    )
    if {"report_scope", "description"} <= {row[4] for row in cursor.fetchall()}:
        return
    cursor.execute(
        "ALTER TABLE related_party_transactions DROP INDEX uq_related_party_transactions_item, "
        "ADD UNIQUE KEY uq_related_party_transactions_item (company_id, report_scope, "
        "counterparty_name, transaction_type, description, period_start, period_end)"
    )


def migrate_enum_columns(cursor: Any) -> None:
    for (table, column), definition in ENUM_COLUMNS.items():
        cursor.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,))
        column_type = cursor.fetchone()[1]
        if isinstance(column_type, bytes):
            column_type = column_type.decode()
        if column_type.replace(" ", "") != definition.removesuffix(" NULL").replace(" ", "").lower():
            cursor.execute(f"ALTER TABLE `{table}` MODIFY COLUMN `{column}` {definition}")


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
        migrate_additional_columns(cursor)
        migrate_enum_columns(cursor)
        migrate_related_party_key(cursor)
        migrate_stock_holders_table(cursor)
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