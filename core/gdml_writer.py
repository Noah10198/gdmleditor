"""GDML Writer — serializes GdmlNode tree back to GDML XML.

Preserves original structure whenever possible.
Only adds wrapper levels for file_transforms or multi-file merge.
Adds XML comments when placement_overrides are applied.

Uses minidom for pretty-printed output (matches cad2gdml convention).
"""

from typing import Dict, Optional, Set
import xml.etree.ElementTree as ET
from xml.dom import minidom
from core.gdml_tree import GdmlNode, GdmlNodeType, Placement


def _fmt(v: float) -> str:
    if isinstance(v, (int, float)):
        return f"{v:.6g}".rstrip(".")
    return str(v)


def _unique(name: str, used: Set[str]) -> str:
    base = name
    n = 1
    while name in used:
        name = f"{base}_{n}"
        n += 1
    used.add(name)
    return name


# -------------------------------------------------------------------
# Linear/angular attribute sets for solid serialisation
# -------------------------------------------------------------------
_LINEAR = {"x", "y", "z", "rmin", "rmax", "rmin1", "rmax1",
           "rmin2", "rmax2", "dx", "dy", "dz", "pDz", "pSteel",
           "pDx1", "pDx2", "pDy1", "pDy2", "width", "height",
           "length", "halflength"}
_ANGULAR = {"startphi", "deltaphi", "starttheta", "deltatheta",
            "SPhi", "DPhi", "STheta", "DTheta"}

_GALACTIC_XML = (
    '<material name="G4_Galactic" Z="1" A="1.0" density="1.0e-25">'
    '<D unit="g/cm3" value="1.0e-25"/>'
    '<fraction n="1" ref="G4_Galactic"/>'
    '</material>')


