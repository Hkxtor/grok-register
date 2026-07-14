#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).resolve().parent / "apply_full_safe_modularization.py"
text = path.read_text(encoding="utf-8")
old = '''def node_span(text: str, node: ast.AST) -> tuple[int, int]:
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    start = offsets[node.lineno - 1] + getattr(node, "col_offset", 0)
    end_line = getattr(node, "end_lineno", node.lineno)
    end_col = getattr(node, "end_col_offset", len(lines[end_line - 1]))
    end = offsets[end_line - 1] + end_col
    while end < len(text) and text[end] in "\\r\\n":
        end += 1
    return start, end
'''
new = '''def node_span(text: str, node: ast.AST) -> tuple[int, int]:
    # AST column offsets are UTF-8 byte offsets, not Python character offsets.
    # Every node moved by this script is top-level, so complete source lines are
    # the safest exact boundary and preserve non-ASCII strings without truncation.
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    start = offsets[node.lineno - 1]
    end_line = getattr(node, "end_lineno", node.lineno)
    end = offsets[end_line]
    return start, end
'''
if text.count(old) != 1:
    raise RuntimeError(f"node_span patch expected one match, got {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("fixed AST source spans")
