"""A glTF's images as UASTC KTX2 with full mip chains and Zstandard, named by KHR_texture_basisu alone.

Usage: gltf_to_ktx2.py <inputs dir> <asset dir> <out dir>

<inputs dir> holds what the asset's two locks name, as the hub's fetch-data-lock.py leaves them: source.lock's glTF
archive extracted (with its stamp) and encoder.lock's KTX-Software tarball for this machine. <asset dir> is
assets/<name>, whose ktx2.json fixes everything else the bytes depend on. The geometry, materials and samplers are
copied unchanged; every image becomes one KTX2 and no PNG or JPEG is left.
"""

import hashlib
import json
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

BASISU = "KHR_texture_basisu"
STAMP = ".assetant-sha256"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
# The slots glTF and its Khronos extensions sample as sRGB colour; every other texture slot holds data.
COLOUR_SLOTS = {"baseColorTexture", "emissiveTexture", "sheenColorTexture", "specularColorTexture",
                "diffuseTexture", "specularGlossinessTexture"}
# KHR_texture_basisu: colour is BT.709 primaries with the sRGB transfer, data has no primaries and a linear transfer.
COLOUR_SPACE = {True: ("SRGB", "srgb", "bt709"), False: ("UNORM", "linear", "none")}
ENCODERS = {"aarch64": "Linux-arm64", "x86_64": "Linux-x86_64"}


def read_lock(path):
    """{file: sha256} from a hub data lock."""
    rows = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if fields and not fields[0].startswith("#"):
            rows[fields[1]] = fields[0]
    return rows


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def head_of(path, size=32):
    with Path(path).open("rb") as handle:
        return handle.read(size)


def texture_slots(value, key=None):
    """(slot name, texture index) for every textureInfo below a material, extensions included."""
    if isinstance(value, dict):
        if key is not None and key.endswith("Texture") and "index" in value:
            yield key, value["index"]
            return
        for child_key, child in value.items():
            yield from texture_slots(child, child_key)
    elif isinstance(value, list):
        for child in value:
            yield from texture_slots(child, key)


def image_colour(doc):
    """True (sRGB colour) or False (linear data) per image, from the material slots that sample it."""
    seen = {}
    for material in doc.get("materials", []):
        for slot, index in texture_slots(material):
            seen.setdefault(doc["textures"][index]["source"], set()).add(slot in COLOUR_SLOTS)
    colour = []
    for image in range(len(doc.get("images", []))):
        kinds = seen.get(image, set())
        if len(kinds) != 1:
            what = "no material slot" if not kinds else "both colour and data slots"
            raise ValueError(f"image {image} is sampled by {what}: its colour space is not one")
        colour.append(kinds.pop())
    return colour


def channels(path):
    """3 or 4, from the file's own header: an 8-bit RGB or RGBA PNG, or a JPEG."""
    head = head_of(path)
    if head.startswith(JPEG_MAGIC):
        return 3
    if head.startswith(PNG_MAGIC) and head[12:16] == b"IHDR" and head[24] == 8 and head[25] in (2, 6):
        return 3 if head[25] == 2 else 4
    raise ValueError(f"{path} is neither a JPEG nor an 8-bit RGB or RGBA PNG")


def check_document(doc):
    """Refuses what the rewrite cannot keep: a texture already extended, an embedded image, more than one buffer."""
    for index, texture in enumerate(doc.get("textures", [])):
        if "source" not in texture or texture.get("extensions"):
            raise ValueError(f"texture {index} must name its image by source alone")
    for index, image in enumerate(doc.get("images", [])):
        uri = image.get("uri", "")
        if not uri or uri.startswith("data:") or "bufferView" in image:
            raise ValueError(f"image {index} must be an external file")
    buffers = doc.get("buffers", [])
    if len(buffers) != 1 or buffers[0].get("uri", "").startswith("data:") or "extensionsUsed" not in doc:
        raise ValueError("the glTF needs one external buffer and an extensionsUsed list")


def install_encoder(inputs, asset_dir, config, work):
    """The pinned ktx tool for this machine, unpacked into work after its tarball matched encoder.lock."""
    arch = ENCODERS.get(platform.machine())
    if arch is None:
        raise ValueError(f"no pinned KTX-Software for {platform.machine()}")
    tarball = f"KTX-Software-{config['encoder']}-{arch}.tar.bz2"
    pinned = read_lock(asset_dir / "encoder.lock").get(tarball)
    if pinned is None or not (inputs / tarball).is_file() or sha256(inputs / tarball) != pinned:
        raise ValueError(f"{inputs / tarball} is missing or does not hash to encoder.lock's pin")
    with tarfile.open(inputs / tarball, "r:bz2") as archive:
        archive.extractall(work, filter="data")
    root = work / tarball.removesuffix(".tar.bz2")
    tool = [str(root / "bin" / "ktx")]
    env = {"LD_LIBRARY_PATH": str(root / "lib")}
    version = subprocess.run([*tool, "--version"], env=env, capture_output=True, text=True, check=True).stdout.strip()
    if not version.endswith(f" v{config['encoder']}"):
        raise ValueError(f"{tarball} reports {version!r}, not v{config['encoder']}")
    return tool, env, {"encoder": version, "encoder_tarball": tarball, "encoder_sha256": pinned}


