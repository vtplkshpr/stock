# Stock

A terminal-based module for looking up listed companies. It reads data from MySQL/MariaDB and loads result lists one page at a time.

## Features

- Search for companies by ticker or name.
- Browse companies already stored in the database.
- View company details, stock prices, shareholders, suppliers, customers, financial reports, and news.
- Paginate with `LIMIT/OFFSET` queries instead of loading the entire result set into memory.
- Fetch full news text only after a news item is selected.

The database stores these data groups:

- `companies`: basic information and listing ticker.
- `stock_prices`: daily prices and trading volume.
- `stock_holders`: shareholders and ownership percentages by snapshot date.
- `finance_reports`: financial metrics, additional metrics, and document paths.
- `tiers`, `company_tiers`: company classifications.
- `supply_chain_relations`: supplier and customer relationships.
- `company_news`: news text and media metadata or paths.

The scripts currently create the schema and provide a CLI for reading data. There is no market-data collection or import job yet, so the views remain empty until data is loaded into the database.

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
python scripts/stock_cli.py
```

If the virtual environment is inside the project, use `source .venv/bin/activate` or `source venv/bin/activate`, as applicable.

The main menu provides:

1. **Search for a company** by ticker or name.
2. **Browse the company list** one page at a time.

In a list, enter `n`/`p` to move forward/backward, select a row number to open a company, or enter `b` to go back. The company menu provides stock prices, shareholders, upstream suppliers, downstream customers, financial reports, and news.

You can open search directly:

```bash
python scripts/stock_cli.py --query HPG --page-size 20
```

`--page-size` accepts values from 1 to 100 and defaults to 10. Enter `q` in the main menu to quit.

The CLI reads `.env` from the module directory. The `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE` environment variables can override its values.

## Project Structure

```text
stock/
├── main.py
├── module_info_draft.py
├── scripts/
│   ├── init_database.py
│   ├── setup_database.sh
│   └── stock_cli.py
├── README.md
└── SETUP.md
```

Run the lookup interface with `scripts/stock_cli.py`. `scripts/init_database.py` is a lower-level script that accepts connection settings through command-line arguments or `MYSQL_*` environment variables; it does not read `.env` itself. For normal initialization, use `scripts/setup_database.sh`.

## Documentation

- [SETUP.md](SETUP.md): installation, configuration, and troubleshooting instructions.