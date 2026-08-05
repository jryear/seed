#!/usr/bin/env bash
# One-time setup. Fails loudly — never claims readiness after an error.
set -euo pipefail
trap 'echo "setup FAILED — repo is NOT ready" >&2' ERR
cd "$(dirname "$0")"
command -v git >/dev/null || { echo "setup FAILED — git not found" >&2; exit 1; }
mkdir -p history inbox
[ -d .git ] || git init -q
required=(seed.md setup.sh bin/probe.py bin/seedd.py)
paths=()
for path in "${required[@]}"; do
  if [ ! -f "$path" ] || [ -L "$path" ]; then
    echo "setup FAILED — expected regular file: $path" >&2
    exit 1
  fi
  paths+=("$path")
done
for optional in tests/test_seed.py .gitignore evidence.jsonl; do
  if [ -e "$optional" ] || [ -L "$optional" ]; then
    if [ ! -f "$optional" ] || [ -L "$optional" ]; then
      echo "setup FAILED — expected regular file: $optional" >&2
      exit 1
    fi
    paths+=("$optional")
  fi
done
git add -- "${paths[@]}"
if ! git diff --cached --quiet -- "${paths[@]}"; then
  git -c core.hooksPath=/dev/null commit --only -qm "seed init" -- "${paths[@]}"
fi
echo "seed repo ready — start the loop with: python3 bin/seedd.py"
