import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";

interface MarkdownRendererProps {
  content: string;
  variant?: "user" | "assistant";
  className?: string;
}

function extractText(node: any): string {
  if (node == null) return "";
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map(extractText).join("");
  }
  if (node.props && node.props.children) {
    return extractText(node.props.children);
  }
  return "";
}

function CodeBlock({ children }: { children?: React.ReactNode }) {
  const [copied, setCopied] = useState(false);

  const codeProps = React.isValidElement(children) ? children.props : undefined;
  const className = (codeProps && (codeProps as any).className) || "";
  const match = /language-(\w+)/.exec(className);
  const language = match ? match[1] : "";

  const handleCopy = async () => {
    const rawText = extractText(children).replace(/\n$/, "");
    if (!rawText) return;

    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(rawText);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = rawText;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy code to clipboard", err);
    }
  };

  return (
    <div className="code-block-container">
      <div className="code-block-header">
        <span className="code-block-lang">{language || "text"}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="code-copy-btn"
          title="Copy code"
        >
          {copied ? (
            <>
              <Check className="size-3.5 text-emerald-400" />
              <span>Copied!</span>
            </>
          ) : (
            <>
              <Copy className="size-3.5" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="code-block-pre">{children}</pre>
    </div>
  );
}

export function MarkdownRenderer({
  content,
  variant = "assistant",
  className = "",
}: MarkdownRendererProps) {
  const variantClass = variant === "user" ? "markdown-user" : "markdown-assistant";

  return (
    <div className={`markdown-content ${variantClass} ${className}`.trim()}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre({ children }) {
            return <CodeBlock>{children}</CodeBlock>;
          },
          table({ children, ...props }) {
            return (
              <div className="markdown-table-wrapper">
                <table {...props}>{children}</table>
              </div>
            );
          },
          a({ href, children, ...props }) {
            const isExternal =
              typeof href === "string" &&
              (href.startsWith("http://") ||
                href.startsWith("https://") ||
                href.startsWith("//"));
            return (
              <a
                href={href}
                target={isExternal ? "_blank" : undefined}
                rel={isExternal ? "noopener noreferrer" : undefined}
                {...props}
              >
                {children}
              </a>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

