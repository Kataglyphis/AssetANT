# Assets: the layout, an archive, and how one is released

The [README](../README.md) lists the assets and their licenses; this page packs, releases, adds
and uses them. Why scenes live outside the code, and the lock every consumer keeps, is the family's
contract, in ANTfrastructure's
[`data-repositories.md`](https://github.com/Kataglyphis/ANTfrastructure/blob/develop/docs/data-repositories.md).

## Layout

| Path | What |
| --- | --- |
| `assets/<name>/asset.json` | One asset: `name` (its directory, and the archive's top-level directory), `version` (its release is `<name>-v<version>`), `file`, `sha256` and `unpacked` (written by `pack.sh --record`), `summary`, `license`, `attribution`, `origin`, `notes`, and `source`: the repository, commit and directory it is packed from |
| `assets/<name>/prior-release.lock` | Optional, pinned prior archive used as the reproducible source when the original Git blobs no longer exist |
| `assets/<name>/licenses/` | Optional, verified original license texts and provenance included beside the asset |
| `scripts/pack.sh` | `pack.sh [--record] <Resources dir> <out dir> [name ...]`: one reproducible archive per asset plus `SHA256SUMS`; fails when an archive does not hash to its `asset.json` |
| `scripts/fetch-source.sh` | `fetch-source.sh <name> <dir>`: a sparse, blob-less checkout of the commit `source` pins, with only that directory |
| `scripts/release-files.sh` | `release-files.sh <Resources dir> <name> <out dir>`: a release's files in `<out>/<name>-v<N>/`, its notes in `<out>/<name>-v<N>.md` |
| `scripts/lib/asset-spec.sh` | One asset-specific path and missing-file verdict shared by fetch, pack and release |
| `assets/<name>/export-gltf.json` | Optional: the settings `scripts/blender/export_gltf.py` converted the asset with |
| `scripts/blender/export_gltf.py` | Runs inside Blender: bakes a scene's box-projected and procedural materials into tiling textures and exports glTF 2.0 ([below](#converting-a-blender-scene-to-gltf)) |
| `assets/<name>/cubemap.json` | Optional: the HDRI (URL and SHA-256) and settings `scripts/cubemap/equirect_to_cubemap.py` converted the asset with |
| `scripts/cubemap/equirect_to_cubemap.py` | Six sRGB PNG cube faces from an equirectangular Radiance HDR ([below](#converting-an-hdri-to-cube-faces)) |
| `scripts/check.py` | Validates every `asset.json` and that the README's asset table lists it |
| `scripts/check.sh` | The push check (`check.yml`): `check.py`, Python tests and the asset-spec fixture/mutation suite on the family image's pinned CPython; ANTfrastructure's `ci_image_python_require` rejects a host interpreter |
| `.github/workflows/lint-gates.yml` | ANTfrastructure's pinned ShellCheck, warning ratchet and strict duplication gate over tracked code on every push and pull request |
| `.github/workflows/release.yml` | A tag `<name>-v<N>` packs that asset from its pinned source and publishes the release |

Initialize `third_party/ANTfrastructure` before running `scripts/check.sh` in a fresh checkout;
the CI check initializes it through the shared host-preparation action.

## Dependency updates

Before adding script or workflow functionality, search this repository and its ANTfrastructure
submodule and follow [AGENTS.md](../AGENTS.md)'s reuse rule.

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
plus `ATTRIBUTION.txt`, written from `asset.json` so the credit travels with the files. When
`assets/<name>/licenses/` exists, its files travel in the archive's `LICENSES/` directory.

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
For a corrected successor, `prior-release.lock` can instead pin the published archive by SHA-256;
the shared ANTfrastructure fetcher verifies and safely extracts it before the old generated
attribution is replaced. `JurassicPark-v2` uses this path, preserving the model bytes while adding
its newly verified original license. Its notice records the exact source and comparison evidence.

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
   (`Resources/...`, as `pack.sh` takes a `Resources` directory). A scene that exists nowhere
   else may instead be **release-only**: `source` is `null`, `pack.sh` packs it from
   `<Resources dir>/Models/<name>`, `fetch-source.sh` refuses it, and it is published by hand with
   `release-files.sh` and `gh release create` before its tag reaches `release.yml`, which then only
   checks the published archive's hash. Its release is the only copy of its files (`Colosseum`).
2. Write `assets/<name>/asset.json` with every field. `license` and `attribution` are what can be
   shown, from a license file, the files' own headers or the place they came from, and `unknown`
   otherwise, never a guess; `notes` says how it was established.
3. `pack.sh --record`, then release it as above. A changed asset is `version` + 1 and a new tag; a
   published archive is never replaced, because every consumer's lock pins its hash.
4. Add it to the README's asset table; `check.py` fails until it is there.

## Converting a Blender scene to glTF

`scripts/blender/export_gltf.py` turns a Blender scene into glTF 2.0 that real-time renderers can load. It runs
inside the Blender that saved the scene (5.3.0 for `Colosseum.blend`), headless and without auto-run scripts:

```bash
blender -b -Y Colosseum/Colosseum.blend --python scripts/blender/export_gltf.py -- \
  --out Resources/Models/Colosseum-gltf --config assets/Colosseum-gltf/export-gltf.json --name Colosseum-gltf
```

It never saves the `.blend`. What it changes, and why:

- Image textures placed by Box projection, and procedural brick materials, become tiling textures that Cycles
  bakes (base colour, roughness, metallic and a tangent-space normal map from the bump relief), on UVs generated
  from the same projection. A map without variation becomes a factor. `bake_inputs` overrides node-group inputs
  for the bake: the Colosseum turns its wall dirt off, which would repeat with every tile.
- Materials made only of 3D noise get their mean colour.
- A per-face colour attribute becomes a palette of materials (`palette`), so faces split no vertices.
- N-gons are triangulated in the mesh data, so linked duplicates still share one mesh and every mesh gets
  tangents.
- `decimate`, `decimate_large` and `render_visibility` make lighter variants: `Colosseum-web` swaps in the
  scene's own low-detail crowd and leaves out the arena net. Collapse decimation cannot shrink a crowd built
  from thousands of small boxes; it breaks it apart.
- `export-report.json` beside the export records the Blender version, the source's SHA-256 and each material's
  treatment.

The bake runs on the CPU when Cycles finds no GPU; the Colosseum takes about five minutes. The output is not
byte-reproducible across Blender builds, so a converted asset is release-only (`source` is `null`): pack it
from `Resources/Models/<name>` with `pack.sh --record` and publish it by hand. Its `licenses/NOTICE.txt` names
the changes, which CC BY 4.0 requires.

## Converting an HDRI to cube faces

`scripts/cubemap/equirect_to_cubemap.py` turns an equirectangular Radiance HDR into six sRGB PNG faces in
Vulkan's cubemap convention (+X, -X, +Y, -Y, +Z, -Z, each face's row 0 at its top), the layout
BeschleunigerBallett's skybox loads. Everything the bytes depend on is in `assets/<name>/cubemap.json`: the HDRI's
URL and SHA-256 (a file that hashes otherwise is refused), the face size, the supersampling, an exposure applied
before clipping to 1 and sRGB encoding, a yaw about +Y, and the face file names. `--stats` prints the HDRI's size,
its peak and where it is, which places the sun for the yaw.

```bash
curl -fLo .work/sky.hdr "$(jq -r .hdri.url assets/<name>/cubemap.json)"
python3 -I scripts/cubemap/equirect_to_cubemap.py .work/sky.hdr .work/Resources/Models/<name> assets/<name>/cubemap.json
bash scripts/pack.sh --record .work/Resources dist <name>
```

`kloofendal_43d_clear_puresky`'s faces hashed the same in the family image (Python 3.15.2, numpy 2.5.4, Pillow
13.0.0) and on a WSL host with other builds (2026-11-18). The HDRI sits in no repository, so the asset is still
release-only (`source` is `null`), published by hand.
`scripts/tests/test_equirect_to_cubemap.py` checks the orientation, the yaw, the seams and the pin on a synthetic HDR.

## Using an asset

Pin the archive in a lock file, one line per asset, `<sha256>  <file>  <url>` (the format of
OxidANT's `models.lock`), and check the hash after every download. The reference is
BeschleunigerBallett's `Resources/assets.lock` and `cmake/FetchAssets.cmake`: the configure
downloads through a per-user cache keyed by the hash, extracts into `Resources/Models`, and leaves a
stamp so the next configure does nothing. What every fetcher checks, the stamp included:
[`data-repositories.md` § The lock](https://github.com/Kataglyphis/ANTfrastructure/blob/develop/docs/data-repositories.md#the-lock).
