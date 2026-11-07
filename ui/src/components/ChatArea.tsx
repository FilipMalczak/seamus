import React, { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Ban,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Copy,
  GitFork,
  Loader2,
  Sparkles,
  Square,
  Wrench,
} from "lucide-react";
import {
  SYNTHETIC_MESSAGE_INDICATOR,
  type AgentStatus,
  type ArtifactInfo,
  type ChatMessage,
  type MessagePart,
  type SessionBranchProvenance,
  type SessionStatus,
  type ThreadInfo,
} from "../api/types";
import { useThreadStream } from "../hooks/useThreadStream";
import { MessageItem } from "./MessageItem";

interface ChatAreaProps {
  agentId: string | null;
  agentName: string | null;
  sessionId: string | null;
  sessionName: string | null;
  sessionMode?: string;
  sessionStatus?: SessionStatus;
  sessionProvenance?: SessionBranchProvenance | null;
  sessionLineage?: SessionBranchProvenance[];
  thread: ThreadInfo | null;
  onStatusChange?: (status: AgentStatus) => void;
  onKillSession?: () => void;
  onSwitchMode?: (mode: "chat" | "plan") => Promise<void> | void;
  onThreadTransition?: (
    toThreadId: string,
    mode?: string,
    phase?: string | null
  ) => void;
  onArtifactsSync?: (
    artifacts: ArtifactInfo[],
    submitArtifact: (
      artifact: ArtifactInfo,
      data: Record<string, unknown>
    ) => Promise<void>,
    submittingArtifactId: string | null
  ) => void;
  onBranchMessage?: (
    messageId: string | null,
    options?: { retryInference?: boolean; promptToSend?: string }
  ) => void;
  onNavigateToSession?: (sessionId: string) => void;
}

