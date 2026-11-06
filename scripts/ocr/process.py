"""Turn one scanned financial report into import CSVs: OCR (cached), parse, validate, assemble.

usage: python scripts/ocr/process.py scripts/ocr/configs/SBT/SBT_2026_Q1_separate.json

Run from the project root with the OCR virtual environment's Python. The CSVs land in the
config's out_dir; the script prints the data_import command that loads them.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def main() -> int:
    config_path = Path(sys.argv[1])
    config = json.loads(config_path.read_text(encoding="utf-8"))
    pdf = Path(config["source_pdf"])
    ocr_dir = Path(config["ocr_dir"])
    if not pdf.is_file():
        print(f"Missing report file: {pdf}", file=sys.stderr)
        return 1
    if ocr_dir.name != pdf.stem:
        print(f"ocr_dir must end with the PDF name ({pdf.stem})", file=sys.stderr)
        return 1
    # run_ocr.py skips pages already OCR'd, so re-running is cheap.
    subprocess.run([sys.executable, str(HERE / "run_ocr.py"), str(pdf), str(ocr_dir.parent)], check=True)
    result = subprocess.run([sys.executable, str(HERE / "assemble.py"), str(config_path)])
    if result.returncode:
        return result.returncode
    out = Path(config["out_dir"])
    files = " ".join(
        f"{csv_file.stem}={csv_file}"
        for csv_file in sorted(out.glob("*.csv"))
    )
    print("\nCheck the output above (ALL CHECKS PASS, no UNMAPPED/DUPLICATE lines), then load with:")
    print(f"  python src/data_import.py --tickers SBT {files} --dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
