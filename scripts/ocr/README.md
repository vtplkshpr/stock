# Financial report OCR

Turns scanned financial-report PDFs (Vietnamese VAS statements, Circular 200 or Circular 99 layout) into the CSVs that `src/data_import.py` loads: the report summary (`finance_reports`), every statement line (`finance_report_items`), related-party transactions, and optional leadership changes.

## Setup

The OCR models are large, so use a separate virtual environment:

```bash
python3 -m venv ~/ocr-venv
~/ocr-venv/bin/pip install -r scripts/ocr/requirements.txt
```

## Process one report

1. Put the PDF under `financial_reports/<TICKER>/<fiscal_year>/` with the standard name (see "Financial Report Files" in the main README).
2. Write a config in `scripts/ocr/configs/<TICKER>/` (copy a similar one; fields below).
3. From the project root:

   ```bash
   ~/ocr-venv/bin/python scripts/ocr/process.py scripts/ocr/configs/SBT/SBT_2026_Q1_separate.json
   ```

   OCR takes about 5 minutes per 60-page report and is cached in `ocr_work/` (ignored by Git), so re-runs are fast.
4. Read the output:
   - `ALL CHECKS PASS`: every total and subtotal of the three statements matches, in every column. Otherwise each mismatch is listed; fix it with `statement_fix` or `set` in the config and run again. `off by 1 VND` notes are rounding in the source and are accepted.
   - `match 0.xx: OCR name -> canonical name`: counterparty names matched to `registry.json`. Matches below 0.80 are not used; map them in `parties` or add the company to the registry.
   - `UNMAPPED PARTIES` / `DUPLICATE KEYS`: must be resolved before importing.
5. Load the printed `data_import` command with `--dry-run` first, then without it, and refresh the backup (`python src/data_import.py --export backups/<date>`).

Process reports one at a time and compare the related-party rows with the page images for new layouts; the extractor reads table positions and can misassign rows when a scan is badly skewed.

## Config fields

| Field | Meaning |
| --- | --- |
| `source_pdf` | Report file, relative to the project root |
| `ocr_dir`, `out_dir` | `ocr_work/out/<pdf name>` and `ocr_work/csv/<pdf name>` |
| `meta` | `report_type` (`quarterly`/`annual`), `scope`, `fiscal_year`, `quarter`, `period_start`, `period_end`, `published_at`, `document`, and for audited reports `audit_status`, `auditor`, `audit_opinion`, `audit_report_date` |
| `employees` | `total`, plus optional `permanent_employees`, `seasonal_employees` (stored in `other_metrics`) |
| `statement_fix` | `{"cash_flow": {"60@11": "09"}}`: change a misread line code (`code@page`, `#n` for the n-th occurrence) |
| `set` | `{"balance_sheet": {"121": [current, comparative]}}`: values OCR missed or misread, taken from the page image or derived from totals (check the derived figure appears on the page) |
| `deskew` | Page numbers whose rows should be rebuilt after skew correction |
| `parties` | `{"OCR name": [canonical name, relationship, ticker]}` for names the registry cannot match (abbreviations such as "Công ty BHC") |
| `description_fix` | `{"OCR text": "standard wording"}` for truncated transaction descriptions |
| `skip_rows`, `extra_rows` | Drop `[page, amount]` rows / add `[name, type, description, amount]` rows by hand |
| `remuneration` | `[name, description, amount]` rows from the board and management remuneration tables (current period) |
| `leaders` | `[name, position, group, appointed_date, dismissed_date, status]` updates from the "Thông tin chung" (general information) pages |

## Files

- `run_ocr.py`: OCR each page (rotating sideways pages) into `pNN.json` with text lines, rows and token positions.
- `parse_reports.py`: find the statement pages and read line codes and values by column position.
- `build.py`: validate totals (Circular 200 and 99 rules) and write `finance_report_items.csv`.
- `rpt.py`, `rpt2.py`: read related-party transaction tables; standard description vocabulary and transaction types.
- `assemble.py`: combine everything into the import CSVs.
- `vas_tt200.py`, `vas_tt99.py`: standard line names per circular.
- `configs/SBT/`: the configs of the SBT reports imported so far. The July–September 2026 separate report was entered by hand; its statement lines were added with `build.py` only.
