import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

export default function MessageBubble({ role, text, sources }) {
  return (
    <div className={`mb-4 ${role === "user" ? "text-right" : "text-left"}`}>
      <div
        className={`inline-block max-w-[85%] px-4 py-3 rounded-lg text-sm leading-relaxed ${
          role === "user"
            ? "bg-indigo-600 text-white"
            : "bg-zinc-900 text-gray-200 border border-white/10"
        }`}
      >
        <ReactMarkdown
          components={{
            p: ({ node, children }) => <div className="mb-2 leading-relaxed">{children}</div>,
            code({ inline, className, children }) {
              const match = /language-(\w+)/.exec(className || "");
              if (!inline) {
                return (
                  <SyntaxHighlighter
                    style={oneDark}
                    language={match ? match[1] : "text"}
                    PreTag="div"
                    className="rounded-md mt-2 overflow-auto"
                  >
                    {String(children).replace(/\n$/, "")}
                  </SyntaxHighlighter>
                );
              } else {
                return <code className="bg-gray-800 px-1 rounded text-yellow-300">{children}</code>;
              }
            },
          }}
        >
          {text}
        </ReactMarkdown>


        {/* Sources */}
        {sources?.length > 0 && (
          <div className="mt-3 pt-2 border-t border-white/10 text-xs text-gray-400">
            <div className="font-semibold mb-1">Sources:</div>
            {sources.map((s, i) => (
              <div key={i}>• {s.file || s}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
