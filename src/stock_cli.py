"""Interactive terminal browser for listed-company data."""

import argparse
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

try:
    from . import data_import, metrics, screening
except ImportError:
    import data_import
    import metrics
    import screening


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
    parser = argparse.ArgumentParser(description="Tra cứu doanh nghiệp niêm yết trong database stock.")
    parser.add_argument("--query", help="Mã cổ phiếu hoặc tên công ty để tìm ngay khi mở chương trình.")
    parser.add_argument("--page-size", type=int, default=10, help="Số dòng mỗi trang (1-100, mặc định 10).")
    args = parser.parse_args(argv)
    if not 1 <= args.page_size <= 100:
        parser.error("--page-size phải nằm trong khoảng từ 1 đến 100.")
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
        print(f"\n{title} | {total} kết quả | Trang {page + 1}/{total_pages}")
        if rows:
            # Number rows by the value to type; hide_id drops the internal id column.
            skip = 1 if hide_id else 0
            print_table(
                ("#", *headers),
                [(index, *row[skip:]) for index, row in enumerate(rows, start=1)],
            )
            print("Nhập số thứ tự để chọn, n: trang sau, p: trang trước, b: quay lại.")
        else:
            print("Không có dữ liệu.")
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
                print("Đang ở trang cuối.")
            continue
        if choice == "p":
            if page > 0:
                page -= 1
            else:
                print("Đang ở trang đầu.")
            continue
        if choice.isdigit() and 1 <= int(choice) <= len(rows):
            cursor.close()
            return rows[int(choice) - 1], page
        print("Lựa chọn không hợp lệ.")


