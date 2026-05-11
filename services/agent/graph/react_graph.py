"""
react_graph.py — LangGraph ReAct Agent for CodeMind

ReAct = Reason + Act
Agent pehle sochta hai (Reason), phir tool use karta hai (Act),
phir observation leta hai, phir dobara sochta hai.

nodes:
  Planner → Tool Selector → Tool Executor → Observation
  → Answer Generator → Critic → Memory Store → END

Phase 3 addition:
  Har tool call ke baad agent_step event publish hota hai.
  Frontend pe live dikhta hai agent kya kar raha hai.
"""

import logging
import os
import hashlib
import json
import redis
from typing import TypedDict, Annotated, Literal
import operator

from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from tools.search_tool import search_code
from tools.file_tools import read_file, get_file_tree, keyword_search
from tools.reference_tool import find_references
from notifications.redis_publisher import publish_agent_step, publish_answer_chunk
from rag.embeddings import generate_embeddings
get_embeddings = generate_embeddings   # alias used in compute_confidence

import numpy as np

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


# =============================================================================
# State — yeh graph ke through travel karta hai
# Har node is state ko read aur update karta hai
# =============================================================================

class AgentState(TypedDict):
    # Input
    project_id:     str
    user_id:        str
    job_id:         str
    question:       str
    original_question: str

    # Agent working memory
    query:          str           # current refined query
    tool_results:   list          # saare tool calls ke results
    iterations:     int           # kitni baar loop hua
    tool_calls_done: int          # total tool calls

    # Output
    answer:         str
    confidence:     float
    sources:        list
    trace:          list          # [{iteration, tool_used, step, confidence, decision}]

    # Control flow
    should_continue: bool         # kya aur tools use karni chahiye?
    query_type:     str           # "simple" ya "complex"


# =============================================================================
# LLM client — singleton
# =============================================================================

_llm = None

def get_llm():
    global _llm
    if _llm is None:
        _llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=GROQ_API_KEY,
            temperature=0.3,
        )
    return _llm


# =============================================================================
# Helper — confidence compute karo
# =============================================================================

def compute_confidence(question: str, answer: str, tool_results: list) -> float:
    """
    Confidence score calculate karo.
    Tool results mein se code chunks ka mean similarity use karo.
    """
    if not tool_results:
        return 0.3  # koi tool nahi chala — low confidence

    try:
        question_vec = get_embeddings([question])[0]
        q_norm = question_vec / (np.linalg.norm(question_vec) + 1e-10)

        sims = []
        for result in tool_results:
            if isinstance(result, list):
                for chunk in result:
                    if isinstance(chunk, dict) and "content" in chunk:
                        content = chunk["content"]
                        if content:
                            content_vec = get_embeddings([content])[0]
                            c_norm = content_vec / (np.linalg.norm(content_vec) + 1e-10)
                            sims.append(float(np.dot(q_norm, c_norm)))

        return float(np.mean(sims)) if sims else 0.4
    except Exception:
        return 0.4


# =============================================================================
# Node 1 — Planner
# Sawaal simple hai ya complex? Simple = direct answer, Complex = tools chahiye
# =============================================================================

def planner_node(state: AgentState) -> AgentState:
    """
    Sawaal ko classify karo.
    Simple: "kya yeh project Python use karta hai?" — ek search kaafi
    Complex: "authentication flow kaise kaam karta hai?" — multiple tools chahiye
    """
    logger.info(f"[planner] Classifying question: {state['question'][:50]}")

    # Simple classification — LLM se nahi poochha kyunki token waste hoga
    # Keywords se decide karo
    complex_keywords = [
        "how does", "explain", "walk me through", "understand",
        "architecture", "flow", "works", "implement", "design",
        "relationship", "connect", "between", "why", "kaise",
        "samjhao", "explain karo", "kya relationship"
    ]

    question_lower = state["question"].lower()
    is_complex = any(kw in question_lower for kw in complex_keywords)

    # Agar pehle se tools use ho chuke hain toh complex treat karo
    if state["iterations"] > 0:
        is_complex = True

    new_state = dict(state)
    new_state["query_type"] = "complex" if is_complex else "simple"

    logger.info(f"[planner] Query type: {new_state['query_type']}")
    return new_state


