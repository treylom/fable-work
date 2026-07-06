#!/bin/bash
# repo-hygiene.sh — public-repo hygiene scan. Run before every push.
#
# Catches the leak class that slipped into public twice in one week: a
# private person-reference / internal bot name / internal directive quote
# sitting inside an otherwise-fine commit (once in a code comment, once in
# a planning doc). Generalization passes kept missing Korean prose, so
# this is the mechanical backstop: grep tracked files for the private
# tokens; any hit = exit 1 with the offending lines.
#
# Functional Korean (regex character classes, test fixtures, ko README
# prose) is fine — the scan targets *specific private names/handles*, not
# the Korean language.
#
# usage: scripts/repo-hygiene.sh   (from anywhere inside the repo)
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# Private tokens that must never appear in a public tree. Extend as needed.
PRIVATE_TOKENS='재경님|글재경|카파시|코난|스트레인지|손석희|허사비스|아크토푸|tofu_mac|obsidian-ai-vault|AI_Second_Brain'

HITS=$(git grep -nE "$PRIVATE_TOKENS" -- ':!scripts/repo-hygiene.sh' || true)
if [ -n "$HITS" ]; then
  echo "repo-hygiene: private tokens found in tracked files:" >&2
  echo "$HITS" >&2
  exit 1
fi

# Secret shapes (belt over the reviewer's braces).
SECRETS=$(git grep -nE 'sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|xox[baprs]-[A-Za-z0-9-]{12,}|ntn_[A-Za-z0-9]{12,}|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY' -- ':!scripts/repo-hygiene.sh' || true)
if [ -n "$SECRETS" ]; then
  echo "repo-hygiene: secret-shaped strings found:" >&2
  echo "$SECRETS" >&2
  exit 1
fi

echo "repo-hygiene: clean ($(git ls-files | wc -l | tr -d ' ') tracked files scanned)"
