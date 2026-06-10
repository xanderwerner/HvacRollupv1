"""Thin CLI wrapper around the pipeline stages."""
import argparse

import pipeline


def main() -> None:
    p = argparse.ArgumentParser(description="HVAC Roll-Up v1 lead sourcing")
    sub = p.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="run full pipeline + write Excel")
    run_p.add_argument("-n", "--limit", type=int, default=10)

    disc_p = sub.add_parser("discover", help="discover + filter only (no Excel)")
    disc_p.add_argument("-n", "--limit", type=int, default=10)

    args = p.parse_args()
    if args.cmd == "run":
        pipeline.run(limit=args.limit, write_excel=True)
    elif args.cmd == "discover":
        res = pipeline.run(limit=args.limit, write_excel=False)
        for lead in res["top"][: args.limit]:
            print(f"{lead.buy_box_fit:8s} {lead.review_count:>4}rv {lead.rating}  "
                  f"{lead.company_name} ({lead.city})")


if __name__ == "__main__":
    main()