export function ChatArea({
  agentId,
  agentName,
  sessionId,
  sessionName,
  sessionMode,
  sessionStatus = "ACTIVE",
  sessionProvenance,
  sessionLineage,
  thread,
  onStatusChange,
  onKillSession,
  onSwitchMode,
  onThreadTransition,
  onArtifactsSync,
  onBranchMessage,
  onNavigateToSession,
}: ChatAreaProps) {
  const [inputText, setInputText] = useState<string>("");
  const viewportRef = useRef<HTMLDivElement>(null);
  const viewportEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [isAtBottom, setIsAtBottom] = useState<boolean>(true);
  const isAtBottomRef = useRef<boolean>(true);
  const prevMessagesCountRef = useRef<number>(0);
  const prevLastMessageContentRef = useRef<string>("");
  const [errorExpanded, setErrorExpanded] = useState<boolean>(false);
  const [copiedError, setCopiedError] = useState<boolean>(false);
  const [submittingArtifactId, setSubmittingArtifactId] = useState<string | null>(null);
  const [switchingMode, setSwitchingMode] = useState<boolean>(false);

  const {
    messages,
    status,
    streamError,
    streamErrorDetails,
    sending,
    sendMessage,
    artifacts,
    hasOpenBlockingArtifact,
    refreshArtifacts,
    submitArtifact,
  } = useThreadStream(
    agentId,
    sessionId,
    thread?.id ?? null,
    sessionStatus,
    onThreadTransition
  );

  const handleSubmitArtifact = useCallback(
    async (artifact: ArtifactInfo, data: Record<string, unknown>) => {
      setSubmittingArtifactId(artifact.name);
      try {
        await submitArtifact(artifact, data);
        await refreshArtifacts();
      } finally {
        setSubmittingArtifactId(null);
      }
    },
    [submitArtifact, refreshArtifacts]
  );

  useEffect(() => {
    onArtifactsSync?.(artifacts, handleSubmitArtifact, submittingArtifactId);
  }, [artifacts, handleSubmitArtifact, submittingArtifactId, onArtifactsSync]);

  const isSessionTerminal = sessionStatus !== "ACTIVE";
  const isOpen = (thread?.is_open ?? false) && !isSessionTerminal;
  const isBusy = isOpen && status !== "AWAITING_USER" && status !== "ERROR";

  const handleBranchItem = useCallback(
    (message: ChatMessage) => {
      if (!onBranchMessage) return;

      if (message.role === "user") {
        const currentIdx = messages.findIndex((m) => m.id === message.id);
        const priorAssistant =
          currentIdx > 0
            ? messages
              .slice(0, currentIdx)
              .reverse()
              .find((m) => m.role === "assistant")
            : undefined;

        if (priorAssistant) {
          let targetId = priorAssistant.id;
          if (priorAssistant.parts && priorAssistant.parts.length > 0) {
            const textPart = priorAssistant.parts.find(
              (p) =>
                p.type === "text" &&
                p.id &&
                !p.id.startsWith("asst-") &&
                !p.id.startsWith("text-asst-")
            );
            if (textPart && textPart.id) {
              targetId = textPart.id;
            } else {
              const toolPart = priorAssistant.parts.find(
                (p) =>
                  p.type === "tool_call" &&
                  p.toolCall.id &&
                  !p.toolCall.id.startsWith("asst-")
              );
              if (
                toolPart &&
                toolPart.type === "tool_call" &&
                toolPart.toolCall.id
              ) {
                targetId = toolPart.toolCall.id;
              }
            }
          }
          onBranchMessage(targetId, { promptToSend: message.text });
        } else {
          onBranchMessage(null, { promptToSend: message.text });
        }
      } else {
        let targetId = message.id;
        if (message.parts && message.parts.length > 0) {
          const textPart = message.parts.find(
            (p: MessagePart) =>
              p.type === "text" &&
              p.id &&
              !p.id.startsWith("asst-") &&
              !p.id.startsWith("text-asst-")
          );
          if (textPart && textPart.id) {
            targetId = textPart.id;
          } else {
            const toolPart = message.parts.find(
              (p: MessagePart) =>
                p.type === "tool_call" &&
                p.toolCall.id &&
                !p.toolCall.id.startsWith("asst-")
            );
            if (
              toolPart &&
              toolPart.type === "tool_call" &&
              toolPart.toolCall.id
            ) {
              targetId = toolPart.toolCall.id;
            }
          }
        }
        onBranchMessage(targetId);
      }
    },
    [messages, onBranchMessage]
  );

  const handleBranchToolItem = useCallback(
    (message: ChatMessage) => {
      if (!onBranchMessage) return;
      let targetId = message.id;
      if (message.toolCalls && message.toolCalls.length > 0) {
        const lastTool = message.toolCalls[message.toolCalls.length - 1];
        if (lastTool && lastTool.id) {
          targetId = lastTool.id;
        }
      }
      onBranchMessage(targetId, { retryInference: true });
    },
    [onBranchMessage]
  );

  const branchPoints = useMemo(() => {
    const list =
      sessionLineage && sessionLineage.length > 0
        ? sessionLineage
        : sessionProvenance
          ? [sessionProvenance]
          : [];

    const map = new Map<number, SessionBranchProvenance[]>();
    if (list.length === 0 || messages.length === 0) return map;

    for (let i = 0; i < list.length; i++) {
      const prov = list[i];
      const targetId = prov.parent_message_id;

      // 1. Direct match on message.id
      let idx = messages.findIndex((m) => m.id === targetId);

      // 2. Match within parts or toolCalls
      if (idx === -1) {
        idx = messages.findIndex((m) =>
          Boolean(
            m.parts?.some(
              (p) =>
                p.id === targetId ||
                (p.type === "tool_call" && p.toolCall.id === targetId)
            ) ||
            m.toolCalls?.some((tc) => tc.id === targetId)
          )
        );
      }

      // 3. Fallback: match by turn index if targetId is asst-N
      if (idx === -1 && targetId.startsWith("asst-")) {
        const suffix = targetId.slice(5);
        if (/^\d+$/.test(suffix)) {
          const turnIdx = parseInt(suffix, 10);
          const asstIndices = messages
            .map((m, j) => (m.role === "assistant" ? j : -1))
            .filter((j) => j >= 0);
          if (turnIdx < asstIndices.length) {
            idx = asstIndices[turnIdx];
          }
        }
      }

      // 4. Fallback if single entry: pick last assistant message
      if (idx === -1 && list.length === 1) {
        for (let j = messages.length - 1; j >= 0; j--) {
          if (messages[j].role === "assistant") {
            idx = j;
            break;
          }
        }
        if (idx === -1) idx = 0;
      }

      if (idx >= 0) {
        const existing = map.get(idx) || [];
        existing.push(prov);
        map.set(idx, existing);
      }
    }
    return map;
  }, [sessionLineage, sessionProvenance, messages]);

  // Notify parent of active thread status changes
  useEffect(() => {
    onStatusChange?.(status);
  }, [status, onStatusChange]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    viewportEndRef.current?.scrollIntoView({ behavior });
  }, []);

  const handleScroll = useCallback(() => {
    const el = viewportRef.current;
    if (!el) return;
    // Consider pinned to bottom if within 60px of the bottom edge
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= 60;
    isAtBottomRef.current = atBottom;
    setIsAtBottom(atBottom);
  }, []);

  // Auto-scroll to bottom ONLY when new messages or new tokens arrive, AND user was already at bottom
  useEffect(() => {
    const lastMsg = messages[messages.length - 1];
    const lastContent = lastMsg
      ? `${lastMsg.id}:${lastMsg.text || ""}:${lastMsg.parts?.length || 0}`
      : "";

    const hasNewContent =
      messages.length !== prevMessagesCountRef.current ||
      lastContent !== prevLastMessageContentRef.current;

    if (hasNewContent) {
      prevMessagesCountRef.current = messages.length;
      prevLastMessageContentRef.current = lastContent;

      if (isAtBottomRef.current) {
        scrollToBottom("smooth");
      }
    }
  }, [messages, scrollToBottom]);

  // When active thread changes, reset scroll pin to bottom
  useEffect(() => {
    isAtBottomRef.current = true;
    isAtBottomRef.current = true;
    setIsAtBottom(true);
    scrollToBottom("auto");
  }, [thread?.id, scrollToBottom]);

  // Auto-focus the message composer whenever active thread changes, opens, or finishes processing
  useEffect(() => {
    if (isOpen && !isBusy && !sending) {
      const timer = setTimeout(() => {
        textareaRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [thread?.id, isOpen, isBusy, sending]);

  const handleSend = async () => {
    if (!inputText.trim() || isBusy || !isOpen || sending || hasOpenBlockingArtifact) return;
    if (inputText.startsWith(SYNTHETIC_MESSAGE_INDICATOR)) {
      alert("Messages starting with the reserved platform indicator cannot be sent directly.");
      return;
    }
    const textToSend = inputText;
    setInputText("");
    isAtBottomRef.current = true;
    setIsAtBottom(true);
    scrollToBottom("smooth");
    try {
      await sendMessage(textToSend);
    } catch {
      // Stream error will display in the alert banner
      setInputText(textToSend);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const renderStatusBadge = () => {
    if (sessionStatus === "KILLED") {
      return (
        <span className="status-pill status-killed">
          <Ban className="size-3.5 text-zinc-400" />
          <span>Killed</span>
        </span>
      );
    }
    if (sessionStatus === "FAILED") {
      return (
        <span className="status-pill status-failed">
          <AlertTriangle className="size-3.5 text-rose-400" />
          <span>Failed</span>
        </span>
      );
    }
    switch (status) {
      case "AWAITING_USER":
        return (
          <span className="status-pill status-ready">
            <CheckCircle2 className="size-3.5" />
            <span>Ready</span>
          </span>
        );
      case "AWAITING_LLM":
        return (
          <span className="status-pill status-thinking">
            <Loader2 className="size-3.5 animate-spin" />
            <span>Thinking...</span>
          </span>
        );
      case "EXECUTING_TOOL":
        return (
          <span className="status-pill status-tool">
            <Wrench className="size-3.5 animate-pulse" />
            <span>Executing Tool...</span>
          </span>
        );
      case "ERROR":
        return (
          <span className="status-pill status-error">
            <AlertCircle className="size-3.5" />
            <span>Execution Error</span>
          </span>
        );
      default:
        return null;
    }
  };

  if (!thread) {
    return (
      <main className="chat-main chat-empty-main">
        <div className="empty-state">
          <Bot className="size-12 text-sky-400" />
          <h2>Select a Session or Thread</h2>
          <p>Choose an agent, session, and thread from the sidebar tree to start chatting.</p>
        </div>
      </main>
    );
  }

  const currentThreadMode = (thread.mode || "plan") as "chat" | "plan";
  const activeSessionMode = ((sessionMode || currentThreadMode || "plan") as "chat" | "plan");
  const currentModeLabel =
    thread.mode_label ||
    (thread.phase ? `${currentThreadMode}/${thread.phase}` : currentThreadMode);

  const handleModeClick = async (targetMode: "chat" | "plan") => {
    if (!onSwitchMode || switchingMode || isBusy || sending || isSessionTerminal) {
      return;
    }
    if (activeSessionMode === targetMode && isOpen && currentThreadMode === targetMode) {
      return;
    }
    setSwitchingMode(true);
    try {
      await onSwitchMode(targetMode);
    } finally {
      setSwitchingMode(false);
    }
  };

  return (
    <main className="chat-main">
      <div className="chat-top-bar">
        <div className="chat-breadcrumbs">
          <span className="crumb-item">
            <span className="crumb-agent">{agentName || agentId || "Agent"}</span>
            <span className="crumb-sep">/</span>
          </span>
          <span className="crumb-item">
            <span className="crumb-session">{sessionName || sessionId || "Session"}</span>
            <span className="crumb-sep">/</span>
          </span>
          <span className="crumb-item crumb-item-thread">
            <span className="crumb-thread">
              {thread.name || thread.id}
            </span>
            <span className={`thread-mode-badge mode-${currentThreadMode}`}>
              {currentModeLabel}
            </span>
            <span className={`thread-state-badge ${isOpen ? "state-open" : "state-closed"}`}>
              {isOpen ? "Active Open Thread" : "Closed Thread"}
            </span>
          </span>
        </div>

        <div className="chat-top-actions">
          {sessionStatus === "ACTIVE" && onSwitchMode && (
            <div className="mode-selector-group" role="group" aria-label="Operational Mode">
              <button
                type="button"
                className={`mode-selector-btn ${activeSessionMode === "chat" ? "active" : ""}`}
                onClick={() => handleModeClick("chat")}
                disabled={isBusy || sending || switchingMode}
                title="Switch session to Chat mode (opens a new Chat thread)"
              >
                Chat
              </button>
              <button
                type="button"
                className={`mode-selector-btn mode-plan ${activeSessionMode === "plan" ? "active" : ""}`}
                onClick={() => handleModeClick("plan")}
                disabled={isBusy || sending || switchingMode}
                title="Switch session to Plan mode (opens a new Plan/Discuss thread)"
              >
                {activeSessionMode === "plan" && (thread.mode === "plan" && thread.phase ? thread.phase : "discuss")
                  ? `Plan (${thread.mode === "plan" && thread.phase ? thread.phase : "discuss"})`
                  : "Plan"}
              </button>
            </div>
          )}
          {sessionStatus === "ACTIVE" && status !== "ERROR" && onKillSession && (
            <button
              type="button"
              className="btn-kill-session"
              onClick={onKillSession}
              title="Kill active session permanently"
            >
              <Square className="size-3 text-rose-400" />
              <span>Kill Session</span>
            </button>
          )}
          {renderStatusBadge()}
        </div>
      </div>

      {sessionStatus === "KILLED" && (
        <div className="terminal-session-notice notice-killed">
          <Ban className="size-4 text-zinc-400" />
          <span>
            This session was manually killed and cannot be continued. You can branch off any completed assistant message above to retry or continue.
          </span>
        </div>
      )}

      {sessionStatus === "FAILED" && (
        <div className="terminal-session-notice notice-failed">
          <AlertTriangle className="size-4 text-rose-400" />
          <span>
            This session terminated due to an unrecoverable failure and cannot be continued. You can branch off any completed assistant message above to retry.
          </span>
        </div>
      )}

      <div
        className="chat-viewport"
        ref={viewportRef}
        onScroll={handleScroll}
      >
        {messages.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">
              <Sparkles className="size-8 text-sky-400" />
            </div>
            <h2>Welcome to Seamus DeepAgent</h2>
            <p>
              Start chatting below. Responses stream via Server-Sent Events (SSE) with
              tool execution visibility.
            </p>
            <div className="empty-suggestions">
              <span className="suggestion-label">Try asking:</span>
              <div className="suggestions-list">
                <button
                  type="button"
                  className="suggestion-pill"
                  onClick={() =>
                    setInputText("I need to test and debug custom artifacts. Create one such artifact. It doesn't matter whats inside, just checking that all the mechanics are correct. Use bundled skills to understand how to handle artifacts, especially custom ones. Try the widget-related skill to build an actual showcase of widgets too.")
                  }
                >
                  Showcase custom artifacts &rarr;
                </button>
                <button
                  type="button"
                  className="suggestion-pill"
                  onClick={() =>
                    setInputText("Put the iris dataset in your workspace. Dont use external libraries - either use python to fetch it or write it from memory. Add a simple (no-dependency) python script that performs rudimentary analysis of dataset (counts examples, counts classes, etc; again - no deps). Skip automated verification, verify manually, by running the script and checking the output.")
                  }
                >
                  Fetch iris dataset &rarr;
                </button>
              </div>
            </div>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <React.Fragment key={msg.id}>
              <MessageItem
                message={msg}
                onBranch={onBranchMessage ? () => handleBranchItem(msg) : undefined}
                onBranchTool={
                  onBranchMessage && msg.role === "assistant" && msg.toolCalls && msg.toolCalls.length > 0
                    ? () => handleBranchToolItem(msg)
                    : undefined
                }
                onSubmitArtifact={handleSubmitArtifact}
                submittingArtifactId={submittingArtifactId}
              />
              {branchPoints.get(idx)?.map((prov, pIdx) => (
                <div
                  key={`${prov.parent_session_id}-${prov.parent_message_id}-${pIdx}`}
                  className="branch-provenance-separator"
                >
                  <div className="separator-line" />
                  <div className="separator-content">
                    <GitFork className="size-3 text-sky-400" />
                    <span className="separator-text">branched from</span>
                    {onNavigateToSession ? (
                      <button
                        type="button"
                        className="separator-link-btn"
                        onClick={() =>
                          onNavigateToSession(prov.parent_session_id)
                        }
                        title={`Navigate to parent session: ${prov.parent_session_name || prov.parent_session_id}`}
                      >
                        {prov.parent_session_name ||
                          prov.parent_session_id.slice(0, 8)}
                      </button>
                    ) : (
                      <span className="separator-name">
                        {prov.parent_session_name ||
                          prov.parent_session_id.slice(0, 8)}
                      </span>
                    )}
                  </div>
                  <div className="separator-line" />
                </div>
              ))}
            </React.Fragment>
          ))
        )}
        <div ref={viewportEndRef} />
      </div>

      {!isAtBottom && messages.length > 0 && (
        <button
          type="button"
          className="scroll-to-bottom-btn"
          onClick={() => {
            isAtBottomRef.current = true;
            setIsAtBottom(true);
            scrollToBottom("smooth");
          }}
          title="Scroll to bottom"
          aria-label="Scroll to bottom"
        >
          <ArrowDown className="size-3.5" />
          <span>Scroll to bottom</span>
        </button>
      )}

      {streamError && (
        <div className="chat-error-panel">
          <div className="chat-error-header">
            <div className="chat-error-main">
              <AlertCircle className="size-4 shrink-0 text-rose-400" />
              {streamErrorDetails?.errorType && (
                <span className="chat-error-type-badge">
                  {streamErrorDetails.errorType}
                </span>
              )}
              <span className="chat-error-message">{streamError}</span>
            </div>
            <div className="chat-error-actions">
              <button
                type="button"
                className="chat-error-action-btn"
                onClick={() => {
                  const fullDiag = [
                    streamErrorDetails?.errorType
                      ? `[${streamErrorDetails.errorType}] ${streamError}`
                      : streamError,
                    streamErrorDetails?.traceback || "",
                  ]
                    .filter(Boolean)
                    .join("\n\n");
                  navigator.clipboard.writeText(fullDiag).then(() => {
                    setCopiedError(true);
                    setTimeout(() => setCopiedError(false), 1800);
                  });
                }}
                title="Copy full error diagnostics"
              >
                {copiedError ? (
                  <>
                    <Check className="size-3.5 text-emerald-400" />
                    <span>Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="size-3.5" />
                    <span>Copy</span>
                  </>
                )}
              </button>
              {streamErrorDetails?.traceback && (
                <button
                  type="button"
                  className="chat-error-action-btn"
                  onClick={() => setErrorExpanded((prev) => !prev)}
                  title={errorExpanded ? "Hide traceback" : "Show full stack trace"}
                >
                  {errorExpanded ? (
                    <>
                      <ChevronDown className="size-3.5" />
                      <span>Hide Traceback</span>
                    </>
                  ) : (
                    <>
                      <ChevronRight className="size-3.5" />
                      <span>Traceback</span>
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
          {errorExpanded && streamErrorDetails?.traceback && (
            <pre className="chat-error-traceback">{streamErrorDetails.traceback}</pre>
          )}
        </div>
      )}

      {!isOpen && !isSessionTerminal && (
        <div className="closed-thread-notice">
          <Clock className="size-4" />
          <span>This thread is closed. New messages cannot be sent to closed threads. Select the active open thread to continue.</span>
        </div>
      )}

      {hasOpenBlockingArtifact && (
        <div className="blocking-artifact-notice">
          <Sparkles className="size-4 text-sky-400" />
          <span>
            An interactive questionnaire requires your response before conversation can continue.
          </span>
        </div>
      )}

      <div className="composer-container">
        <div className="composer-box">
          <textarea
            ref={textareaRef}
            className="composer-textarea"
            placeholder={
              sessionStatus === "KILLED"
                ? "This session was killed. Branch off any message above to continue."
                : sessionStatus === "FAILED"
                  ? "This session failed. Branch off any message above to retry."
                  : !isOpen
                    ? "This thread is closed. Select the active open thread to continue."
                    : hasOpenBlockingArtifact
                      ? "Questionnaire in progress (drafting enabled; submit questionnaire to send)..."
                      : isBusy
                        ? "Agent is busy processing (drafting enabled; please wait to send)..."
                        : "Send a message to Seamus... (Enter to send, Shift+Enter for newline)"
            }
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!isOpen}
            rows={2}
            autoFocus
          />

          <button
            type="button"
            className="composer-send-btn"
            onClick={handleSend}
            disabled={!inputText.trim() || !isOpen || isBusy || sending || hasOpenBlockingArtifact}
            title={
              hasOpenBlockingArtifact
                ? "Questionnaire in progress"
                : isBusy
                  ? "Agent is busy"
                  : "Send message (Enter)"
            }
          >
            {isOpen && (isBusy || sending) ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <ArrowUp className="size-4" />
            )}
          </button>
        </div>
      </div>
    </main>
  );
}

