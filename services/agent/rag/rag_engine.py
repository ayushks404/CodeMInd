"""
rag_engine.py — Core indexing and retrieval pipeline

Changes from original:
1. chunker now returns dicts instead of plain strings
   - Each chunk has: content, file, language, chunk_type, function_name, class_name, start_line, end_line
   - The full dict is stored as Qdrant payload — richer context in answers
2. vector_store is now Qdrant — FAISS removed
3. Answer prompt now includes function_name and line numbers when available
   - Makes answers like "in auth.py line 42, function validate_token()" possible
"""

import os
import numpy as np
from rag.repo_cloner import clone_repo
from rag.chunker import read_files, chunk_code
from rag.embeddings import generate_embeddings
from rag.vector_store import save_index, load_index
from llm_client import generate


def index_repo(project_id: str, repo_url: str) -> dict:
    """
    Full indexing pipeline for a GitHub repo.

    Steps:
    1. Clone repo to ./tmp/repos/<project_id>/
    2. Read all supported code files
    3. Chunk each file by function/class boundaries (AST-aware)
    4. Generate sentence-transformer embeddings for every chunk
    5. Save to Qdrant collection project_{project_id}

    Returns stats so the backend knows indexing succeeded.
    """
    repo_path = clone_repo(repo_url, project_id)
    files = read_files(repo_path)

    all_texts = []    # text strings to embed
    all_meta  = []    # full metadata dicts to store in Qdrant

    for file in files:
        chunks = chunk_code(file)   # returns list of dicts now
        for chunk in chunks:
            all_texts.append(chunk["content"])  # embed the text
            all_meta.append(chunk)              # store full dict as payload

    if not all_texts:
        return {"status": "no_chunks", "files": len(files), "chunks": 0}

    vectors = generate_embeddings(all_texts)   # shape: (num_chunks, 384)
    save_index(project_id, vectors, all_meta)

    return {
        "status": "indexed",
        "files": len(files),
        "chunks": len(all_texts)
    }


def answer_question(project_id: str, question: str, k: int = 5) -> dict:
    """
    Retrieves the top-k most relevant chunks and asks the LLM to answer.

    Returns:
        answer:            LLM-generated response in markdown
        query_vector:      Embedding of the question — shape (1, 384)
        retrieved_vectors: List of embeddings for the k retrieved chunks
                           Used by compute_confidence() in app.py

    Changes from original:
    - Context blocks now include function name + line numbers when available
      (from AST chunker metadata stored in Qdrant payload)
    - Source objects include chunk_type, function_name, start_line, end_line
    """
    index, metadata = load_index(project_id)

    query_vector = generate_embeddings([question])  # shape: (1, 384)
    D, I = index.search(query_vector, k)

    context_blocks = []
    sources = []
    retrieved_vectors = []

    for idx in I[0]:
        if idx < 0 or idx >= len(metadata):
            continue

        meta = metadata[idx]
        file       = meta.get("file", "unknown")
        code       = meta.get("content", "")
        fn_name    = meta.get("function_name")
        cls_name   = meta.get("class_name")
        start_line = meta.get("start_line", "?")
        end_line   = meta.get("end_line", "?")
        language   = meta.get("language", "")

        # Build a rich header so the LLM knows exactly where this code lives
        location_parts = [f"File: {file}"]
        if cls_name:
            location_parts.append(f"Class: {cls_name}")
        if fn_name:
            location_parts.append(f"Function: {fn_name}()")
        location_parts.append(f"Lines: {start_line}–{end_line}")
        header = " | ".join(location_parts)

        context_blocks.append(f"{header}\n\n```{language}\n{code}\n```\n{'─'*40}")
        sources.append({
            "file":          file,
            "function_name": fn_name,
            "class_name":    cls_name,
            "start_line":    start_line,
            "end_line":      end_line,
        })

        chunk_embedding = index.reconstruct(int(idx))
        retrieved_vectors.append(chunk_embedding)

    context = "\n\n".join(context_blocks)

    prompt = f"""You are a senior software engineer and codebase analyst.

When showing code:
- Always use markdown code blocks with the language name
- Mention the filename and function name above each code block
- Include line numbers when referencing specific code

Respond in clean markdown using headings, bullets, and code blocks.

Code Context:
{context}

Question:
{question}
"""

    answer = generate(prompt)

    return {
        "answer":            answer,
        "query_vector":      query_vector,           # shape (1, 384)
        "retrieved_vectors": retrieved_vectors,      # list of (384,) arrays
        "sources":           sources,
    }
