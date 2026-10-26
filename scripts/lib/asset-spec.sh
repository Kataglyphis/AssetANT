#!/usr/bin/env bash

asset_spec_require() {
  local root spec
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || return 2
  spec="${root}/assets/${1}/asset.json"
  if [[ ! -f "${spec}" ]]; then
    printf 'no %s\n' "${spec}" >&2
    return 2
  fi
  printf '%s\n' "${spec}"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  asset_spec_require "${1:-}"
fi
