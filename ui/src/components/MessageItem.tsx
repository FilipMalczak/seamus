import { useEffect, useState } from "react";
import {
  Bot,
  Brain,
  ChevronDown,
  ChevronRight,
  GitFork,
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

export type BranchItemType =
  | "user_message"
  | "system_event"
  | "bot_message"
  | "bot_thinking"
  | "tool_call";

export type BranchHandler = (
  targetId: string,
  position: "before" | "after",
  itemType: BranchItemType,
  text?: string
) => void;

export function BubbleBranchActions({
  targetId,
  itemType,
  text,
  onBranch,
  direction = "right",
}: {
  targetId: string;
  itemType: BranchItemType;
  text?: string;
  onBranch?: BranchHandler;
  direction?: "left" | "right";
}) {
  if (!onBranch) return null;

  const beforeTooltip =
    itemType === "user_message"
      ? "Branch before this message (get back to waiting for user input)"
      : itemType === "system_event"
        ? "Branch before this event (get back to waiting for user input)"
        : itemType === "tool_call"
          ? "Branch before tool execution (re-execute tool)"
          : itemType === "bot_thinking"
            ? "Branch before thinking (re-generate reasoning)"
            : "Branch before this message (send message again and continue)";

  const afterTooltip =
    itemType === "user_message"
      ? "Branch after this message (start inference)"
      : itemType === "system_event"
        ? "Branch after this event (start inference)"
        : itemType === "tool_call"
          ? "Branch after tool execution (keep tool result, continue processing)"
          : itemType === "bot_thinking"
            ? "Branch after thinking (keep reasoning, continue processing)"
            : "Branch after this message (message already sent, continue processing)";

  return (
    <div className={`bubble-branch-actions branch-dir-${direction}`}>
      <button
        type="button"
        className="branch-action-icon-btn branch-before-btn"
        onClick={() => onBranch(targetId, "before", itemType, text)}
        title={beforeTooltip}
        aria-label={beforeTooltip}
      >
        <GitFork className="size-3.5 branch-icon-before" />
      </button>
      <button
        type="button"
        className="branch-action-icon-btn branch-after-btn"
        onClick={() => onBranch(targetId, "after", itemType, text)}
        title={afterTooltip}
        aria-label={afterTooltip}
      >
        <GitFork className="size-3.5 branch-icon-after" />
      </button>
    </div>
  );
}

export function MessageItem({
  message,
  sequenceIndex,
  sequenceIndices,
  onBranch,
  onSubmitArtifact,
  submittingArtifactId,
}: {
  message: ChatMessage;
  sequenceIndex?: number;
  sequenceIndices?: Map<string, number>;
  onBranch?: BranchHandler;
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
          <div className="bubble-row synthetic-bubble-row">
            <BubbleBranchActions
              targetId={message.id}
              itemType="system_event"
              text={message.text}
              onBranch={onBranch}
              direction="left"
            />
            <SyntheticMessageBlock text={message.text || ""} />
          </div>
        ) : hasParts ? (
          <div className="message-parts-container">
            {message.parts!.map((part) => {
              const partSeq = getSeq(part.id);
              if (part.type === "reasoning") {
                return (
                  <div key={part.id} className="bubble-row assistant-bubble-row">
                    <ReasoningBlock
                      content={part.content}
                      isStreaming={part.isStreaming}
                      timestamp={part.timestamp || message.timestamp}
                      sequenceIndex={partSeq}
                    />
                    <BubbleBranchActions
                      targetId={part.id}
                      itemType="bot_thinking"
                      text={part.content}
                      onBranch={onBranch}
                      direction="right"
                    />
                  </div>
                );
              }
              if (part.type === "tool_call") {
                const toolSeq = partSeq ?? getSeq(part.toolCall?.id);
                return (
                  <div key={part.id} className="bubble-row assistant-bubble-row">
                    <ToolCallItem
                      toolCall={part.toolCall}
                      sequenceIndex={toolSeq}
                    />
                    <BubbleBranchActions
                      targetId={part.toolCall.id}
                      itemType="tool_call"
                      onBranch={onBranch}
                      direction="right"
                    />
                  </div>
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
                  <div key={part.id} className="bubble-row assistant-bubble-row">
                    <div className="message-bubble assistant-bubble">
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
                    <BubbleBranchActions
                      targetId={part.id}
                      itemType="bot_message"
                      text={part.content}
                      onBranch={onBranch}
                      direction="right"
                    />
                  </div>
                );
              }
              return null;
            })}
          </div>
        ) : (
          <>
            {!isUser && (message.reasoning || message.isReasoning) && (
              <div className="bubble-row assistant-bubble-row">
                <ReasoningBlock
                  content={message.reasoning || ""}
                  isStreaming={message.isReasoning}
                  timestamp={message.timestamp}
                  sequenceIndex={getSeq(`${message.id}-reasoning`)}
                />
                <BubbleBranchActions
                  targetId={`${message.id}-reasoning`}
                  itemType="bot_thinking"
                  text={message.reasoning}
                  onBranch={onBranch}
                  direction="right"
                />
              </div>
            )}

            {message.text && (
              <div
                className={`bubble-row ${isUser ? "user-bubble-row" : "assistant-bubble-row"}`}
              >
                {isUser && (
                  <BubbleBranchActions
                    targetId={message.id}
                    itemType="user_message"
                    text={message.text}
                    onBranch={onBranch}
                    direction="left"
                  />
                )}
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
                {!isUser && (
                  <BubbleBranchActions
                    targetId={message.id}
                    itemType="bot_message"
                    text={message.text}
                    onBranch={onBranch}
                    direction="right"
                  />
                )}
              </div>
            )}

            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="tool-calls-container">
                {message.toolCalls.map((tc) => (
                  <div key={tc.id} className="bubble-row assistant-bubble-row">
                    <ToolCallItem
                      toolCall={tc}
                      sequenceIndex={getSeq(tc.id)}
                    />
                    <BubbleBranchActions
                      targetId={tc.id}
                      itemType="tool_call"
                      onBranch={onBranch}
                      direction="right"
                    />
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
