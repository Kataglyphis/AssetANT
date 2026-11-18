"""Six sRGB PNG cube faces from an equirectangular Radiance HDR, in Vulkan's cubemap convention.

Usage: equirect_to_cubemap.py <in.hdr> <out dir> <config.json> [--stats]

The config fixes everything the bytes depend on: the HDRI's SHA-256, face size, supersampling, exposure, yaw
and the face names; --stats prints the HDRI's size, peak and upper-hemisphere luminance instead.
"""

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# +X, -X, +Y, -Y, +Z, -Z: the order vkCmdCopyBufferToImage takes a cube's layers in.
FACE_AXES = ("+X", "-X", "+Y", "-Y", "+Z", "-Z")


def read_hdr(path):
    """A Radiance RGBE file, flat or new-style run-length encoded, as float32 HxWx3."""
    data = Path(path).read_bytes()
    pos = 0
    while True:
        end = data.index(b"\n", pos)
        line = data[pos:end]
        pos = end + 1
        if line == b"":
            break
        if line.startswith(b"FORMAT=") and line != b"FORMAT=32-bit_rle_rgbe":
            raise ValueError(f"unsupported {line.decode()}")
    end = data.index(b"\n", pos)
    size = data[pos:end].split()
    pos = end + 1
    if len(size) != 4 or size[0] != b"-Y" or size[2] != b"+X":
        raise ValueError(f"unsupported orientation {size}")
    height, width = int(size[1]), int(size[3])
    rgbe = np.empty((height, width, 4), dtype=np.uint8)
    buf = np.frombuffer(data, dtype=np.uint8)
    for y in range(height):
        if buf[pos] == 2 and buf[pos + 1] == 2 and (int(buf[pos + 2]) << 8 | int(buf[pos + 3])) == width:
            pos += 4
            for channel in range(4):
                x = 0
                while x < width:
                    count = int(buf[pos])
                    pos += 1
                    if count > 128:
                        count -= 128
                        rgbe[y, x : x + count, channel] = buf[pos]
                        pos += 1
                    else:
                        rgbe[y, x : x + count, channel] = buf[pos : pos + count]
                        pos += count
                    x += count
        else:
            rgbe[y] = buf[pos : pos + 4 * width].reshape(width, 4)
            pos += 4 * width
    exponent = rgbe[..., 3].astype(np.int32)
    scale = np.where(exponent > 0, np.ldexp(1.0, exponent - 136), 0.0).astype(np.float32)
    return rgbe[..., :3].astype(np.float32) * scale[..., None]


def face_directions(axis, size, samples):
    """World directions through every supersample of one face; row 0 is the image's top."""
    offsets = (np.arange(size * samples, dtype=np.float64) + 0.5) / (size * samples) * 2.0 - 1.0
    sc, tc = np.meshgrid(offsets, offsets)
    one = np.ones_like(sc)
    # Vulkan spec, cube map face selection: (sc, tc) per major axis.
    x, y, z = {
        "+X": (one, -tc, -sc),
        "-X": (-one, -tc, sc),
        "+Y": (sc, one, tc),
        "-Y": (sc, -one, -tc),
        "+Z": (sc, -tc, one),
        "-Z": (-sc, -tc, -one),
    }[axis]
    length = np.sqrt(x * x + y * y + z * z)
    return x / length, y / length, z / length


def sample_equirect(image, x, y, z, yaw):
    """Bilinear lookup; +Y is up, and the image's centre column faces -Z before `yaw` turns it about +Y."""
    height, width, _ = image.shape
    longitude = np.arctan2(x, -z) + yaw
    u = (longitude / (2.0 * math.pi) + 0.5) % 1.0 * width - 0.5
    v = np.arccos(np.clip(y, -1.0, 1.0)) / math.pi * height - 0.5
    u0 = np.floor(u).astype(np.int64)
    v0 = np.clip(np.floor(v).astype(np.int64), 0, height - 1)
    v1 = np.clip(v0 + 1, 0, height - 1)
    fu = (u - u0)[..., None]
    fv = np.clip(v - np.floor(v), 0.0, 1.0)[..., None]
    u0 %= width
    u1 = (u0 + 1) % width
    top = image[v0, u0] * (1 - fu) + image[v0, u1] * fu
    bottom = image[v1, u0] * (1 - fu) + image[v1, u1] * fu
    return top * (1 - fv) + bottom * fv


def linear_to_srgb(linear):
    linear = np.clip(linear, 0.0, 1.0)
    return np.where(linear <= 0.0031308, linear * 12.92, 1.055 * np.power(linear, 1.0 / 2.4) - 0.055)


def main(argv):
    if len(argv) < 4:
        sys.exit(__doc__)
    config = json.loads(Path(argv[3]).read_text())
    pinned = config.get("hdri", {}).get("sha256")
    if pinned is not None and hashlib.sha256(Path(argv[1]).read_bytes()).hexdigest() != pinned:
        sys.exit(f"{argv[1]} does not hash to the pinned {pinned}")
    image = read_hdr(argv[1])
    if "--stats" in argv[4:]:
        luminance = image @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        row, column = np.unravel_index(np.argmax(luminance), luminance.shape)
        upper = luminance[: image.shape[0] // 2]
        print(f"{image.shape[1]}x{image.shape[0]}, peak {luminance.max():.1f} at row {row} column {column}")
        for q in (50, 90, 99, 99.9):
            print(f"upper hemisphere p{q}: {np.percentile(upper, q):.4f}")
        return
    size, samples = config["face_size"], config["supersample"]
    exposure, yaw = config["exposure"], math.radians(config["yaw_degrees"])
    out = Path(argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for axis in FACE_AXES:
        x, y, z = face_directions(axis, size, samples)
        radiance = sample_equirect(image, x, y, z, yaw) * exposure
        radiance = radiance.reshape(size, samples, size, samples, 3).mean(axis=(1, 3))
        pixels = np.round(linear_to_srgb(radiance) * 255.0).astype(np.uint8)
        Image.fromarray(pixels, "RGB").save(out / config["faces"][axis], optimize=True)


if __name__ == "__main__":
    main(sys.argv)