# =============================================================================
# Node 2 — Tool Selector
# Konsa tool use karna chahiye decide karo
# =============================================================================

def tool_selector_node(state: AgentState) -> AgentState:
    """
    Current query ke basis pe best tool select karo.

    Simple heuristic:
    - Pehla tool hamesha search_code
    - Agar file mention hai → read_file
    - Agar "where is" / "references" hai → find_references
    - Agar "structure" / "files" hai → get_file_tree
    - Agar exact name dhundna hai → keyword_search
    """
    query = state["query"].lower()
    tools_done = state.get("tool_calls_done", 0)

    # Pehli baar hamesha search_code
    if tools_done == 0:
        selected_tool = "search_code"

    # File path mention hai?
    elif any(ext in state["query"] for ext in [".py", ".js", ".ts", ".jsx", ".tsx", ".java"]):
        selected_tool = "read_file"

    # References dhundhni hain?
    elif any(kw in query for kw in ["where is", "called from", "references", "who calls", "uses"]):
        selected_tool = "find_references"

    # Structure/tree chahiye?
    elif any(kw in query for kw in ["structure", "files", "directory", "folder", "tree", "overview"]):
        selected_tool = "get_file_tree"

    # Exact match chahiye?
    elif any(kw in query for kw in ["exact", "find all", "grep", "search for"]):
        selected_tool = "keyword_search"

    # Function signature chahiye?
    elif any(kw in query for kw in [
        "signature", "parameters", "arguments",
        "what does", "return type", "params"
    ]):
        selected_tool = "get_function_signature"

    # File ka summary chahiye?
    elif any(kw in query for kw in [
        "summarise", "summarize", "summary",
        "overview of file", "what is in", "whats in"
    ]):
        selected_tool = "summarise_file"

    # Default: dobara search_code different query se
    else:
        selected_tool = "search_code"

    new_state = dict(state)
    new_state["selected_tool"] = selected_tool
    logger.info(f"[tool_selector] Selected tool: {selected_tool}")
    return new_state


# =============================================================================
# Node 3 — Tool Executor
# Tool chalao, result lo, agent_step event publish karo
# =============================================================================

