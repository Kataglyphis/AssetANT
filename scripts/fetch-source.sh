#!/usr/bin/env bash
# A reused checkout must preserve the repository and commit pinned by asset.json.
set -euo pipefail

[[ $# -eq 2 ]] || { printf 'usage: %s <name> <dir>\n' "$0" >&2; exit 2; }
name="$1"
dir="$2"

# shellcheck source=lib/asset-spec.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/asset-spec.sh"
spec="$(asset_spec_require "${name}")" || exit $?
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