class GdmlWriter:
    """GDML file writer with override and file-transform support."""

    def __init__(self):
        self._overrides: Dict[str, Placement] = {}
        self._used_names: Set[str] = set()
        self._written_vols: Set[str] = set()
        self._written_solids: Set[str] = set()
        self._file_node: Optional[GdmlNode] = None

    # ── Public entry point ────────────────────────────────────────

    def write(self, root_node: GdmlNode,
              placement_overrides: Dict[str, Placement],
              filepath: str) -> None:
        self._overrides = placement_overrides
        self._used_names.clear()
        self._written_vols.clear()
        self._written_solids.clear()
        self._file_node = None

        files = [c for c in root_node.children
                 if c.node_type == GdmlNodeType.GDML_FILE]

        gdml = ET.Element("gdml")
        gdml.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
        gdml.set("xsi:noNamespaceSchemaLocation",
                 "http://service-spi.web.cern.ch/service-spi/"
                 "app/releases/GDML/schema/gdml.xsd")

        define = ET.SubElement(gdml, "define")
        materials = ET.SubElement(gdml, "materials")
        solids = ET.SubElement(gdml, "solids")
        structure = ET.SubElement(gdml, "structure")

        # ── Single file, no file_transform: write almost verbatim ──
        if len(files) == 1:
            self._file_node = files[0]
            self._export_single(files[0], define, solids, structure)
        # ── Multi-file: merge under a unifying World ───────────────
        elif len(files) > 1:
            self._export_multi(files, define, materials, solids, structure)

        self._ensure_galactic(materials)
        rough = ET.tostring(gdml, encoding="unicode")
        pretty = minidom.parseString(rough).toprettyxml(indent="  ")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(pretty)

    # ── Single-file export ────────────────────────────────────────

    def _export_single(self, fn: GdmlNode,
                       define: ET.Element,
                       solids: ET.Element,
                       structure: ET.Element) -> None:
        ft = fn.file_transform
        wn = self._find_world_node(fn)
        wv = self._find_world_volume(wn) if wn else None
        if wv is None:
            return

        # Collect all solids (from whole file tree)
        for d in fn.get_all_descendants():
            if d.node_type == GdmlNodeType.SOLID_DEF and d.name:
                self._check_write_solid(solids, d, d.name)

        # Collect and write all logical volumes (direct children of fn)
        for c in fn.children:
            if (c.node_type == GdmlNodeType.VOLUME_NODE
                    and c.name != wv.name):
                self._write_volume_to_structure(c, structure, solids, define)

        # Write the top world volume itself (with its physvols)
        self._write_volume_to_structure(wv, structure, solids, define,
                                        parent_ft=ft)

        # If file_transform exists, wrap the world volume
        if ft is not None and (ft.x or ft.y or ft.z
                               or ft.rot_x or ft.rot_y or ft.rot_z):
            self._wrap_world_volume(wv, ft, define, solids, structure)

    def _wrap_world_volume(self, wv: GdmlNode, ft: Placement,
                           define: ET.Element, solids: ET.Element,
                           structure: ET.Element) -> None:
        """Replace the world volume with a wrapper that applies file_transform."""
        wv_name = wv.name or "World"
        wrap_name = _unique(f"{wv_name}_ft", self._used_names)
        box_name = _unique(f"Box_{wrap_name}", self._used_names)
        pos_name = _unique(f"pos_{wrap_name}", self._used_names)
        rot_name = None

        # Add comment
        cmt = f" file_transform: x={_fmt(ft.x)} y={_fmt(ft.y)} z={_fmt(ft.z)}"
        if ft.rot_x or ft.rot_y or ft.rot_z:
            cmt += f" rot_x={_fmt(ft.rot_x)} rot_y={_fmt(ft.rot_y)} rot_z={_fmt(ft.rot_z)}"
        structure.insert(list(structure).index(structure.findall("./volume")[0])
                         if len(structure) > 0 else 0,
                         ET.Comment(cmt))

        # Tiny wrapper box
        b = ET.SubElement(solids, "box")
        b.set("name", box_name)
        b.set("x", "1")
        b.set("y", "1")
        b.set("z", "1")
        b.set("lunit", "mm")

        # Position + rotation in define
        pos = ET.SubElement(define, "position")
        pos.set("name", pos_name)
        pos.set("x", _fmt(ft.x))
        pos.set("y", _fmt(ft.y))
        pos.set("z", _fmt(ft.z))
        pos.set("unit", ft.unit or "mm")
        if ft.rot_x or ft.rot_y or ft.rot_z:
            rot_name = _unique(f"rot_{wrap_name}", self._used_names)
            rot = ET.SubElement(define, "rotation")
            rot.set("name", rot_name)
            rot.set("x", _fmt(ft.rot_x))
            rot.set("y", _fmt(ft.rot_y))
            rot.set("z", _fmt(ft.rot_z))
            rot.set("unit", ft.rot_unit or "deg")

        # Wrapper volume
        vol = ET.SubElement(structure, "volume")
        vol.set("name", wrap_name)
        ET.SubElement(vol, "materialref").set("ref", "G4_Galactic")
        ET.SubElement(vol, "solidref").set("ref", box_name)

        ipv = ET.SubElement(vol, "physvol")
        ET.SubElement(ipv, "volumeref").set("ref", wv_name)
        ET.SubElement(ipv, "positionref").set("ref", pos_name)
        if rot_name:
            ET.SubElement(ipv, "rotationref").set("ref", rot_name)

    # ── Multi-file export ─────────────────────────────────────────

    def _export_multi(self, files: list[GdmlNode],
                      define: ET.Element,
                      materials: ET.Element,
                      solids: ET.Element,
                      structure: ET.Element) -> None:
        # Collect solids from all files
        for fn in files:
            for d in fn.get_all_descendants():
                if d.node_type == GdmlNodeType.SOLID_DEF and d.name:
                    self._check_write_solid(solids, d, d.name)

        # World box
        wb_name = _unique("WorldBox", self._used_names)
        b = ET.SubElement(solids, "box")
        b.set("name", wb_name)
        b.set("x", "200000")
        b.set("y", "200000")
        b.set("z", "200000")
        b.set("lunit", "mm")

        world_vol = ET.Element("volume")
        world_vol.set("name", "World")
        ET.SubElement(world_vol, "materialref").set("ref", "G4_Galactic")
        ET.SubElement(world_vol, "solidref").set("ref", wb_name)

        for fn in files:
            ft = fn.file_transform
            wn = self._find_world_node(fn)
            wv = self._find_world_volume(wn) if wn else None
            if wv is None:
                continue

            # Write logical volumes
            for c in fn.children:
                if (c.node_type == GdmlNodeType.VOLUME_NODE
                        and c.name != wv.name):
                    self._write_volume_to_structure(
                        c, structure, solids, define)

            self._write_volume_to_structure(
                wv, structure, solids, define, parent_ft=ft)

            # Build a physvol referencing the file's world volume
            target_name = wv.name or "World"
            if ft is not None and (ft.x or ft.y or ft.z
                                   or ft.rot_x or ft.rot_y or ft.rot_z):
                # Wrap in transform wrapper
                wrap_name = _unique(f"{target_name}_ft", self._used_names)
                box_name = _unique(f"Box_{wrap_name}", self._used_names)
                pos_name = _unique(f"pos_{wrap_name}", self._used_names)

                b2 = ET.SubElement(solids, "box")
                b2.set("name", box_name)
                b2.set("x", "1")
                b2.set("y", "1")
                b2.set("z", "1")
                b2.set("lunit", "mm")

                pos = ET.SubElement(define, "position")
                pos.set("name", pos_name)
                pos.set("x", _fmt(ft.x))
                pos.set("y", _fmt(ft.y))
                pos.set("z", _fmt(ft.z))
                pos.set("unit", ft.unit or "mm")

                wvol = ET.SubElement(structure, "volume")
                wvol.set("name", wrap_name)
                ET.SubElement(wvol, "materialref").set("ref", "G4_Galactic")
                ET.SubElement(wvol, "solidref").set("ref", box_name)
                ipv = ET.SubElement(wvol, "physvol")
                ET.SubElement(ipv, "volumeref").set("ref", target_name)
                ET.SubElement(ipv, "positionref").set("ref", pos_name)

                target_name = wrap_name

            pv = ET.SubElement(world_vol, "physvol")
            ET.SubElement(pv, "volumeref").set("ref", target_name)

        structure.append(world_vol)

    # ── Volume writer ─────────────────────────────────────────────

    def _check_write_solid(self, parent: ET.Element,
                           node: GdmlNode, name: str) -> None:
        if name in self._written_solids:
            return
        self._written_solids.add(name)
        tag = node.gdml_tag or "box"
        try:
            e = ET.SubElement(parent, tag)
        except ValueError:
            e = ET.SubElement(parent, "box")
        e.set("name", name)

        has_l = has_a = False
        for k, v in (node.solid_params or {}).items():
            if not isinstance(v, (int, float)):
                continue
            if k in _LINEAR:
                e.set(k, _fmt(v))
                has_l = True
            elif k in _ANGULAR:
                e.set(k, _fmt(v))
                has_a = True
            else:
                e.set(k, _fmt(v))
        if has_l:
            e.set("lunit", "mm")
        if has_a:
            e.set("aunit", "deg")
        if node.gdml_attrs:
            for k, v in node.gdml_attrs.items():
                if k != "name" and k not in (node.solid_params or {}):
                    e.set(k, v)

    def _write_volume_to_structure(self, vn: GdmlNode,
                                   structure: ET.Element,
                                   solids: ET.Element,
                                   define: ET.Element,
                                   parent_ft: Optional[Placement] = None,
                                   _depth: int = 0) -> None:
        name = vn.name or "unnamed"
        if name in self._written_vols:
            return
        self._written_vols.add(name)

        vol = ET.SubElement(structure, "volume")
        vol.set("name", name)

        # materialref
        mat = vn.material_name or (vn.gdml_attrs or {}).get("materialref")
        if mat:
            ET.SubElement(vol, "materialref").set("ref", mat)
        else:
            ET.SubElement(vol, "materialref").set("ref", "G4_Galactic")

        # solidref
        sref = (vn.gdml_attrs or {}).get("solidref")
        if not sref:
            for c in vn.children:
                if c.node_type == GdmlNodeType.SOLID_DEF and c.name:
                    sref = c.name
                    break
        if sref:
            ET.SubElement(vol, "solidref").set("ref", sref)

        # Children: physvols and nested volumes
        for c in vn.children:
            if c.node_type == GdmlNodeType.PHYVOL_NODE:
                self._write_physvol(c, vol, parent_ft, define)
            elif c.node_type == GdmlNodeType.VOLUME_NODE:
                self._write_volume_to_structure(
                    c, structure, solids, define, None, _depth + 1)

    # ── Physvol writer ────────────────────────────────────────────

    def _has_override(self, pv: GdmlNode) -> bool:
        return bool(pv.entry_id and pv.entry_id in self._overrides)

    def _get_effective(self, pv: GdmlNode) -> Placement:
        if pv.entry_id and pv.entry_id in self._overrides:
            return self._overrides[pv.entry_id]
        return pv.placement or Placement()

    def _write_physvol(self, pv_node: GdmlNode,
                       parent_vol: ET.Element,
                       parent_ft: Optional[Placement],
                       define: ET.Element) -> None:
        # Add comment if overridden
        is_overridden = self._has_override(pv_node)
        effective = self._get_effective(pv_node)

        # Merge file_transform into placement
        if parent_ft is not None:
            effective = Placement(
                x=effective.x + parent_ft.x,
                y=effective.y + parent_ft.y,
                z=effective.z + parent_ft.z,
                rot_x=effective.rot_x + parent_ft.rot_x,
                rot_y=effective.rot_y + parent_ft.rot_y,
                rot_z=effective.rot_z + parent_ft.rot_z,
                unit=effective.unit or parent_ft.unit,
                rot_unit=effective.rot_unit or parent_ft.rot_unit
            )

        if is_overridden:
            parts = []
            orig = pv_node.placement or Placement()
            if abs(effective.x - orig.x) > 1e-9:
                parts.append(f"x={_fmt(orig.x)}→{_fmt(effective.x)}")
            if abs(effective.y - orig.y) > 1e-9:
                parts.append(f"y={_fmt(orig.y)}→{_fmt(effective.y)}")
            if abs(effective.z - orig.z) > 1e-9:
                parts.append(f"z={_fmt(orig.z)}→{_fmt(effective.z)}")
            if abs(effective.rot_x - orig.rot_x) > 1e-9:
                parts.append(f"rot_x={_fmt(orig.rot_x)}→{_fmt(effective.rot_x)}")
            if abs(effective.rot_y - orig.rot_y) > 1e-9:
                parts.append(f"rot_y={_fmt(orig.rot_y)}→{_fmt(effective.rot_y)}")
            if abs(effective.rot_z - orig.rot_z) > 1e-9:
                parts.append(f"rot_z={_fmt(orig.rot_z)}→{_fmt(effective.rot_z)}")
            if parts:
                cmt = " transform overridden: " + ", ".join(parts)
                parent_vol.append(ET.Comment(cmt))

        pv = ET.SubElement(parent_vol, "physvol")
        if pv_node.name:
            pv.set("name", pv_node.name)

        # volumeref
        vref = (pv_node.gdml_attrs or {}).get("volumeref")
        if not vref:
            vref = pv_node.ref_name
        if not vref:
            for c in pv_node.children:
                if c.node_type == GdmlNodeType.VOLUME_NODE and c.name:
                    vref = c.name
                    break
        if vref:
            ET.SubElement(pv, "volumeref").set("ref", vref)
        else:
            return  # invalid physvol

        # position
        if effective.x or effective.y or effective.z:
            pos = ET.SubElement(pv, "position")
            pos.set("name", f"pos_{pv_node.name or 'pv'}")
            pos.set("x", _fmt(effective.x))
            pos.set("y", _fmt(effective.y))
            pos.set("z", _fmt(effective.z))
            pos.set("unit", effective.unit or "mm")

        # rotation
        if effective.rot_x or effective.rot_y or effective.rot_z:
            rot = ET.SubElement(pv, "rotation")
            rot.set("name", f"rot_{pv_node.name or 'pv'}")
            rot.set("x", _fmt(effective.rot_x))
            rot.set("y", _fmt(effective.rot_y))
            rot.set("z", _fmt(effective.rot_z))
            rot.set("unit", effective.rot_unit or "deg")

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _find_world_node(fn: GdmlNode) -> Optional[GdmlNode]:
        for c in fn.children:
            if c.node_type == GdmlNodeType.WORLD_NODE:
                return c
            if c.node_type == GdmlNodeType.VOLUME_NODE:
                for cc in c.children:
                    if cc.node_type == GdmlNodeType.WORLD_NODE:
                        return cc
        return None

    @staticmethod
    def _find_world_volume(wn: GdmlNode) -> Optional[GdmlNode]:
        for c in wn.children:
            if c.node_type == GdmlNodeType.VOLUME_NODE:
                return c
        return None

    def _ensure_galactic(self, materials: ET.Element) -> None:
        for child in materials:
            if child.tag == "material" and child.get("name") == "G4_Galactic":
                return
        try:
            materials.append(ET.fromstring(_GALACTIC_XML))
        except Exception:
            pass
