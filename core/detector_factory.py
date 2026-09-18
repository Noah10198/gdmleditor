"""
DetectorFactory — build a standalone GDML file node for a simple detector.

The Project Tree shows every GDML file as a top-level entry, so a detector
created from the toolbar becomes a *sibling* of the imported files:

    box1.gdml
      +-- Solids
      |     +-- worldbox_solid      (world reference box)
      |     +-- box1                (detector solid, named in the dialog)
      +-- World
            +-- worldbox            (world logical volume)
                +-- box1_vol        (physical placement of the detector)

The tree mirrors what the parser produces for an imported file (file node ->
WORLD_NODE + logical VOLUME_NODE, each physvol owning an independent instance
clone), so the scene builder, the export writer, the transform dialog and the
material dialog all consume it unchanged.

All sizes here are millimetres, matching what the parser stores in
`GdmlNode.solid_params`.
"""

from typing import Dict, Iterable, Optional, Sequence, Set, Tuple

from core.gdml_tree import GdmlNode, GdmlNodeType, Placement

BOX = "box"
SPHERE = "sphere"

#: Per-shape spec shared by the toolbar dialog and the node builder.
#: `params` becomes the spin boxes; `defaults` are prefilled sizes in mm
#: (a 10 cm x 10 cm x 3 mm slab by default).
SHAPES: Dict[str, dict] = {
    BOX: {
        "label": "Box",
        "params": (("x", "X"), ("y", "Y"), ("z", "Z")),
        "defaults": {"x": 100.0, "y": 100.0, "z": 3.0},
    },
    SPHERE: {
        "label": "Sphere",
        "params": (("rmax", "RMax"),),
        "defaults": {"rmax": 50.0},
    },
}

#: Logical-volume name of the world each detector file gets.
WORLD_VOLUME_NAME: Dict[str, str] = {BOX: "worldbox", SPHERE: "worldsphere"}

#: Fallback world edge = (largest detector dimension) x this factor.
#: Only used when the project has no world volume to copy a size from.
WORLD_SIZE_FACTOR = 10.0


# ==================== Names ====================


def collect_existing_names(root_node: Optional[GdmlNode]) -> Set[str]:
    """Every name already taken in the project: file names + all node names."""
    names: Set[str] = set()
    if root_node is None:
        return names
    for file_node in root_node.children:
        if file_node.node_type != GdmlNodeType.GDML_FILE:
            continue
        if file_node.name:
            names.add(file_node.name)
        for node in file_node.get_all_descendants():
            if node.name:
                names.add(node.name)
    return names


def make_unique_name(existing: Iterable[str], base: str) -> str:
    """box1, box2, ... — the prefilled name for a newly added detector."""
    used = set(existing)
    n = 1
    while f"{base}{n}" in used:
        n += 1
    return f"{base}{n}"


def is_valid_name(name: str) -> bool:
    """Names must survive a round-trip as an XML attribute value."""
    return bool(name) and all(c.isalnum() or c in "_-" for c in name)


# ==================== Sizes ====================


def derive_world_size(params_mm: Dict[str, float]) -> Tuple[float, float, float]:
    """World box edge that encloses the detector — used when the scene is empty."""
    extent = max([abs(float(v)) for v in params_mm.values()] + [1.0])
    edge = extent * WORLD_SIZE_FACTOR
    return (edge, edge, edge)


def format_size_text(shape: str, params_mm: Dict[str, float]) -> str:
    """Human-readable size for the log line, e.g. '100 x 100 x 3 mm'."""
    keys = SHAPES[shape]["params"]
    single = len(keys) == 1
    parts = [(f"{label}=" if single else "") + f"{params_mm.get(key, 0.0):g}"
             for key, label in keys]
    return " x ".join(parts) + " mm"


# ==================== Node construction ====================


def _instance_clone(volume: GdmlNode) -> GdmlNode:
    """Copy a logical volume into a placed instance, like the parser does."""
    node = GdmlNode(GdmlNodeType.VOLUME_NODE, volume.name)
    node.gdml_tag = volume.gdml_tag
    node.solid_params = dict(volume.solid_params) if volume.solid_params else None
    node.material_name = volume.material_name
    node.gdml_attrs = dict(volume.gdml_attrs)
    return node


def build_detector_file_node(*, shape: str, name: str,
                             params_mm: Dict[str, float],
                             world_size: Optional[Sequence[float]] = None) -> GdmlNode:
    """Build the GDML file node holding one box / sphere detector."""
    if shape not in SHAPES:
        raise ValueError(f"unsupported detector shape: {shape!r}")

    params = {key: abs(float(value)) for key, value in params_mm.items()}
    world = tuple(float(v) for v in (world_size or derive_world_size(params)))

    vol_name = WORLD_VOLUME_NAME.get(shape, "worldbox")
    solid_name = f"{vol_name}_solid"
    det_vol_name = f"{name}_vol"

    file_node = GdmlNode(GdmlNodeType.GDML_FILE, f"{name}.gdml")

    # ---- world: box + logical volume, named worldbox / worldsphere ----
    world_solid = GdmlNode(GdmlNodeType.SOLID_DEF, solid_name)
    world_solid.gdml_tag = BOX
    world_solid.gdml_attrs = {"name": solid_name}
    world_solid.solid_params = {"x": world[0], "y": world[1], "z": world[2]}

    world_vol = GdmlNode(GdmlNodeType.WORLD_NODE, vol_name)
    world_vol.gdml_tag = BOX
    world_vol.ref_name = solid_name
    # Material is deliberately left unset: pick it in the Material panel.
    world_vol.gdml_attrs = {"name": vol_name, "solidref": solid_name}
    world_vol.solid_params = dict(world_solid.solid_params)
    world_vol.add_child(world_solid)

    # ---- detector: solid + logical volume (the file-level volume store) ----
    solid = GdmlNode(GdmlNodeType.SOLID_DEF, name)
    solid.gdml_tag = shape
    solid.gdml_attrs = {"name": name}
    solid.solid_params = dict(params)

    det_vol = GdmlNode(GdmlNodeType.VOLUME_NODE, det_vol_name)
    det_vol.gdml_tag = shape
    det_vol.ref_name = name
    det_vol.gdml_attrs = {"name": det_vol_name, "solidref": name}
    det_vol.solid_params = dict(params)
    det_vol.add_child(solid)

    # ---- physical placement inside the world, at its centre ----
    physvol = GdmlNode(GdmlNodeType.PHYVOL_NODE, f"physvol_{name}")
    physvol.ref_name = det_vol_name
    physvol.gdml_attrs = {"name": f"physvol_{name}", "volumeref": det_vol_name}
    physvol.placement = Placement(0.0, 0.0, 0.0)
    physvol.add_child(_instance_clone(det_vol))
    world_vol.add_child(physvol)

    file_node.add_child(world_vol)
    file_node.add_child(det_vol)
    return file_node
