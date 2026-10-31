import { useState } from "react";
import { Bot, Brain, ChevronDown, ChevronRight, User } from "lucide-react";
import type { ChatMessage } from "../api/types";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { ToolCallItem } from "./ToolCallItem";

export function MessageItem({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const [reasoningOpen, setReasoningOpen] = useState<boolean>(false);
  const hasReasoning = Boolean(message.reasoning && message.reasoning.trim().length > 0);
  const showReasoningCard = !isUser && (hasReasoning || message.isReasoning);

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

        {showReasoningCard && (
          <div className="reasoning-card">
            <button
              type="button"
              className="reasoning-card-header"
              onClick={() => setReasoningOpen((prev) => !prev)}
              title="Toggle agent reasoning"
            >
              <div className="reasoning-card-title">
                <Brain
                  className={`size-3.5 text-sky-400 ${message.isReasoning ? "animate-pulse" : ""}`}
                />
                <span className="reasoning-label">
                  {message.isReasoning ? "Thinking..." : "Thought process"}
                </span>
              </div>
              {reasoningOpen ? (
                <ChevronDown className="size-3.5" />
              ) : (
                <ChevronRight className="size-3.5" />
              )}
            </button>
            {(reasoningOpen || message.isReasoning) && hasReasoning && (
              <div className="reasoning-card-body">
                <p className="reasoning-text">{message.reasoning}</p>
              </div>
            )}
          </div>
        )}

        {message.text && (
          <div className={`message-bubble ${isUser ? "user-bubble" : "assistant-bubble"}`}>
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
      </div>
    </div>
  );
}

