"""Interactive terminal browser for listed-company data."""

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Sequence


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
            print_table(headers, rows)
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
        ("#", "Mã", "Tên doanh nghiệp", "Sàn", "Ngành"),
        page_size,
        start_page,
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
        ("#", "Mã", "Tên doanh nghiệp", "Sàn", "Ngành"),
        page_size,
        start_page,
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
        ("Website", "website"),
        ("Ngày thành lập", "established_date"),
        ("Ngày niêm yết", "listed_date"),
        ("Mô tả", "description"),
    ):
        if company.get(key) is not None:
            print(f"{label}: {company[key]}")


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


def browse_supply_chain(
    connection: Any, company_id: int, ticker: str, direction: str, page_size: int
) -> None:
    if direction == "upstream":
        title = f"Nhà cung cấp của {ticker} (upstream)"
        foreign_key = "customer_id"
        company_alias = "supplier"
    else:
        title = f"Khách hàng của {ticker} (downstream)"
        foreign_key = "supplier_id"
        company_alias = "customer"

    browse_pages(
        connection,
        title,
        f"""SELECT relation.{foreign_key}, {company_alias}.ticker,
                   {company_alias}.company_name, relation.product_category,
                   relation.percentage_revenue, relation.source_url
            FROM supply_chain_relations AS relation
            JOIN companies AS {company_alias}
              ON {company_alias}.company_id = relation.{('supplier_id' if direction == 'upstream' else 'customer_id')}
            WHERE relation.{foreign_key} = %s
            ORDER BY {company_alias}.ticker, relation.product_category
            LIMIT %s OFFSET %s""",
        f"SELECT COUNT(*) FROM supply_chain_relations WHERE {foreign_key} = %s",
        (company_id,),
        ("ID", "Mã", "Doanh nghiệp", "Danh mục", "Tỷ trọng %", "Nguồn"),
        page_size,
    )


def browse_reports(connection: Any, company_id: int, ticker: str, page_size: int) -> None:
    browse_pages(
        connection,
        f"Báo cáo tài chính {ticker}",
        """SELECT report_type, fiscal_year, fiscal_quarter, currency, revenue,
                  gross_profit, net_income, earnings_per_share, document_storage_path
           FROM finance_reports WHERE company_id = %s
           ORDER BY fiscal_year DESC, fiscal_quarter DESC, report_id DESC
           LIMIT %s OFFSET %s""",
        "SELECT COUNT(*) FROM finance_reports WHERE company_id = %s",
        (company_id,),
        ("Loại", "Năm", "Quý", "Tiền tệ", "Doanh thu", "LN gộp", "LN ròng", "EPS", "Đường dẫn file"),
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
        ("ID", "Tiêu đề", "Dạng", "Ngày đăng", "Nguồn", "Media URL", "Đường dẫn file"),
        page_size,
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


def company_menu(connection: Any, selected: tuple[Any, ...], page_size: int) -> None:
    company_id, ticker, company_name, _, _ = selected
    while True:
        show_company(connection, company_id)
        print("\n1. Giá cổ phiếu   2. Cổ đông   3. Nhà cung cấp (upstream)")
        print("4. Khách hàng (downstream)   5. Báo cáo tài chính   6. Tin tức")
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