#!/usr/bin/env bash
# The image's pinned CPython is the consumer runtime.
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
"${python}" -I -m unittest discover -s scripts/tests -p 'test_*.py'
shellcheck -x -P scripts -P scripts/lib scripts/*.sh scripts/lib/*.sh
printf 'check: ok\n'
