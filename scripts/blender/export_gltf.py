"""Bake a Blender scene's procedural, box-projected materials into tiling textures and export glTF 2.0.

Run headless, never with auto-run scripts:
  blender -b -Y <scene.blend> --python scripts/blender/export_gltf.py -- --out <dir> [--config <scene.json>]
The .blend is never saved; every change happens in memory before the export.
"""

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bmesh  # ty: ignore[unresolved-import]  # Blender's bundled Python provides it
import bpy  # ty: ignore[unresolved-import]  # Blender's bundled Python provides it
import numpy as np  # ty: ignore[unresolved-import]  # Blender bundles numpy

PROCEDURAL = {
    "ShaderNodeTexNoise",
    "ShaderNodeTexVoronoi",
    "ShaderNodeTexWave",
    "ShaderNodeTexMagic",
    "ShaderNodeTexGradient",
    "ShaderNodeTexWhiteNoise",
}
CHANNELS = (("Base Color", "basecolor", False), ("Roughness", "roughness", True), ("Metallic", "metallic", True))
GPU_BACKENDS = ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL")
UV_NAME = "BoxUV"


def log(msg):
    print(f"[export_gltf] {msg}", flush=True)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser(prog="export_gltf.py")
    p.add_argument("--out", required=True, help="output directory for <name>.gltf, .bin and textures/")
    p.add_argument("--config", help="scene JSON with bake_inputs, brick_repeats, palette, texel_m")
    p.add_argument("--name", help="glTF file stem (default: the .blend's stem)")
    p.add_argument("--device", default="auto", choices=("auto", "cpu", "gpu"))
    args = p.parse_args(argv)
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else {}
    return args, cfg


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def walk_nodes(tree):
    for node in tree.nodes:
        yield node
        if node.bl_idname == "ShaderNodeGroup" and node.node_tree:
            yield from walk_nodes(node.node_tree)


