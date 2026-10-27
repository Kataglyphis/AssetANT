#!/usr/bin/env bash
# The shared extractor verifies the archived bytes before the generated attribution is replaced.
asset_fetch_prior_release() {
  local name="$1" dir="$2" path="$3" lock="$4" fetcher work
  [[ "${path}" == "Resources/Models/${name}" ]] || { printf 'invalid prior-release source path: %s\n' "${path}" >&2; return 1; }
  [[ ! -e "${dir}/${path}" ]] || { printf 'source target already exists: %s\n' "${dir}/${path}" >&2; return 1; }
  fetcher="$(antfrastructure_path linux/scripts/lib/fetch-data-lock.py)" || return 1
  work="$(mktemp -d)" || return 1
  (
    trap 'rm -rf "${work}"' EXIT
    python3 "${fetcher}" --lock "${lock}" --dest "${work}" --extract --only "${name}" || exit $?
    [[ -f "${work}/${name}/ATTRIBUTION.txt" && -f "${work}/${name}/.assetant-sha256" ]] || {
      printf 'prior archive lacks its original attribution or verification stamp\n' >&2; exit 1;
    }
    mkdir -p "${dir}/Resources/Models" || exit $?
    cp -R "${work}/${name}" "${dir}/${path}" || exit $?
    rm "${dir}/${path}/ATTRIBUTION.txt" "${dir}/${path}/.assetant-sha256" || exit $?
  ) || return 1
  printf '%s\n' "${dir}/${path}"
}