def browse_company_search(
    connection: Any, query: str, page_size: int, start_page: int
) -> tuple[tuple[Any, ...], int] | None:
    pattern = f"%{query}%"
    return browse_pages(
        connection,
        f"Doanh nghiệp khớp '{query}'",
        """SELECT company_id, ticker, company_name, exchange, industry
           FROM companies
           WHERE ticker LIKE %s OR company_name LIKE %s
           ORDER BY ticker, company_id LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM companies WHERE ticker LIKE %s OR company_name LIKE %s",
        (pattern, pattern),
        ("Mã", "Tên doanh nghiệp", "Sàn", "Ngành"),
        page_size,
        start_page,
        hide_id=True,
    )


def browse_company_catalog(
    connection: Any, page_size: int, start_page: int
) -> tuple[tuple[Any, ...], int] | None:
    return browse_pages(
        connection,
        "Danh sách doanh nghiệp niêm yết",
        """SELECT company_id, ticker, company_name, exchange, industry
           FROM companies
           ORDER BY ticker, company_id LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM companies",
        (),
        ("Mã", "Tên doanh nghiệp", "Sàn", "Ngành"),
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
        print("Không tìm thấy doanh nghiệp này.")
        return

    print("\n" + "=" * 72)
    print(f"{company['ticker']} - {company['company_name']}")
    for label, key in (
        ("Sàn", "exchange"),
        ("Ngành", "industry"),
        ("Mã số thuế", "tax_code"),
        ("Vốn điều lệ", "charter_capital"),
        ("KL CP đang niêm yết", "listed_shares"),
        ("KL CP đang lưu hành", "outstanding_shares"),
        ("KL CP niêm yết lần đầu", "initial_listed_shares"),
        ("Ngày giao dịch đầu tiên", "first_trading_date"),
        ("Ngày thành lập", "established_date"),
        ("Ngày niêm yết", "listed_date"),
        ("Giấy phép niêm yết", "listing_license"),
        ("Tháng bắt đầu năm tài chính", "fiscal_year_start_month"),
        ("GCNĐKDN điều chỉnh lần", "business_registration_amendment"),
        ("Ngày cấp GCNĐKDN gần nhất", "business_registration_date"),
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
        ("Địa chỉ trụ sở", "headquarters_addresses"),
        ("Điện thoại", "phone_numbers"),
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
        print("Lịch sử:")
        print(history)

    description = company.get("description")
    if description:
        try:
            source_data = json.loads(description)
        except (json.JSONDecodeError, TypeError):
            source_data = description
        print("Thông tin nguồn:")
        if isinstance(source_data, dict):
            for key, value in source_data.items():
                print(f"  {key}: {value}")
        else:
            print(source_data)


LEADER_GROUPS = (
    ("board", "Hội đồng quản trị"),
    ("audit_committee", "Ủy ban Kiểm toán"),
    ("management", "Ban giám đốc/Kế toán trưởng"),
    ("other", "Vị trí khác"),
    (None, "Chưa phân nhóm"),
)


def leader_line(name: str, position: str, birth_year: Any, appointed: Any,
                dismissed: Any, legal_rep: Any) -> str:
    notes = []
    if birth_year:
        notes.append(f"sinh {birth_year}")
    if appointed:
        notes.append(f"bổ nhiệm {appointed:%d/%m/%Y}")
    if dismissed:
        notes.append(f"miễn nhiệm {dismissed:%d/%m/%Y}")
    if legal_rep:
        notes.append("đại diện theo pháp luật")
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

    print("Ban lãnh đạo:")
    current = [leader for leader in leaders if leader[1] != "former"]
    for group, label in LEADER_GROUPS:
        members = [leader[2:] for leader in current if leader[0] == group]
        if members:
            print(f"  {label}:")
            for member in members:
                print(leader_line(*member))
    former = [leader[2:] for leader in leaders if leader[1] == "former"]
    if former:
        print("  Đã miễn nhiệm/thôi giữ chức:")
        for member in former:
            print(leader_line(*member))


def browse_prices(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Giá cổ phiếu {ticker}",
        """SELECT price_date, open_price, high_price, low_price, close_price,
                  adjusted_close, trading_volume
           FROM stock_prices WHERE company_id = %s
           ORDER BY price_date DESC LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM stock_prices WHERE company_id = %s",
        (company_id,),
        ("Ngày", "Mở cửa", "Cao", "Thấp", "Đóng cửa", "Điều chỉnh", "Khối lượng"),
        page_size,
    )


def browse_holders(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Cổ đông {ticker}",
        """SELECT holder_name, holder_type, shares_owned, ownership_percentage,
                  snapshot_date, source_url
           FROM stock_holders WHERE company_id = %s
           ORDER BY snapshot_date DESC, ownership_percentage DESC LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM stock_holders WHERE company_id = %s",
        (company_id,),
        ("Cổ đông", "Loại", "Cổ phần", "Tỷ lệ %", "Ngày chốt", "Nguồn"),
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
        title = f"Nhà cung cấp của {ticker} (upstream)"
        own_side, other_side = "customer_id", "supplier_id"
        own_types, reverse_types = PURCHASE_TYPES, SALE_TYPES
    else:
        title = f"Khách hàng của {ticker} (downstream)"
        own_side, other_side = "supplier_id", "customer_id"
        own_types, reverse_types = SALE_TYPES, PURCHASE_TYPES

    union_sql = f"""
        SELECT partner.ticker AS partner_ticker, partner.company_name AS partner_name,
               relation.product_category AS content, relation.percentage_revenue AS share,
               NULL AS amount, NULL AS period_end, NULL AS scope, relation.source_url AS source
        FROM supply_chain_relations AS relation
        JOIN companies AS partner ON partner.company_id = relation.{other_side}
        WHERE relation.{own_side} = %s
        UNION ALL
        SELECT trade.counterparty_ticker, trade.counterparty_name, trade.description,
               NULL, trade.amount, trade.period_end, trade.report_scope,
               COALESCE(trade.document_storage_path, trade.source_url)
        FROM related_party_transactions AS trade
        WHERE trade.company_id = %s AND trade.transaction_type IN ({own_types})
        UNION ALL
        SELECT seller.ticker, seller.company_name, trade.description,
               NULL, trade.amount, trade.period_end, trade.report_scope,
               COALESCE(trade.document_storage_path, trade.source_url)
        FROM related_party_transactions AS trade
        JOIN companies AS seller ON seller.company_id = trade.company_id
        WHERE trade.counterparty_ticker = %s AND trade.transaction_type IN ({reverse_types})"""
    browse_pages(
        connection,
        title,
        f"""SELECT * FROM ({union_sql}) AS partners
            ORDER BY period_end DESC, amount DESC, partner_name
            LIMIT %s OFFSET %s""",
        f"SELECT COUNT(*) FROM ({union_sql}) AS partners",
        (company_id, company_id, ticker),
        ("Mã", "Doanh nghiệp", "Nội dung", "Tỷ trọng %", "Giá trị", "Kỳ đến", "Phạm vi", "Nguồn"),
        page_size,
    )


def browse_reports(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Báo cáo tài chính {ticker}",
        """SELECT fiscal_year, fiscal_quarter, report_type, report_scope, period_end,
                  net_revenue, profit_before_tax, net_income, total_assets, equity,
                  document_storage_path
           FROM finance_reports WHERE company_id = %s
           ORDER BY period_end DESC, fiscal_year DESC, fiscal_quarter DESC, report_id DESC
           LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM finance_reports WHERE company_id = %s",
        (company_id,),
        (
            "Năm TC", "Quý", "Loại", "Phạm vi", "Đến ngày", "DT thuần", "LN trước thuế",
            "LN sau thuế", "Tổng tài sản", "Vốn CSH", "Đường dẫn file",
        ),
        page_size,
    )


def browse_investments(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Công ty con, liên kết & đầu tư của {ticker}",
        """SELECT relation_type,
                  CASE is_direct WHEN 1 THEN 'trực tiếp' WHEN 0 THEN 'gián tiếp' END,
                  investee_name, investee_ticker, shares_owned, ownership_percentage,
                  voting_percentage, investment_cost, as_of_date
           FROM company_investments WHERE company_id = %s
           ORDER BY FIELD(relation_type, 'subsidiary', 'associate', 'shareholding'),
                    is_direct DESC, investment_cost DESC, ownership_percentage DESC,
                    investment_id
           LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM company_investments WHERE company_id = %s",
        (company_id,),
        ("Loại", "Sở hữu", "Công ty", "Mã", "Số CP", "Tỷ lệ %", "Biểu quyết %", "Giá gốc", "Tính đến"),
        page_size,
    )


def browse_related_parties(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Giao dịch bên liên quan của {ticker}",
        """SELECT period_end, report_scope, counterparty_name, relationship, transaction_type,
                  description, amount
           FROM related_party_transactions WHERE company_id = %s
           ORDER BY period_end DESC, report_scope, counterparty_name, transaction_type
           LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM related_party_transactions WHERE company_id = %s",
        (company_id,),
        ("Kỳ đến", "Phạm vi", "Bên liên quan", "Quan hệ", "Loại", "Nội dung", "Giá trị"),
        page_size,
    )


def flag_sql() -> str:
    return "CONCAT_WS(', ', " + ", ".join(
        f"IF({column}, '{label}', NULL)" for column, label in metrics.FLAG_LABELS.items()) + ")"


def browse_metrics(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    print("\nPhạm vi: 1. Hợp nhất  2. Riêng   |   Kỳ: a. TTM  b. Năm  c. Quý (Enter = hợp nhất, TTM)")
    answer = (prompt("> ") or "").lower()
    scope = "separate" if "2" in answer else "consolidated"
    period = {"b": "year", "c": "quarter"}.get(next((ch for ch in answer if ch in "abc"), "a"), "ttm")
    browse_pages(
        connection,
        f"Chỉ số tài chính {ticker} ({'hợp nhất' if scope == 'consolidated' else 'riêng'}, {period}) "
        "- tiền: tỷ đồng, tỷ lệ: %",
        f"""SELECT CONCAT('NĐ', fiscal_year, ' Q', fiscal_quarter), period_end,
                   CASE flow_source WHEN 'derived' THEN 'suy ra' WHEN 'mixed' THEN 'một phần suy ra' ELSE 'công bố' END,
                   ROUND(cfo / 1e9, 1), ROUND(cfi / 1e9, 1), ROUND(cff / 1e9, 1), ROUND(free_cash_flow / 1e9, 1),
                   cash_flow_pattern, lifecycle_stage, ROUND(net_margin * 100, 1), ROUND(roe * 100, 1),
                   ROUND(debt_to_equity, 2), ROUND(net_debt_to_ebitda, 1), ROUND(interest_coverage, 2),
                   ROUND(cfo_to_net_income, 2), ROUND(current_ratio, 2), {flag_sql()}
            FROM financial_metrics
            WHERE company_id = %s AND report_scope = %s AND period_type = %s
            ORDER BY period_end DESC LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM financial_metrics WHERE company_id = %s AND report_scope = %s AND period_type = %s",
        (company_id, scope, period),
        ("Kỳ", "Đến ngày", "Nguồn", "CFO", "CFI", "CFF", "FCF", "Mẫu", "Vòng đời", "LN ròng %", "ROE %",
         "Nợ/VCSH", "Nợ ròng/EBITDA", "EBIT/lãi", "CFO/LN", "Thanh toán", "Cảnh báo"),
        page_size,
    )


def browse_valuations(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Định giá {ticker} theo ngày (chỉ dùng báo cáo đã công bố trước ngày giá)",
        """SELECT price_date, close_price, ROUND(market_cap / 1e9, 0), ROUND(pe_ttm, 1), ROUND(pb, 2),
                  ROUND(ps_ttm, 2), ROUND(ev_ebitda, 1), ROUND(dividend_yield * 100, 2),
                  ROUND(fcf_yield * 100, 2), report_scope
           FROM valuation_metrics WHERE company_id = %s
           ORDER BY price_date DESC LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM valuation_metrics WHERE company_id = %s",
        (company_id,),
        ("Ngày", "Giá", "Vốn hóa (tỷ)", "P/E", "P/B", "P/S", "EV/EBITDA", "Cổ tức %", "FCF yield %", "Phạm vi"),
        page_size,
    )


def browse_news(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    result = browse_pages(
        connection,
        f"Tin tức {ticker}",
        """SELECT news_id, title, media_type, published_at, source_name,
                  media_url, storage_path
           FROM company_news WHERE company_id = %s
           ORDER BY published_at DESC, news_id DESC LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM company_news WHERE company_id = %s",
        (company_id,),
        ("Tiêu đề", "Dạng", "Ngày đăng", "Nguồn", "Media URL", "Đường dẫn file"),
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
        print(f"Ngày đăng: {news['published_at'] or '-'} | Nguồn: {news['source_name'] or '-'}")
        print(f"URL nguồn: {news['source_url'] or '-'}")
        print(f"URL media: {news['media_url'] or '-'}")
        print(f"Đường dẫn lưu trữ: {news['storage_path'] or '-'}")
        print("\n" + (news["content_text"] or "(Không có nội dung text.)"))
        input("\nNhấn Enter để quay lại...")


def prompt(message: str) -> str | None:
    try:
        return input(message).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def confirm_and_commit(connection: Any, results: dict[str, data_import.ImportStats]) -> None:
    print("\nKết quả:")
    print(data_import.format_report(results))
    if any(stats.errors for stats in results.values()):
        connection.rollback()
        print("Có lỗi, không lưu thay đổi nào. Sửa dữ liệu rồi nhập lại.")
        return
    if not any(stats.inserted or stats.updated for stats in results.values()):
        connection.rollback()
        print("Không có thay đổi nào.")
        return
    answer = prompt("Lưu thay đổi? (y/N): ")
    if answer is not None and answer.lower() in {"y", "yes", "c", "co", "có"}:
        if data_import.METRIC_SOURCES & set(results):
            print(metrics.format_summary(metrics.recompute(connection)))
        connection.commit()
        print("Đã lưu thay đổi.")
    else:
        connection.rollback()
        print("Đã hủy, không lưu thay đổi.")


def choose_categories(multiple: bool) -> list[data_import.Category]:
    categories = list(data_import.CATEGORIES.values())
    print()
    for index, category in enumerate(categories, start=1):
        print(f"{index}. {category.label}")
    hint = "Chọn danh mục (vd: 1,3 hoặc a = tất cả)" if multiple else "Chọn danh mục"
    answer = prompt(f"{hint}, b để quay lại: ")
    if answer is None or answer.lower() == "b":
        return []
    if multiple and answer.lower() == "a":
        return categories

    chosen: list[data_import.Category] = []
    for part in answer.split(","):
        part = part.strip()
        if not part.isdigit() or not 1 <= int(part) <= len(categories):
            print("Lựa chọn không hợp lệ.")
            return []
        if categories[int(part) - 1] not in chosen:
            chosen.append(categories[int(part) - 1])
    if not chosen or (not multiple and len(chosen) != 1):
        print("Lựa chọn không hợp lệ.")
        return []
    return chosen


def manual_entry(connection: Any, ticker: str) -> None:
    categories = choose_categories(multiple=False)
    if not categories:
        return
    category = categories[0]
    print(f"\nNhập {category.label} cho {ticker}. Enter để bỏ trống (giữ nguyên giá trị đang có).")

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
        print(f"Không hợp lệ: {exc}")
        return
    finally:
        cursor.close()

    if existing is None:
        print("Bản ghi mới. Giá trị hiện tại hiển thị trong [ ].")
    else:
        print("Đã có bản ghi này. Giá trị hiện tại hiển thị trong [ ].")
    for column in category.values:
        current = display_value(existing.get(column)) if existing else "-"
        required = " (bắt buộc)" if existing is None and column in category.required else ""
        options = choices.get(column)
        if options:
            print(f"{column}: " + "   ".join(f"{i}. {o}" for i, o in enumerate(options, start=1)))
            value = prompt(f"Chọn số hoặc gõ giá trị{required} [{current}]: ")
        else:
            value = prompt(f"{column}{required} [{current}]: ")
        if value is None:
            return
        if options and value.isdigit():
            if not 1 <= int(value) <= len(options):
                print("Lựa chọn không hợp lệ.")
                return
            value = options[int(value) - 1]
        raw[column] = value

    stats = data_import.merge_rows(connection, category, [("nhập tay", raw)], [ticker])
    confirm_and_commit(connection, {category.table: stats})


def csv_import(connection: Any, tickers: list[str] | None) -> None:
    categories = choose_categories(multiple=True)
    if not categories:
        return
    print("\nCột CSV hỗ trợ (dòng đầu là tên cột, ô trống = giữ nguyên giá trị đang có):")
    for category in categories:
        print(f"  {category.table}.csv: {','.join(category.columns)}")
    if tickers is None or len(tickers) > 1:
        print("Mỗi dòng cần cột mã (ticker / supplier_ticker / customer_ticker) để xác định công ty.")
    else:
        print(f"Dòng không có cột mã sẽ áp dụng cho {tickers[0]}.")

    files: dict[str, Path] = {}
    if len(categories) > 1:
        folder = prompt("Thư mục chứa các file <danh_mục>.csv (Enter để nhập từng file): ")
        if folder is None:
            return
        if folder:
            directory = Path(folder).expanduser()
            for category in categories:
                path = directory / f"{category.table}.csv"
                if path.is_file():
                    files[category.table] = path
                else:
                    print(f"Không thấy {path}, bỏ qua {category.label}.")
    if not files:
        for category in categories:
            path = prompt(f"File CSV cho {category.label} (Enter để bỏ qua): ")
            if path is None:
                return
            if path:
                files[category.table] = Path(path).expanduser()
    if not files:
        print("Không có file nào để nhập.")
        return

    confirm_and_commit(connection, data_import.import_files(connection, files, tickers))


def data_entry_menu(connection: Any, tickers: list[str] | None) -> None:
    label = ", ".join(tickers) if tickers else "mọi mã trong file"
    while True:
        print(f"\n=== NHẬP/CẬP NHẬT DỮ LIỆU: {label} ===")
        print("1. Nhập tay   2. Import file CSV   b. Quay lại")
        choice = prompt("> ")
        if choice is None or choice.lower() == "b":
            return
        if choice == "1":
            if tickers is None or len(tickers) != 1:
                print("Nhập tay chỉ áp dụng cho 1 công ty.")
            else:
                manual_entry(connection, tickers[0])
        elif choice == "2":
            csv_import(connection, tickers)
        else:
            print("Lựa chọn không hợp lệ.")


def run_data_entry(connection: Any) -> None:
    answer = prompt(
        "\nMã công ty áp dụng (vd: HPG hoặc HPG,VNM; * = mọi mã trong file; b để quay lại): "
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
            print(f"Chưa có trong DB: {', '.join(missing)} (chỉ nhập được Thông tin cơ bản để tạo mới).")
    data_entry_menu(connection, tickers)


def company_menu(connection: Any, selected: tuple[Any, ...], page_size: int) -> None:
    company_id, ticker, company_name, _, _ = selected
    while True:
        show_company(connection, company_id)
        print("\n1. Giá cổ phiếu   2. Cổ đông   3. Nhà cung cấp (upstream)")
        print("4. Khách hàng (downstream)   5. Báo cáo tài chính   6. Tin tức")
        print("7. Công ty con, liên kết & đầu tư   8. Nhập/cập nhật dữ liệu")
        print("9. Giao dịch bên liên quan   10. Chỉ số tài chính   11. Định giá")
        print("b. Quay lại tìm kiếm")
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
        else:
            print("Lựa chọn không hợp lệ.")


def browse_list(title: str, headers: Sequence[str], rows: list[Sequence[Any]], page_size: int) -> int | None:
    """Page through in-memory rows; return the index of the chosen row, or None."""
    page, total_pages = 0, max(1, (len(rows) + page_size - 1) // page_size)
    while True:
        chunk = rows[page * page_size:(page + 1) * page_size]
        print(f"\n{title} | {len(rows)} kết quả | Trang {page + 1}/{total_pages}")
        if not chunk:
            print("Không có dữ liệu.")
            return None
        print_table(("#", *headers), [(i, *row) for i, row in enumerate(chunk, start=1)])
        print("Nhập số thứ tự để mở công ty, n: trang sau, p: trang trước, b: quay lại.")
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
            print("Lựa chọn không hợp lệ.")


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
    return (s.ticker, s.name, f"NĐ{s.now['fiscal_year']} Q{s.now['fiscal_quarter']}",
            "HN" if s.now["report_scope"] == "consolidated" else "Riêng", s.now.get("cash_flow_pattern") or "-",
            pct(s.get("roe")), num(roe_change, 1), num(s.get("cfo_to_net_income")), num(s.get("debt_to_equity")),
            f"{result.met}/{len(result.required)}", "; ".join(failed) or "-")


SCREEN_HEADERS = ("Mã", "Doanh nghiệp", "Kỳ TTM", "Phạm vi", "Mẫu", "ROE %", "ΔROE (điểm %)", "CFO/LN",
                  "Nợ/VCSH", "Đạt", "Chưa đạt / thiếu dữ liệu")


def show_group(connection: Any, group: "screening.Group", results: list, page_size: int) -> None:
    print(f"\n=== {group.name.upper()} ===\n{group.meaning}\nĐiều kiện:")
    for criterion in group.criteria:
        print(f"  - {criterion.label}{'' if criterion.required else ' (tham khảo)'}")
    matched = [r for r in results if r.matched]
    near = [r for r in results if not r.matched and r.near]
    rows = [("KHỚP", *screening_row(r)) for r in matched] + [("gần khớp", *screening_row(r)) for r in near]
    while True:
        index = browse_list(f"{group.name}: {len(matched)} khớp, {len(near)} gần khớp (thiếu 1 điều kiện)",
                            ("Kết quả", *SCREEN_HEADERS), rows, page_size)
        if index is None:
            return
        open_company(connection, (matched + near)[index].snapshot.company_id, page_size)


def show_warnings(connection: Any, snapshots: list, page_size: int) -> None:
    rows, targets = [], []
    for s in snapshots:
        active = [label for column, label in metrics.FLAG_LABELS.items() if s.now.get(column)]
        if active:
            rows.append((len(active), s.ticker, s.name, f"NĐ{s.now['fiscal_year']} Q{s.now['fiscal_quarter']}",
                         num(s.get("interest_coverage")), num(s.get("net_debt_to_ebitda"), 1),
                         num(s.get("cfo_to_net_income")), num(s.get("current_ratio")), ", ".join(active)))
            targets.append(s.company_id)
    order = sorted(range(len(rows)), key=lambda i: -rows[i][0])
    rows, targets = [rows[i] for i in order], [targets[i] for i in order]
    while True:
        index = browse_list("Cảnh báo sớm (cờ trên kỳ TTM mới nhất, nhiều cờ xếp trước)",
                            ("Số cờ", "Mã", "Doanh nghiệp", "Kỳ TTM", "EBIT/lãi", "Nợ ròng/EBITDA", "CFO/LN",
                             "Thanh toán", "Cảnh báo"), rows, page_size)
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
        print(f"\n=== LỌC CỔ PHIẾU & CẢNH BÁO SỚM === (kỳ TTM mới nhất của {len(snapshots)} doanh nghiệp có báo cáo)")
        for index, group in enumerate(screening.GROUPS, start=1):
            group_results = [r for r in results if r.group is group]
            print(f"{index}. {group.name}: {sum(r.matched for r in group_results)} khớp, "
                  f"{sum((not r.matched) and r.near for r in group_results)} gần khớp")
        flagged = sum(1 for s in snapshots if any(s.now.get(c) for c in metrics.FLAG_LABELS))
        print(f"{len(screening.GROUPS) + 1}. Cảnh báo sớm: {flagged} doanh nghiệp có cờ")
        print(f"{len(screening.GROUPS) + 2}. Bảng tổng hợp mọi doanh nghiệp")
        print("b. Quay lại")
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
                rows.append((s.ticker, s.name, f"NĐ{s.now['fiscal_year']} Q{s.now['fiscal_quarter']}",
                             s.now.get("cash_flow_pattern") or "-", s.now.get("lifecycle_stage") or "-",
                             *[("✓ " if r.matched else "") + f"{r.met}/{len(r.required)}" for r in own]))
            index = browse_list("Mức khớp từng nhóm (✓ = khớp)",
                                ("Mã", "Doanh nghiệp", "Kỳ TTM", "Mẫu", "Vòng đời",
                                 *[g.name for g in screening.GROUPS]), rows, page_size)
            if index is not None:
                open_company(connection, snapshots[index].company_id, page_size)
        else:
            print("Lựa chọn không hợp lệ.")


def run_search(connection: Any, page_size: int, initial_query: str | None = None) -> None:
    query = initial_query
    while True:
        if query is None:
            try:
                query = input("\nNhập mã cổ phiếu hoặc tên doanh nghiệp (b để quay lại): ").strip()
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


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        import mysql.connector
    except ImportError:
        print("Thiếu MySQL connector. Chạy scripts/setup_database.sh trước.", file=sys.stderr)
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
        print(f"Không kết nối được database: {exc}", file=sys.stderr)
        print("Chạy scripts/setup_database.sh để thiết lập hoặc kiểm tra database.env.", file=sys.stderr)
        return 1

    try:
        if args.query:
            run_search(connection, args.page_size, args.query)
        else:
            while True:
                print("\n=== STOCK: DOANH NGHIỆP NIÊM YẾT ===")
                print("1. Tìm kiếm doanh nghiệp")
                print("2. Xem danh sách doanh nghiệp")
                print("3. Nhập/cập nhật dữ liệu (nhập tay / CSV)")
                print("4. Lọc cổ phiếu & cảnh báo sớm")
                print("q. Thoát")
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
                    print("Lựa chọn không hợp lệ.")
    except Exception as exc:
        print(f"Lỗi khi truy vấn database: {exc}", file=sys.stderr)
        connection.close()
        return 1

    connection.close()
    print("Đã thoát.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())