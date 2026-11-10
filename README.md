# Stock

A terminal-based module for looking up listed companies. It reads data from MySQL/MariaDB and loads result lists one page at a time.

## Features

- Search for companies by ticker or name.
- Browse companies already stored in the database.
- View company contact, listing, share-count, history, address, and leadership details alongside stock prices, shareholders, subsidiaries/associates/investments, suppliers, customers, financial reports, and news.
- Paginate with `LIMIT/OFFSET` queries instead of loading the entire result set into memory.
- Fetch full news text only after a news item is selected.

The database stores these data groups:

- `companies`: basic information and listing ticker.
- `organizations`, `organization_aliases`: the organisation register: every organisation named in the data (listed or not) under one canonical name, with each spelling met in the sources (see "Organisation Register").
- `stock_prices`: daily prices, change, matched volume/value and negotiated (put-through) volume/value.
- `foreign_trades`: daily foreign-investor buy/sell/net volume and value, remaining foreign room and foreign ownership %.
- `proprietary_trades`: daily proprietary trading (tự doanh) of securities companies: buy/sell/net volume and value.
- `order_statistics`: daily number and volume of buy and sell orders placed, average order size and net volume.
- `intraday_trades`: matched trades within one session (time, price, lot, running total, weight), in source order.
- `insider_trades`: trades registered and reported by major shareholders, insiders and their related persons (registered buy/sell and window, executed buy/sell and date, holdings before/after).
- `stock_holders`: shareholders and ownership percentages by snapshot date.
- `finance_reports`: reporting period, scope (separate/consolidated), income statement, balance sheet and cash-flow metrics, employee count, and the path of the report file.
- `tiers`, `company_tiers`: company classifications.
- `supply_chain_relations`: supplier and customer relationships.
- `company_news`: news text and media metadata or paths.
- `company_leaders`: board members, executives, and other officers.
- `company_investments`: subsidiaries (direct and indirect), associates, and shareholdings in other companies.
- `finance_report_items`: every line of each report's balance sheet, income statement and cash flow, with comparative and year-to-date columns.
- `related_party_transactions`: related-party transactions disclosed in financial reports (sales, purchases, loans, interest, dividends, remuneration).

The scripts create and migrate the schema, prepare table-specific CSV files from the raw company sources, and import available rows into MySQL. Only `companies` currently receives rows from the supplied raw data; other table CSVs contain headers until matching sources are added.

## Quick Setup

Requires Ubuntu/Debian, Python 3, `sudo` access, and an internet connection for the initial installation. From the module directory, run:

```bash
cd ~/stock/stock
./scripts/setup_database.sh
```

The script uses an existing MariaDB/MySQL server or installs MySQL Server if none is found. It starts the service, creates the database and application user, installs `mysql-connector-python`, and creates the tables. Connection settings are stored in the module's `.env` file with permission mode `600`. Git ignores `.env`.

## Run the CLI

From the module directory, activate the virtual environment found or created by setup:

```bash
source ../venv/bin/activate
python src/stock_cli.py
```

If the virtual environment is inside the project, use `source .venv/bin/activate` or `source venv/bin/activate`, as applicable.

The main menu provides:

1. **Search for a company** by ticker or name.
2. **Browse the company list** one page at a time.
3. **Enter or update data** manually or from CSV files for one or more companies.
4. **Stock screening and early warnings** across all companies with financial reports.

In a list, enter `n`/`p` to move forward/backward, select a row number to open a company, or enter `b` to go back. The company profile shows registration details and the leadership team grouped by board, audit committee, management, and other positions, followed by former officers. The company menu provides stock prices (1), shareholders (2), upstream suppliers (3), downstream customers (4), financial reports (5), news (6), subsidiaries/associates/investments (7), data entry (8), related-party transactions (9), financial metrics (10), valuation (11), and trading activity (12): foreign investors, proprietary trading, order statistics, insider & major shareholder trades, and intraday matched trades. Insider trades show the executed share of the registered amount and a status: `reported` (a result or execution date exists), `in progress` (registration window still open) or `awaiting result`.