def tool_executor_node(state: AgentState) -> AgentState:
    """
    Selected tool chalao.
    Har tool call ke baad frontend ko agent_step event bhejo.
    Yeh Phase 3 ka key feature hai — live agent transparency.
    """
    tool = state.get("selected_tool", "search_code")
    project_id = state["project_id"]
    user_id    = state["user_id"]
    job_id     = state["job_id"]
    query      = state["question"]

    logger.info(f"[tool_executor] Running tool: {tool}")

    result = None
    step_message = ""

    if tool == "search_code":
        step_message = f"Searching codebase for: {query[:60]}..."
        # Agent step frontend pe publish karo
        publish_agent_step(
            user_id=user_id,
            job_id=job_id,
            step=step_message,
            tool_used="search_code"
        )
        result = search_code(project_id, query, top_k=5)

    elif tool == "read_file":
        # Query se file path extract karne ki koshish
        # Simple: query mein pehla .py/.js/.ts wala word nikalo
        import re
        file_match = re.search(
            r'[\w/\-]+\.(py|js|ts|jsx|tsx|java|go|rs|cpp|c|h)',
            state["query"]
        )
        filepath = file_match.group(0) if file_match else "README.md"
        step_message = f"Reading file: {filepath}"
        publish_agent_step(
            user_id=user_id,
            job_id=job_id,
            step=step_message,
            tool_used="read_file"
        )
        result = read_file(project_id, filepath)

    elif tool == "find_references":
        # Query se function name extract karo
        words = state["question"].split()
        # Camel case ya snake_case wala word dhundho
        name = next(
            (w for w in words if "_" in w or (w[0].islower() and any(c.isupper() for c in w[1:]))),
            words[-1] if words else query
        )
        step_message = f"Finding references for: {name}"
        publish_agent_step(
            user_id=user_id,
            job_id=job_id,
            step=step_message,
            tool_used="find_references"
        )
        result = find_references(project_id, name)

    elif tool == "get_file_tree":
        step_message = "Getting repository structure..."
        publish_agent_step(
            user_id=user_id,
            job_id=job_id,
            step=step_message,
            tool_used="get_file_tree"
        )
        result = get_file_tree(project_id)

    elif tool == "keyword_search":
        # Query se search term nikalo
        words = [w for w in state["question"].split() if len(w) > 3]
        term  = words[0] if words else query
        step_message = f"Searching for keyword: {term}"
        publish_agent_step(
            user_id=user_id,
            job_id=job_id,
            step=step_message,
            tool_used="keyword_search"
        )
        result = keyword_search(project_id, term)
    elif tool == "get_function_signature":
        # Question se function name nikalo
        # snake_case ya camelCase wala word dhundho
        words = state["question"].split()
        fn_name = next(
            (w for w in words if "_" in w or (len(w) > 2 and w[0].islower() and any(c.isupper() for c in w[1:]))),
            words[-1] if words else query
        )
        step_message = f"Getting function signature for: {fn_name}"
        publish_agent_step(
            user_id=user_id,
            job_id=job_id,
            step=step_message,
            tool_used="get_function_signature"
        )
        from tools.file_tools import get_function_signature
        result = get_function_signature(project_id, fn_name)

    elif tool == "summarise_file":
        # Question se file path nikalo
        import re as _re
        file_match = _re.search(
            r'[\w/\-]+\.(py|js|ts|jsx|tsx|java|go|rs|cpp|c|h|md)',
            state["question"]
        )
        filepath = file_match.group(0) if file_match else "README.md"
        step_message = f"Summarising file: {filepath}"
        publish_agent_step(
            user_id=user_id,
            job_id=job_id,
            step=step_message,
            tool_used="summarise_file"
        )
        from tools.file_tools import summarise_file
        result = summarise_file(project_id, filepath)

    # Tool results mein add karo
    new_state = dict(state)
    tool_results = list(state.get("tool_results", []))
    tool_results.append(result)
    new_state["tool_results"]    = tool_results
    new_state["tool_calls_done"] = state.get("tool_calls_done", 0) + 1
    new_state["last_tool"]       = tool
    new_state["last_tool_result"] = result

    # Trace mein record karo
    trace = list(state.get("trace", []))
    trace.append({
        "tool_used": tool,
        "step":      step_message,
        "iteration": state["iterations"],
    })
    new_state["trace"] = trace

    return new_state


# =============================================================================
# Node 4 — Observation
# Kya kafi information mili? Kya aur tools use karni chahiye?
# =============================================================================

def observation_node(state: AgentState) -> AgentState:
    """
    Tool results evaluate karo.
    Agar enough info nahi mili aur max tool calls nahi hue → aur tools chalao.
    """
    tool_results    = state.get("tool_results", [])
    tool_calls_done = state.get("tool_calls_done", 0)
    MAX_TOOL_CALLS  = 3  # maximum 3 tool calls per query

    # Kya kafi results mile?
    has_results = False
    for result in tool_results:
        if isinstance(result, list) and len(result) > 0:
            has_results = True
            break
        elif isinstance(result, dict) and result.get("content"):
            has_results = True
            break

    # Agar nahi mile aur limit nahi aayi → aur tools chalao
    should_continue = (not has_results) and (tool_calls_done < MAX_TOOL_CALLS)

    new_state = dict(state)
    new_state["should_continue"] = should_continue

    logger.info(
        f"[observation] has_results={has_results}, "
        f"tool_calls_done={tool_calls_done}, "
        f"should_continue={should_continue}"
    )
    return new_state


