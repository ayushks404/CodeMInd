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
from typing import TypedDict, Annotated, Literal
import operator

from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from tools.search_tool import search_code
from tools.file_tools import read_file, get_file_tree, keyword_search
from tools.reference_tool import find_references
from notifications.redis_publisher import publish_agent_step
from rag.embeddings import get_embeddings

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

    Context mein yeh daalte hain:
    - Saare tool results (code chunks, file content, references)
    - Original question
    - File names, function names, line numbers

    Better context = better answer.
    """
    logger.info(f"[answer_generator] Generating answer for job {state['job_id']}")

    question     = state["original_question"]
    tool_results = state.get("tool_results", [])

    # Context build karo tool results se
    context_parts = []
    sources       = []

    for result in tool_results:
        if isinstance(result, list):
            for chunk in result:
                if isinstance(chunk, dict):
                    if "content" in chunk and chunk["content"]:
                        file_info = f"File: {chunk.get('file', 'unknown')}"
                        if chunk.get("function_name"):
                            file_info += f" | Function: {chunk['function_name']}()"
                        if chunk.get("start_line"):
                            file_info += f" | Lines: {chunk['start_line']}-{chunk['end_line']}"

                        context_parts.append(f"--- {file_info} ---\n{chunk['content']}")

                        # Sources list ke liye
                        if chunk.get("file"):
                            sources.append({
                                "file":          chunk["file"],
                                "function_name": chunk.get("function_name"),
                                "start_line":    chunk.get("start_line"),
                                "end_line":      chunk.get("end_line"),
                            })

                    # keyword_search ya find_references result
                    elif "line_content" in chunk:
                        context_parts.append(
                            f"File: {chunk.get('file')} | "
                            f"Line {chunk.get('line_number')}: {chunk.get('line_content')}"
                        )
                        if chunk.get("file"):
                            sources.append({"file": chunk["file"]})

        elif isinstance(result, dict):
            # read_file result
            if result.get("content"):
                context_parts.append(
                    f"--- File: {result.get('filepath', 'unknown')} ---\n"
                    f"{result['content'][:3000]}"  # First 3000 chars
                )
                if result.get("filepath"):
                    sources.append({"file": result["filepath"]})

            # get_file_tree result
            elif result.get("tree"):
                context_parts.append(
                    f"--- Repository Structure ---\n{result['tree']}"
                )

    context = "\n\n".join(context_parts) if context_parts else "No relevant code found."

    # Duplicate sources remove karo
    seen_files = set()
    unique_sources = []
    for s in sources:
        if s["file"] not in seen_files:
            seen_files.add(s["file"])
            unique_sources.append(s)

    # LLM ko call karo
    system_prompt = """You are CodeMind, an expert code analysis assistant.
Answer questions about the codebase using the provided code context.
Always reference specific files, functions, and line numbers in your answer.
Be precise and technical. Use markdown formatting."""

    user_prompt = f"""Question: {question}

Code Context:
{context}

Provide a detailed, accurate answer based on the code above.
Reference specific files and functions."""

    try:
        llm = get_llm()
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        answer = response.content
    except Exception as e:
        logger.error(f"[answer_generator] LLM error: {e}")
        answer = f"Error generating answer: {str(e)}"

    new_state = dict(state)
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


def route_after_critic(state: AgentState) -> Literal["planner", "__end__"]:
    """Confidence low → retry (planner), High → end."""
    last_trace = state.get("trace", [{}])[-1]
    if last_trace.get("decision") == "retry":
        return "planner"
    return "__end__"


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

    # Entry point
    graph.set_entry_point("planner")

    # Edges — fixed
    graph.add_edge("tool_selector",    "tool_executor")
    graph.add_edge("tool_executor",    "observation")
    graph.add_edge("answer_generator", "critic")

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
            "planner":  "planner",
            "__end__":  END,
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