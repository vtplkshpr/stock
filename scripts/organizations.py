"""Maintain the organisation register (see src/organizations.py).

  python scripts/organizations.py build                       # register new names, link rows
  python scripts/organizations.py review-export review.csv    # write the review sheet
  python scripts/organizations.py review-import review.csv    # apply its `action` column

Every command runs in one transaction; --dry-run reports and rolls back.
"""

import argparse
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR / "src"))

import organizations  # noqa: E402
import stock_cli  # noqa: E402

DEFAULT_REVIEW = MODULE_DIR / "processed_data" / "organizations_review.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintain the organisation register.")
    parser.add_argument("command", choices=("build", "review-export", "review-import"))
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_REVIEW,
                        help=f"review CSV (default {DEFAULT_REVIEW.relative_to(MODULE_DIR)})")
    parser.add_argument("--dry-run", action="store_true", help="Run, report, then roll back.")
    args = parser.parse_args()

    import mysql.connector

    config = stock_cli.load_database_config()
    config["port"] = int(config["port"])
    connection = mysql.connector.connect(**config)
    try:
        connection.start_transaction()
        if args.command == "build":
            print(organizations.build(connection))
        elif args.command == "review-export":
            count = organizations.export_review(connection, args.path)
            print(f"{count} organisations written to {args.path}")
            print("Fill the `action` column (ok / merge:<canonical name or org_id> / not_org), then run review-import.")
        else:
            print(organizations.apply_review(connection, args.path))
        if args.dry_run:
            connection.rollback()
            print("Dry run: nothing was saved.")
        else:
            connection.commit()
    except (ValueError, OSError) as exc:
        connection.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
