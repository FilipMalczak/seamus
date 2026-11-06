import { useEffect, useState } from "react";
import {
  Bot,
  Brain,
  ChevronDown,
  ChevronRight,
  GitFork,
  RotateCcw,
  User,
  Zap,
} from "lucide-react";
import {
  SYNTHETIC_MESSAGE_INDICATOR,
  type ArtifactInfo,
  type ChatMessage,
} from "../api/types";
import { ArtifactRenderer } from "./ArtifactRenderer";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { ToolCallItem } from "./ToolCallItem";

export function SyntheticMessageBlock({ text }: { text: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const cleanText = text
    .replace(/^<SYNTHETIC MESSAGE INDICATOR>\s*[\r\n]?/i, "")
    .trim();

  let summary = cleanText.split("\n")[0] || "Synthetic event";
  const payloadMatch = cleanText.match(/^(.*?with payload:)([\s\S]*)$/i);
  let payloadPart: string | null = null;
  if (payloadMatch) {
    summary = payloadMatch[1].trim();
    payloadPart = payloadMatch[2].trim();
  } else if (cleanText.length > 80) {
    summary = cleanText.slice(0, 80) + "...";
  }

  let formattedPayload = payloadPart;
  if (payloadPart && (payloadPart.startsWith("{") || payloadPart.startsWith("["))) {
    try {
      formattedPayload = JSON.stringify(JSON.parse(payloadPart), null, 2);
    } catch {
      formattedPayload = payloadPart;
    }
  }

  return (
    <div className="synthetic-message-card">
      <button
        type="button"
        className="synthetic-card-header"
        onClick={() => setIsOpen((prev) => !prev)}
        title="Toggle event details"
      >
        <div className="synthetic-card-title">
          <Zap className="size-3.5 text-amber-400 shrink-0" />
          <span className="synthetic-badge">Event</span>
          <span className="synthetic-summary">{summary}</span>
        </div>
        {isOpen ? (
          <ChevronDown className="size-3.5 text-zinc-400 shrink-0" />
        ) : (
          <ChevronRight className="size-3.5 text-zinc-400 shrink-0" />
        )}
      </button>
      {isOpen && (
        <div className="synthetic-card-body">
          {formattedPayload ? (
            <MarkdownRenderer
              content={`\`\`\`json\n${formattedPayload}\n\`\`\``}
              variant="assistant"
            />
          ) : (
            <MarkdownRenderer content={cleanText} variant="assistant" />
          )}
        </div>
      )}
    </div>
  );
}

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

export function MessageItem({
  message,
  onBranch,
  onBranchTool,
  onSubmitArtifact,
  submittingArtifactId,
}: {
  message: ChatMessage;
  onBranch?: () => void;
  onBranchTool?: () => void;
  onSubmitArtifact?: (artifact: ArtifactInfo, data: Record<string, unknown>) => Promise<void> | void;
  submittingArtifactId?: string | null;
}) {
  const isSynthetic = Boolean(
    message.text?.startsWith(SYNTHETIC_MESSAGE_INDICATOR)
  );
  const isUser = message.role === "user" && !isSynthetic;
  const hasParts = !isUser && !isSynthetic && Boolean(message.parts && message.parts.length > 0);

  return (
    <div
      className={`message-row ${
        isSynthetic ? "synthetic-row" : isUser ? "user-row" : "assistant-row"
      }`}
    >
      <div
        className={`message-avatar ${
          isSynthetic ? "synthetic-avatar" : isUser ? "user-avatar" : "assistant-avatar"
        }`}
      >
        {isSynthetic ? (
          <Zap className="size-4 text-amber-400" />
        ) : isUser ? (
          <User className="size-4" />
        ) : (
          <Bot className="size-4 text-sky-400" />
        )}
      </div>

      <div className="message-content-wrapper">
        <div className="message-header">
          <span className="message-sender">
            {isSynthetic ? "System Event" : isUser ? "You" : "Seamus Agent"}
          </span>
          <span className="message-time">
            {new Date(message.timestamp).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </div>

        {isSynthetic ? (
          <SyntheticMessageBlock text={message.text || ""} />
        ) : hasParts ? (
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
              if (part.type === "artifact") {
                return (
                  <ArtifactRenderer
                    key={part.id}
                    artifact={part.artifact}
                    onSubmit={(data) => onSubmitArtifact?.(part.artifact, data)}
                    isSubmitting={submittingArtifactId === part.artifact.name}
                  />
                );
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

        {onBranch && (
          <div className="message-footer-actions">
            <button
              type="button"
              className="message-action-btn branch-msg-btn"
              onClick={onBranch}
              title={
                isUser
                  ? "Branch on latest Seamus bubble and retry this prompt"
                  : "Branch off this message into a new parallel session"
              }
            >
              <GitFork className="size-3" />
              <span>Branch</span>
            </button>

            {!isUser && onBranchTool && (
              <button
                type="button"
                className="message-action-btn branch-tool-btn"
                onClick={onBranchTool}
                title="Branch right after tool execution and retry inference in a new session"
              >
                <RotateCcw className="size-3" />
                <span>Branch after tools (retry inference)</span>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
