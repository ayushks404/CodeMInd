"""
file_tools.py — File system tools for the agent

Teen tools:
1. read_file      — ek file ka content padho
2. get_file_tree  — poora repo ka structure dekho
3. keyword_search — exact word across all files dhundho
"""

import os
import logging

logger = logging.getLogger(__name__)

# Cloned repos yahan hote hain — index_worker bhi yahi clone karta hai
REPOS_BASE = "./tmp/repos"


def _get_repo_path(project_id: str) -> str:
    """Project ka cloned repo path return karo."""
    return os.path.join(REPOS_BASE, project_id)


# Files jo skip karni hain — irrelevant content se bachne ke liye
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv",
    "venv", "dist", "build", ".next", "coverage"
}

ALLOWED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
    ".rs", ".cpp", ".c", ".h", ".cs", ".rb", ".php",
    ".html", ".css", ".json", ".yaml", ".yml", ".md",
    ".env.example", ".gitignore", "Dockerfile"
}


def read_file(project_id: str, filepath: str) -> dict:
    """
    Ek specific file ka content padho.

    Args:
        project_id: kaun sa project
        filepath:   file path relative to repo root (e.g. "src/auth/login.js")

    Returns:
        { content, filepath, lines, error }
    """
    repo_path = _get_repo_path(project_id)

    # Security: path traversal prevent karo
    # filepath mein ".." nahi hona chahiye
    if ".." in filepath or filepath.startswith("/"):
        return {
            "content": "",
            "filepath": filepath,
            "lines": 0,
            "error": "Invalid filepath — path traversal not allowed"
        }

    full_path = os.path.join(repo_path, filepath)

    # File exist karti hai?
    if not os.path.exists(full_path):
        return {
            "content": "",
            "filepath": filepath,
            "lines": 0,
            "error": f"File not found: {filepath}"
        }

    # File too large? (500KB limit)
    file_size = os.path.getsize(full_path)
    if file_size > 500 * 1024:
        return {
            "content": f"[File too large: {file_size // 1024}KB — showing first 200 lines only]",
            "filepath": filepath,
            "lines": 0,
            "error": None
        }

    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        lines = content.count("\n") + 1
        logger.info(f"[read_file] Read {filepath} — {lines} lines")

        return {
            "content":  content,
            "filepath": filepath,
            "lines":    lines,
            "error":    None
        }

    except Exception as e:
        logger.error(f"[read_file] Error reading {filepath}: {e}")
        return {
            "content": "",
            "filepath": filepath,
            "lines": 0,
            "error": str(e)
        }


def get_file_tree(project_id: str, max_depth: int = 3) -> dict:
    """
    Poore repo ka directory structure return karo.

    Agent is tool ko use karta hai jab usay pata nahi kahan se shuru kare.
    Entry points dhundhne ke liye, module structure samajhne ke liye.

    Args:
        project_id: kaun sa project
        max_depth:  kitna deep jaana hai (default 3 levels)

    Returns:
        { tree: "string representation", files: [list of all files] }
    """
    repo_path = _get_repo_path(project_id)

    if not os.path.exists(repo_path):
        return {
            "tree":  f"Repo not found at {repo_path}",
            "files": [],
            "error": "Repo not cloned yet"
        }

    tree_lines = []
    all_files  = []

    def walk_dir(path: str, prefix: str = "", depth: int = 0):
        if depth > max_depth:
            return

        try:
            entries = sorted(os.listdir(path))
        except PermissionError:
            return

        # Directories pehle, files baad mein
        dirs  = [e for e in entries if os.path.isdir(os.path.join(path, e)) and e not in SKIP_DIRS]
        files = [e for e in entries if os.path.isfile(os.path.join(path, e))]

        for d in dirs:
            tree_lines.append(f"{prefix}📁 {d}/")
            walk_dir(os.path.join(path, d), prefix + "  ", depth + 1)

        for f in files:
            _, ext = os.path.splitext(f)
            if ext in ALLOWED_EXTENSIONS or f in {"Dockerfile", ".gitignore", ".env.example"}:
                rel_path = os.path.relpath(
                    os.path.join(path, f), repo_path
                )
                tree_lines.append(f"{prefix}📄 {f}")
                all_files.append(rel_path.replace("\\", "/"))

    walk_dir(repo_path)

    tree_str = "\n".join(tree_lines) if tree_lines else "Empty repository"
    logger.info(f"[get_file_tree] {len(all_files)} files found in {project_id}")

    return {
        "tree":  tree_str,
        "files": all_files,
        "error": None
    }


def keyword_search(project_id: str, term: str, max_results: int = 20) -> list[dict]:
    """
    Exact keyword/grep search across all files.

    search_code semantic hai (meaning-based).
    keyword_search exact hai (exact word match).

    Useful jab: function name dhundhna ho, variable dhundhna ho,
    import dhundhna ho, exact string match chahiye ho.

    Args:
        project_id:  kaun sa project
        term:        exact search term
        max_results: max kitne results return karo

    Returns:
        List of { file, line_number, line_content, context }
    """
    repo_path = _get_repo_path(project_id)

    if not os.path.exists(repo_path):
        return []

    results = []
    term_lower = term.lower()

    for root, dirs, files in os.walk(repo_path):
        # Skip irrelevant directories
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
                    if term_lower in line.lower():
                        # Context: ek line pehle aur ek line baad
                        context_start = max(0, i - 1)
                        context_end   = min(len(lines), i + 2)
                        context = "".join(lines[context_start:context_end]).strip()

                        results.append({
                            "file":         rel_path,
                            "line_number":  i + 1,
                            "line_content": line.strip(),
                            "context":      context,
                        })

                        if len(results) >= max_results:
                            logger.info(f"[keyword_search] Found {len(results)} results for '{term}'")
                            return results

            except Exception:
                continue

    logger.info(f"[keyword_search] Found {len(results)} results for '{term}'")
    return results