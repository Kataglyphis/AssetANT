#!/usr/bin/env bash
# Every asset.json is valid and listed, and every script passes shellcheck, on the image's pinned CPython (check.yml runs it).
# Usage: scripts/check.sh   (in the family's Linux image)
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${root}"
# The pinned CPython lives in the image's venv; the runner's own python3 is another interpreter.
if [ ! -x /opt/venv/bin/python3 ] || [ -z "${PYTHON_MAJOR_MINOR:-}" ]; then
  printf 'check.sh runs in the family Linux image (docs/assets.md#layout)\n' >&2
  exit 2
fi
python=/opt/venv/bin/python3
printf 'python: %s\n' "$("${python}" --version)"

"${python}" -I scripts/check.py
shellcheck scripts/*.sh
printf 'check: ok\n'