def output_node(tree):
    outs = [n for n in tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial"]
    return next((n for n in outs if n.is_active_output), outs[0] if outs else None)


def find_principled(socket, seen=None):
    seen = seen if seen is not None else set()
    if not socket.is_linked:
        return None
    node = socket.links[0].from_node
    if node.name in seen:
        return None
    seen.add(node.name)
    if node.bl_idname == "ShaderNodeBsdfPrincipled":
        return node
    for inp in node.inputs:
        if inp.type == "SHADER":
            hit = find_principled(inp, seen)
            if hit:
                return hit
    return None


def upstream(socket):
    """Every node feeding a socket, groups entered through their outputs' links."""
    found, stack = [], [socket]
    while stack:
        s = stack.pop()
        for link in s.links:
            node = link.from_node
            if node in found:
                continue
            found.append(node)
            stack.extend(i for i in node.inputs if i.is_linked)
            if node.bl_idname == "ShaderNodeGroup" and node.node_tree:
                found.extend(walk_nodes(node.node_tree))
    return found


def group_input_value(group_node, inner_socket):
    """The value a group node feeds into an inner socket wired straight from its Group Input."""
    if not inner_socket.is_linked:
        return inner_socket.default_value
    link = inner_socket.links[0]
    if link.from_node.bl_idname != "NodeGroupInput":
        return inner_socket.default_value
    outer = next((i for i in group_node.inputs if i.identifier == link.from_socket.identifier), None)
    return outer.default_value if outer is not None else inner_socket.default_value


def socket_value(owner, sock):
    return group_input_value(owner, sock) if owner else sock.default_value


def brick_tile(mat, repeats):
    """Tile size (u, v) in object units for the first brick texture, or None."""
    for node in mat.node_tree.nodes:
        owner = node if node.bl_idname == "ShaderNodeGroup" and node.node_tree else None
        candidates = owner.node_tree.nodes if owner else [node]
        brick = next((n for n in candidates if n.bl_idname == "ShaderNodeTexBrick"), None)
        if brick is None:
            continue
        scale = float(socket_value(owner, brick.inputs["Scale"])) or 1.0
        width = float(socket_value(owner, brick.inputs["Brick Width"])) / scale
        row = float(socket_value(owner, brick.inputs["Row Height"])) / scale
        period_rows = max(brick.offset_frequency, brick.squash_frequency, 1)
        return width * repeats[0], row * period_rows * repeats[1]
    return None


def mapping_scale(mat):
    for node in mat.node_tree.nodes:
        if node.bl_idname == "ShaderNodeTexImage" and node.inputs["Vector"].is_linked:
            for up in upstream(node.inputs["Vector"]):
                if up.bl_idname == "ShaderNodeMapping":
                    return tuple(float(x) for x in up.inputs["Scale"].default_value)
            return (1.0, 1.0, 1.0)
    return None


def face_color_attribute(principled, mesh_users):
    sock = principled.inputs["Base Color"]
    if not sock.is_linked or sock.links[0].from_node.bl_idname != "ShaderNodeAttribute":
        return None
    name = sock.links[0].from_node.attribute_name
    for me in mesh_users:
        attr = me.attributes.get(name)
        if attr is not None and attr.domain == "FACE" and attr.data_type in ("FLOAT_COLOR", "BYTE_COLOR"):
            return name
    return None


def classify(mat, mesh_users, cfg):
    tree = mat.node_tree
    out = output_node(tree) if tree else None
    principled = find_principled(out.inputs["Surface"]) if out else None
    if principled is None:
        return {"kind": "unsupported"}
    info = {"principled": principled.name}
    attr = face_color_attribute(principled, mesh_users)
    if attr:
        return info | {"kind": "palette", "attribute": attr}
    nodes = list(walk_nodes(tree))
    types = {n.bl_idname for n in nodes}
    tile = brick_tile(mat, cfg.get("brick_repeats", [4, 4]))
    if tile:
        return info | {"kind": "tile", "tile": tile, "floor_v": tile[1], "source_res": 0}
    scale = mapping_scale(mat) if "ShaderNodeTexImage" in types else None
    if scale:
        sx, _, sz = scale
        res = max((max(n.image.size) for n in nodes if n.bl_idname == "ShaderNodeTexImage" and n.image), default=0)
        return info | {"kind": "tile", "tile": (1.0 / sx, 1.0 / sz), "floor_v": 1.0 / scale[1], "source_res": res}
    linked = [c for c, _, _ in CHANNELS if principled.inputs[c].is_linked]
    if linked and types & PROCEDURAL:
        return info | {"kind": "mean", "channels": linked}
    return info | {"kind": "constant"}


# ---------------------------------------------------------------- baking


def configure_device(scene, wanted):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    if wanted == "cpu":
        return "CPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in GPU_BACKENDS:
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type == backend]
        if gpus:
            for d in prefs.devices:
                d.use = d.type == backend
            scene.cycles.device = "GPU"
            return f"{backend}: {', '.join(d.name for d in gpus)}"
    if wanted == "gpu":
        raise RuntimeError("no Cycles GPU backend found")
    return "CPU"


def bake_scene(device, samples):
    scene = bpy.data.scenes.new("ExportBake")
    log(f"bake device: {configure_device(scene, device)}")
    # A new scene renders 4096 samples; emission and normal bakes only need antialiasing.
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.render.bake.margin = 0
    scene.render.bake.use_clear = True
    return scene


def make_plane(scene, width, height):
    me = bpy.data.meshes.new("BakePlane")
    me.from_pydata([(0, 0, 0), (width, 0, 0), (width, 0, height), (0, 0, height)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name=UV_NAME)
    for loop, coord in zip(uv.data, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop.uv = coord
    ob = bpy.data.objects.new("BakePlane", me)
    scene.collection.objects.link(ob)
    return ob


def new_image(name, res_u, res_v, data, float_buffer=False):
    img = bpy.data.images.new(name, res_u, res_v, alpha=False, float_buffer=float_buffer, is_data=data)
    img.colorspace_settings.name = "Non-Color" if data else "sRGB"
    return img


def apply_bake_inputs(mat, overrides):
    for node in mat.node_tree.nodes:
        if node.bl_idname != "ShaderNodeGroup" or not node.node_tree:
            continue
        for key, value in overrides.get(node.node_tree.name, {}).items():
            if key in node.inputs:
                node.inputs[key].default_value = value


def neutralize_procedurals(mat):
    """Top-level 3D noise cannot tile; its mean (0.5) keeps the baked tile seamless."""
    tree = mat.node_tree
    for node in [n for n in tree.nodes if n.bl_idname in PROCEDURAL]:
        for out in node.outputs:
            for link in list(out.links):
                if out.type == "RGBA":
                    const = tree.nodes.new("ShaderNodeRGB")
                    const.outputs[0].default_value = (0.5, 0.5, 0.5, 1.0)
                else:
                    const = tree.nodes.new("ShaderNodeValue")
                    const.outputs[0].default_value = 0.5
                tree.links.new(const.outputs[0], link.to_socket)


def bake_pass(scene, plane, mat, image, bake_type, source=None):
    work = mat.copy()
    work.name = f"__bake_{mat.name}"
    tree = work.node_tree
    if source is not None:
        principled = tree.nodes[source[0]]
        out = output_node(tree)
        emit = tree.nodes.new("ShaderNodeEmission")
        emit.inputs["Strength"].default_value = 1.0
        tree.links.new(principled.inputs[source[1]].links[0].from_socket, emit.inputs["Color"])
        tree.links.new(emit.outputs[0], out.inputs["Surface"])
    target = tree.nodes.new("ShaderNodeTexImage")
    target.image = image
    tree.nodes.active = target
    plane.data.materials.clear()
    plane.data.materials.append(work)
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0], active_object=plane,
                                   object=plane, selected_objects=[plane], selected_editable_objects=[plane]):
        if bake_type == "NORMAL":
            bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", margin=0, use_clear=True)
        else:
            bpy.ops.object.bake(type="EMIT", margin=0, use_clear=True)
    plane.data.materials.clear()
    bpy.data.materials.remove(work)


