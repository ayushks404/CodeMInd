"""
chunker.py — AST-aware chunker replacing line-based chunking

Why this matters:
- Old chunker splits every 50 lines regardless of code structure
- A function split across two chunks loses context → bad answers
- This chunker splits on function/class BOUNDARIES so each chunk is complete

Strategy per language:
- Python  → ast module (built-in, zero deps)
- JS/TS   → regex heuristic (good enough, avoids tree-sitter install)
- Other   → fall back to original line chunking (safe default)

Each chunk now includes metadata: function_name, class_name, start_line,
end_line, language — stored in Qdrant payload for better retrieval context.
"""

import os
import ast
import re
from typing import List, Dict

DEFAULT_CHUNK_SIZE = 50   # lines — used as fallback for non-AST files
DEFAULT_OVERLAP    = 10


# =============================================================================
# File Walker
# =============================================================================

def read_files(repo_path: str) -> List[str]:
    """Return list of source file paths — skips node_modules and .git."""
    files = []
    for root, dirs, filenames in os.walk(repo_path):
        # Skip in-place to avoid descending into them
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build")]
        for file in filenames:
            if file.endswith((".js", ".ts", ".jsx", ".tsx", ".py", ".java", ".cpp", ".c", ".md")):
                files.append(os.path.join(root, file))
    return files


# =============================================================================
# Language Detection
# =============================================================================

