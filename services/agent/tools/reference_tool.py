"""
reference_tool.py — Find where a function/variable is referenced

Agent is tool ko use karta hai jab usay samajhna ho:
"Yeh function kahan kahan call hota hai?"
"Agar main yeh change karun toh kya affect hoga?"
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

REPOS_BASE = "./tmp/repos"

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv",
    "venv", "dist", "build", ".next", "coverage"
}

ALLOWED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
    ".rs", ".cpp", ".c", ".h", ".cs", ".rb", ".php"
}


def find_references(project_id: str, name: str, max_results: int = 15) -> list[dict]:
    """
    Poore codebase mein dhundho ki yeh function/class/variable kahan use hota hai.

    Simple approach: regex se name dhundho across all code files.
    Agent ko accurate results milte hain bina complex AST parsing ke.

    Args:
        project_id:  kaun sa project
        name:        function name, class name, ya variable name
        max_results: max results

    Returns:
        List of { file, line_number, line_content, reference_type }
    """
    repo_path = os.path.join(REPOS_BASE, project_id)

    if not os.path.exists(repo_path):
        return []

    results  = []
    # Word boundary use karo taaki partial matches na aayein
    # e.g. "auth" dhundho toh "authenticate" match na ho
    pattern  = re.compile(r'\b' + re.escape(name) + r'\b')

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for filename in files:
            _, ext = os.path.splitext(filename)
            if ext not in ALLOWED_EXTENSIONS:
                continue

            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, repo_path).replace("\\", "/")

            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()

                for i, line in enumerate(lines):
                    if pattern.search(line):
                        # Reference type classify karo
                        line_stripped = line.strip()

                        if f"def {name}" in line_stripped or f"function {name}" in line_stripped:
                            ref_type = "definition"
                        elif f"class {name}" in line_stripped:
                            ref_type = "class_definition"
                        elif f"import {name}" in line_stripped or f"from" in line_stripped and name in line_stripped:
                            ref_type = "import"
                        else:
                            ref_type = "usage"

                        results.append({
                            "file":         rel_path,
                            "line_number":  i + 1,
                            "line_content": line_stripped,
                            "reference_type": ref_type,
                        })

                        if len(results) >= max_results:
                            return results

            except Exception:
                continue

    logger.info(f"[find_references] Found {len(results)} references for '{name}'")
    return results