def tile_resolution(extent_m, source_res, cfg):
    texel = cfg.get("texel_m", 0.004)
    lo, hi = cfg.get("min_res", 256), cfg.get("max_res", 2048)
    want = max(extent_m / texel, source_res)
    return int(min(hi, max(lo, 2 ** math.ceil(math.log2(max(want, 1.0))))))


def bake_tile(scene, mat, label, info, cfg, bake_dir):
    tile_u, tile_v = info["tile"]
    res = tile_resolution(max(tile_u, tile_v), info["source_res"], cfg)
    plane = make_plane(scene, tile_u, tile_v)
    principled = mat.node_tree.nodes[info["principled"]]
    maps, constants = {}, {}
    for channel, suffix, data in CHANNELS:
        if principled.inputs[channel].is_linked:
            img = new_image(f"{label}_{suffix}", res, res, data)
            bake_pass(scene, plane, mat, img, "EMIT", source=(principled.name, channel))
            flat = flat_value(img) if data else None
            if flat is not None:
                constants[channel] = flat
                bpy.data.images.remove(img)
            else:
                maps[channel] = save_image(img, bake_dir, "PNG" if data else "JPEG", cfg.get("jpeg_quality", 92))
    if principled.inputs["Normal"].is_linked:
        img = new_image(f"{label}_normal", res, res, True)
        bake_pass(scene, plane, mat, img, "NORMAL")
        maps["Normal"] = save_image(img, bake_dir, "PNG")
    bpy.data.objects.remove(plane)
    return res, maps, constants


def flat_value(img):
    """The value of a data map without variation, which then ships as a factor instead of a texture."""
    px = np.empty(len(img.pixels), np.float32)
    img.pixels.foreach_get(px)
    grey = px.reshape(-1, 4)[:, 0]
    return float(grey.mean()) if float(grey.max() - grey.min()) < 1.0 / 255.0 else None


def save_image(img, bake_dir, fmt, quality=92):
    path = bake_dir / f"{img.name}.{'jpg' if fmt == 'JPEG' else 'png'}"
    img.filepath_raw = str(path)
    img.file_format = fmt
    if fmt == "JPEG":
        img.save(quality=quality)
    else:
        img.save()
    return img


def bake_mean(scene, mat, info):
    """Mean of a non-tiling procedural channel, from a float bake over a 16 m plane."""
    plane = make_plane(scene, 16.0, 16.0)
    principled = mat.node_tree.nodes[info["principled"]]
    means = {}
    for channel in info["channels"]:
        img = new_image(f"__mean_{mat.name}_{channel}", 64, 64, True, float_buffer=True)
        bake_pass(scene, plane, mat, img, "EMIT", source=(principled.name, channel))
        px = np.empty(64 * 64 * 4, np.float32)
        img.pixels.foreach_get(px)
        means[channel] = px.reshape(-1, 4)[:, :3].mean(axis=0).tolist()
        bpy.data.images.remove(img)
    bpy.data.objects.remove(plane)
    return means


