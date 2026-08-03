#!/usr/bin/env bash
# One-time setup. Fails loudly — never claims readiness after an error.
set -euo pipefail
trap 'echo "setup FAILED — repo is NOT ready" >&2' ERR
cd "$(dirname "$0")"
command -v git >/dev/null || { echo "setup FAILED — git not found" >&2; exit 1; }
mkdir -p history inbox
[ -d .git ] || git init -q
git add -A
if ! git diff --cached --quiet; then
  git commit -qm "seed init"
fi
echo "seed repo ready — start the loop with: python3 bin/seedd.py"