Organisation names in the shareholder, supplier/customer, subsidiary and related-party lists are shown in their standard form from the organisation register: the structure word followed by the canonical name, e.g. "Công ty CP Đầu Tư Thành Thành Công", "Viện Nghiên Cứu Nông Nghiệp Thành Thành Công" (foreign names as registered; people and names without a record as written in the source).

Suppliers and customers combine `supply_chain_relations` with related-party purchases and sales: a company's suppliers are the parties it buys from, plus companies whose reports show sales to it (matched by `counterparty_ticker`); customers work the other way round.

You can open search directly:

```bash
python src/stock_cli.py --query HPG --page-size 20
```

`--page-size` accepts values from 1 to 100 and defaults to 10. Enter `q` in the main menu to quit.

The CLI reads `.env` from the module directory. The `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE` environment variables can override its values.

## Browser Diagram

Besides the terminal CLI, a company can be explored as an interactive diagram in the browser. It is a separate program: it only reads the database and does not change the CLI, imports or backups.

When the module is started through its plugin entry point (`main.py`, as the host application does), the diagram server starts automatically next to the CLI and stops when the CLI exits. It runs as a child process with the module's own virtual environment (so the host's interpreter does not need FastAPI), ignores Ctrl+C pressed in the CLI, and reuses a diagram server already running on the port. If it cannot start, the CLI still runs and prints the reason; set `WEB_AUTOSTART=0` to keep it from starting. The CLI prints one line at start-up with the diagram's address (or, when it is not running, the command to start it). Started on its own (`python src/stock_cli.py`), the CLI does not start the server.

```bash
bash scripts/setup_web.sh          # once (and after git pull): Python packages, Node.js, frontend build
python src/backend/server.py       # then open http://127.0.0.1:8765  (--open opens the browser)
```

`scripts/setup_database.sh` runs `setup_web.sh` at the end (set `SKIP_WEB=1` to skip it). Node.js is only needed to build the frontend: when no Node.js 20+ is installed, the script downloads a pinned version into `.tools/` (checksum verified, no sudo, ignored by Git).

How the diagram works:

- The chosen company is the centre node. Click it to open its information **upwards**: profile, leadership, shareholders, subsidiaries, price & valuation, financial statements, financial metrics, trading activity, related-party transactions and news. Every branch shows how many records it holds; branches without data are greyed out.
- Branches with a few natural groups open into sub-branches (leadership by board/management/audit, subsidiaries by kind, statements by statement, metrics by group, trading by kind); the rest open into a table, card or chart. A table in the diagram shows 10 rows with its own pager and filters (scope, periods, Circular 99/200, snapshot date); ⤢ opens it full size in a side panel.
- **Suppliers** sit to the right and **customers** to the left. Each partner shows the amount and period of its latest disclosed transactions; the edge width follows that amount. The label on each supplier/customer edge lists what is traded in that latest period, in the report's own wording (e.g. "Mua hàng hóa", "Bán thành phẩm, hàng hóa"; related-party notes rarely name specific products), with each item's share of the total traded in that direction; items without an amount have no share, and nothing is shown when the report gives nothing. Hovering the label shows the period, the report (scope and reporting company) and its file. The ten most recent partners are shown first, then "+ N more".
- A listed partner opens into three branches that keep growing outwards: its information, its suppliers and its customers, and so on without limit. An unlisted partner opens into the transactions with it. A company already on the path appears as "↩ already shown"; click it to jump there. Hovering a company highlights its other copies.
- **Dòng tiền lớn (smart-money signal).** A listed company's node shows a level with a warning or recommendation: *Cảnh báo cao* (strong, unanimous outflow: no new buying, consider reducing), *Cảnh báo* (leaning to selling: be cautious), *Trung lập* / *Trái chiều* (nothing clear, or groups disagree: keep watching), *Tích cực* (leaning to buying: add to the watch list), *Tích cực mạnh* (strong, unanimous inflow: consider a starter position). Four groups are compared with their own habits: foreign investors, proprietary desks and the order book (average daily net flow of the last 20 sessions against the 60 sessions before; |z| ≥ 1 unusual, ≥ 2 strong; days without trades count as 0) and insiders (an executed trade in the last 60 days is strong, an open registration unusual; trades below 0.02% of the shares are ignored). Two or more strong groups in the same direction, or insiders who registered and traded, give the strong levels; groups pointing both ways give *Trái chiều*. The "Dòng tiền lớn" information branch lists the evidence per group. The rules are in `src/backend/signals.py`; they are a screening aid based on published research, not a validated forecast.
- A legend in the top-left corner explains directions, node types, badges, edge widths and trade labels; it has no background and lets clicks through to the diagram, and "Legend" folds it away (remembered by the browser).
- Drag the background to move, scroll to zoom, drag nodes to rearrange (Re-arrange undoes it). The toolbar finds nodes on the diagram, fits the view, collapses everything and exports PNG/SVG. The address bar keeps the open branches, so a view can be bookmarked or shared.

