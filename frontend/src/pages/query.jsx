import { useState, useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import API from "../api";
import { Send, Loader2, Sparkles, FileText, ChevronDown, ChevronUp } from "lucide-react";

// =============================================================================
// AgentTrace
// =============================================================================
function AgentTrace({ trace }) {
  const [open, setOpen] = useState(false);
  if (!trace || trace.length === 0) return null;

  return (
    <div className="mt-2 text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-gray-500 hover:text-gray-300"
      >
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        Agent trace ({trace.length} iteration{trace.length !== 1 ? "s" : ""})
      </button>
      {open && (
        <div className="mt-1 space-y-1 pl-2 border-l border-gray-700">
          {trace.map((t, i) => (
            <div key={i} className="text-gray-500">
              Iter {t.iteration}: confidence {(t.confidence * 100).toFixed(0)}% →{" "}
              <span className={t.decision === "accept" ? "text-green-500" : "text-yellow-500"}>
                {t.decision}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// SourceList
// =============================================================================
function SourceList({ sources }) {
  if (!sources || sources.length === 0) return null;
  const unique = [...new Map(sources.map((s) => [s.file, s])).values()];
  return (
    <div className="mt-3 pt-3 border-t border-gray-700 text-xs text-gray-400">
      <div className="flex items-center gap-1 mb-1">
        <FileText size={12} />
        Sources
      </div>
      {unique.map((s, i) => (
        <div key={i} className="pl-2">
          {s.file}
          {s.function_name && <span className="text-gray-500"> → {s.function_name}()</span>}
          {s.start_line && <span className="text-gray-600"> L{s.start_line}–{s.end_line}</span>}
        </div>
      ))}
    </div>
  );
}

// =============================================================================
// MarkdownMessage
// =============================================================================
function MarkdownMessage({ text }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ node, inline, className, children, ...props }) {
          const match = /language-(\w+)/.exec(className || "");
          return !inline && match ? (
            <SyntaxHighlighter
              style={oneDark}
              language={match[1]}
              PreTag="div"
              className="rounded-lg text-sm my-2"
              {...props}
            >
              {String(children).replace(/\n$/, "")}
            </SyntaxHighlighter>
          ) : (
            <code className="bg-gray-700 px-1 py-0.5 rounded text-sm font-mono text-blue-300" {...props}>
              {children}
            </code>
          );
        },
        h1: ({ children }) => <h1 className="text-lg font-bold text-white mt-4 mb-2">{children}</h1>,
        h2: ({ children }) => <h2 className="text-base font-bold text-white mt-3 mb-1">{children}</h2>,
        h3: ({ children }) => <h3 className="text-sm font-semibold text-gray-200 mt-2 mb-1">{children}</h3>,
        p:  ({ children }) => <p className="text-gray-300 mb-2 leading-relaxed">{children}</p>,
        ul: ({ children }) => <ul className="list-disc list-inside text-gray-300 mb-2 space-y-1">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal list-inside text-gray-300 mb-2 space-y-1">{children}</ol>,
        li: ({ children }) => <li className="ml-2">{children}</li>,
        strong: ({ children }) => <strong className="text-white font-semibold">{children}</strong>,
        em:     ({ children }) => <em className="text-gray-200 italic">{children}</em>,
        hr: () => <hr className="border-gray-700 my-3" />,
      }}
    >
      {text}
    </ReactMarkdown>
  );
}

// =============================================================================
// Main Query Page
// =============================================================================
export default function Query() {
  const { projectId } = useParams();
  const [question,    setQuestion]    = useState("");
  const [messages,    setMessages]    = useState([]);
  const [loading,     setLoading]     = useState(false);
  const [projectName, setProjectName] = useState("");
  const boxRef = useRef();

  useEffect(() => {
    const loadProject = async () => {
      try {
        const res = await API.get(`/project/${projectId}`);
        setProjectName(res.data.name);
      } catch (err) {
        console.error("Failed to load project", err);
      }
    };
    if (projectId) loadProject();
  }, [projectId]);

  useEffect(() => {
    if (boxRef.current) {
      boxRef.current.scrollTop = boxRef.current.scrollHeight;
    }
  }, [messages]);

  const send = async () => {
    if (!question.trim() || loading) return;

    const userMsg = { role: "user", text: question };
    setMessages((m) => [...m, userMsg]);
    setQuestion("");
    setLoading(true);

    try {
      const res = await API.post("/query", { project_id: projectId, question });

      // FIX: no more guess chain — backend now always returns these exact keys
      const answer     = res.data.answer     ?? "No answer received.";
      const sources    = res.data.sources    ?? [];
      const trace      = res.data.trace      ?? [];
      const confidence = res.data.confidence ?? null;

      setMessages((m) => [...m, { role: "ai", text: answer, sources, trace, confidence }]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "ai", text: "Query failed. Please try again.", sources: [], trace: [] },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-black">
      <div className="max-w-5xl mx-auto p-6">

        <div className="flex items-center justify-between mb-6 bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <Sparkles className="text-blue-500" size={24} />
            <div>
              <h1 className="text-xl font-bold text-white">Project Query</h1>
              <p className="text-xs text-gray-500">Ask anything about your codebase</p>
            </div>
          </div>
          <div className="text-sm text-gray-400">
            Project: <span className="text-white font-medium">{projectName || "Loading..."}</span>
          </div>
        </div>

        <div
          ref={boxRef}
          className="h-[65vh] overflow-y-auto bg-gray-900 border border-gray-800 rounded-xl p-6 mb-4 space-y-4"
        >
          {messages.length === 0 && (
            <div className="h-full flex items-center justify-center text-gray-600 text-sm">
              Ask a question about the codebase to get started
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div
                className={`max-w-3xl px-4 py-3 rounded-xl ${
                  m.role === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-800 border border-gray-700"
                }`}
              >
                {m.role === "user" ? (
                  <p className="text-white">{m.text}</p>
                ) : (
                  <>
                    {m.confidence !== null && m.confidence !== undefined && (
                      <div className="flex items-center gap-2 mb-2">
                        <div
                          className={`text-xs px-2 py-0.5 rounded-full ${
                            m.confidence >= 0.8
                              ? "bg-green-900 text-green-300"
                              : m.confidence >= 0.5
                              ? "bg-yellow-900 text-yellow-300"
                              : "bg-red-900 text-red-300"
                          }`}
                        >
                          {(m.confidence * 100).toFixed(0)}% confidence
                        </div>
                      </div>
                    )}
                    <MarkdownMessage text={m.text} />
                    <SourceList sources={m.sources} />
                    <AgentTrace trace={m.trace} />
                  </>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="bg-gray-800 border border-gray-700 px-4 py-3 rounded-xl flex items-center gap-2 text-gray-400 text-sm">
                <Loader2 className="animate-spin" size={16} />
                Searching codebase...
              </div>
            </div>
          )}
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a question about the codebase... (Ctrl+Enter to send)"
            rows={3}
            className="w-full bg-black border border-gray-700 text-white rounded-lg p-3 resize-none focus:outline-none focus:border-blue-500 transition-colors"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send();
            }}
          />
          <div className="mt-3 flex justify-end">
            <button
              onClick={send}
              disabled={loading || !question.trim()}
              className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed px-4 py-2 rounded-lg text-white flex items-center gap-2 transition-colors"
            >
              {loading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Thinking...
                </>
              ) : (
                <>
                  Send
                  <Send size={16} />
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
