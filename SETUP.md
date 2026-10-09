# Installation and Usage

This guide covers the current stock module. It uses MySQL/MariaDB to store data and provides a terminal CLI for company lookups.

## Requirements

- Ubuntu or Debian.
- Python 3.10 or later and `venv`.
- `sudo` access to install/start the database server and create a database user.
- An internet connection if MySQL Server or the Python connector must be installed.

The script uses an existing MariaDB or MySQL server. If no server is found, it installs `mysql-server`. The current development machine uses MariaDB.

## Set Up the Database

From the module directory:

```bash
cd ~/stock/stock
./scripts/setup_database.sh
```

The script will:

1. Check for, install if needed, and start MariaDB or MySQL.
2. Create the database (default: `stock_market`) and application user (default: `stock_app`).
3. Generate a random password if `MYSQL_PASSWORD` is not provided.
4. Use an existing virtual environment or create one for the project, then install `mysql-connector-python`.
5. Write connection settings to `.env` in the module root and initialize the tables.

Setup uses administrative access to the database over its local socket and may prompt for your `sudo` password. It does not require logging in as MySQL `root` with a password.

### Connection Settings

The `.env` file contains settings such as:

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=stock_app
MYSQL_PASSWORD=<generated-password>
MYSQL_DATABASE=stock_market
```

These are example variable names, not shared credentials. Setup creates the file with permission mode `600`; `.gitignore` excludes `.env` from Git. Do not commit or share this file. The `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE` environment variables override `.env` values when running the CLI.

## Database Schema

`scripts/init_database.py` creates the following InnoDB tables using `utf8mb4`:

| Table | Contents |
| --- | --- |
| `companies` | Ticker, company name, exchange, industry, and basic information |
| `stock_prices` | Daily open/high/low/close prices and trading volume |
| `stock_holders` | Shareholders, shares held, and ownership percentage by snapshot date |
| `finance_reports` | Financial metrics, additional metrics in JSON, and document paths |
| `tiers` | Company classification tiers |
| `company_tiers` | Links companies to tiers |
| `supply_chain_relations` | Suppliers, customers, product categories, and revenue percentages |
| `company_news` | Text news and media URLs or storage paths |

Foreign keys link related records to `companies`; deleting a company cascades to its dependent records. Initialization uses `CREATE TABLE IF NOT EXISTS`, so it can be rerun to create missing tables without deleting existing data.

## Run the CLI

Setup looks for a virtual environment in the module's `.venv/` or `venv/` directory, then in `../venv/`. Activate the environment used by setup to use the short `python` command:

```bash
cd ~/stock/stock
source ../venv/bin/activate
python scripts/stock_cli.py
```

If setup used a different virtual environment, adjust the `source` path or invoke its Python executable directly, for example:

```bash
../venv/bin/python scripts/stock_cli.py
```

The CLI main menu provides:

1. **Search for a company** by ticker or name.
2. **Browse the company list** one page at a time.

In a list, enter a row number to select a company, `n`/`p` to move between pages, or `b` to go back. The company detail menu includes stock prices, shareholders, upstream suppliers, downstream customers, financial reports, and news. Lists are queried one page at a time; full news text is fetched only after selecting an item.

Search directly without opening the main menu:

```bash
python scripts/stock_cli.py --query HPG --page-size 20
```

The default page size is 10; accepted values range from 1 to 100. Use `--help` to see the CLI options.

## Loading Data

`setup_database.sh` and `init_database.py` install/initialize the database schema; the CLI only reads existing data. The project does not yet include an automated collector or importer for companies, prices, shareholders, reports, or news. A newly initialized database may therefore return no results until data is loaded separately.

Stock prices and financial metrics use `DECIMAL` columns. If a financial report cannot be parsed into numeric metrics, its document path can be stored in `finance_reports.document_storage_path`. News can store text content, media URLs, or storage paths in `company_news`.

## Troubleshooting

### Cannot connect to the database

Check the service status:

```bash
sudo systemctl status mariadb
```

If you use MySQL instead of MariaDB:

```bash
sudo systemctl status mysql
```

Verify that `.env` exists in the module directory and has permission mode `600`. Do not print or share `MYSQL_PASSWORD` when sharing logs.

### Database access denied

Do not switch the CLI to the `root` account. Run `./scripts/setup_database.sh` again from a terminal to create/update the `stock_app` user through the administrative socket and write fresh credentials to `.env`.

### Missing `mysql.connector`

Run the CLI using the virtual environment created by setup, or activate the correct environment and install the connector:

```bash
python -m pip install mysql-connector-python
```

### No companies found

Check whether data has been loaded into the database. Setup only creates the tables; it does not download company or market data.