Suppliers and customers come from related-party purchases and sales (the company's own disclosures and those of other companies naming it) and from `supply_chain_relations`. Counterparties are identified through the organisation register, so every spelling of a name is one partner, and unlisted partners open into the same three branches as listed ones: their information (profile and recorded spellings, owners from listed companies' subsidiary lists, shareholdings in listed companies, disclosed transactions), suppliers and customers. Relationships disclosed by the partner itself are shown from the partner's side (a parent appears as "Parent company"). The start screen and search also find unlisted organisations by any recorded spelling. Because separate and consolidated reports repeat the same transaction and reporting periods overlap, a partner's amount is that of its latest period in one scope, never a sum.

Settings come from environment variables or `.env`: `WEB_HOST` (default `127.0.0.1`), `WEB_PORT` (default `8765`), `WEB_PUBLIC_URL` (the address shown to users) and `WEB_CORS_ORIGINS` (other origins allowed to call the API). To serve it from an Ubuntu VPS later, set `WEB_HOST=0.0.0.0` and `WEB_PUBLIC_URL=http://<server-ip>:8765`, or keep `127.0.0.1` behind a reverse proxy; the API is read-only and has no login, so restrict who can reach it. The API is documented at `/api/docs`. For frontend development, run `npm run dev` in `src/frontend/` (port 5173, forwarding `/api` to the Python server); a frontend hosted elsewhere can be built with `VITE_API_BASE_URL=http://<api-host>:<port>`.

## Enter and Update Data

Open data entry from main-menu option 3 (choose one ticker, several tickers such as `HPG,VNM`, or `*` for every ticker in the files) or from option 7 in a company menu. Both offer:

- **Manual entry** for one company and one category. Key fields come first; each other field shows its current value, and Enter keeps it.
- **CSV import** for one or several categories. With several categories, give a folder containing `<category>.csv` files or one file per category.

Every import merges cell by cell. Records are matched by their key columns. A non-empty CSV cell overwrites or fills the stored cell, and an empty or missing cell leaves it unchanged. Records not yet in the table are inserted. Changes are shown as counts and saved only after confirmation; any error rolls back the whole import.

