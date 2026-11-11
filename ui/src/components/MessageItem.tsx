import React, { useEffect, useState } from "react";
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
  type MessagePart,
  type SessionBranchProvenance,
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

export function BranchProvenanceSeparator({
  provenance,
  onNavigateToSession,
}: {
  provenance: SessionBranchProvenance;
  onNavigateToSession?: (sessionId: string) => void;
}) {
  const label =
    provenance.branch_position === "before"
      ? "branched before"
      : provenance.branch_position === "after"
        ? "branched after"
        : "branched from";

  return (
    <div
      className="branch-provenance-separator"
      data-testid="branch-provenance-separator"
    >
      <div className="separator-line" />
      <div className="separator-content">
        <GitFork className="size-3 text-sky-400" />
        <span className="separator-text">{label}</span>
        {onNavigateToSession ? (
          <button
            type="button"
            className="separator-link-btn"
            onClick={() => onNavigateToSession(provenance.parent_session_id)}
            title={`Navigate to parent session: ${provenance.parent_session_name || provenance.parent_session_id}`}
          >
            {provenance.parent_session_name ||
              provenance.parent_session_id.slice(0, 8)}
          </button>
        ) : (
          <span className="separator-name">
            {provenance.parent_session_name ||
              provenance.parent_session_id.slice(0, 8)}
          </span>
        )}
      </div>
      <div className="separator-line" />
    </div>
  );
}

export function BubbleBranchActions({
  targetId,
  itemType,
  text,
  onBranch,
  direction = "right",
  isGroup = false,
}: {
  targetId: string;
  itemType: BranchItemType;
  text?: string;
  onBranch?: BranchHandler;
  direction?: "left" | "right";
  isGroup?: boolean;
}) {
  if (!onBranch) return null;

  const beforeTooltip =
    itemType === "user_message"
      ? "Branch before this message (get back to waiting for user input)"
      : itemType === "system_event"
        ? "Branch before this event (get back to waiting for user input)"
        : itemType === "tool_call"
          ? isGroup
            ? "Branch before tool group (restart all tools in group)"
            : "Branch before tool execution (re-execute tool)"
          : itemType === "bot_thinking"
            ? "Branch before thinking (re-generate reasoning)"
            : "Branch before this message (send message again and continue)";

  const afterTooltip =
    itemType === "user_message"
      ? "Branch after this message (start inference)"
      : itemType === "system_event"
        ? "Branch after this event (start inference)"
        : itemType === "tool_call"
          ? isGroup
            ? "Branch after tool group (keep tool results, continue processing)"
            : "Branch after tool execution (keep tool result, continue processing)"
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
        <GitFork className="size-2.5 branch-icon-before" />
      </button>
      <button
        type="button"
        className="branch-action-icon-btn branch-after-btn"
        onClick={() => onBranch(targetId, "after", itemType, text)}
        title={afterTooltip}
        aria-label={afterTooltip}
      >
        <GitFork className="size-2.5 branch-icon-after" />
      </button>
    </div>
  );
}

type GroupedPart =
  | { type: "single"; part: MessagePart }
  | {
      type: "tool_group";
      parts: (Extract<MessagePart, { type: "tool_call" }>)[];
    };

function groupMessageParts(parts: MessagePart[]): GroupedPart[] {
  const result: GroupedPart[] = [];
  let currentToolGroup: (Extract<MessagePart, { type: "tool_call" }>)[] = [];

  for (const part of parts) {
    if (part.type === "tool_call") {
      currentToolGroup.push(part);
    } else {
      if (currentToolGroup.length > 0) {
        if (currentToolGroup.length === 1) {
          result.push({ type: "single", part: currentToolGroup[0] });
        } else {
          result.push({ type: "tool_group", parts: currentToolGroup });
        }
        currentToolGroup = [];
      }
      result.push({ type: "single", part });
    }
  }

  if (currentToolGroup.length > 0) {
    if (currentToolGroup.length === 1) {
      result.push({ type: "single", part: currentToolGroup[0] });
    } else {
      result.push({ type: "tool_group", parts: currentToolGroup });
    }
  }

  return result;
}

