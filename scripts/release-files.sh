#!/usr/bin/env bash
# Makes one asset's release: <out>/<name>-v<version>/ holds what to upload, <out>/<name>-v<version>.md its notes.
# Usage: scripts/release-files.sh <BB Resources dir> <name> <out dir>
# The archive must hash to asset.json's sha256 (scripts/pack.sh checks), so a release never differs from the locks.
set -euo pipefail

[[ $# -eq 3 ]] || { printf 'usage: %s <BB Resources dir> <name> <out dir>\n' "$0" >&2; exit 2; }
resources="$1"
name="$2"
out="$3"

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
spec="${root}/assets/${name}/asset.json"
[[ -f "${spec}" ]] || { printf 'no %s\n' "${spec}" >&2; exit 2; }
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