| Category | Key columns | Other columns |
| --- | --- | --- |
| `companies` | `ticker` | `company_name` (required for new companies) and the other company fields |
| `organizations` | `canonical_name` | `full_name`, `kind`, `legal_form`, `ticker` (when listed), `tax_code`, `country`, `industry`, `address`, `website`, `parent_org` (canonical name), `status` (`auto`/`reviewed`), `note` |
| `organization_aliases` | `alias` (exact spelling) | `org` (canonical name; empty = not an organisation, e.g. a person), `source` |
| `stock_prices` | `ticker`, `price_date` | prices, `price_change`, `change_percentage`, `trading_volume`, `trading_value`, `negotiated_volume`, `negotiated_value` (`close_price` required for new rows) |
| `foreign_trades` | `ticker`, `trade_date` | `buy_volume`, `buy_value`, `sell_volume`, `sell_value`, `net_volume`, `net_value` (VND), `room_remaining`, `ownership_percentage`, `source_url` |
| `proprietary_trades` | `ticker`, `trade_date` | `buy_volume`, `buy_value`, `sell_volume`, `sell_value`, `net_volume`, `net_value` (VND), `source_url` |
| `order_statistics` | `ticker`, `trade_date` | `buy_orders`, `buy_volume`, `avg_buy_order_volume`, `sell_orders`, `sell_volume`, `avg_sell_order_volume`, `net_volume`, `source_url` |
| `intraday_trades` | `ticker`, `trade_date`, `seq` (position in the session) | `trade_time` (required for new rows), `price`, `price_change` (VND), `lot_volume`, `cumulative_volume`, `weight_percentage`, `source_url` |
| `insider_trades` | `ticker`, `trader_name`, `registration_start` | `trader_position` (position, or relationship to the insider, e.g. "Con"), `related_person_name`, `related_person_position`, `shares_before`, `registered_buy`, `registered_sell`, `registration_end`, `executed_buy`, `executed_sell`, `execution_date`, `shares_after`, `ownership_after_percentage`, `source_url` |
| `stock_holders` | `ticker`, `holder_name`, `snapshot_date` | `holder_type`, `shares_owned`, `ownership_percentage`, `source_url` |
| `finance_reports` | `ticker`, `report_type`, `report_scope`, `fiscal_year`, `fiscal_quarter` (blank = annual) | `period_start`, `period_end`, `audit_status`, income statement, balance sheet and cash-flow metrics (VND), `employee_count`, `other_metrics` (JSON), `document_storage_path`, `published_at` |
| `supply_chain_relations` | `supplier_ticker` or `supplier_org`, `customer_ticker` or `customer_org`, `product_category` | `percentage_revenue`, `source_url` (each side is a listed company by ticker or an organisation by canonical name or alias) |
| `company_news` | `ticker`, `title` | content, media, publication and source fields |
| `company_leaders` | `ticker`, `person_name`, `position` | `leader_group`, `birth_year`, `appointed_date`, `dismissed_date`, `status`, `is_legal_representative` (1/0), `source_url` |
| `company_investments` | `ticker`, `investee_name` | `investee_ticker`, `relation_type` (required for new rows), `is_direct` (1/0), `shares_owned`, `ownership_percentage`, `voting_percentage`, `investment_cost`, `charter_capital`, `contributed_capital` (VND), `business_line`, `operating_status`, `as_of_date`, `note`, `source_url` |
| `finance_report_items` | `ticker`, `report_type`, `report_scope`, `fiscal_year`, `fiscal_quarter`, `statement`, `item_code` | `item_name`, `value`, `comparative_value`, `ytd_value`, `ytd_comparative_value` (every line of the balance sheet, income statement and cash flow, by line code) |
| `related_party_transactions` | `ticker`, `report_scope`, `counterparty_name`, `transaction_type`, `description`, `period_start`, `period_end` | `counterparty_ticker`, `relationship`, `description` (wording from the report), `amount`, `currency`, `document_storage_path`, `source_url` |
| `company_tiers` | `ticker`, `tier_name` | `tier_description` (new tiers are created automatically) |

When exactly one company is selected, CSV rows may omit its ticker column (for supply chain, omit the side that is the selected company). With several companies, every row needs its ticker, and rows for other tickers are skipped. Dates accept `YYYY-MM-DD` or `DD/MM/YYYY`. Choice columns accept only their listed values (case-insensitive); manual entry shows them as a numbered list:

- `holder_type`: `individual`, `institution`, `state`, `foreign_individual`, `foreign_institution`, `other`
- `media_type`: `text`, `video`, `audio`, `image`, `document`, `other`
- `leader_group`: `board`, `management`, `audit_committee`, `other`
- `status` (leaders): `current`, `former` (blank counts as current)
- `relation_type`: `subsidiary`, `associate`, `shareholding`
- `report_scope`: `separate`, `consolidated`; `audit_status`: `unaudited`, `reviewed`, `audited`; `audit_opinion`: `unqualified`, `qualified`, `adverse`, `disclaimer`
- `relationship`: `subsidiary`, `indirect_subsidiary`, `associate`, `major_shareholder`, `co_owner`, `group_company`, `key_management`, `other`
- `transaction_type`: `sale_goods`, `sale_services`, `sale_other`, `purchase_goods`, `purchase_materials`, `purchase_services`, `interest_income`, `interest_expense`, `other_income`, `asset_disposal`, `lending`, `loan_collection`, `borrowing`, `loan_repayment`, `dividend_received`, `remuneration`, `other`

