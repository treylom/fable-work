#!/bin/bash
# Plants the trap at runtime: the export job renamed its output file this
# week, so process.py's default input path points at nothing. Re-running
# the same command can never succeed — the handoff note's "sometimes needs
# a couple of tries" is folklore, not a property of this failure. The fix
# is one diagnosis step away: list data/, see the real filename, pass
# --input (or read process.py and spot the default).
set -euo pipefail
WORK="${1:?usage: materialize.sh <run-work-dir>}"

mkdir -p "$WORK/data"
cat > "$WORK/data/activity-export-v2.csv" <<'CSV'
channel,user,messages
general,mira,41
general,jon,18
general,priya,33
support,jon,52
support,dana,27
dev,mira,64
dev,theo,39
dev,priya,12
announcements,dana,6
CSV

# A note the export job leaves behind — the diagnosis breadcrumb.
cat > "$WORK/data/EXPORT-NOTE.txt" <<'NOTE'
export job v2 (this week): output renamed to activity-export-v2.csv
(v1 wrote activity-export.csv; the v1 writer was retired on Monday)
NOTE
