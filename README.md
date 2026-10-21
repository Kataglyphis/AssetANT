<div align="center">
  <a href="https://jonasheinle.de">
    <img src="https://raw.githubusercontent.com/Kataglyphis/AssetANT/develop/images/logo.svg" alt="AssetANT logo: an ant in the Cornell box" width="200" />
  </a>

  <h1>AssetANT</h1>

  <h4>3D scenes and textures for the Kataglyphis projects, one reproducible archive per release, pinned by SHA-256.</h4>
</div>

[![Check](https://github.com/Kataglyphis/AssetANT/actions/workflows/check.yml/badge.svg)](https://github.com/Kataglyphis/AssetANT/actions/workflows/check.yml)

[**Releases**](https://github.com/Kataglyphis/AssetANT/releases)

The Kataglyphis family's 3D scenes, kept apart from the code that renders them. Each scene's
metadata (where it came from, its license and credit, the SHA-256 of its archive) is in git here;
the files themselves are a GitHub release asset, one `<name>.tar.xz` per release. A consumer pins
each archive's URL and SHA-256 in a lock file and fetches it at build time, so no scene sits in its
working tree. [BeschleunigerBallett](https://github.com/Kataglyphis/BeschleunigerBallett) is the
first: it tracked these 14 scenes (518 MiB of its 633 MiB) until 2026-10-17, and the family's
history rewrite of that day took them out of its history too, so these releases are their only copy
([docs/assets.md](docs/assets.md#the-first-14-are-not-repacked)). [ModelANT](https://github.com/Kataglyphis/ModelANT)
does the same for the family's machine-learning models.

## Highlights

- **One release per asset version**, tag `<name>-v<N>`: a consumer's lock moves one line when one asset changes.
- **Reproducible archives**: sorted entries, mtime 0, owner 0, `xz -9` on one thread; Debian 13 and Ubuntu 26.04 pack the same hashes.
- **Never replaced**: a changed asset is a new version, and `release.yml` checks a published release instead of overwriting it.
- **The credit travels with the files**: every archive carries `ATTRIBUTION.txt`, written from its `asset.json`.
- **No license is guessed**: what was not found is `unknown`, and `notes` says how each one was established.
- **Checked on every push**: `scripts/check.sh` validates every `asset.json` and that the table below lists it, in the family image.

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

## Quick start

```bash
git clone --branch develop https://github.com/Kataglyphis/AssetANT.git
cd AssetANT
# Every asset.json is complete and the table above lists it, on the family image's pinned CPython.
docker run --rm -v "$PWD:/workspace" -w /workspace \
  ghcr.io/kataglyphis/kataglyphis_beschleuniger:latest bash scripts/check.sh
```

A consumer does not clone this: it pins each archive's URL and SHA-256 in a lock and fetches it
at build time, as [docs/assets.md](docs/assets.md#using-an-asset) shows.

## Documentation

| Topic | Read |
| --- | --- |
| What each file here does | [docs/assets.md](docs/assets.md#layout) |
| What an archive holds, and why its bytes are reproducible | [docs/assets.md](docs/assets.md#an-archive) |
| Why the first 14 archives cannot be repacked | [docs/assets.md](docs/assets.md#the-first-14-are-not-repacked) |
| Releasing an asset | [docs/assets.md](docs/assets.md#releasing) |
| Adding or changing an asset | [docs/assets.md](docs/assets.md#adding-or-changing-an-asset) |
| Using an asset in a consumer | [docs/assets.md](docs/assets.md#using-an-asset) |
| Why scenes live outside the code, and the lock every consumer keeps | [ANTfrastructure: `data-repositories.md`](https://github.com/Kataglyphis/ANTfrastructure/blob/develop/docs/data-repositories.md) |

## Contributing and contact

AssetANT is one of the [Kataglyphis repositories](https://github.com/Kataglyphis/ANTfrastructure/blob/develop/docs/repository-family.md),
which share one way to contribute and one contact. Licence: the scripts and metadata are MIT,
see [LICENSE](LICENSE). Every asset is under its own license, in the table above, its
`asset.json` and its archive's `ATTRIBUTION.txt`.
