#!/usr/bin/env bash
# Release payloads must preserve the archive hash pinned by asset.json.
set -euo pipefail

[[ $# -eq 3 ]] || { printf 'usage: %s <BB Resources dir> <name> <out dir>\n' "$0" >&2; exit 2; }
resources="$1"
name="$2"
out="$3"

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/asset-spec.sh
source "${root}/scripts/lib/asset-spec.sh"
spec="$(asset_spec_require "${name}")" || exit $?
tag="${name}-v$(jq -r '.version' "${spec}")"
file="$(jq -r '.file' "${spec}")"
dir="${out}/${tag}"

rm -rf "${dir}"
mkdir -p "${dir}"
bash "${root}/scripts/pack.sh" "${resources}" "${dir}" "${name}"
cp "${spec}" "${dir}/${name}.asset.json"
(cd "${dir}" && sha256sum "${file}" "${name}.asset.json" >SHA256SUMS)

{
  jq -r '"\(.summary)",
    "",
    "License: \(.license). Attribution: \(.attribution).",
    (if (.notes // "") != "" then "", .notes else empty end),
    "",
    "`tar -xJf \(.file)` gives `\(.name)/`, with its credit in `\(.name)/ATTRIBUTION.txt`."' "${spec}"
  printf '\nSHA-256:\n```\n'
  cat "${dir}/SHA256SUMS"
  printf '```\n'
} >"${out}/${tag}.md"

printf '%s: upload %s/* with notes %s\n' "${tag}" "${dir}" "${out}/${tag}.md"