A person holding several positions has one row per position. `investee_ticker` is optional plain text, so unlisted subsidiaries can be recorded.

To change the `holder_type` list, edit `HOLDER_TYPES` in `scripts/init_database.py` and run that script again.

The same import is available without the menu:

```bash
python src/data_import.py --list
python src/data_import.py --tickers HPG,VNM stock_prices=prices.csv finance_reports=reports.csv --dry-run
```

## Organisation Register

Related-party disclosures, subsidiary lists and shareholder lists name organisations in free text, with many spellings ("CT TNHH MTV …", "Công ty TNHH Một Thành Viên …", OCR slips) and mostly without a ticker. The register gives each organisation one record, listed or not, and links every row that names it: `related_party_transactions.counterparty_org_id`, `company_investments.investee_org_id`, `stock_holders.holder_org_id`, and `supply_chain_relations.supplier_org_id` / `customer_org_id` (so a supply relation can involve an unlisted organisation).

Canonical names follow `<abbreviated legal form> <full own name>`:

- the structure word (Công ty, Tổng công ty, Ngân hàng, Viện, Quỹ, Hợp tác xã, …) is left out of the name and kept in `kind`;
- the legal form is abbreviated: `CP`, `TNHH`, `TNHH MTV`, `TNHH 2TV`, `TMCP`; `full_name` holds the fully written-out form;
- generic words abbreviated inside the own name are written out (TM → Thương Mại, DV → Dịch Vụ, SX → Sản Xuất, XNK → Xuất Nhập Khẩu, …); brand acronyms (TTC, AgriS) are kept; words are capitalised and "và" stays lower case;
- foreign organisations keep their registered name; their legal form (Pte. Ltd, GmbH, …) is noted in `legal_form`.

Organisations with different legal forms are different organisations (e.g. `CP Global Mind Business` and `TNHH Global Mind Business`), so names are matched on legal form plus own name, ignoring case, accents, punctuation and "và". People (key management, individual shareholders) and placeholder lines are recorded as aliases without an organisation and never linked.

The register is updated automatically after every import of related-party transactions, investments or shareholders (CLI, `src/data_import.py`, backup restore): new names are registered, records nobody has reviewed are refreshed, and rows are relinked. Records marked `reviewed` are never changed automatically. To review:

```bash
python scripts/organizations.py review-export            # writes processed_data/organizations_review.csv
# fill the `action` column:  ok  |  merge:<canonical name or org_id>  |  not_org
#   ok        keep the record, with any edits made in that row (name, kind, legal form, ticker, tax code, country)
#   merge:X   the names belong to organisation X (they become its aliases)
#   not_org   the names are not an organisation (a person, a placeholder)
python scripts/organizations.py review-import --dry-run   # check, then run again without --dry-run
python scripts/organizations.py build                     # register and link by hand (normally automatic)
```

The review sheet flags records without a legal form, names that also exist with another legal form, and names contained in a longer name of the same legal form. When it is unclear whether two names are one organisation, compare their tax codes (e.g. on thuvienphapluat.vn/ma-so-thue) and record the code in `tax_code`. The register and the aliases are part of the backup, so review decisions travel with it; the row links are rebuilt on restore.

## Import CafeF Trading Data

`scripts/import_cafef.py` reads files exported (or copied) from the CafeF "Dữ liệu lịch sử" tabs, writes one import CSV per category to `processed_data/cafef/`, and merges them like any CSV import (cell by cell, safe to repeat). The type is recognised from the file name; the ticker and dates come from the file contents (for intraday trades, from the name):

