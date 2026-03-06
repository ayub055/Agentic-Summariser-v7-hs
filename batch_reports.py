"""
Batch combined-report generator.

Generates a combined report (banking + bureau) for every CRN in the input
list, writes one Excel row per customer, then merges all rows into a single
master Excel file.

Usage:
    python batch_reports.py [--crns 100070028 200001234 ...]
                            [--crn-file path/to/crns.txt]
                            [--output reports/batch_output.xlsx]

If neither --crns nor --crn-file is supplied, the script reads all unique
CRNs from data/rgs.csv automatically.
"""

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("batch_reports")


def _load_crns_from_csv() -> list:
    """Read unique CRNs from the main transaction file."""
    from data.loader import get_transactions_df
    df = get_transactions_df()
    return sorted(df["cust_id"].unique().tolist())


def run_batch(crns: list, output_excel: str) -> None:
    from tools.combined_report import generate_combined_report_pdf, _EXCEL_OUTPUT_DIR
    from tools.excel_exporter import merge_excel_reports

    total = len(crns)
    succeeded, failed = 0, 0

    for i, crn in enumerate(crns, 1):
        logger.info("[%d/%d] Processing CRN %s …", i, total, crn)
        try:
            generate_combined_report_pdf(int(crn))
            succeeded += 1
        except Exception as exc:
            logger.error("CRN %s failed: %s", crn, exc)
            failed += 1

    logger.info("Done. %d succeeded, %d failed.", succeeded, failed)

    # Merge all per-customer Excel files into one master file
    excel_dir = _EXCEL_OUTPUT_DIR
    if Path(excel_dir).exists() and any(Path(excel_dir).glob("*.xlsx")):
        try:
            merged_path = merge_excel_reports(excel_dir, output_excel)
            logger.info("Master Excel written → %s", merged_path)
        except Exception as exc:
            logger.error("Excel merge failed: %s", exc)
    else:
        logger.warning("No per-customer Excel files found in %s", excel_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch combined report generator")
    parser.add_argument("--crns", nargs="+", type=int, help="List of CRNs to process")
    parser.add_argument("--crn-file", type=str, help="Text file with one CRN per line")
    parser.add_argument(
        "--output",
        type=str,
        default="reports/batch_output.xlsx",
        help="Output path for merged Excel (default: reports/batch_output.xlsx)",
    )
    args = parser.parse_args()

    if args.crn_file:
        crns = [int(line.strip()) for line in open(args.crn_file) if line.strip()]
    elif args.crns:
        crns = args.crns
    else:
        logger.info("No CRNs supplied — reading from data/rgs.csv …")
        crns = _load_crns_from_csv()

    if not crns:
        logger.error("No CRNs to process. Exiting.")
        sys.exit(1)

    logger.info("Processing %d CRNs …", len(crns))
    run_batch(crns, args.output)


if __name__ == "__main__":
    main()
