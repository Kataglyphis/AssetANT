# Assets: the layout, an archive, and how one is released

The [README](../README.md) lists the assets and their licenses; this page packs, releases, adds
and uses them. Why scenes live outside the code, and the lock every consumer keeps, is the family's
contract, in ANTfrastructure's
[`data-repositories.md`](https://github.com/Kataglyphis/ANTfrastructure/blob/develop/docs/data-repositories.md).

## Layout

| Path | What |
| --- | --- |
| `assets/<name>/asset.json` | One asset: `name` (its directory, and the archive's top-level directory), `version` (its release is `<name>-v<version>`), `file`, `sha256` and `unpacked` (written by `pack.sh --record`), `summary`, `license`, `attribution`, `origin`, `notes`, and `source`: the repository, commit and directory it is packed from |
| `scripts/pack.sh` | `pack.sh [--record] <Resources dir> <out dir> [name ...]`: one reproducible archive per asset plus `SHA256SUMS`; fails when an archive does not hash to its `asset.json` |
| `scripts/fetch-source.sh` | `fetch-source.sh <name> <dir>`: a sparse, blob-less checkout of the commit `source` pins, with only that directory |
| `scripts/release-files.sh` | `release-files.sh <Resources dir> <name> <out dir>`: a release's files in `<out>/<name>-v<N>/`, its notes in `<out>/<name>-v<N>.md` |
| `scripts/check.py` | Validates every `asset.json` and that the README's asset table lists it |
| `scripts/check.sh` | The push check (`check.yml`): `check.py` on the family Linux image's pinned CPython, then shellcheck over the root scripts and their bootstrap; anywhere else it stops (owner, 2026-10-20: the image's Python, not the runner's, at the price of the image pull) |
| `.github/workflows/release.yml` | A tag `<name>-v<N>` packs that asset from its pinned source and publishes the release |

## Dependency updates

From Linux or WSL, run `bash scripts/renovate-local.sh --apply` from this checkout. The thin
wrapper initializes the recorded hub submodule if absent, then uses this repo's
`.github/renovate.json` and the hub's pinned Renovate driver to update supported dependencies,
including GitHub Actions and direct submodule gitlinks. Report and `--apply --dry-run` do not
initialize the hub; initialize it explicitly or provide an existing checkout before those
read-only calls. A Windows-authored WSL checkout uses the copied Git mode helper during that
bootstrap. The driver reports a refusal if it cannot safely complete an update; its exit
status must be checked.

The `source.commit` and archive checksum in each `asset.json` describe the exact bytes released.
Changing them requires fetching the source, packing, recording its new hash and passing
`scripts/check.sh` and release verification. A general dependency bump cannot infer those bytes.

## An archive

`<name>.tar.xz` unpacks to `<name>/`: the source directory exactly as it is at `source.commit`,
plus `ATTRIBUTION.txt`, written from `asset.json` so the credit travels with the files.

The bytes depend on the content alone: GNU tar in `gnu` format, entries sorted by name, mtime 0,
owner and group 0, modes 644 and 755, no xattrs or ACLs, then `xz -9` on one thread. On
2026-10-17 Debian 13 (tar 1.35, xz 5.8.1) and Ubuntu 26.04 (tar 1.35, xz 5.8.3) packed
`CornellBox`, `Dinosaurs` and `mori_knob` to the same hashes, and so did a umask of 077 over a
source fetched with `fetch-source.sh` instead of a full clone.

### The first 14 are not repacked

Their `source.commit` is BeschleunigerBallett's `c610c76`, from before the family's history
rewrite of 2026-10-17. The rewrite dropped every file of 500 KB or more that no branch held, the
scenes among them, so neither `fetch-source.sh` nor `release.yml` can rebuild these archives. They
stay as published; their `source` records where they were packed from. A new asset needs a source
that still exists: a public commit that holds its files, often the author's own repository.

## Releasing

One release per asset version, tag `<name>-v<N>`, carrying `<name>.tar.xz`, `<name>.asset.json`
and `SHA256SUMS`, at `https://github.com/Kataglyphis/AssetANT/releases/download/<name>-v<N>/<name>.tar.xz`.
Per asset, not one bundle: a consumer's lock moves one line when one asset changes, no release is
ever edited or carries an unchanged copy, and the tag names exactly what it holds.

```bash
bash scripts/fetch-source.sh <name> .work/src          # or any checkout of source.repository at source.commit
bash scripts/pack.sh --record .work/src/Resources dist <name>   # writes sha256 and unpacked into asset.json
docker run --rm -v "$PWD:/workspace" -w /workspace ghcr.io/kataglyphis/kataglyphis_beschleuniger:latest bash scripts/check.sh
git commit -am "<name>: v<N>" && git tag <name>-v<N> && git push origin develop <name>-v<N>
```

`release.yml` then repacks the asset from its pinned source on an `ubuntu-26.04` runner (no
container) and publishes it only when the archive hashes to `asset.json`'s `sha256`. A release
that already exists is checked, never replaced. To publish by hand, from the same files:

```bash
bash scripts/release-files.sh <Resources dir> <name> dist
gh release create <name>-v<N> dist/<name>-v<N>/* --title <name>-v<N> --notes-file dist/<name>-v<N>.md
```

## Adding or changing an asset

1. Its files must sit in a public commit: `source` names the repository, commit and directory
   (`Resources/...`, as `pack.sh` takes a `Resources` directory).
2. Write `assets/<name>/asset.json` with every field. `license` and `attribution` are what can be
   shown, from a license file, the files' own headers or the place they came from, and `unknown`
   otherwise, never a guess; `notes` says how it was established.
3. `pack.sh --record`, then release it as above. A changed asset is `version` + 1 and a new tag; a
   published archive is never replaced, because every consumer's lock pins its hash.
4. Add it to the README's asset table; `check.py` fails until it is there.

## Using an asset

Pin the archive in a lock file, one line per asset, `<sha256>  <file>  <url>` (the format of
OxidANT's `models.lock`), and check the hash after every download. The reference is
BeschleunigerBallett's `Resources/assets.lock` and `cmake/FetchAssets.cmake`: the configure
downloads through a per-user cache keyed by the hash, extracts into `Resources/Models`, and leaves a
stamp so the next configure does nothing. What every fetcher checks, the stamp included:
[`data-repositories.md` § The lock](https://github.com/Kataglyphis/ANTfrastructure/blob/develop/docs/data-repositories.md#the-lock).