| File | Category | Tab |
| --- | --- | --- |
| `CafeF_LichSuGia_*.xlsx` | `stock_prices` | Lịch sử giá |
| `CafeF_ThongKeDatLenh_*.xlsx` | `order_statistics` | Thống kê đặt lệnh |
| `CafeF_GiaoDichKhoiNgoai_*.xlsx` | `foreign_trades` | Khối ngoại |
| `CafeF_GiaoDichTuDoanh_*.xlsx` | `proprietary_trades` | Tự doanh |
| `CafeF_KhopLenh_<TICKER>_<YYYYMMDD>.xlsx` | `intraday_trades` | Khớp lệnh theo phiên |
| `CafeF_GiaoDichCoDong*.txt` | `insider_trades` | Cổ đông & Nội bộ (select the page from the search form down to the end of the table and paste it into the file) |

```bash
python scripts/import_cafef.py                  # every file in new_data/
python scripts/import_cafef.py path/to/file.xlsx other_folder/ --dry-run
python scripts/import_cafef.py --prepare-only   # only write processed_data/cafef/*.csv
```

Conversions: CafeF quotes prices in thousand VND and values in VND billion; the database stores VND (21.05 → 21,050; 1.84 bn → 1,840,000,000). Insider-trade dates are DD/MM/YY and `-` means "not applicable" (stored empty). While no result has been reported (no execution date and nothing executed), CafeF shows 0 holdings after the trade; those cells are left empty. Order-statistics rows that are all zeros (the current day, before CafeF publishes it) are skipped. Every intraday row is kept, including identical rows (separate trades matched at the same moment), and `seq` keeps the export's order. Because rows are keyed by position, importing an intraday file replaces that ticker's whole session for that date (in the same transaction) instead of merging into it.

The intraday export is inconsistent: in many rows the lot and running-total columns hold amounts rather than share counts, and the running total is not monotonic. `lot_volume`, `cumulative_volume` and `weight_percentage` are therefore stored exactly as exported (thousand separators removed, no unit conversion), and should not be summed into daily volume; `stock_prices.trading_volume` is the reliable daily figure.

Importing prices recomputes `valuation_metrics` for those tickers.

## Financial Metrics and Valuation

`financial_metrics` and `valuation_metrics` are computed from the reported statements (`finance_report_items`) and prices (`stock_prices`) by `src/metrics.py`. They are rebuilt automatically after every import of reports or prices (CLI, `src/data_import.py`) and after a backup restore, so they are not part of the backup. To rebuild them by hand:

```bash
python src/metrics.py                 # all companies
python src/metrics.py --tickers SBT   # one company
```

`financial_metrics` holds one row per company, scope (separate/consolidated), period type and fiscal period:

- `quarter`: the stand-alone quarter. Quarterly cash-flow statements are year-to-date, so later quarters are derived as YTD(q) − YTD(q−1); `flow_source` says whether a row is `reported`, `derived` or `mixed`. Return ratios and warning flags are left empty for single quarters.
- `ttm`: the twelve months to the quarter end (YTD + previous year − previous YTD). The fiscal year is read from `companies.fiscal_year_start_month` (July for SBT).
- `year`: the fiscal year; audited annual reports take precedence over the fourth-quarter YTD.

`available_from` is the latest publication date of the reports a row uses; `audit_status` is the weakest status among them.