# ---------------------------------------------------------------- rebuilding


KEEP = ("Metallic", "Roughness", "Alpha", "IOR", "Coat Weight", "Coat Roughness", "Specular IOR Level",
        "Emission Color", "Emission Strength")


def principled_values(node):
    vals = {}
    for key in KEEP + ("Base Color",):
        sock = node.inputs.get(key)
        if sock is not None and not sock.is_linked:
            dv = sock.default_value
            vals[key] = list(dv) if hasattr(dv, "__len__") else float(dv)
    return vals


def rebuild(mat, values, maps):
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    tree.links.new(bsdf.outputs[0], out.inputs["Surface"])
    for key, val in values.items():
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = val
    if not maps:
        return
    uv = tree.nodes.new("ShaderNodeUVMap")
    uv.uv_map = UV_NAME
    for channel, img in maps.items():
        tex = tree.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tree.links.new(uv.outputs[0], tex.inputs["Vector"])
        if channel == "Normal":
            nmap = tree.nodes.new("ShaderNodeNormalMap")
            nmap.uv_map = UV_NAME
            tree.links.new(tex.outputs["Color"], nmap.inputs["Color"])
            tree.links.new(nmap.outputs[0], bsdf.inputs["Normal"])
        else:
            tree.links.new(tex.outputs["Color"], bsdf.inputs[channel])


def kmeans(colors, k, iterations=12):
    rng = np.random.default_rng(0)
    sample = colors[rng.choice(len(colors), size=min(len(colors), 200_000), replace=False)]
    centers = sample[rng.choice(len(sample), size=k, replace=False)]
    for _ in range(iterations):
        labels = np.argmin(((sample[:, None, :] - centers[None]) ** 2).sum(-1), axis=1)
        for i in range(k):
            members = sample[labels == i]
            if len(members):
                centers[i] = members.mean(axis=0)
    labels = np.empty(len(colors), np.int32)
    for start in range(0, len(colors), 500_000):
        chunk = colors[start : start + 500_000]
        labels[start : start + len(chunk)] = np.argmin(((chunk[:, None, :] - centers[None]) ** 2).sum(-1), axis=1)
    return centers, labels


def palette(mat, info, users, k):
    """Face colours become k materials, so no vertex splits per face and no COLOR_0 support is needed."""
    values = principled_values(mat.node_tree.nodes[info["principled"]])
    made = []
    for me in users:
        attr = me.attributes[info["attribute"]]
        cols = np.empty(len(attr.data) * 4, np.float32)
        attr.data.foreach_get("color", cols)
        centers, labels = kmeans(cols.reshape(-1, 4)[:, :3], k)
        slot = list(me.materials).index(mat)
        mats = []
        for i, c in enumerate(centers):
            m = bpy.data.materials.new(f"{mat.name}_{i:02d}")
            rebuild(m, values | {"Base Color": [*c.tolist(), 1.0]}, {})
            mats.append(m)
        base = len(me.materials)
        for m in mats:
            me.materials.append(m)
        idx = np.empty(len(me.polygons), np.int32)
        me.polygons.foreach_get("material_index", idx)
        idx = np.where(idx == slot, base + labels, idx)
        me.polygons.foreach_set("material_index", idx)
        made += [m.name for m in mats]
    return made


