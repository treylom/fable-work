#!/usr/bin/env python3
"""Weekly activity summarizer.

Reads the raw activity export (CSV: channel,user,messages) and writes
summary.txt with per-channel totals and top contributors.
"""
import argparse
import collections
import csv
import pathlib
import sys

DEFAULT_INPUT = "data/activity-export.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=DEFAULT_INPUT, help="activity export CSV")
    parser.add_argument("--output", default="summary.txt")
    args = parser.parse_args()

    src = pathlib.Path(args.input)
    rows = []
    with src.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append(row)

    channels: collections.Counter = collections.Counter()
    users: collections.Counter = collections.Counter()
    for row in rows:
        n = int(row["messages"])
        channels[row["channel"]] += n
        users[row["user"]] += n

    out = pathlib.Path(args.output)
    with out.open("w", encoding="utf-8") as fh:
        fh.write(f"rows: {len(rows)}\n")
        fh.write(f"total messages: {sum(channels.values())}\n")
        fh.write("per channel:\n")
        for name, count in channels.most_common():
            fh.write(f"  {name}: {count}\n")
        fh.write("top contributors:\n")
        for name, count in users.most_common(3):
            fh.write(f"  {name}: {count}\n")
    print(f"wrote {out} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