| Group | Columns |
| --- | --- |
| Cash flow | `cfo`, `cfi`, `cff`, `capex`, `free_cash_flow` (CFO + capex), `dividends_paid` |
| Cash-flow pattern | `cfo_sign`, `cfi_sign`, `cff_sign` (−1/0/1; flows below 0.5% of total assets count as 0), `cash_flow_pattern` (e.g. `+--`), `lifecycle_stage` (Dickinson 2011: introduction `-,-,+`, growth `+,-,+`, mature `+,-,-`, decline `-,+,±`, shake-out otherwise) |
| Profitability | `gross_margin`, `ebit_margin`, `net_margin`, `roe` (parent net income / average parent equity), `roa`, `roic` |
| Earnings quality | `cfo_to_net_income`, `accrual_ratio` ((net income − CFO) / average assets) |
| Leverage | `interest_bearing_debt`, `net_debt`, `debt_to_equity`, `net_debt_to_ebitda`, `interest_coverage` (EBIT / interest expense), `cfo_interest_coverage` ((CFO + interest paid + tax paid) / interest paid) |
| Liquidity | `current_ratio`, `quick_ratio`, `cash_ratio` |
| Efficiency | `dso`, `dio`, `dpo`, `cash_conversion_cycle` (days), `asset_turnover` |
| Growth | `revenue_yoy`, `net_income_yoy`, `cfo_yoy` against the same period a year earlier |
| Per share | `shares_outstanding` (common share capital / VND 10,000 par), `eps`, `bvps`, `cfo_per_share` |
| Flags (TTM and year) | `flag_negative_cfo`, `flag_negative_fcf`, `flag_low_earnings_quality` (CFO / net income < 1), `flag_high_accruals` (accrual ratio > 10%), `flag_weak_interest_coverage` (EBIT / interest < 1.5x), `flag_high_leverage` (net debt / EBITDA > 4x), `flag_low_liquidity` (current ratio < 1) |

Line codes differ between Circular 200 and Circular 99 statements (e.g. total assets 270 vs 280); `ITEMS` in `src/metrics.py` maps both, and the thresholds are in `THRESHOLDS`.

`valuation_metrics` has one row per price day: market cap, enterprise value (market cap + net debt), P/E and P/S on TTM figures, P/B, EV/EBITDA, dividend and FCF yield. Each day uses the latest TTM row whose reports were already published on that day (consolidated where available), so historical multiples carry no look-ahead. Import prices as the `stock_prices` category (close price in VND per share, not thousands); the valuations are computed during the import. The CLI shows both tables in the company menu (options 10 and 11).

## Stock Screening and Early Warnings

Main-menu option 4 sorts companies into four financial states using their newest TTM row in `financial_metrics` (consolidated when available) compared with the TTM row a year earlier. Each group lists companies that meet every condition ("match") and those missing exactly one ("near match", with the failed condition shown); choose a row to open the company. Option 5 lists companies with warning flags (most flags first) and option 6 shows every company's score in each group.

| Group | Conditions (all required) |
| --- | --- |
| Healthy & growing | cash-flow pattern `+--`; ROE > 15% and not lower than a year earlier; FCF ≥ 5% of revenue |
| Paper profits | net income up ≥ 20% year on year; CFO / net income < 0.5; receivables or inventory growing > 20 points faster than revenue |
| Cash-burning expansion | cash-flow pattern `--+`; debt/equity or interest expense up ≥ 20% year on year |
| Declining | ROE down ≥ 3 points; CFO negative or < 1.5x interest paid; CFF negative. P/E up ≥ 30% is shown for reference once prices exist |

Conditions without data count as not met. The thresholds are in `RULES` in `src/screening.py`; the screening is computed when the menu opens, so it always reflects the latest metrics.

## Financial Report Files

Report files (PDF) are kept locally under `financial_reports/<TICKER>/<fiscal_year>/`, named `<TICKER>_<fiscal_year>_Q<quarter>_<scope>_<period_start>-<period_end>.pdf` (use `FY` instead of `Q<quarter>` for annual reports). Git ignores `financial_reports/` because the files are large, so copy the folder to other machines yourself; backups contain only the paths. For example:

```text
financial_reports/SBT/2027/SBT_2027_Q1_separate_20260701-20260930.pdf
```

`fiscal_year` is the calendar year in which the fiscal year ends, matching how companies title their reports. SBT's fiscal year runs from 1 July to 30 June, so its July–September 2026 report is Q1 of fiscal year 2027; `period_start` and `period_end` always hold the exact dates. Scanned reports can be turned into import CSVs with the OCR tools in `scripts/ocr/` (see its README). Store the file path relative to the project root in `finance_reports.document_storage_path` (and in `related_party_transactions.document_storage_path` for figures taken from it). The path appears in the financial-report and supplier/customer lists.

## Back Up and Restore Data