export function MessageItem({
  message,
  sequenceIndex,
  sequenceIndices,
  onBranch,
  onSubmitArtifact,
  submittingArtifactId,
  provenanceList,
  onNavigateToSession,
}: {
  message: ChatMessage;
  sequenceIndex?: number;
  sequenceIndices?: Map<string, number>;
  onBranch?: BranchHandler;
  onSubmitArtifact?: (
    artifact: ArtifactInfo,
    data: Record<string, unknown>
  ) => Promise<void> | void;
  submittingArtifactId?: string | null;
  provenanceList?: SessionBranchProvenance[];
  onNavigateToSession?: (sessionId: string) => void;
}) {
  const isSynthetic = Boolean(
    message.text?.startsWith(SYNTHETIC_MESSAGE_INDICATOR)
  );
  const isUser = message.role === "user" && !isSynthetic;
  const hasParts =
    !isUser && !isSynthetic && Boolean(message.parts && message.parts.length > 0);

  const hasText = isUser
    ? Boolean(message.text)
    : hasParts
      ? Boolean(
          message.parts?.some(
            (p) => p.type === "text" && Boolean(p.content)
          )
        )
      : Boolean(message.text);

  const formattedTime = formatBubbleTime(message.timestamp);
  const fullTimestamp = formatFullDate(message.timestamp);

  const getSeq = (key?: string): number | undefined => {
    if (!key) return sequenceIndex;
    return sequenceIndices?.get(key) ?? sequenceIndex;
  };

  const headerSeq = getSeq(message.id);

  // Helper to extract provenance entries that match any candidate IDs
  const getProvsFor = (
    targetIds: (string | undefined)[]
  ): SessionBranchProvenance[] => {
    const validIds = new Set(targetIds.filter(Boolean) as string[]);
    if (validIds.size === 0 || !provenanceList || provenanceList.length === 0)
      return [];
    return provenanceList.filter((p) => {
      if (validIds.has(p.parent_message_id)) return true;
      for (const vid of validIds) {
        if (
          vid.length > 5 &&
          (vid === p.parent_message_id ||
            p.parent_message_id === `call-${vid}` ||
            vid === `call-${p.parent_message_id}` ||
            p.parent_message_id === `group-${vid}` ||
            vid === `group-${p.parent_message_id}`)
        ) {
          return true;
        }
      }
      return false;
    });
  };

  const renderSeparators = (provs: SessionBranchProvenance[]) => {
    return provs.map((prov, pIdx) => (
      <BranchProvenanceSeparator
        key={`${prov.parent_session_id}-${prov.parent_message_id}-${pIdx}`}
        provenance={prov}
        onNavigateToSession={onNavigateToSession}
      />
    ));
  };

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
          (() => {
            const synthProvs = getProvsFor([message.id]);
            const synthBefore = synthProvs.filter(
              (p) => p.branch_position === "before"
            );
            const synthAfter = synthProvs.filter(
              (p) => p.branch_position !== "before"
            );
            return (
              <>
                {renderSeparators(synthBefore)}
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
                {renderSeparators(synthAfter)}
              </>
            );
          })()
        ) : hasParts ? (
          <div className="message-parts-container">
            {groupMessageParts(message.parts!).map((item, itemIdx) => {
              if (item.type === "tool_group") {
                const groupIds = item.parts.flatMap((p) => [
                  p.id,
                  p.toolCall.id,
                  `call-${p.toolCall.id}`,
                  `group-${p.toolCall.id}`,
                ]);
                const gProvs = getProvsFor(groupIds);
                const gBefore = gProvs.filter(
                  (p) => p.branch_position === "before"
                );
                const gAfter = gProvs.filter(
                  (p) => p.branch_position !== "before"
                );
                const groupTargetId = item.parts[0].toolCall.id;
                const midIndex = Math.floor(item.parts.length / 2);

                return (
                  <React.Fragment key={`tool-group-${groupTargetId}-${itemIdx}`}>
                    <div className="tool-group-wrapper assistant-bubble-row">
                      <div className="tool-group-brace-container">
                        <div className="tool-group-brace" />
                        <div className="tool-group-items">
                          {item.parts.map((p, pIdx) => {
                            const toolSeq =
                              getSeq(p.id) ?? getSeq(p.toolCall?.id);
                            const isMidpoint =
                              gBefore.length > 0 && pIdx === midIndex;
                            return (
                              <React.Fragment key={p.id}>
                                {isMidpoint && renderSeparators(gBefore)}
                                <div className="bubble-row tool-sub-row">
                                  <ToolCallItem
                                    toolCall={p.toolCall}
                                    sequenceIndex={toolSeq}
                                  />
                                </div>
                              </React.Fragment>
                            );
                          })}
                        </div>
                      </div>
                      <BubbleBranchActions
                        targetId={groupTargetId}
                        itemType="tool_call"
                        onBranch={onBranch}
                        direction="right"
                        isGroup={true}
                      />
                    </div>
                    {renderSeparators(gAfter)}
                  </React.Fragment>
                );
              }

              const part = item.part;
              const partSeq = getSeq(part.id);

              if (part.type === "reasoning") {
                const rProvs = getProvsFor([part.id, `${message.id}-reasoning`]);
                const rBefore = rProvs.filter(
                  (p) => p.branch_position === "before"
                );
                const rAfter = rProvs.filter(
                  (p) => p.branch_position !== "before"
                );
                return (
                  <React.Fragment key={part.id}>
                    {renderSeparators(rBefore)}
                    <div className="bubble-row assistant-bubble-row">
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
                    {renderSeparators(rAfter)}
                  </React.Fragment>
                );
              }

              if (part.type === "tool_call") {
                const toolSeq = partSeq ?? getSeq(part.toolCall?.id);
                const tcProvs = getProvsFor([
                  part.id,
                  part.toolCall.id,
                  `call-${part.toolCall.id}`,
                ]);
                const tcBefore = tcProvs.filter(
                  (p) => p.branch_position === "before"
                );
                const tcAfter = tcProvs.filter(
                  (p) => p.branch_position !== "before"
                );
                return (
                  <React.Fragment key={part.id}>
                    {renderSeparators(tcBefore)}
                    <div className="bubble-row assistant-bubble-row">
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
                    {renderSeparators(tcAfter)}
                  </React.Fragment>
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
                const tProvs = getProvsFor([
                  part.id,
                  message.id,
                  `text-${part.id}`,
                ]);
                const tBefore = tProvs.filter(
                  (p) => p.branch_position === "before"
                );
                const tAfter = tProvs.filter(
                  (p) => p.branch_position !== "before"
                );
                return (
                  <React.Fragment key={part.id}>
                    {renderSeparators(tBefore)}
                    <div className="bubble-row assistant-bubble-row">
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
                          <MarkdownRenderer
                            content={part.content}
                            variant="assistant"
                          />
                        </div>
                        <div className="bubble-footer">
                          <span
                            className="bubble-timestamp"
                            title={formatFullDate(textTime)}
                          >
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
                    {renderSeparators(tAfter)}
                  </React.Fragment>
                );
              }

              return null;
            })}
          </div>
        ) : (
          <>
            {!isUser && (message.reasoning || message.isReasoning) && (
              (() => {
                const rProvs = getProvsFor([`${message.id}-reasoning`]);
                const rBefore = rProvs.filter(
                  (p) => p.branch_position === "before"
                );
                const rAfter = rProvs.filter(
                  (p) => p.branch_position !== "before"
                );
                return (
                  <>
                    {renderSeparators(rBefore)}
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
                    {renderSeparators(rAfter)}
                  </>
                );
              })()
            )}

            {message.text && (
              (() => {
                const textProvs = getProvsFor([message.id]);
                const textBefore = textProvs.filter(
                  (p) => p.branch_position === "before"
                );
                const textAfter = textProvs.filter(
                  (p) => p.branch_position !== "before"
                );
                return (
                  <>
                    {renderSeparators(textBefore)}
                    <div
                      className={`bubble-row ${
                        isUser ? "user-bubble-row" : "assistant-bubble-row"
                      }`}
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
                        className={`message-bubble ${
                          isUser ? "user-bubble" : "assistant-bubble"
                        }`}
                      >
                        {getSeq(isUser ? message.id : `${message.id}-text`) !==
                          undefined && (
                          <div className="bubble-top-bar">
                            <span
                              className="bubble-sequence-badge"
                              title={`Step #${getSeq(
                                isUser ? message.id : `${message.id}-text`
                              )} in sequence`}
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
                          <span
                            className="bubble-timestamp"
                            title={fullTimestamp}
                          >
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
                    {renderSeparators(textAfter)}
                  </>
                );
              })()
            )}

            {message.toolCalls && message.toolCalls.length > 0 && (
              (() => {
                if (message.toolCalls.length === 1) {
                  const tc = message.toolCalls[0];
                  const tcProvs = getProvsFor([tc.id, `call-${tc.id}`]);
                  const tcBefore = tcProvs.filter(
                    (p) => p.branch_position === "before"
                  );
                  const tcAfter = tcProvs.filter(
                    (p) => p.branch_position !== "before"
                  );
                  return (
                    <div className="tool-calls-container">
                      {renderSeparators(tcBefore)}
                      <div className="bubble-row assistant-bubble-row">
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
                      {renderSeparators(tcAfter)}
                    </div>
                  );
                }

                // Tool group with brace (> 1 tool calls)
                const groupIds = message.toolCalls.flatMap((tc) => [
                  tc.id,
                  `call-${tc.id}`,
                  `group-${tc.id}`,
                ]);
                const gProvs = getProvsFor(groupIds);
                const gBefore = gProvs.filter(
                  (p) => p.branch_position === "before"
                );
                const gAfter = gProvs.filter(
                  (p) => p.branch_position !== "before"
                );
                const groupTargetId = message.toolCalls[0].id;
                const midIndex = Math.floor(message.toolCalls.length / 2);

                return (
                  <div className="tool-calls-container">
                    <div className="tool-group-wrapper assistant-bubble-row">
                      <div className="tool-group-brace-container">
                        <div className="tool-group-brace" />
                        <div className="tool-group-items">
                          {message.toolCalls.map((tc, pIdx) => {
                            const isMidpoint =
                              gBefore.length > 0 && pIdx === midIndex;
                            return (
                              <React.Fragment key={tc.id}>
                                {isMidpoint && renderSeparators(gBefore)}
                                <div className="bubble-row tool-sub-row">
                                  <ToolCallItem
                                    toolCall={tc}
                                    sequenceIndex={getSeq(tc.id)}
                                  />
                                </div>
                              </React.Fragment>
                            );
                          })}
                        </div>
                      </div>
                      <BubbleBranchActions
                        targetId={groupTargetId}
                        itemType="tool_call"
                        onBranch={onBranch}
                        direction="right"
                        isGroup={true}
                      />
                    </div>
                    {renderSeparators(gAfter)}
                  </div>
                );
              })()
            )}
          </>
        )}
      </div>
    </div>
  );
}