# =============================================================================
# Node 5 — Answer Generator
# Saari gathered information se final answer banao
# =============================================================================

def answer_generator_node(state: AgentState) -> AgentState:
    """
    Tool results ko combine karke LLM se answer banao.

    Token budget: Groq free tier = 12000 TPM.
    - Har search chunk: max 800 chars
    - read_file: max 1500 chars
    - file_tree: max 800 chars
    - keyword results: max 5 lines
    - Total context hard cap: 4000 chars
    - max_tokens response: 800
    Yeh limits rate_limit_exceeded error se bachate hain.
    """
    import time

    logger.info(f"[answer_generator] Generating answer for job {state['job_id']}")

    question     = state["original_question"]
    tool_results = state.get("tool_results", [])

    # ── Token-safe context builder ──────────────────────────────────────────
    # Each piece is trimmed before appending.
    # Total context capped at 4000 chars to stay under TPM limit.
    CHUNK_LIMIT    = 800   # per search/qdrant chunk
    FILE_LIMIT     = 1500  # per read_file result
    TREE_LIMIT     = 800   # file tree is verbose but low-value
    KEYWORD_LINES  = 5     # max keyword_search lines included
    CONTEXT_CAP    = 4000  # total context hard cap

    context_parts = []
    sources       = []

    for result in tool_results:
        if isinstance(result, list):
            keyword_count = 0
            for chunk in result:
                if not isinstance(chunk, dict):
                    continue

                if "content" in chunk and chunk["content"]:
                    file_info = f"File: {chunk.get('file', 'unknown')}"
                    if chunk.get("function_name"):
                        file_info += f" | Function: {chunk['function_name']}()"
                    if chunk.get("start_line"):
                        file_info += f" | Lines: {chunk['start_line']}-{chunk['end_line']}"

                    trimmed = chunk["content"][:CHUNK_LIMIT]
                    context_parts.append(f"--- {file_info} ---\n{trimmed}")

                    if chunk.get("file"):
                        sources.append({
                            "file":          chunk["file"],
                            "function_name": chunk.get("function_name"),
                            "start_line":    chunk.get("start_line"),
                            "end_line":      chunk.get("end_line"),
                        })

                elif "line_content" in chunk:
                    if keyword_count >= KEYWORD_LINES:
                        continue
                    context_parts.append(
                        f"File: {chunk.get('file')} | "
                        f"Line {chunk.get('line_number')}: {chunk.get('line_content')}"
                    )
                    if chunk.get("file"):
                        sources.append({"file": chunk["file"]})
                    keyword_count += 1

        elif isinstance(result, dict):
            if result.get("content"):
                trimmed = result["content"][:FILE_LIMIT]
                context_parts.append(
                    f"--- File: {result.get('filepath', 'unknown')} ---\n{trimmed}"
                )
                if result.get("filepath"):
                    sources.append({"file": result["filepath"]})

            elif result.get("tree"):
                trimmed = result["tree"][:TREE_LIMIT]
                context_parts.append(f"--- Repository Structure ---\n{trimmed}")

    # Hard cap on total context
    raw_context = "\n\n".join(context_parts) if context_parts else "No relevant code found."
    context     = raw_context[:CONTEXT_CAP]
    if len(raw_context) > CONTEXT_CAP:
        context += "\n[... context trimmed to stay within token limits ...]"

    # Duplicate sources remove karo
    seen_files     = set()
    unique_sources = []
    for s in sources:
        if s["file"] not in seen_files:
            seen_files.add(s["file"])
            unique_sources.append(s)

    system_prompt = (
        "You are CodeMind, a precise code analysis assistant. "
        "Answer using only the provided code context. "
        "Reference specific files, functions, and line numbers. "
        "Use markdown. Be concise."
    )

    user_prompt = (
        f"Question: {question}\n\n"
        f"Code Context:\n{context}\n\n"
        "Answer based on the code above. Reference specific files and functions."
    )

    # ── LLM call with rate-limit retry ─────────────────────────────────────
    # Groq returns 429 with a wait time in the error message.
    # We parse it and sleep exactly that long, then retry once.
    MAX_RETRIES = 2
    answer      = ""

    for attempt in range(MAX_RETRIES):
        try:
            llm = get_llm()

            for chunk in llm.stream(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)],
                config={"max_tokens": 800},   # keep response tokens low
            ):
                token = chunk.content
                if token:
                    answer += token
                    publish_answer_chunk(
                        user_id=state["user_id"],
                        job_id=state["job_id"],
                        chunk=token,
                    )
            break  # success — exit retry loop

        except Exception as e:
            err_str = str(e)
            logger.error(f"[answer_generator] LLM error (attempt {attempt+1}): {err_str}")

            # Parse wait time from Groq 429 message: "Please try again in X.XXXs"
            if "rate_limit_exceeded" in err_str or "429" in err_str:
                import re
                match = re.search(r"try again in (\d+\.?\d*)s", err_str)
                wait  = float(match.group(1)) + 0.5 if match else 5.0
                logger.warning(f"[answer_generator] Rate limited — waiting {wait:.1f}s before retry")
                time.sleep(wait)
                if attempt == MAX_RETRIES - 1:
                    answer = (
                        "Rate limit reached on the AI provider. "
                        "Please wait a moment and try again."
                    )
            else:
                answer = f"Error generating answer: {err_str}"
                break

    new_state            = dict(state)
    new_state["answer"]  = answer
    new_state["sources"] = unique_sources
    return new_state


