"""Convert CafeF trading-data exports into import CSVs and merge them into the database.

Recognised files (the ticker and dates come from the file contents or name):

  CafeF_LichSuGia_*.xlsx            -> stock_prices        (price history, matched + negotiated)
  CafeF_GiaoDichKhoiNgoai_*.xlsx    -> foreign_trades      (foreign investor trading)
  CafeF_GiaoDichTuDoanh_*.xlsx      -> proprietary_trades  (proprietary trading)
  CafeF_ThongKeDatLenh_*.xlsx       -> order_statistics    (orders placed)
  CafeF_KhopLenh_<TICKER>_<YYYYMMDD>.xlsx -> intraday_trades (matched trades of one session)
  CafeF_GiaoDichCoDong*.txt         -> insider_trades      (page text copied from the
                                                            "Co dong & Noi bo" tab)

CafeF quotes prices in thousand VND and values in VND billion; the CSVs hold VND.
The CSVs are written in the data_import format, then merged cell by cell like any CSV import.
"""

import argparse
import csv
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR / "src"))

import data_import  # noqa: E402

THOUSAND = Decimal(1000)
BILLION = Decimal(1_000_000_000)
CHANGE_PATTERN = re.compile(r"([+-]?[\d.,]+)\s*\(\s*([+-]?[\d.,]+)\s*%\s*\)")
INTRADAY_PRICE_PATTERN = re.compile(r"([\d,]+)\s*([+-]*)\s*([\d,]+)?")
TICKER_PATTERN = re.compile(r"[A-Z0-9]{3,10}")


