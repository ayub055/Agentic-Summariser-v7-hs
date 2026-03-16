"""
Batch combined-report generator.

Generates a combined report (banking + bureau) for every CRN in the input
list, writes one Excel row per customer, then merges all rows into a single
master Excel file.

Usage:
    python batch_reports.py [--crns 100070028 200001234 ...]
                            [--crn-file path/to/crns.txt]
                            [--source tl_features|rgs]
                            [--output reports/batch_output.xlsx]
                            [--resume]      # skip CRNs already done
                            [--force]       # reprocess all even if done

Resume behaviour:
    By default the script processes every CRN.  Pass --resume to skip any
    CRN whose per-customer Excel file (reports/excel/<crn>.xlsx) already
    exists — i.e. it completed successfully in a prior run.  The final
    merged Excel is built from ALL files in the excel directory (old + new),
    so the output is always complete.

If neither --crns nor --crn-file is supplied, the script reads all unique
CRNs from the chosen --source automatically.
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
    """Read unique CRNs from the main transaction file (rgs.csv)."""
    from data.loader import get_transactions_df
    df = get_transactions_df()
    return sorted(df["cust_id"].unique().tolist())


def _load_crns_from_tl_features() -> list:
    """Read unique CRNs from tl_features.csv."""
    import pandas as pd
    from config.settings import TL_FEATURES_FILE, TL_FEATURES_DELIMITER
    df = pd.read_csv(TL_FEATURES_FILE, sep=TL_FEATURES_DELIMITER, usecols=["crn"])
    return sorted(df["crn"].dropna().astype(int).unique().tolist())


def run_batch(crns: list, output_excel: str, resume: bool = False) -> None:
    from tools.combined_report import generate_combined_report_pdf, _EXCEL_OUTPUT_DIR
    from tools.excel_exporter import merge_excel_reports

    excel_dir = Path(_EXCEL_OUTPUT_DIR)
    total = len(crns)
    succeeded, failed, skipped = 0, 0, 0

    for i, crn in enumerate(crns, 1):
        excel_file = excel_dir / f"{crn}.xlsx"

        if resume and excel_file.exists():
            logger.info("[%d/%d] SKIP CRN %s — already done (resume mode)", i, total, crn)
            skipped += 1
            continue

        logger.info("[%d/%d] Processing CRN %s …", i, total, crn)
        try:
            generate_combined_report_pdf(int(crn))
            succeeded += 1
        except Exception as exc:
            logger.error("CRN %s failed: %s", crn, exc)
            failed += 1

    logger.info(
        "Done. %d succeeded, %d failed, %d skipped (already done).",
        succeeded, failed, skipped,
    )

    # Merge ALL per-customer Excel files (old + new) into one master file
    if excel_dir.exists() and any(excel_dir.glob("*.xlsx")):
        try:
            merged_path = merge_excel_reports(str(excel_dir), output_excel)
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
        "--source",
        choices=["rgs", "tl_features"],
        default="rgs",
        help="Auto-discover CRNs from: 'rgs' (rgs.csv, default) or 'tl_features' (tl_features.csv)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="reports/batch_output.xlsx",
        help="Output path for merged Excel (default: reports/batch_output.xlsx)",
    )
    resume_group = parser.add_mutually_exclusive_group()
    resume_group.add_argument(
        "--resume",
        action="store_true",
        help="Skip CRNs whose per-customer Excel already exists (safe to use after a crash/reset)",
    )
    resume_group.add_argument(
        "--force",
        action="store_true",
        help="Reprocess all CRNs even if their Excel already exists (overrides --resume)",
    )
    args = parser.parse_args()

    if args.crn_file:
        crns = [int(line.strip()) for line in open(args.crn_file) if line.strip()]
    elif args.crns:
        crns = args.crns
    elif args.source == "tl_features":
        logger.info("No CRNs supplied — reading from tl_features.csv …")
        crns = _load_crns_from_tl_features()
    else:
        logger.info("No CRNs supplied — reading from data/rgs.csv …")
        crns = _load_crns_from_csv()

    if not crns:
        logger.error("No CRNs to process. Exiting.")
        sys.exit(1)

    resume = args.resume and not args.force
    if resume:
        logger.info("Resume mode ON — CRNs with existing Excel will be skipped.")

    logger.info("Processing %d CRNs …", len(crns))
    run_batch(crns, args.output, resume=resume)


if __name__ == "__main__":
    main()