# =============================================================================
# Node 6 — Critic
# Answer ka quality check karo
# =============================================================================

def critic_node(state: AgentState) -> AgentState:
    """
    Answer evaluate karo.
    Confidence calculate karo.
    Agar low confidence aur iterations baaki hain → retry.
    """
    confidence = compute_confidence(
        question=state["original_question"],
        answer=state["answer"],
        tool_results=state["tool_results"],
    )

    iterations     = state["iterations"]
    MAX_ITERATIONS = 3
    THRESHOLD      = 0.8

    # Accept karo agar: confidence kaafi hai, ya max iterations ho gaye
    should_retry = (confidence < THRESHOLD) and (iterations < MAX_ITERATIONS - 1)
    decision     = "retry" if should_retry else "accept"

    logger.info(
        f"[critic] confidence={confidence:.3f}, "
        f"iterations={iterations}, decision={decision}"
    )

    # Trace update karo
    trace = list(state.get("trace", []))
    if trace:
        trace[-1]["confidence"] = confidence
        trace[-1]["decision"]   = decision
    else:
        trace.append({
            "iteration":  iterations,
            "confidence": confidence,
            "decision":   decision,
        })

    new_state = dict(state)
    new_state["confidence"] = confidence
    new_state["trace"]      = trace
    new_state["iterations"] = iterations + 1

    # Retry ke liye query refine karo
    if should_retry:
        new_state["query"] = (
            f"Original Question: {state['original_question']}\n\n"
            f"Previous Answer (needs improvement): {state['answer']}\n\n"
            "Provide a more accurate and detailed answer with specific "
            "file names, function names, and line numbers."
        )
        # Tool results reset karo fresh search ke liye
        new_state["tool_results"]    = []
        new_state["tool_calls_done"] = 0

    return new_state


# =============================================================================
# Routing functions — LangGraph ko batate hain kahan jaana hai
# =============================================================================

def route_after_planner(state: AgentState) -> Literal["tool_selector", "answer_generator"]:
    """Simple query → direct answer, Complex → tools."""
    if state["query_type"] == "simple" and state["iterations"] == 0:
        return "tool_selector"  # Hamesha tools use karo — better accuracy
    return "tool_selector"


def route_after_observation(state: AgentState) -> Literal["tool_selector", "answer_generator"]:
    """Aur info chahiye → tool_selector, Kaafi info → answer_generator."""
    if state.get("should_continue", False):
        return "tool_selector"
    return "answer_generator"


