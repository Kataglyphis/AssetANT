# AssetANT

The Kataglyphis family's 3D scenes, kept apart from the code that renders them. Each scene's
metadata (where it came from, its license and credit, the SHA-256 of its archive) is in git here;
the files themselves are a GitHub release asset, one `<name>.tar.xz` per release. A consumer pins
each archive's URL and SHA-256 in a lock file and fetches it at build time, so no scene sits in its
working tree. [BeschleunigerBallett](https://github.com/Kataglyphis/BeschleunigerBallett) is the
first: it tracked these 14 scenes (518 MiB of its 633 MiB) until 2026-10-17, and its history still
holds them, which is where the archives are packed from. [ModelANT](https://github.com/Kataglyphis/ModelANT)
does the same for the family's machine-learning models.

## The assets

| Asset | What | License | Archive | Unpacked | Release |
| --- | --- | --- | --- | --- | --- |
| `Ajax` | Bust of Ajax, a 60,000-triangle scan | unknown | 1.2 MiB | 4.1 MiB | `Ajax-v1` |
| `bmw` | Mike Pan's BMW, cleaned up by Morgan McGuire | CC0 1.0 | 2.8 MiB | 29.0 MiB | `bmw-v1` |
| `buddha` | Stanford's Happy Buddha scan | Stanford 3D Scanning Repository | 13.9 MiB | 86.7 MiB | `buddha-v1` |
| `bunny` | Stanford bunny scan | Stanford 3D Scanning Repository | 1.5 MiB | 12.8 MiB | `bunny-v1` |
| `CornellBox` | Eight Cornell Box scenes | CC BY 3.0 | 0.1 MiB | 1.1 MiB | `CornellBox-v1` |
| `crytek-sponza` | Crytek's Sponza atrium, textured | CC BY 3.0 | 27.7 MiB | 47.2 MiB | `crytek-sponza-v1` |
| `Dinosaurs` | Two dinosaur skeletons on a ground plane | unknown | 3.8 MiB | 26.0 MiB | `Dinosaurs-v1` |
| `JurassicPark` | A mosquito in amber | unknown | 0.4 MiB | 1.5 MiB | `JurassicPark-v1` |
| `mori_knob` | Yasutoshi Mori's material test orb | CC BY 4.0 | 0.1 MiB | 0.9 MiB | `mori_knob-v1` |
| `Pillum` | Small textured scene 'PilumPainting' | unknown | 0.6 MiB | 0.6 MiB | `Pillum-v1` |
| `sibenik` | Sibenik cathedral interior, textured | CC BY-NC | 1.5 MiB | 5.9 MiB | `sibenik-v1` |
| `sportsCar` | Yasutoshi Mori's sports car | CC BY 4.0 | 2.1 MiB | 15.6 MiB | `sportsCar-v1` |
| `StanfordDragon` | Stanford's Chinese dragon scan | Stanford 3D Scanning Repository | 11.1 MiB | 69.0 MiB | `StanfordDragon-v1` |
| `Sulo` | A grandfather clock, a wine glass and a sword, with their Blender source | by [Sulo456](https://github.com/Sulo456), with his permission | 51.2 MiB | 217.3 MiB | `Sulo-v1` |

Each `assets/<name>/asset.json` says how its license was established. **Four are `unknown`**
(`Ajax`, `Dinosaurs`, `JurassicPark`, `Pillum`): no license or credit file came with them and
none was found. Their notes record what the files themselves hint at; settle each before relying
on it. `Sulo` was modelled by [Sulo456](https://github.com/Sulo456), a professional 3D artist,
and is published here with his permission (2026-10-17); it carries no open license, so reuse
beyond the Kataglyphis projects needs his consent. `sibenik` is non-commercial, and the three
Stanford scans may not be used commercially without Stanford's permission.

## Layout

| Path | What |
| --- | --- |
| `assets/<name>/asset.json` | One asset: `name` (its directory, and the archive's top-level directory), `version` (its release is `<name>-v<version>`), `file`, `sha256` and `unpacked` (written by `pack.sh --record`), `summary`, `license`, `attribution`, `origin`, `notes`, and `source`: the repository, commit and directory it is packed from |
| `scripts/pack.sh` | `pack.sh [--record] <Resources dir> <out dir> [name ...]`: one reproducible archive per asset plus `SHA256SUMS`; fails when an archive does not hash to its `asset.json` |
| `scripts/fetch-source.sh` | `fetch-source.sh <name> <dir>`: a sparse, blob-less checkout of the commit `source` pins, with only that directory |
| `scripts/release-files.sh` | `release-files.sh <Resources dir> <name> <out dir>`: a release's files in `<out>/<name>-v<N>/`, its notes in `<out>/<name>-v<N>.md` |
| `scripts/check.py` | Validates every `asset.json` and that this table lists it; `check.yml` runs it with shellcheck on every push |
| `.github/workflows/release.yml` | A tag `<name>-v<N>` packs that asset from its pinned source and publishes the release |

## An archive

`<name>.tar.xz` unpacks to `<name>/`: the source directory exactly as it is at `source.commit`,
plus `ATTRIBUTION.txt`, written from `asset.json` so the credit travels with the files. The bytes
depend on the content alone: GNU tar in `gnu` format, entries sorted by name, mtime 0, owner and
group 0, modes 644 and 755, no xattrs or ACLs, then `xz -9` on one thread. On 2026-10-17 Debian 13
(tar 1.35, xz 5.8.1) and Ubuntu 26.04 (tar 1.35, xz 5.8.3) packed `CornellBox`, `Dinosaurs` and
`mori_knob` to the same hashes, and so did a umask of 077 over a source fetched with
`fetch-source.sh` instead of a full clone.

## Releasing

One release per asset version, tag `<name>-v<N>`, carrying `<name>.tar.xz`, `<name>.asset.json`
and `SHA256SUMS`, at `https://github.com/Kataglyphis/AssetANT/releases/download/<name>-v<N>/<name>.tar.xz`.
Per asset rather than one bundle, so a consumer's lock moves one line when one asset changes,
no release is ever edited or carries an unchanged copy, and the tag names exactly what it holds.

```bash
bash scripts/fetch-source.sh <name> .work/src          # or any checkout of source.repository at source.commit
bash scripts/pack.sh --record .work/src/Resources dist <name>   # writes sha256 and unpacked into asset.json
python3 -I scripts/check.py
git commit -am "<name>: v<N>" && git tag <name>-v<N> && git push origin develop <name>-v<N>
```

`release.yml` then repacks the asset from its pinned source on an `ubuntu-26.04` runner (no container) and publishes it only
when the archive hashes to `asset.json`'s `sha256`. A release that already exists is checked, never
replaced. To publish by hand instead, from the same files:

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
4. Add it to the table above.

## Using an asset

Pin the archive in a lock file, one line per asset, `<sha256>  <file>  <url>` (the format of
OxidANT's `models.lock`), and check the hash after every download. BeschleunigerBallett's
`Resources/assets.lock` and `cmake/FetchAssets.cmake` are the reference: the configure downloads
through a per-user cache keyed by the hash, extracts into `Resources/Models`, and leaves a stamp so
the next configure does nothing.

## License

The scripts and metadata in this repository are MIT-licensed (`LICENSE`). Every asset is under its
own license, in the table above, its `asset.json` and its archive's `ATTRIBUTION.txt`.
