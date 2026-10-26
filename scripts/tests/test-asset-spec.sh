#!/usr/bin/env bash
# Scope: asset spec lookup and caller verdicts; network fetch and archive reproducibility have separate checks.
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "${script_dir}/../.." && pwd)"
# shellcheck source=../lib/antfrastructure.sh
source "${root}/scripts/lib/antfrastructure.sh"
antfrastructure_source linux/scripts/lib/test-harness.sh || exit 1

work="$(mktemp -d)" || exit 1
trap 'rm -rf -- "${work}"' EXIT
fixture="${work}/asset repo [one]"
origin="${work}/source repo [one]"
mkdir -p "${fixture}/scripts/lib" "${fixture}/assets/example" "${origin}/Resources/example" || exit 1
cp "${root}/scripts/lib/asset-spec.sh" "${fixture}/scripts/lib/asset-spec.sh" || exit 1
for script in fetch-source.sh pack.sh release-files.sh; do
  cp "${root}/scripts/${script}" "${fixture}/scripts/${script}" || exit 1
done
printf 'fixture payload\n' > "${origin}/Resources/example/data.txt"
git -C "${origin}" init -q || exit 1
t_git_commit "${origin}" || exit 1
commit="$(git -C "${origin}" rev-parse HEAD)" || exit 1
jq -n --arg repository "${origin}" --arg commit "${commit}" '{
  name: "example", version: 1, file: "example.tar.xz", sha256: "",
  summary: "Fixture", license: "MIT", attribution: "Fixture author", origin: null, notes: "",
  source: {repository: $repository, commit: $commit, path: "Resources/example"},
  unpacked: {files: 0, bytes: 0}
}' > "${fixture}/assets/example/asset.json" || exit 1

spec="${fixture}/assets/example/asset.json"
output=""
status=0
t_case 'existing spec preserves spaces and brackets in its absolute path'
t_capture_command output status bash "${fixture}/scripts/lib/asset-spec.sh" example
t_assert_eq 0 "${status}"
t_assert_eq "${spec}" "${output}"

t_case 'fetch, pack and release all use the pinned spec successfully'
t_capture_command output status bash "${fixture}/scripts/fetch-source.sh" example "${work}/fetched source"
t_assert_eq 0 "${status}"
t_assert_ok test -f "${work}/fetched source/Resources/example/data.txt"
t_capture_command output status bash "${fixture}/scripts/pack.sh" --record \
  "${work}/fetched source/Resources" "${work}/packed output" example
t_assert_eq 0 "${status}"
t_assert_ok test -f "${work}/packed output/example.tar.xz"
t_capture_command output status bash "${fixture}/scripts/release-files.sh" \
  "${work}/fetched source/Resources" example "${work}/release output"
t_assert_eq 0 "${status}"
t_assert_ok test -f "${work}/release output/example-v1/example.asset.json"

missing="no ${fixture}/assets/absent/asset.json"
t_case 'all three callers keep exit 2 and the exact missing-spec diagnostic'
t_capture_command output status bash "${fixture}/scripts/fetch-source.sh" absent "${work}/unused source"
t_assert_eq 2 "${status}"
t_assert_eq "${missing}" "${output}"
t_capture_command output status bash "${fixture}/scripts/pack.sh" \
  "${work}/fetched source/Resources" "${work}/unused packed" absent
t_assert_eq 2 "${status}"
t_assert_eq "${missing}" "${output}"
t_capture_command output status bash "${fixture}/scripts/release-files.sh" \
  "${work}/fetched source/Resources" absent "${work}/unused release"
t_assert_eq 2 "${status}"
t_assert_eq "${missing}" "${output}"

missing_spec_contract() {
  local library="$1" repo_root="$2" got rc=0
  got="$(bash "${library}" absent 2>&1)" || rc=$?
  if [[ "${rc}" -eq 2 && "${got}" == "no ${repo_root}/assets/absent/asset.json" ]]; then return 0; fi
  return 1
}

t_case 'the missing-spec contract rejects a removed file check'
t_assert_ok missing_spec_contract "${fixture}/scripts/lib/asset-spec.sh" "${fixture}"
mutant="${fixture}/scripts/lib/asset-spec-mutant.sh"
sed 's/\[\[ ! -f "\${spec}" \]\]/[[ ! -n "${spec}" ]]/' \
  "${fixture}/scripts/lib/asset-spec.sh" > "${mutant}" || exit 1
if cmp -s "${fixture}/scripts/lib/asset-spec.sh" "${mutant}"; then
  printf 'mutation recipe did not change the spec guard\n' >&2
  exit 1
fi
t_assert_fails missing_spec_contract "${mutant}" "${fixture}"

t_summary
