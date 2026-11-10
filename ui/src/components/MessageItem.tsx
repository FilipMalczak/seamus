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
import { formatBubbleTime, formatFullDate } from "../utils/sequence";
import { ArtifactRenderer } from "./ArtifactRenderer";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { ToolCallItem } from "./ToolCallItem";

export { formatBubbleTime, formatFullDate };

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
  timestamp,
  sequenceIndex,
}: {
  content: string;
  isStreaming?: boolean;
  timestamp?: string;
  sequenceIndex?: number;
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
          {sequenceIndex !== undefined && (
            <span
              className="bubble-sequence-badge"
              title={`Step #${sequenceIndex} in sequence`}
            >
              #{sequenceIndex}
            </span>
          )}
          <Brain
            className={`size-3.5 text-sky-400 ${isStreaming ? "animate-pulse" : ""}`}
          />
          <span className="reasoning-label">
            {isStreaming ? "Thinking..." : "Thought process"}
          </span>
          {timestamp && (
            <span
              className="part-timestamp"
              title={formatFullDate(timestamp)}
            >
              {formatBubbleTime(timestamp)}
            </span>
          )}
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
  sequenceIndex,
  sequenceIndices,
  onBranch,
  onBranchTool,
  onSubmitArtifact,
  submittingArtifactId,
}: {
  message: ChatMessage;
  sequenceIndex?: number;
  sequenceIndices?: Map<string, number>;
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

  const hasText = isUser
    ? Boolean(message.text)
    : hasParts
      ? Boolean(message.parts?.some((p) => p.type === "text" && Boolean(p.content)))
      : Boolean(message.text);

  const formattedTime = formatBubbleTime(message.timestamp);
  const fullTimestamp = formatFullDate(message.timestamp);

  const getSeq = (key?: string): number | undefined => {
    if (!key) return sequenceIndex;
    return sequenceIndices?.get(key) ?? sequenceIndex;
  };

  const headerSeq = getSeq(message.id);

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
          {headerSeq !== undefined && !hasText && !hasParts && (
            <span
              className="bubble-sequence-badge"
              title={`Step #${headerSeq} in sequence`}
            >
              #{headerSeq}
            </span>
          )}
          <span className="message-sender">
            {isSynthetic ? "System Event" : isUser ? "You" : "Seamus Agent"}
          </span>
          <span className="message-time" title={fullTimestamp}>
            {formattedTime}
          </span>
        </div>

        {isSynthetic ? (
          <SyntheticMessageBlock text={message.text || ""} />
        ) : hasParts ? (
          <div className="message-parts-container">
            {message.parts!.map((part) => {
              const partSeq = getSeq(part.id);
              if (part.type === "reasoning") {
                return (
                  <ReasoningBlock
                    key={part.id}
                    content={part.content}
                    isStreaming={part.isStreaming}
                    timestamp={part.timestamp || message.timestamp}
                    sequenceIndex={partSeq}
                  />
                );
              }
              if (part.type === "tool_call") {
                const toolSeq = partSeq ?? getSeq(part.toolCall?.id);
                return (
                  <ToolCallItem
                    key={part.id}
                    toolCall={part.toolCall}
                    sequenceIndex={toolSeq}
                  />
                );
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
                const textTime = part.timestamp || message.timestamp;
                return (
                  <div key={part.id} className="message-bubble assistant-bubble">
                    {partSeq !== undefined && (
                      <div className="bubble-top-bar">
                        <span
                          className="bubble-sequence-badge"
                          title={`Step #${partSeq} in sequence`}
                        >
                          #{partSeq}
                        </span>
                      </div>
                    )}
                    <div className="bubble-content">
                      <MarkdownRenderer content={part.content} variant="assistant" />
                    </div>
                    <div className="bubble-footer">
                      <span className="bubble-timestamp" title={formatFullDate(textTime)}>
                        {formatBubbleTime(textTime)}
                      </span>
                    </div>
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
                timestamp={message.timestamp}
                sequenceIndex={getSeq(`${message.id}-reasoning`)}
              />
            )}

            {message.text && (
              <div
                className={`message-bubble ${isUser ? "user-bubble" : "assistant-bubble"}`}
              >
                {getSeq(isUser ? message.id : `${message.id}-text`) !== undefined && (
                  <div className="bubble-top-bar">
                    <span
                      className="bubble-sequence-badge"
                      title={`Step #${getSeq(isUser ? message.id : `${message.id}-text`)} in sequence`}
                    >
                      #{getSeq(isUser ? message.id : `${message.id}-text`)}
                    </span>
                  </div>
                )}
                <div className="bubble-content">
                  <MarkdownRenderer
                    content={message.text}
                    variant={isUser ? "user" : "assistant"}
                  />
                </div>
                <div className="bubble-footer">
                  <span className="bubble-timestamp" title={fullTimestamp}>
                    {formattedTime}
                  </span>
                </div>
              </div>
            )}

            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="tool-calls-container">
                {message.toolCalls.map((tc) => (
                  <ToolCallItem
                    key={tc.id}
                    toolCall={tc}
                    sequenceIndex={getSeq(tc.id)}
                  />
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