def number(value: Any) -> Decimal | None:
    """Parse a cell: real numbers as-is, text with ',' thousand separators, '-' as empty."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace(",", "")
    if text in ("", "-"):
        return None
    return Decimal(text)


def vn_number(text: str) -> Decimal:
    """Parse Vietnamese formatting: '.' thousand separator, ',' decimal mark."""
    return Decimal(text.strip().replace(".", "").replace(",", "."))


def fmt(value: Decimal | int | None) -> str:
    if value is None:
        return ""
    return format(Decimal(value).normalize(), "f")


def scaled(value: Any, factor: Decimal) -> str:
    """Format a CafeF figure converted to VND; empty cells stay empty."""
    parsed = number(value)
    return fmt(None if parsed is None else parsed * factor)


def dmy(text: str) -> str:
    """'06/11/2026' or '06/11/26' -> '2026-11-06'; '-' -> ''."""
    text = str(text or "").strip()
    if text in ("", "-"):
        return ""
    day, month, year = text.split("/")
    year = int(year) + (2000 if len(year) == 2 else 0)
    return date(year, int(month), int(day)).isoformat()


def xlsx_rows(path: Path) -> tuple[list[str], list[tuple]]:
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("Reading .xlsx needs openpyxl: pip install openpyxl") from exc
    sheet = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
    rows = [row for row in sheet.iter_rows(values_only=True) if any(cell is not None for cell in row)]
    return [str(cell or "").strip() for cell in rows[0]], rows[1:]


def check_header(path: Path, header: list[str], expected: tuple[str, ...]) -> None:
    if tuple(header[:len(expected)]) != expected:
        raise ValueError(f"{path.name}: unexpected columns {header}; expected {list(expected)}")


def parse_price_history(path: Path) -> list[dict[str, str]]:
    header, rows = xlsx_rows(path)
    check_header(path, header, (
        "Mã", "Ngày", "Giá đóng cửa", "Giá điều chỉnh", "Thay đổi", "Khối lượng khớp lệnh",
        "Giá trị khớp lệnh", "Khối lượng thỏa thuận", "Giá trị thỏa thuận", "Giá mở cửa",
        "Giá cao nhất", "Giá thấp nhất",
    ))
    result = []
    for (ticker, day, close, adjusted, change, volume, value, neg_volume, neg_value,
         open_, high, low, *_) in rows:
        price_change = change_percentage = None
        match = CHANGE_PATTERN.search(str(change or ""))
        if match:
            price_change = vn_number(match.group(1)) * THOUSAND
            change_percentage = vn_number(match.group(2))
        result.append({
            "ticker": ticker, "price_date": dmy(day),
            "open_price": scaled(open_, THOUSAND),
            "high_price": scaled(high, THOUSAND),
            "low_price": scaled(low, THOUSAND),
            "close_price": scaled(close, THOUSAND),
            "adjusted_close": scaled(adjusted, THOUSAND),
            "price_change": fmt(price_change), "change_percentage": fmt(change_percentage),
            "trading_volume": fmt(number(volume)),
            "trading_value": scaled(value, BILLION),
            "negotiated_volume": fmt(number(neg_volume)),
            "negotiated_value": scaled(neg_value, BILLION),
        })
    return result


def parse_foreign(path: Path) -> list[dict[str, str]]:
    header, rows = xlsx_rows(path)
    check_header(path, header, (
        "Mã", "Ngày", "Thay đổi", "KLGD ròng", "GTGD ròng", "KL Mua", "GT Mua", "KL Bán",
        "GT Bán", "Room còn lại", "Đang sở hữu (%)",
    ))
    return [{
        "ticker": ticker, "trade_date": dmy(day),
        "net_volume": fmt(number(net_volume)), "net_value": scaled(net_value, BILLION),
        "buy_volume": fmt(number(buy_volume)), "buy_value": scaled(buy_value, BILLION),
        "sell_volume": fmt(number(sell_volume)), "sell_value": scaled(sell_value, BILLION),
        "room_remaining": fmt(number(room)), "ownership_percentage": fmt(number(owned)),
    } for (ticker, day, _change, net_volume, net_value, buy_volume, buy_value, sell_volume,
           sell_value, room, owned, *_) in rows]


def parse_proprietary(path: Path) -> list[dict[str, str]]:
    header, rows = xlsx_rows(path)
    check_header(path, header, (
        "Mã", "Ngày", "Khối lượng mua", "Giá trị mua (tỷ đồng)", "Khối lượng bán",
        "Giá trị bán (tỷ đồng)", "Khối lượng giao dịch ròng", "Giá trị giao dịch ròng (tỷ đồng)",
    ))
    return [{
        "ticker": ticker, "trade_date": dmy(day),
        "buy_volume": fmt(number(buy_volume)), "buy_value": scaled(buy_value, BILLION),
        "sell_volume": fmt(number(sell_volume)), "sell_value": scaled(sell_value, BILLION),
        "net_volume": fmt(number(net_volume)), "net_value": scaled(net_value, BILLION),
    } for (ticker, day, buy_volume, buy_value, sell_volume, sell_value, net_volume,
           net_value, *_) in rows]


def parse_order_statistics(path: Path) -> list[dict[str, str]]:
    header, rows = xlsx_rows(path)
    check_header(path, header, (
        "Mã", "Ngày", "Thay đổi", "Số lệnh mua", "Khối lượng mua", "KLTB/lệnh mua",
        "Số lệnh bán", "Khối lượng bán", "KLTB/lệnh bán", "Khối lượng ròng",
    ))
    result = []
    for (ticker, day, _change, buy_orders, buy_volume, avg_buy, sell_orders, sell_volume,
         avg_sell, net_volume, *_) in rows:
        figures = (buy_orders, buy_volume, avg_buy, sell_orders, sell_volume, avg_sell, net_volume)
        if all(not number(value) for value in figures):
            continue  # CafeF lists the current day as all zeros until the statistics are published
        result.append({
            "ticker": ticker, "trade_date": dmy(day),
            "buy_orders": fmt(number(buy_orders)), "buy_volume": fmt(number(buy_volume)),
            "avg_buy_order_volume": fmt(number(avg_buy)),
            "sell_orders": fmt(number(sell_orders)), "sell_volume": fmt(number(sell_volume)),
            "avg_sell_order_volume": fmt(number(avg_sell)),
            "net_volume": fmt(number(net_volume)),
        })
    return result


def parse_intraday(path: Path) -> list[dict[str, str]]:
    match = re.search(r"KhopLenh_([A-Z0-9]+)_(\d{8})", path.name)
    if not match:
        raise ValueError(f"{path.name}: name must be CafeF_KhopLenh_<TICKER>_<YYYYMMDD>.xlsx")
    ticker, day = match.group(1), match.group(2)
    trade_date = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    header, rows = xlsx_rows(path)
    check_header(path, header, ("Thời gian", "Giá", "Khối lượng lô", "Khối lượng tích lũy", "Tỷ trọng"))

    # Every row is kept: identical rows are separate trades matched at the same moment.
    result = []
    for row in rows:
        time_text, price_text, lot, cumulative, weight = (str(cell or "").strip() for cell in row[:5])
        price = change = None
        price_match = INTRADAY_PRICE_PATTERN.match(price_text)
        if price_match:
            price = vn_number(price_match.group(1)) * THOUSAND
            if price_match.group(3):
                change = vn_number(price_match.group(3)) * THOUSAND
                if "-" in price_match.group(2):
                    change = -change
        result.append({
            "ticker": ticker, "trade_date": trade_date, "seq": str(len(result) + 1),
            "trade_time": time_text, "price": fmt(price), "price_change": fmt(change),
            "lot_volume": lot.replace(".", ""), "cumulative_volume": cumulative.replace(".", ""),
            "weight_percentage": fmt(vn_number(weight.rstrip("%"))) if weight else "",
        })
    return result


def parse_insider_text(path: Path) -> list[dict[str, str]]:
    """Parse text copied from CafeF's "Co dong & Noi bo" table.

    Each record starts with a line holding only the ticker, followed by the trader's name and
    position, the related person's name and position (both optional), and finally 10 figures:
    shares before, registered buy/sell, registration start/end, executed buy/sell, execution
    date, shares after, ownership %. Dates are DD/MM/YY; '-' means not applicable.
    """
    lines = [line.rstrip() for line in path.read_text(encoding="utf-8-sig").splitlines()]
    # The table starts after its second header row ("Chức vụ  Tên  Chức vụ  Mua  Bán ...");
    # anything above it (search form, page title) is ignored.
    start = next((i + 1 for i, line in enumerate(lines)
                  if line.startswith("Chức vụ\t") and "Ngày TH" in line), None)
    if start is None:
        raise ValueError(f"{path.name}: table header row ('Chức vụ  Tên  Chức vụ ...') not found")
    records: list[list[str]] = []
    for line in lines[start:]:
        cells = [cell.strip() for cell in line.split("\t")]
        if len(cells) <= 2 and TICKER_PATTERN.fullmatch(cells[0]) and not any(cells[1:]):
            records.append([cells[0]])
        elif records and line.strip():
            records[-1].append(line)

    result = []
    for record in records:
        ticker, parts = record[0], record[1:]
        cells = [cell.strip() for cell in "\t".join(parts).split("\t")]
        cells = [cell for cell in cells if cell]
        if len(cells) < 11 or len(cells) > 14:
            raise ValueError(f"{path.name}: unexpected record for {ticker}: {cells}")
        names = cells[:-10] + [""] * (14 - len(cells))
        (before, reg_buy, reg_sell, start, end, exe_buy, exe_sell, exe_date, after,
         ratio) = cells[-10:]
        trader_name, trader_position, related_name, related_position = names[:4]
        reported = dmy(exe_date) or any(number(v) for v in (exe_buy, exe_sell))
        result.append({
            "ticker": ticker, "trader_name": trader_name, "trader_position": trader_position,
            "related_person_name": related_name, "related_person_position": related_position,
            "shares_before": fmt(number(before)),
            "registered_buy": fmt(number(reg_buy)), "registered_sell": fmt(number(reg_sell)),
            "registration_start": dmy(start), "registration_end": dmy(end),
            "executed_buy": fmt(number(exe_buy)), "executed_sell": fmt(number(exe_sell)),
            "execution_date": dmy(exe_date),
            # CafeF shows 0 / 0.00 while no result has been reported yet; keep those empty.
            "shares_after": fmt(number(after)) if reported else "",
            "ownership_after_percentage": fmt(number(ratio)) if reported else "",
        })
    return result


PARSERS: dict[str, tuple[str, Callable[[Path], list[dict[str, str]]]]] = {
    "CafeF_LichSuGia_": ("stock_prices", parse_price_history),
    "CafeF_GiaoDichKhoiNgoai_": ("foreign_trades", parse_foreign),
    "CafeF_GiaoDichTuDoanh_": ("proprietary_trades", parse_proprietary),
    "CafeF_ThongKeDatLenh_": ("order_statistics", parse_order_statistics),
    "CafeF_KhopLenh_": ("intraday_trades", parse_intraday),
    "CafeF_GiaoDichCoDong": ("insider_trades", parse_insider_text),
}


def parser_for(path: Path) -> tuple[str, Callable[[Path], list[dict[str, str]]]] | None:
    for prefix, entry in PARSERS.items():
        if path.name.startswith(prefix):
            return entry
    return None


def collect(paths: Iterable[Path]) -> dict[str, list[dict[str, str]]]:
    """Parse every recognised file; return rows grouped by category."""
    grouped: dict[str, list[dict[str, str]]] = {}
    files = []
    for path in paths:
        files.extend(sorted(p for p in path.iterdir() if p.is_file()) if path.is_dir() else [path])
    for path in files:
        entry = parser_for(path)
        if entry is None:
            print(f"  skipped (unrecognised name): {path.name}")
            continue
        table, parse = entry
        rows = parse(path)
        grouped.setdefault(table, []).extend(rows)
        print(f"  {path.name} -> {table}: {len(rows)} rows")
    return grouped


def write_csvs(grouped: dict[str, list[dict[str, str]]], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for table in data_import.CATEGORIES:  # import order
        if table not in grouped:
            continue
        path = output_dir / f"{table}.csv"
        with path.open("w", encoding="utf-8", newline="") as destination:
            writer = csv.DictWriter(destination, fieldnames=data_import.CATEGORIES[table].columns)
            writer.writeheader()
            writer.writerows(grouped[table])
        files[table] = path
    return files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "inputs", nargs="*", type=Path, default=[MODULE_DIR / "new_data"],
        help="CafeF files or folders (default: new_data/).",
    )
    parser.add_argument(
        "--output", type=Path, default=MODULE_DIR / "processed_data" / "cafef",
        help="Folder for the generated CSVs (default: processed_data/cafef/).",
    )
    parser.add_argument("--prepare-only", action="store_true", help="Write the CSVs; do not import.")
    parser.add_argument("--dry-run", action="store_true", help="Import, report, then roll back.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("Reading CafeF files:")
    try:
        grouped = collect(args.inputs)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not grouped:
        print("No CafeF files found.", file=sys.stderr)
        return 1
    files = write_csvs(grouped, args.output)
    print(f"CSVs written to {args.output}")
    if args.prepare_only:
        return 0

    import metrics
    import mysql.connector
    import stock_cli

    config = stock_cli.load_database_config()
    config["port"] = int(config["port"])
    connection = mysql.connector.connect(**config)
    try:
        # An intraday file is a whole session keyed by row position (seq), so a re-import
        # replaces that session instead of merging, in the same transaction as the import.
        connection.start_transaction()
        cursor = connection.cursor()
        for ticker, trade_date in sorted({(row["ticker"], row["trade_date"])
                                          for row in grouped.get("intraday_trades", [])}):
            cursor.execute(
                "DELETE t FROM intraday_trades AS t JOIN companies AS c USING (company_id) "
                "WHERE c.ticker = %s AND t.trade_date = %s",
                (ticker, trade_date),
            )
            print(f"Replacing intraday session {ticker} {trade_date} ({cursor.rowcount} old rows).")
        cursor.close()
        results = data_import.import_files(connection, files, None)
        print(data_import.format_report(results))
        if any(stats.errors for stats in results.values()):
            connection.rollback()
            print("Errors found; nothing was saved.", file=sys.stderr)
            return 1
        if data_import.METRIC_SOURCES & set(files):
            tickers = sorted({row["ticker"] for table in data_import.METRIC_SOURCES & set(files)
                              for row in grouped[table]})
            print("Recomputing financial metrics:")
            print(metrics.format_summary(metrics.recompute(connection, tickers)))
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
