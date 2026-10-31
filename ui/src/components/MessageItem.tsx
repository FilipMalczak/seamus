import { useEffect, useState } from "react";
import { Bot, Brain, ChevronDown, ChevronRight, User } from "lucide-react";
import type { ChatMessage } from "../api/types";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { ToolCallItem } from "./ToolCallItem";

export function ReasoningBlock({
  content,
  isStreaming,
}: {
  content: string;
  isStreaming?: boolean;
}) {
  const [userToggled, setUserToggled] = useState<boolean>(false);
  const [isOpen, setIsOpen] = useState<boolean>(Boolean(isStreaming));

  // Auto-collapse when reasoning finishes streaming (unless user explicitly toggled)
  useEffect(() => {
    if (!userToggled) {
      setIsOpen(Boolean(isStreaming));
    }
  }, [isStreaming, userToggled]);

  const hasContent = content.trim().length > 0;
  if (!hasContent && !isStreaming) return null;

  return (
    <div className="reasoning-card">
      <button
        type="button"
        className="reasoning-card-header"
        onClick={() => {
          setUserToggled(true);
          setIsOpen((prev) => !prev);
        }}
        title="Toggle agent reasoning"
      >
        <div className="reasoning-card-title">
          <Brain
            className={`size-3.5 text-sky-400 ${isStreaming ? "animate-pulse" : ""}`}
          />
          <span className="reasoning-label">
            {isStreaming ? "Thinking..." : "Thought process"}
          </span>
        </div>
        {isOpen ? (
          <ChevronDown className="size-3.5" />
        ) : (
          <ChevronRight className="size-3.5" />
        )}
      </button>
      {isOpen && hasContent && (
        <div className="reasoning-card-body">
          <p className="reasoning-text">{content}</p>
        </div>
      )}
    </div>
  );
}

export function MessageItem({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const hasParts = !isUser && Boolean(message.parts && message.parts.length > 0);

  return (
    <div className={`message-row ${isUser ? "user-row" : "assistant-row"}`}>
      <div className={`message-avatar ${isUser ? "user-avatar" : "assistant-avatar"}`}>
        {isUser ? <User className="size-4" /> : <Bot className="size-4 text-sky-400" />}
      </div>

      <div className="message-content-wrapper">
        <div className="message-header">
          <span className="message-sender">{isUser ? "You" : "Seamus Agent"}</span>
          <span className="message-time">
            {new Date(message.timestamp).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </div>

        {hasParts ? (
          <div className="message-parts-container">
            {message.parts!.map((part) => {
              if (part.type === "reasoning") {
                return (
                  <ReasoningBlock
                    key={part.id}
                    content={part.content}
                    isStreaming={part.isStreaming}
                  />
                );
              }
              if (part.type === "tool_call") {
                return <ToolCallItem key={part.id} toolCall={part.toolCall} />;
              }
              if (part.type === "text") {
                if (!part.content) return null;
                return (
                  <div key={part.id} className="message-bubble assistant-bubble">
                    <MarkdownRenderer content={part.content} variant="assistant" />
                  </div>
                );
              }
              return null;
            })}
          </div>
        ) : (
          <>
            {!isUser && (message.reasoning || message.isReasoning) && (
              <ReasoningBlock
                content={message.reasoning || ""}
                isStreaming={message.isReasoning}
              />
            )}

            {message.text && (
              <div
                className={`message-bubble ${isUser ? "user-bubble" : "assistant-bubble"}`}
              >
                <MarkdownRenderer
                  content={message.text}
                  variant={isUser ? "user" : "assistant"}
                />
              </div>
            )}

            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="tool-calls-container">
                {message.toolCalls.map((tc) => (
                  <ToolCallItem key={tc.id} toolCall={tc} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