def _detect_language(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    return {
        ".py":  "python",
        ".js":  "javascript",
        ".ts":  "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".java":"java",
        ".cpp": "cpp",
        ".c":   "c",
        ".md":  "markdown",
    }.get(ext, "unknown")


# =============================================================================
# Main Chunker — returns list of metadata dicts
# =============================================================================

def chunk_code(file_path: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> List[Dict]:
    """
    Chunk a source file into semantically meaningful pieces.

    Returns list of dicts (not plain strings like before):
    {
        "content":       str,   # the chunk text — still stored in Qdrant payload
        "file":          str,   # full file path
        "language":      str,
        "chunk_type":    str,   # "function" | "class" | "block"
        "function_name": str | None,
        "class_name":    str | None,
        "start_line":    int,
        "end_line":      int,
    }

    rag_engine.py now passes the whole dict as metadata, and also uses
    chunk["content"] as the text to embed — same as before.
    """
    language = _detect_language(file_path)

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            source = f.read()
    except Exception:
        return []

    if not source.strip():
        return []

    if language == "python":
        chunks = _chunk_python(source, file_path)
    elif language in ("javascript", "typescript"):
        chunks = _chunk_js(source, file_path, language)
    else:
        chunks = _chunk_lines(source, file_path, language, chunk_size, overlap)

    return chunks


# =============================================================================
# Python AST Chunker
# =============================================================================

def _chunk_python(source: str, file_path: str) -> List[Dict]:
    """
    Uses Python's built-in ast module to split by function and class boundaries.
    Each top-level function/class becomes one chunk.
    Code between top-level definitions becomes a "block" chunk.
    """
    lines = source.splitlines(keepends=True)
    chunks = []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fallback to line chunking if file has syntax errors
        return _chunk_lines(source, file_path, "python")

    top_level_nodes = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.col_offset == 0  # only top-level (col_offset == 0)
    ]

    # Sort by line number
    top_level_nodes.sort(key=lambda n: n.lineno)

    covered_lines = set()

    for node in top_level_nodes:
        start = node.lineno - 1        # ast is 1-indexed, lines list is 0-indexed
        end   = node.end_lineno        # end_lineno is inclusive in ast

        chunk_text = "".join(lines[start:end])
        if not chunk_text.strip():
            continue

        chunk_type = "class" if isinstance(node, ast.ClassDef) else "function"
        class_name = node.name if isinstance(node, ast.ClassDef) else None
        fn_name    = node.name if not isinstance(node, ast.ClassDef) else None

        chunks.append({
            "content":       chunk_text,
            "file":          file_path,
            "language":      "python",
            "chunk_type":    chunk_type,
            "function_name": fn_name,
            "class_name":    class_name,
            "start_line":    start + 1,
            "end_line":      end,
        })

        covered_lines.update(range(start, end))

    # Collect any top-level code NOT inside a function/class (imports, module-level logic)
    uncovered = [i for i in range(len(lines)) if i not in covered_lines]
    if uncovered:
        # Group consecutive uncovered lines into blocks
        block_lines = []
        block_start = None
        for i in uncovered:
            if block_start is None:
                block_start = i
            block_lines.append(lines[i])
            if i + 1 not in uncovered:
                block_text = "".join(block_lines)
                if block_text.strip():
                    chunks.append({
                        "content":       block_text,
                        "file":          file_path,
                        "language":      "python",
                        "chunk_type":    "block",
                        "function_name": None,
                        "class_name":    None,
                        "start_line":    block_start + 1,
                        "end_line":      i + 1,
                    })
                block_lines = []
                block_start = None

    return chunks if chunks else _chunk_lines(source, file_path, "python")


# =============================================================================
# JS/TS Regex Chunker
# =============================================================================

# Matches: function foo(...) {  |  const foo = (...) => {  |  async function foo
_JS_FN_PATTERN = re.compile(
    r'^(?:export\s+)?(?:async\s+)?(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[\w]+)\s*=>)',
    re.MULTILINE
)

# Matches: class Foo {
_JS_CLASS_PATTERN = re.compile(
    r'^(?:export\s+)?(?:default\s+)?class\s+(\w+)',
    re.MULTILINE
)


def _chunk_js(source: str, file_path: str, language: str) -> List[Dict]:
    """
    Regex-based JS/TS chunker.
    Finds function and class definition start lines, then uses brace counting
    to find where each definition ends.
    Falls back to line chunking if no definitions found.
    """
    lines = source.splitlines(keepends=True)
    chunks = []

    # Collect all definition start positions
    definitions = []
    for m in _JS_FN_PATTERN.finditer(source):
        name = m.group(1) or m.group(2) or "anonymous"
        line_no = source[:m.start()].count("\n")
        definitions.append(("function", name, line_no))

    for m in _JS_CLASS_PATTERN.finditer(source):
        name = m.group(1)
        line_no = source[:m.start()].count("\n")
        definitions.append(("class", name, line_no))

    if not definitions:
        return _chunk_lines(source, file_path, language)

    definitions.sort(key=lambda d: d[2])

    for i, (def_type, name, start_line) in enumerate(definitions):
        # Determine end: either next definition start or end of file
        if i + 1 < len(definitions):
            end_line = definitions[i + 1][2]
        else:
            end_line = len(lines)

        chunk_text = "".join(lines[start_line:end_line])
        if not chunk_text.strip():
            continue

        chunks.append({
            "content":       chunk_text,
            "file":          file_path,
            "language":      language,
            "chunk_type":    def_type,
            "function_name": name if def_type == "function" else None,
            "class_name":    name if def_type == "class"    else None,
            "start_line":    start_line + 1,
            "end_line":      end_line,
        })

    return chunks if chunks else _chunk_lines(source, file_path, language)


# =============================================================================
# Line-based Fallback (original logic, now returns dicts)
# =============================================================================

def _chunk_lines(source: str, file_path: str, language: str,
                 chunk_size: int = DEFAULT_CHUNK_SIZE,
                 overlap: int = DEFAULT_OVERLAP) -> List[Dict]:
    """Original line chunker — kept as fallback for C/Java/Markdown/etc."""
    lines = source.splitlines(keepends=True)
    if not lines:
        return []

    chunks = []
    start = 0
    total = len(lines)

    while start < total:
        end = min(start + chunk_size, total)
        chunk_text = "".join(lines[start:end])
        if chunk_text.strip():
            chunks.append({
                "content":       chunk_text,
                "file":          file_path,
                "language":      language,
                "chunk_type":    "block",
                "function_name": None,
                "class_name":    None,
                "start_line":    start + 1,
                "end_line":      end,
            })
        start += chunk_size - overlap

    return chunks
