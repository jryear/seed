#!/usr/bin/env bash
# One-time setup. Run from wherever you want the seed repo to live:
#   bash setup.sh
set -e
cd "$(dirname "$0")"
mkdir -p history inbox bin
git init -q 2>/dev/null || true
git add -A && git commit -q -m "seed v0" 2>/dev/null || true
echo "seed repo ready. Start the loop with:  python3 bin/seedd.py"
