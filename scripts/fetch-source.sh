#!/usr/bin/env bash
# Checks out an asset's source directory at the commit its asset.json pins, fetching only that directory's blobs.
# Usage: scripts/fetch-source.sh <name> <dir>   then: scripts/pack.sh <dir>/Resources <out> <name>
# A second name into the same <dir> must pin the same repository and commit; it widens the checkout.
set -euo pipefail

[[ $# -eq 2 ]] || { printf 'usage: %s <name> <dir>\n' "$0" >&2; exit 2; }
name="$1"
dir="$2"

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
spec="${root}/assets/${name}/asset.json"
[[ -f "${spec}" ]] || { printf 'no %s\n' "${spec}" >&2; exit 2; }
repo="$(jq -r '.source.repository' "${spec}")"
commit="$(jq -r '.source.commit' "${spec}")"
path="$(jq -r '.source.path' "${spec}")"

if [[ -d "${dir}/.git" ]]; then
  have="$(git -C "${dir}" remote get-url origin)"
  [[ "${have}" == "${repo}" ]] || { printf '%s fetches %s, not %s\n' "${dir}" "${have}" "${repo}" >&2; exit 1; }
  head="$(git -C "${dir}" rev-parse HEAD)"
  [[ "${head}" == "${commit}" ]] || { printf '%s is at %s, not %s\n' "${dir}" "${head}" "${commit}" >&2; exit 1; }
  git -C "${dir}" sparse-checkout add "/${path}/"
else
  git init -q "${dir}"
  git -C "${dir}" remote add origin "${repo}"
  git -C "${dir}" sparse-checkout set --no-cone "/${path}/"
fi
git -C "${dir}" fetch -q --depth 1 --filter=blob:none origin "${commit}"
git -C "${dir}" -c advice.detachedHead=false checkout -q "${commit}"
[[ -d "${dir}/${path}" ]] || { printf '%s has no %s at %s\n' "${repo}" "${path}" "${commit}" >&2; exit 1; }
printf '%s\n' "${dir}/${path}"
