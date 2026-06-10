"""Entry point: run the full v1 free-spine pipeline and write 10 leads.

Usage:  python run.py [N]      (N = number of leads, default 10)
"""
import subprocess
import sys

import config
import pipeline


def close_excel_workbook() -> None:
    """Best-effort: ask Excel to close the target workbook (no save) so the
    file is free to write. Safe no-op if Excel isn't running."""
    name = config.EXCEL_PATH.name
    script = (
        'tell application "System Events"\n'
        '  if (exists process "Microsoft Excel") then\n'
        '    tell application "Microsoft Excel"\n'
        f'      repeat with w in (every workbook whose name is "{name}")\n'
        '        close w saving no\n'
        '      end repeat\n'
        '    end tell\n'
        '  end if\n'
        'end tell'
    )
    try:
        subprocess.run(["osascript", "-e", script], timeout=20,
                       capture_output=True, text=True)
    except Exception as exc:
        print(f"(could not auto-close Excel: {exc} — write may still succeed)")


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(f"HVAC Roll-Up v1 — sourcing {limit} qualified leads "
          f"(-> {config.WRITE_TARGET})\n")
    if config.WRITE_TARGET == "excel":
        close_excel_workbook()
    result = pipeline.run(limit=limit)

    print("\n================ SUMMARY ================")
    print(f"raw results      : {result['raw']}")
    print(f"unique companies : {result['unique']}")
    print(f"buy-box survivors: {result['survivors']}")
    print(f"written to Excel : {len(result['written'])}")
    for i, name in enumerate(result["written"], 1):
        print(f"   {i:2d}. {name}")


if __name__ == "__main__":
    main()
