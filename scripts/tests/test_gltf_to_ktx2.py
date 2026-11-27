"""The KTX2 converter's glTF rewrite, colour spaces and pins, with a stand-in for the ktx tool."""

import hashlib
import importlib.util
import io
import json
import pathlib
import platform
import struct
import tarfile
import tempfile
import unittest
import zlib

TOOL = pathlib.Path(__file__).resolve().parents[1] / "ktx2" / "gltf_to_ktx2.py"
SPEC = importlib.util.spec_from_file_location("gltf_to_ktx2", TOOL)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the converter")
KTX2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(KTX2)

VERSION = "9.9.9"
# Writes its arguments where the KTX2 would go and reports a PSNR, as ktx create does.
FAKE_KTX = f"""#!/bin/sh
case "$1" in
  --version) echo "ktx version: v{VERSION}" ;;
  create) for last; do :; done; printf 'KTX2 %s\\n' "$*" > "$last"; echo "Level 0:     PSNR: 51.5" ;;
  validate) ;;
esac
"""


def png(rgba: bool) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    width = 4 if rgba else 3
    header = struct.pack(">IIBBBBB", 4, 4, 8, 6 if rgba else 2, 0, 0, 0)
    pixels = zlib.compress(b"".join(b"\0" + bytes(4 * width) for _ in range(4)))
    return KTX2.PNG_MAGIC + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


class ConverterTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = pathlib.Path(temp.name)
        self.inputs = self.root / "in"
        self.asset = self.root / "assets" / "Thing-ktx2"
        self.asset.mkdir(parents=True)
        source = self.inputs / "Thing"
        (source / "tex").mkdir(parents=True)
        (source / "tex" / "colour.jpg").write_bytes(KTX2.JPEG_MAGIC + b"\xe0 not decoded")
        (source / "tex" / "normal.png").write_bytes(png(False))
        (source / "tex" / "alpha.png").write_bytes(png(True))
        (source / "Thing.bin").write_bytes(b"geometry bytes")
        (source / "report.json").write_text("{}\n")
        self.doc = {
            "asset": {"generator": "exporter", "version": "2.0"},
            "extensionsUsed": ["KHR_lights_punctual"],
            "materials": [
                {"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}, "normalTexture": {"index": 1, "scale": 1}},
                {"emissiveTexture": {"index": 2}},
            ],
            "textures": [{"sampler": 0, "source": 0}, {"sampler": 0, "source": 1}, {"sampler": 0, "source": 2}],
            "images": [{"mimeType": "image/jpeg", "name": "colour", "uri": "tex/colour.jpg"},
                       {"mimeType": "image/png", "name": "normal", "uri": "tex/normal.png"},
                       {"mimeType": "image/png", "name": "alpha", "uri": "tex/alpha.png"}],
            "samplers": [{"magFilter": 9729, "minFilter": 9987}],
            "buffers": [{"byteLength": 14, "uri": "Thing.bin"}],
        }
        self.write_source(self.doc)
        archive = self.root / "Thing.tar.xz"
        archive.write_bytes(b"the source archive")
        sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        (self.asset / "source.lock").write_text(f"{sha} Thing.tar.xz https://example.invalid/Thing.tar.xz\n")
        (source / KTX2.STAMP).write_text(f"{sha} 6\n")
        tarball = self.encoder_tarball()
        (self.asset / "encoder.lock").write_text(
            f"{hashlib.sha256(tarball.read_bytes()).hexdigest()} {tarball.name} https://example.invalid/{tarball.name}\n")
        config = {"gltf": "Thing.gltf", "encoder": VERSION, "uastc_quality": 2, "zstd": 18, "mipmap_filter": "box",
                  "mipmap_wrap": "wrap", "threads": 3, "copy": ["report.json"], "copyright": "Thing by someone, CC BY 4.0"}
        (self.asset / "ktx2.json").write_text(json.dumps(config))
        self.out = self.root / "out"

    def write_source(self, doc: dict) -> None:
        (self.inputs / "Thing" / "Thing.gltf").write_text(json.dumps(doc, separators=(",", ":")))

    def encoder_tarball(self) -> pathlib.Path:
        top = f"KTX-Software-{VERSION}-{KTX2.ENCODERS.get(platform.machine(), 'none')}"
        path = self.inputs / f"{top}.tar.bz2"
        with tarfile.open(path, "w:bz2") as archive:
            for name, data, mode in ((f"{top}/bin/ktx", FAKE_KTX.encode(), 0o755), (f"{top}/lib/libktx.so", b"", 0o644)):
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(data), mode
                archive.addfile(info, io.BytesIO(data))
        return path

    def convert(self) -> dict:
        KTX2.convert(self.inputs, self.asset, self.out)
        return json.loads((self.out / "Thing-ktx2.gltf").read_text())

    def test_every_texture_names_its_ktx2_through_basisu_alone(self) -> None:
        doc = self.convert()
        self.assertEqual(doc["extensionsUsed"], ["KHR_lights_punctual", "KHR_texture_basisu"])
        self.assertEqual(doc["extensionsRequired"], ["KHR_texture_basisu"])
        self.assertEqual(list(doc)[:3], ["asset", "extensionsUsed", "extensionsRequired"])
        for index, texture in enumerate(doc["textures"]):
            self.assertEqual(texture, {"sampler": 0, "extensions": {"KHR_texture_basisu": {"source": index}}})
        self.assertEqual([i["uri"] for i in doc["images"]], ["tex/colour.ktx2", "tex/normal.ktx2", "tex/alpha.ktx2"])
        self.assertEqual({i["mimeType"] for i in doc["images"]}, {"image/ktx2"})
        for key in ("materials", "samplers"):
            self.assertEqual(doc[key], self.doc[key])
        self.assertEqual(doc["buffers"], [{"byteLength": 14, "uri": "Thing-ktx2.bin"}])
        self.assertEqual((self.out / "Thing-ktx2.bin").read_bytes(), b"geometry bytes")
        self.assertEqual(doc["asset"]["copyright"], "Thing by someone, CC BY 4.0")
        files = sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob("*") if p.is_file())
        self.assertEqual(files, ["Thing-ktx2.bin", "Thing-ktx2.gltf", "ktx2-report.json", "report.json",
                                 "tex/alpha.ktx2", "tex/colour.ktx2", "tex/normal.ktx2"])

    def test_colour_slots_are_srgb_and_data_slots_linear_and_alpha_stays(self) -> None:
        self.convert()
        args = {name: (self.out / "tex" / f"{name}.ktx2").read_text() for name in ("colour", "normal", "alpha")}
        self.assertIn("--format R8G8B8_SRGB --assign-tf srgb --assign-primaries bt709", args["colour"])
        self.assertIn("--format R8G8B8_UNORM --assign-tf linear --assign-primaries none", args["normal"])
        self.assertIn("--format R8G8B8A8_SRGB", args["alpha"])
        self.assertIn("--threads 3 --no-sse", args["alpha"])
        for text in args.values():
            self.assertIn("--encode uastc --uastc-quality 2 --zstd 18 --generate-mipmap --mipmap-filter box", text)
        report = json.loads((self.out / "ktx2-report.json").read_text())
        self.assertEqual([i["colour"] for i in report["images"]], ["sRGB", "linear", "sRGB"])
        self.assertEqual(report["encoder"], f"ktx version: v{VERSION}")

    def test_an_image_in_colour_and_data_slots_is_refused(self) -> None:
        self.doc["materials"][1]["occlusionTexture"] = {"index": 0}
        self.write_source(self.doc)
        with self.assertRaisesRegex(ValueError, "both colour and data slots"):
            self.convert()

    def test_a_source_or_encoder_off_its_pin_is_refused(self) -> None:
        stamp = self.inputs / "Thing" / KTX2.STAMP
        good = stamp.read_text()
        stamp.write_text("0" * 64 + " 6\n")
        with self.assertRaisesRegex(ValueError, "was not extracted from"):
            self.convert()
        stamp.write_text(good)
        lock = self.asset / "encoder.lock"
        lock.write_text("0" * 64 + lock.read_text()[64:])
        with self.assertRaisesRegex(ValueError, "does not hash to encoder.lock"):
            self.convert()


if __name__ == "__main__":
    unittest.main()
