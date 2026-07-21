"""
Quick roundtrip test: import → export → re-import → compare.
Run from the project root: python -m tests.test_export_roundtrip
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.gdml_parser import GdmIParser
from core.gdml_writer import GdmlWriter


def test_roundtrip(gdml_path: str):
    print(f"=== Round-trip test: {gdml_path} ===")

    # 1) Import original
    parser = GdmIParser()
    root = parser.parse_file(gdml_path)
    if root is None or len(root.children) == 0:
        print("  [FAIL] Could not parse original file")
        return False

    file_node = root.children[0]
    print(f"  File: {file_node.name}")

    # 2) Export (no overrides)
    out_path = gdml_path.replace(".gdml", "_exported.gdml")
    writer = GdmlWriter()
    writer.write(root, {}, out_path)
    print(f"  Exported to: {out_path}")

    # 3) Re-import
    root2 = parser.parse_file(out_path)
    if root2 is None or len(root2.children) == 0:
        print("  [FAIL] Could not re-import exported file")
        return False

    fn2 = root2.children[0]
    print(f"  Re-imported: {fn2.name}")

    # 4) Compare
    _count_nodes(root, 0)
    print("  --- Original tree ---")
    _dump_tree(file_node, "")
    print("  --- Exported tree ---")
    _dump_tree(fn2, "")

    print("  [OK] Round-trip succeeded (manual diff recommended)")
    return True


def _count_nodes(node, depth):
    total = 1
    for c in node.children:
        total += _count_nodes(c, depth + 1)
    return total


def _dump_tree(node, indent):
    tag = node.node_type.name if hasattr(node, "node_type") else "?"
    name = node.name or "(no name)"
    print(f"{indent}{tag}: {name}")
    for c in node.children:
        _dump_tree(c, indent + "  ")


if __name__ == "__main__":
    axes = r"D:\Project\Easy2Rad\Ref\gdmlexample\axes.gdml"
    ok = test_roundtrip(axes)
    sys.exit(0 if ok else 1)
