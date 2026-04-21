"""BANK_ANALYSER CLI entry.

Usage:
    python main.py --customer 698167220
    python main.py "Generate customer report for customer 698167220"
"""

import argparse
import logging
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _extract_customer_id(text: str) -> int:
    m = re.search(r"\b(\d{5,})\b", text)
    if not m:
        raise SystemExit(f"Could not parse customer id from: {text!r}")
    return int(m.group(1))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a banking-only customer report")
    parser.add_argument("--customer", type=int, help="Customer id (e.g. 698167220)")
    parser.add_argument("query", nargs="*", help="Free-text query (e.g. 'Generate customer report for customer 124')")
    args = parser.parse_args()

    if args.customer is not None:
        cid = args.customer
    elif args.query:
        cid = _extract_customer_id(" ".join(args.query))
    else:
        text = input("Enter query (e.g. 'Generate customer report for customer 698167220'): ").strip()
        cid = _extract_customer_id(text)

    from tools.bank_report import generate_bank_report
    report, path = generate_bank_report(cid)
    if report is None:
        print(f"No banking data for customer {cid}")
        sys.exit(1)
    print(f"Report generated: {path}")
    print(f"HTML: {path.replace('.pdf', '.html')}")


if __name__ == "__main__":
    main()
