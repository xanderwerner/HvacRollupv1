"""Source fresh 10+ employee trades leads from Apollo (with owner contacts)
and write them into the Google Sheet Organic List.

Usage:  python run_apollo.py [N]    (N = target new leads, default 12)
"""
import sys

import apollo_source
import gsheets_writer


def main():
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    print(f"Apollo sourcing — {target} 10+ employee trades leads (Phoenix metro)\n")
    rows = apollo_source.source(target=target, reveal_cap=target * 2 + 6)
    written = gsheets_writer.append_row_dicts(rows)
    print(f"\nwrote {len(written)} new Apollo-sourced rows to the Google Sheet:")
    for i, n in enumerate(written, 1):
        print(f"  {i:2d}. {n}")


if __name__ == "__main__":
    main()
