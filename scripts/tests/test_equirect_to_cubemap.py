"""The cube faces' orientation, seams and the HDRI pin, on a synthetic equirectangular HDR."""

import hashlib
import importlib.util
import json
import math
import pathlib
import tempfile
import unittest

import numpy as np
from PIL import Image

TOOL = pathlib.Path(__file__).resolve().parents[1] / "cubemap" / "equirect_to_cubemap.py"
SPEC = importlib.util.spec_from_file_location("equirect_to_cubemap", TOOL)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the converter")
CUBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CUBE)

FACES = {"+X": "RT.png", "-X": "LF.png", "+Y": "UP.png", "-Y": "DN.png", "+Z": "FT.png", "-Z": "BK.png"}


def write_flat_hdr(path: pathlib.Path, rgb: np.ndarray) -> None:
    """Uncompressed RGBE, which every reader takes."""
    peak = rgb.max(axis=2)
    mantissa, exponent = np.frexp(np.maximum(peak, 1e-30))
    scale = np.where(peak > 1e-30, mantissa * 256.0 / np.maximum(peak, 1e-30), 0.0)
    rgbe = np.zeros(rgb.shape[:2] + (4,), dtype=np.uint8)
    rgbe[..., :3] = np.clip(rgb * scale[..., None], 0, 255).astype(np.uint8)
    rgbe[..., 3] = np.where(peak > 1e-30, exponent + 128, 0).astype(np.uint8)
    header = f"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y {rgb.shape[0]} +X {rgb.shape[1]}\n".encode()
    path.write_bytes(header + rgbe.tobytes())


class CubemapTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = pathlib.Path(temp.name)
        height, width = 64, 128
        rows = (np.arange(height) + 0.5) / height
        sky = np.where(rows < 0.5, 0.2, 0.02).astype(np.float32)
        rgb = np.repeat(sky[:, None], width, axis=1)[..., None] * np.array([0.6, 0.8, 1.0], dtype=np.float32)
        # A hot spot at elevation 0 in the image's centre column, which the converter puts at -Z.
        rgb[30:34, 62:66] = 50.0
        self.hdr = self.dir / "sky.hdr"
        write_flat_hdr(self.hdr, rgb.astype(np.float32))

    def convert(self, **overrides: object) -> dict[str, np.ndarray]:
        config = {"face_size": 16, "supersample": 2, "exposure": 1.0, "yaw_degrees": 0, "faces": FACES}
        config.update(overrides)
        path = self.dir / "config.json"
        path.write_text(json.dumps(config))
        out = self.dir / "out"
        CUBE.main(["tool", str(self.hdr), str(out), str(path)])
        return {axis: np.asarray(Image.open(out / name), dtype=np.float32) for axis, name in FACES.items()}

    def test_the_sky_is_up_and_the_ground_down(self) -> None:
        faces = self.convert()
        self.assertGreater(faces["+Y"].mean(), 110)
        self.assertLess(faces["-Y"].mean(), 60)
        for axis in ("+X", "-X", "+Z"):
            self.assertGreater(faces[axis][0].mean(), faces[axis][-1].mean(), f"{axis}'s top row is not sky")

    def test_the_centre_column_faces_minus_z_and_yaw_turns_it(self) -> None:
        faces = self.convert()
        self.assertEqual(int(np.argmax([f[6:10, 6:10].max() for f in faces.values()])), list(FACES).index("-Z"))
        turned = self.convert(yaw_degrees=90)
        self.assertEqual(int(np.argmax([f[6:10, 6:10].max() for f in turned.values()])), list(FACES).index("-X"))

    def test_neighbouring_faces_meet_without_a_seam(self) -> None:
        faces = self.convert()
        pairs = [("+Z", (slice(None), -1), "+X", (slice(None), 0)), ("+Z", (0, slice(None)), "+Y", (-1, slice(None))),
                 ("-X", (slice(None), -1), "+Z", (slice(None), 0)), ("+Z", (-1, slice(None)), "-Y", (0, slice(None)))]
        for a, edge_a, b, edge_b in pairs:
            self.assertLess(np.abs(faces[a][edge_a] - faces[b][edge_b]).mean(), 12, f"{a}/{b}")

    def test_an_hdri_that_differs_from_its_pin_is_refused(self) -> None:
        good = hashlib.sha256(self.hdr.read_bytes()).hexdigest()
        self.convert(hdri={"sha256": good})
        with self.assertRaises(SystemExit):
            self.convert(hdri={"sha256": "0" * 64})

    def test_the_direction_table_matches_vulkans_face_selection(self) -> None:
        for axis in FACES:
            x, y, z = CUBE.face_directions(axis, 4, 1)
            major = {"X": x, "Y": y, "Z": z}[axis[1]]
            self.assertTrue(np.all(np.sign(major) == (1 if axis[0] == "+" else -1)))
            self.assertTrue(np.allclose(x * x + y * y + z * z, 1.0))
        self.assertAlmostEqual(math.degrees(math.acos(CUBE.face_directions("+Y", 1, 1)[1][0, 0])), 0.0, places=5)


if __name__ == "__main__":
    unittest.main()
