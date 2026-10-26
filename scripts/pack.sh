#!/usr/bin/env bash
# The archive hash must match asset.json unless --record refreshes its pin.
set -euo pipefail

usage() {
  printf 'usage: %s [--record] <BB Resources dir> <out dir> [name ...]\n' "$0" >&2
  exit 2
}

record=0
if [[ "${1:-}" == "--record" ]]; then
  record=1
  shift
fi
[[ $# -ge 2 ]] || usage
resources="$1"
out="$2"
shift 2

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/asset-spec.sh
source "${root}/scripts/lib/asset-spec.sh"
[[ -d "${resources}" ]] || { printf 'no directory %s\n' "${resources}" >&2; exit 2; }
mkdir -p "${out}"
out="$(cd "${out}" && pwd)"

names=("$@")
if [[ ${#names[@]} -eq 0 ]]; then
  for spec in "${root}"/assets/*/asset.json; do
    names+=("$(basename "$(dirname "${spec}")")")
  done
fi

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

# The archive carries this text, so the credit travels with the files; never the hash, which it would change.
write_attribution() {
  local spec="$1"
  local target="$2"
  jq -r '"\(.name): \(.summary)",
    "",
    "License:     \(.license)",
    "Attribution: \(.attribution)",
    "Origin:      \(.origin // "unknown")",
    (if (.notes // "") != "" then "Notes:       \(.notes)" else empty end),
    "",
    "Packed by AssetANT (https://github.com/Kataglyphis/AssetANT, assets/\(.name)/asset.json)",
    "from \(.source.repository) at \(.source.commit), \(.source.path)."' "${spec}" >"${target}"
  return 0
}

packed=()
for name in "${names[@]}"; do
  spec="$(asset_spec_require "${name}")" || exit $?
  path="$(jq -r '.source.path' "${spec}")"
  file="$(jq -r '.file' "${spec}")"
  [[ "${path}" == Resources/* ]] || { printf '%s: source.path %s is not under Resources/\n' "${name}" "${path}" >&2; exit 1; }
  src="${resources}/${path#Resources/}"
  [[ -d "${src}" ]] || { printf '%s: no directory %s\n' "${name}" "${src}" >&2; exit 1; }
  [[ ! -e "${src}/ATTRIBUTION.txt" ]] || { printf '%s: %s/ATTRIBUTION.txt would be overwritten\n' "${name}" "${src}" >&2; exit 1; }

  stage="${work}/${name}"
  mkdir -p "${stage}"
  cp -R "${src}" "${stage}/${name}"
  write_attribution "${spec}" "${stage}/${name}/ATTRIBUTION.txt"
  odd="$(find "${stage}" ! -type f ! -type d)"
  [[ -z "${odd}" ]] || { printf '%s: only files and directories are packed, not:\n%s\n' "${name}" "${odd}" >&2; exit 1; }

  # Sorted names, one owner, one mtime and normalised modes: the bytes depend on the content alone.
  LC_ALL=C tar --create --format=gnu --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
    --mode='u=rwX,go=rX' --no-acls --no-xattrs --no-selinux -C "${stage}" -f - "${name}" |
    xz -9 -T1 -c >"${out}/${file}.part"
  mv "${out}/${file}.part" "${out}/${file}"

  sha="$(sha256sum "${out}/${file}" | cut -d' ' -f1)"
  files="$(find "${stage}/${name}" -type f | wc -l)"
  bytes="$(find "${stage}/${name}" -type f -printf '%s\n' | awk '{ s += $1 } END { printf "%d", s }')"
  if [[ ${record} -eq 1 ]]; then
    jq --arg sha "${sha}" --argjson files "${files}" --argjson bytes "${bytes}" \
      '.sha256 = $sha | .unpacked = { files: $files, bytes: $bytes }' "${spec}" >"${spec}.part"
    mv "${spec}.part" "${spec}"
  fi
  recorded="$(jq -r '"\(.sha256) \(.unpacked.files) \(.unpacked.bytes)"' "${spec}")"
  if [[ "${recorded}" != "${sha} ${files} ${bytes}" ]]; then
    printf '%s: packed %s, asset.json records %s (sha256 files bytes; --record writes them)\n' \
      "${name}" "${sha} ${files} ${bytes}" "${recorded}" >&2
    exit 1
  fi
  rm -rf "${stage}"
  printf '%s  %s (%s files, %s bytes unpacked)\n' "${sha}" "${file}" "${files}" "${bytes}"
  packed+=("${file}")
done

(cd "${out}" && sha256sum "${packed[@]}" >SHA256SUMS)
