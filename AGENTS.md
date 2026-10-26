# AssetANT — agent rules

## Reuse first

Before adding a Bash or PowerShell helper, script, or CI step, search this repository and its
submodules for an implementation. Call or extend the canonical ANTfrastructure implementation
when it exists, and pass AssetANT-specific values from this repository. Follow the
[family adoption rule](https://github.com/Kataglyphis/ANTfrastructure/blob/develop/docs/adopting-in-a-new-project.md#reuse-before-adding-functionality).

## Asset releases

`assets/<name>/asset.json` pins the source commit and the exact release archive hash. Changing
either requires fetching the pinned source, packing the archive, and verifying the new bytes;
Renovate cannot infer them. The first 14 archives cannot be rebuilt from the rewritten source
history, and a published release must never be replaced. See [docs/assets.md](docs/assets.md).

`bash scripts/check.sh` runs metadata, Python and Bash regression tests in the family Linux image
after `third_party/ANTfrastructure` is initialized. The shared lint workflow checks tracked shell
scripts and rejects duplicated code on every push and pull request. Update the README, docs and
CHANGELOG with behavior changes.