def box_uvs(me, scales):
    """One UV per loop from object-space position along the face's dominant axis, in tiles."""
    nv, npoly, nl = len(me.vertices), len(me.polygons), len(me.loops)
    co = np.empty(nv * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    lv = np.empty(nl, np.int32)
    me.loops.foreach_get("vertex_index", lv)
    normal = np.empty(npoly * 3, np.float32)
    me.polygons.foreach_get("normal", normal)
    start = np.empty(npoly, np.int32)
    me.polygons.foreach_get("loop_start", start)
    total = np.empty(npoly, np.int32)
    me.polygons.foreach_get("loop_total", total)
    mi = np.empty(npoly, np.int32)
    me.polygons.foreach_get("material_index", mi)
    poly_of_loop = np.empty(nl, np.int32)
    for p_start, p_total, p in zip(start, total, range(npoly)):
        poly_of_loop[p_start : p_start + p_total] = p
    axis = np.argmax(np.abs(normal.reshape(-1, 3)), axis=1)[poly_of_loop]
    su, sv_wall, sv_floor = (scales[:, i][mi[poly_of_loop]] for i in range(3))
    p = co[lv]
    u = np.where(axis == 0, p[:, 1], p[:, 0]) * su
    v = np.where(axis == 2, p[:, 1] * sv_floor, p[:, 2] * sv_wall)
    layer = me.uv_layers.get(UV_NAME) or me.uv_layers.new(name=UV_NAME)
    layer.data.foreach_set("uv", np.stack([u, v], axis=1).astype(np.float32).ravel())
    me.uv_layers.active = layer
    layer.active_render = True


# ---------------------------------------------------------------- export


def triangulate_ngons(me):
    """In the mesh data, not as a modifier: linked duplicates keep sharing it and export one mesh."""
    bm = bmesh.new()
    bm.from_mesh(me)
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    if ngons:
        bmesh.ops.triangulate(bm, faces=ngons, quad_method="BEAUTY", ngon_method="BEAUTY")
        bm.to_mesh(me)
    bm.free()
    return len(ngons)


def large_mesh(ob, depsgraph, large):
    # A modifier makes the exporter write one mesh per object, so linked duplicates are never decimated.
    return ob.data.users == 1 and len(ob.evaluated_get(depsgraph).data.loop_triangles) > large["min_triangles"]


def reduce_and_triangulate(scene, cfg):
    """Decimate what the config asks for, and triangulate n-gons, whose tangents MikkTSpace skips."""
    named, large = cfg.get("decimate", {}), cfg.get("decimate_large")
    meshes = {ob.data for ob in scene.objects if ob.type == "MESH" and not ob.hide_render}
    split = sum(triangulate_ngons(me) for me in meshes)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for ob in [o for o in scene.objects if o.type == "MESH" and not o.hide_render]:
        ratio = named.get(ob.name)
        if ratio is None and large and large_mesh(ob, depsgraph, large):
            ratio = large["ratio"]
        if ratio is None:
            continue
        if cfg.get("smooth_decimated"):
            ob.data.shade_smooth()
        dec = ob.modifiers.new("ExportDecimate", "DECIMATE")
        dec.ratio = float(ratio)
        dec.use_collapse_triangulate = True
    log(f"triangulated {split} n-gons")


def apply_render_visibility(scene, visibility):
    """A variant may swap in the author's own lighter objects, such as a hidden low-detail crowd."""
    for name, shown in visibility.items():
        if name in scene.objects:
            scene.objects[name].hide_render = not shown


def finished(doc, active_camera):
    """Lights are optional, though Blender marks them required; glTF has no active camera, so extras name it."""
    required = [e for e in doc.get("extensionsRequired", []) if e != "KHR_lights_punctual"]
    if required:
        doc["extensionsRequired"] = required
    else:
        doc.pop("extensionsRequired", None)
    if active_camera and doc.get("scenes"):
        doc["scenes"][doc.get("scene", 0)].setdefault("extras", {})["active_camera"] = active_camera
    return doc


def finish_gltf(path, active_camera):
    if path.suffix == ".gltf":
        doc = finished(json.loads(path.read_text(encoding="utf-8")), active_camera)
        path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
        return
    data = path.read_bytes()
    json_len = int.from_bytes(data[12:16], "little")
    doc = finished(json.loads(data[20 : 20 + json_len]), active_camera)
    chunk = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    chunk += b" " * (-len(chunk) % 4)
    rest = data[20 + json_len :]
    body = len(chunk).to_bytes(4, "little") + b"JSON" + chunk + rest
    path.write_bytes(data[:8] + (12 + len(body)).to_bytes(4, "little") + body)


def export(path, cfg):
    known = set(bpy.ops.export_scene.gltf.get_rna_type().properties.keys())
    opts = {
        "filepath": str(path),
        "export_format": "GLTF_SEPARATE",
        "export_texture_dir": "textures",
        "export_image_format": "AUTO",
        "export_image_quality": cfg.get("jpeg_quality", 92),
        "export_apply": True,
        "export_yup": True,
        "export_texcoords": True,
        "export_normals": True,
        "export_tangents": True,
        "export_materials": "EXPORT",
        "export_vertex_color": "NONE",
        "export_cameras": True,
        "export_lights": True,
        "export_extras": False,
        "export_animations": False,
        "export_draco_mesh_compression_enable": False,
        "export_gpu_instances": False,
        "use_renderable": True,
        "use_visible": False,
    } | cfg.get("gltf_options", {})
    dropped = sorted(k for k in opts if k not in known)
    if dropped:
        log(f"exporter lacks options, skipped: {dropped}")
    bpy.ops.export_scene.gltf(**{k: v for k, v in opts.items() if k in known})


def material_meshes(scene):
    meshes = {}
    for ob in scene.objects:
        if ob.type == "MESH" and not ob.hide_render:
            for slot in ob.material_slots:
                if slot.material:
                    meshes.setdefault(slot.material, set()).add(ob.data)
    return meshes


def convert_tile(baker, mat, info, cfg, bake_dir, overrides, tile_scales):
    src = mat.copy()
    apply_bake_inputs(src, overrides)
    neutralize_procedurals(src)
    values = principled_values(src.node_tree.nodes[info["principled"]])
    res, maps, constants = bake_tile(baker, src, mat.name, info, cfg, bake_dir)
    bpy.data.materials.remove(src)
    rebuild(mat, values | constants, maps)
    tile_scales[mat.name] = (1.0 / info["tile"][0], 1.0 / info["tile"][1], 1.0 / info["floor_v"])
    return {"tile_m": [round(x, 4) for x in info["tile"]], "res": res, "maps": sorted(maps),
            "constants": {k: round(v, 4) for k, v in constants.items()}}


def convert_mean(baker, mat, info):
    values = principled_values(mat.node_tree.nodes[info["principled"]])
    means = bake_mean(baker, mat, info)
    for channel, mean in means.items():
        values[channel] = [*mean, 1.0] if channel == "Base Color" else float(np.mean(mean))
    rebuild(mat, values, {})
    return {"means": {k: [round(x, 4) for x in (v if isinstance(v, list) else [v])] for k, v in means.items()}}


def convert_material(baker, mat, users, cfg, bake_dir, overrides, tile_scales):
    info = classify(mat, users, cfg)
    entry = {"kind": info["kind"], "meshes": len(users)}
    if info["kind"] == "tile":
        entry |= convert_tile(baker, mat, info, cfg, bake_dir, overrides, tile_scales)
    elif info["kind"] == "mean":
        entry |= convert_mean(baker, mat, info)
    elif info["kind"] == "palette":
        entry["palette"] = palette(mat, info, users, cfg.get("palette", 32))
    elif info["kind"] == "constant":
        rebuild(mat, principled_values(mat.node_tree.nodes[info["principled"]]), {})
    return entry


def apply_box_uvs(meshes, tile_scales):
    for me in {m for mat in meshes for m in meshes[mat]}:
        mats = list(me.materials)
        if not any(m and m.name in tile_scales for m in mats):
            continue
        scales = np.array([tile_scales.get(m.name, (0.0, 0.0, 0.0)) if m else (0.0, 0.0, 0.0) for m in mats],
                          np.float32).reshape(-1, 3)
        box_uvs(me, scales)


def main():
    t0 = time.time()
    args, cfg = parse_args()
    blend = Path(bpy.data.filepath)
    name = args.name or blend.stem
    out = Path(args.out)
    bake_dir = out / "_bake"
    bake_dir.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    apply_render_visibility(scene, cfg.get("render_visibility", {}))
    meshes = material_meshes(scene)
    report = {"blender": bpy.app.version_string, "source": blend.name, "source_sha256": sha256(blend),
              "config": cfg, "materials": {}}
    baker = bake_scene(args.device, cfg.get("samples", 16))
    overrides = cfg.get("bake_inputs", {})
    tile_scales = {}
    for mat, users in sorted(meshes.items(), key=lambda kv: kv[0].name):
        entry = convert_material(baker, mat, users, cfg, bake_dir, overrides, tile_scales)
        report["materials"][mat.name] = entry
        log(f"{mat.name}: {entry}")
    apply_box_uvs(meshes, tile_scales)
    bpy.data.scenes.remove(baker)
    reduce_and_triangulate(scene, cfg)
    binary = cfg.get("gltf_options", {}).get("export_format") == "GLB"
    gltf = out / f"{name}.{'glb' if binary else 'gltf'}"
    export(gltf, cfg)
    finish_gltf(gltf, scene.camera.name if scene.camera else None)
    report["seconds"] = round(time.time() - t0, 1)
    (out / "export-report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    log(f"done in {report['seconds']} s: {gltf}")

main()