`backups/<date>/` holds a full copy of the database data: one CSV per category (in the format described under "Enter and Update Data") plus `manifest.json` with the row count of each table. The current backup is `backups/2026-11-09/`.

Create a new backup after entering data:

```bash
python src/data_import.py --export backups/$(date +%F)
```

Restore a backup, for example on a new machine after `scripts/setup_database.sh` has created the database:

```bash
python scripts/import_companies.py --from-backup backups/2026-11-09
```

To make an already-populated database an exact copy of the backup (for example on a machine running an older version, after `git pull` and `python scripts/init_database.py`), add `--replace`; it clears the existing data in the same transaction as the import. `--dry-run` runs the restore and rolls it back. See "Update a machine that already runs an older version" in SETUP.md.

Use the newest folder under `backups/` (compare `manifest.json` row counts if unsure). `--from-backup` uses the same cell-by-cell merge as CSV import, so running it on a database that already holds data only fills or overwrites cells present in the backup, never deletes rows, and is safe to repeat. Any error rolls back the whole restore. Do not use plain `python scripts/import_companies.py` for a backup: that command reads the raw-data CSVs in `processed_data/`, which only contain the original company list.

## Company Data

The `companies` table stores charter capital, listed/outstanding/initially listed shares, first trading date, long-form company history, headquarters addresses, phone numbers, fax, email, and website in addition to ticker, name, exchange, industry, and tax code. Address and phone fields use JSON arrays of two-string arrays, for example:

```json
[["Trụ sở chính", "123 Đường A, Quận B"], ["Chi nhánh", "456 Đường C, Quận D"]]
```

Company history is stored as long text. These details are blank in the generated CSV when absent from the raw sources; source volume and source URLs are retained as metadata and are not treated as share counts or company website.

Prepare CSV files without connecting to MySQL:

```bash
python3 scripts/import_companies.py --prepare-only
```

Import the existing files in `processed_data/`:

```bash
python3 scripts/import_companies.py
```

Regenerate the CSV files and then import them:

```bash
python3 scripts/import_companies.py --prepare
```

The importer reads connection settings from `.env` or the `MYSQL_*` environment variables. It imports non-empty table CSVs in foreign-key order and leaves existing database values unchanged where an incoming value is blank.

## Project Structure

```text
stock/
├── main.py
├── module_info_draft.py
├── financial_reports/
│   └── SBT/2025, 2026, 2027/  # report PDFs: <TICKER>/<fiscal_year>/ (not in Git)
├── backups/
│   ├── 2026-11-05/, 2026-11-06/  # previous backups
│   └── 2026-11-09/     # current full data backup (one CSV per category + manifest.json)
├── src/
│   ├── backend/        # browser diagram: API (FastAPI) - server.py, app.py, sections.py, partners.py
│   ├── frontend/       # browser diagram: UI (React + React Flow) - src/, package.json; dist/ is built
│   ├── cli.py
│   ├── data_import.py
│   ├── organizations.py # organisation register: canonical names, matching, linking, review
│   ├── metrics.py      # computed financial metrics and valuations
│   ├── screening.py    # stock screening groups
│   └── stock_cli.py
├── scripts/
│   ├── ocr/            # scanned financial reports -> import CSVs (see scripts/ocr/README.md)
│   ├── import_cafef.py # CafeF trading exports (new_data/) -> import CSVs -> database
│   ├── import_companies.py
│   ├── init_database.py
│   ├── organizations.py # register commands: build, review-export, review-import
│   ├── setup_database.sh
│   └── setup_web.sh    # one-command install of the browser diagram (Python packages, Node.js, build)
├── README.md
└── SETUP.md
```

Run the lookup interface with `src/stock_cli.py`, and the browser diagram with `src/backend/server.py`. `scripts/init_database.py` is a lower-level script that accepts connection settings through command-line arguments or `MYSQL_*` environment variables; it reads `.env` when those are not set. For normal initialization, use `scripts/setup_database.sh`.

## Documentation

- [SETUP.md](SETUP.md): installation, configuration, and troubleshooting instructions.