def encode(tool, env, config, source, target, colour):
    """One image as UASTC KTX2, checked by ktx validate's glTF profile; the PSNR ktx reports for its base level."""
    suffix, transfer, primaries = COLOUR_SPACE[colour]
    layout = "R8G8B8A8" if channels(source) == 4 else "R8G8B8"
    args = [*tool, "create", "--format", f"{layout}_{suffix}", "--assign-tf", transfer, "--assign-primaries", primaries,
            "--encode", "uastc", "--uastc-quality", str(config["uastc_quality"]), "--zstd", str(config["zstd"]),
            "--generate-mipmap", "--mipmap-filter", config["mipmap_filter"], "--mipmap-wrap", config["mipmap_wrap"],
            # The blocks do not depend on the thread count, but the file records it in KTXwriterScParams.
            "--threads", str(config["threads"]),
            # The scalar path on every machine: x86_64 would otherwise take SSE where arm64 cannot.
            "--no-sse", "--compare-psnr", str(source), str(target)]
    run = subprocess.run(args, check=False, env=env, capture_output=True, text=True)
    psnr = re.search(r"Level 0:\s+PSNR:\s+([0-9.]+)", run.stdout)
    if run.returncode != 0 or psnr is None:
        raise RuntimeError(f"ktx create {source}: {run.returncode}\n{run.stdout}{run.stderr}")
    check = subprocess.run([*tool, "validate", "--gltf-basisu", "--warnings-as-errors", str(target)],
                           check=False, env=env, capture_output=True, text=True)
    if check.returncode != 0:
        raise RuntimeError(f"ktx validate --gltf-basisu {target}:\n{check.stdout}{check.stderr}")
    return float(psnr.group(1))


def rewrite(doc, name, uris, generator, copyright_text):
    """The glTF with every texture naming its KTX2 through KHR_texture_basisu alone, required, and the buffer renamed."""
    for image, uri in zip(doc["images"], uris, strict=True):
        image["uri"] = uri
        image["mimeType"] = "image/ktx2"
    for texture in doc["textures"]:
        texture["extensions"] = {BASISU: {"source": texture.pop("source")}}
    doc["buffers"][0]["uri"] = f"{name}.bin"
    doc["asset"]["generator"] = f"{doc['asset'].get('generator', 'unknown')}, {generator}"
    doc["asset"]["copyright"] = copyright_text
    out = {}
    for key, value in doc.items():
        if key != "extensionsRequired":
            out[key] = value
        if key == "extensionsUsed":
            out[key] = [*value, BASISU]
            out["extensionsRequired"] = [*doc.get("extensionsRequired", []), BASISU]
    return out


def convert(inputs, asset_dir, out):
    config = json.loads((asset_dir / "ktx2.json").read_text(encoding="utf-8"))
    name = asset_dir.name
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"{out} is not empty")
    (source_file, source_sha), = read_lock(asset_dir / "source.lock").items()
    source = inputs / source_file.removesuffix(".tar.xz")
    stamp = (source / STAMP).read_text(encoding="utf-8").split()[0] if (source / STAMP).is_file() else None
    if stamp != source_sha:
        raise ValueError(f"{source} was not extracted from source.lock's {source_file} (stamp {stamp})")
    gltf = source / config["gltf"]
    doc = json.loads(gltf.read_text(encoding="utf-8"))
    check_document(doc)
    colour = image_colour(doc)
    targets = [Path(image["uri"]).with_suffix(".ktx2").as_posix() for image in doc["images"]]
    if len(set(targets)) != len(targets):
        raise ValueError("two images would share one KTX2 name")
    report = {"source": source_file, "source_sha256": source_sha, "gltf": config["gltf"]}
    with tempfile.TemporaryDirectory() as work:
        tool, env, encoder = install_encoder(inputs, asset_dir, config, Path(work))
        report.update(encoder, config=config, images=[])
        for index, (image, target) in enumerate(zip(doc["images"], targets, strict=True)):
            (out / target).parent.mkdir(parents=True, exist_ok=True)
            psnr = encode(tool, env, config, source / image["uri"], out / target, colour[index])
            entry = {"uri": target, "from": image["uri"], "from_sha256": sha256(source / image["uri"]),
                     "colour": "sRGB" if colour[index] else "linear", "bytes": (out / target).stat().st_size,
                     "sha256": sha256(out / target), "level0_psnr": psnr}
            report["images"].append(entry)
            print(f"{index} {target} {entry['colour']} {entry['bytes']} B, base level PSNR {psnr}", flush=True)
    buffer = gltf.parent / doc["buffers"][0]["uri"]
    generator = f"KTX2 by AssetANT scripts/ktx2/gltf_to_ktx2.py and KTX-Software v{config['encoder']}"
    rewritten = rewrite(doc, name, targets, generator, config["copyright"])
    (out / f"{name}.bin").write_bytes(buffer.read_bytes())
    (out / f"{name}.gltf").write_text(json.dumps(rewritten, separators=(",", ":")), encoding="utf-8")
    for extra in config.get("copy", []):
        (out / extra).write_bytes((source / extra).read_bytes())
    (out / "ktx2-report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    left = [p.name for p in out.rglob("*") if p.is_file() and head_of(p, 8).startswith((PNG_MAGIC, JPEG_MAGIC))]
    if left:
        raise ValueError(f"PNG or JPEG left in {out}: {left}")


def main(argv):
    if len(argv) != 4:
        sys.exit(__doc__)
    try:
        convert(Path(argv[1]), Path(argv[2]), Path(argv[3]))
    except ValueError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main(sys.argv)
