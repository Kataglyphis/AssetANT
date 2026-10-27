#!/usr/bin/env bash
# Tests prior-archive integrity and repacking; it does not establish rights for unreviewed assets.
set -uo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib/antfrastructure.sh
source "${root}/scripts/lib/antfrastructure.sh"
antfrastructure_source linux/scripts/lib/test-harness.sh || exit 1
work="$(mktemp -d)" || exit 1
trap 'rm -rf "${work}"' EXIT
fixture="${work}/repo"
mkdir -p "${fixture}/scripts/lib" "${fixture}/assets/example/licenses" "${work}/original/example" || exit 1
cp "${root}/scripts/pack.sh" "${root}/scripts/fetch-source.sh" "${fixture}/scripts/"
cp "${root}/scripts/lib/asset-spec.sh" "${root}/scripts/lib/antfrastructure.sh" \
  "${root}/scripts/lib/renovate-git-mode.sh" "${root}/scripts/lib/prior-release.sh" "${fixture}/scripts/lib/"
printf 'original model\n' > "${work}/original/example/model.obj"
printf 'old attribution\n' > "${work}/original/example/ATTRIBUTION.txt"
printf 'verified original license\n' > "${fixture}/assets/example/licenses/LICENSE.txt"
tar -C "${work}/original" -cJf "${work}/example.tar.xz" example || exit 1
sha="$(sha256sum "${work}/example.tar.xz" | cut -d' ' -f1)"
printf '%s example.tar.xz file://%s/example.tar.xz\n' "${sha}" "${work}" > "${fixture}/assets/example/prior-release.lock"
jq -n '{name:"example",version:2,file:"example.tar.xz",sha256:"",summary:"Fixture",license:"MIT",attribution:"Fixture",origin:null,notes:"",source:{repository:"https://example.test/source",commit:"0000000000000000000000000000000000000000",path:"Resources/Models/example"},unpacked:{files:0,bytes:0}}' > "${fixture}/assets/example/asset.json"
export KATAGLYPHIS_ASSET_CACHE="${work}/cache"

t_case 'fetch verifies the prior archive and preserves original model bytes'
t_assert_ok bash "${fixture}/scripts/fetch-source.sh" example "${work}/source"
t_assert_ok cmp "${work}/original/example/model.obj" "${work}/source/Resources/Models/example/model.obj"
t_assert_fails test -e "${work}/source/Resources/Models/example/ATTRIBUTION.txt"
t_assert_fails test -e "${work}/source/Resources/Models/example/.assetant-sha256"

t_case 'a corrected archive includes its tracked license and packs reproducibly'
t_assert_ok bash "${fixture}/scripts/pack.sh" --record "${work}/source/Resources" "${work}/packed" example
t_assert_ok bash "${fixture}/scripts/pack.sh" "${work}/source/Resources" "${work}/packed-again" example
t_assert_ok cmp "${work}/packed/example.tar.xz" "${work}/packed-again/example.tar.xz"
verifier="$(antfrastructure_path linux/scripts/verify_package_license.py)" || exit 1
t_assert_ok python3 "${verifier}" "${work}/packed/example.tar.xz" \
  --require "example/LICENSES/LICENSE.txt=${fixture}/assets/example/licenses/LICENSE.txt"

t_case 'a bad source checksum and a conflicting source LICENSES directory fail'
printf '%064d example.tar.xz file://%s/example.tar.xz\n' 0 "${work}" > "${fixture}/assets/example/prior-release.lock"
t_assert_fails bash "${fixture}/scripts/fetch-source.sh" example "${work}/bad-source"
mkdir "${work}/source/Resources/Models/example/LICENSES"
t_assert_fails bash "${fixture}/scripts/pack.sh" "${work}/source/Resources" "${work}/conflict" example
t_summary