def route_after_critic(state: AgentState) -> Literal["planner", "memory_store"]:
    """Confidence low → retry (planner), High → memory_store then end."""
    last_trace = state.get("trace", [{}])[-1]
    if last_trace.get("decision") == "retry":
        return "planner"
    return "memory_store"


# =============================================================================
# Node 7 — Memory Store
# Conversation turn Redis mein save karo (Level 1 — Phase 3)
# Mem0 hook Phase 4 mein fill hoga
# =============================================================================

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
_redis = None

def _get_redis():
    global _redis
    if _redis is None:
        _redis = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def memory_store_node(state: AgentState) -> AgentState:
    """
    Level 1 — Conversation memory Redis mein save karo.
    Key: memory:{user_id}:{project_id}
    TTL: 24 hours (86400 seconds)
    Format: last 10 turns ka JSON list

    Level 2 — Mem0 (Phase 4 mein implement hoga)
    Placeholder stub yahan hai taaki Phase 4 mein sirf fill karna pade.
    """
    user_id    = state["user_id"]
    project_id = state["project_id"]
    question   = state["original_question"]
    answer     = state.get("answer", "")
    confidence = state.get("confidence", 0.0)

    # --- Level 1: Redis conversation memory ---
    try:
        r   = _get_redis()
        key = f"memory:{user_id}:{project_id}"

        # Existing turns load karo
        raw   = r.get(key)
        turns = json.loads(raw) if raw else []

        # Naya turn add karo
        turns.append({
            "question":   question,
            "answer":     answer,
            "confidence": round(confidence, 3),
        })

        # Sirf last 10 turns rakhte hain
        turns = turns[-10:]

        # Save karo with 24hr TTL
        r.set(key, json.dumps(turns), ex=86400)
        logger.info(
            f"[memory_store] Saved turn to Redis | "
            f"user={user_id} project={project_id} turns={len(turns)}"
        )

    except Exception as e:
        # Memory failure query ko fail nahi karni chahiye
        logger.error(f"[memory_store] Redis write failed: {e}")

    # --- Level 2: Mem0 (Phase 4 stub) ---
    # Phase 4 mein yahan mem0_client.add() call hoga
    # Abhi log karo taaki Phase 4 mein dhundhna easy ho
    logger.debug(
        "[memory_store] Mem0 write skipped — Phase 4 not yet implemented"
    )

    return state  # state unchanged — memory is a side effect


# =============================================================================
# Graph build karo
# =============================================================================

def build_react_graph():
    """
    LangGraph graph build karo.
    Nodes define karo, edges connect karo, compile karo.
    """
    graph = StateGraph(AgentState)

    # Nodes add karo
    graph.add_node("planner",          planner_node)
    graph.add_node("tool_selector",    tool_selector_node)
    graph.add_node("tool_executor",    tool_executor_node)
    graph.add_node("observation",      observation_node)
    graph.add_node("answer_generator", answer_generator_node)
    graph.add_node("critic",           critic_node)
    graph.add_node("memory_store",     memory_store_node)   # Phase 3 addition

    # Entry point
    graph.set_entry_point("planner")

    # Edges — fixed
    graph.add_edge("tool_selector",    "tool_executor")
    graph.add_edge("tool_executor",    "observation")
    graph.add_edge("answer_generator", "critic")
    graph.add_edge("memory_store",     END)                 # memory → end

    # Conditional edges — routing functions ke basis pe
    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "tool_selector":    "tool_selector",
            "answer_generator": "answer_generator",
        }
    )
    graph.add_conditional_edges(
        "observation",
        route_after_observation,
        {
            "tool_selector":    "tool_selector",
            "answer_generator": "answer_generator",
        }
    )
    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "planner":      "planner",
            "memory_store": "memory_store",   # accept → save memory → end
        }
    )

    return graph.compile()


# Singleton graph — ek baar compile karo
_graph = None

def get_react_graph():
    global _graph
    if _graph is None:
        _graph = build_react_graph()
        logger.info("[react_graph] Graph compiled successfully")
    return _graph