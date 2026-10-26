#!/usr/bin/env bash
# Asset checks run inside the family image to use its pinned Python.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${root}"
# shellcheck source=lib/antfrastructure.sh
source "${root}/scripts/lib/antfrastructure.sh"
antfrastructure_source linux/scripts/01-core/python-probe.sh
ci_image_python_require check.sh docs/assets.md#layout || exit $?
python="${PREFLIGHT_PYTHON}"
printf 'python: %s\n' "$("${python}" --version)"

"${python}" -I scripts/check.py
"${python}" -I -m unittest discover -s scripts/tests -p 'test_*.py'
bash scripts/tests/test-asset-spec.sh
printf 'check: ok\n'
