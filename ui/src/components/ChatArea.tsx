import React, { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Ban,
  Bot,
  CheckCircle2,
  Clock,
  GitFork,
  Loader2,
  Sparkles,
  Square,
  Wrench,
} from "lucide-react";
import type { AgentStatus, SessionBranchProvenance, SessionStatus, ThreadInfo } from "../api/types";
import { useThreadStream } from "../hooks/useThreadStream";
import { MessageItem } from "./MessageItem";

interface ChatAreaProps {
  agentId: string | null;
  agentName: string | null;
  sessionId: string | null;
  sessionName: string | null;
  sessionStatus?: SessionStatus;
  sessionProvenance?: SessionBranchProvenance | null;
  sessionLineage?: SessionBranchProvenance[];
  thread: ThreadInfo | null;
  onStatusChange?: (status: AgentStatus) => void;
  onKillSession?: () => void;
  onBranchMessage?: (messageId: string) => void;
  onNavigateToSession?: (sessionId: string) => void;
}

export function ChatArea({
  agentId,
  agentName,
  sessionId,
  sessionName,
  sessionStatus = "ACTIVE",
  sessionProvenance,
  sessionLineage,
  thread,
  onStatusChange,
  onKillSession,
  onBranchMessage,
  onNavigateToSession,
}: ChatAreaProps) {
  const [inputText, setInputText] = useState<string>("");
  const viewportRef = useRef<HTMLDivElement>(null);
  const viewportEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [isAtBottom, setIsAtBottom] = useState<boolean>(true);

  const { messages, status, streamError, sending, sendMessage } =
    useThreadStream(agentId, sessionId, thread?.id ?? null);

  const isSessionTerminal = sessionStatus !== "ACTIVE";
  const isOpen = (thread?.is_open ?? false) && !isSessionTerminal;
  const isBusy = status !== "AWAITING_USER";

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
    setIsAtBottom(atBottom);
  }, []);

  // Auto-scroll to bottom as new messages/tokens arrive ONLY if user was already at bottom
  useEffect(() => {
    if (isAtBottom) {
      scrollToBottom("smooth");
    }
  }, [messages, isAtBottom, scrollToBottom]);

  // When active thread changes, reset scroll pin to bottom
  useEffect(() => {
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
    if (!inputText.trim() || isBusy || !isOpen || sending) return;
    const textToSend = inputText;
    setInputText("");
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

  const renderStatusBadge = (st: AgentStatus) => {
    switch (st) {
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
            <span className={`thread-state-badge ${isOpen ? "state-open" : "state-closed"}`}>
              {isOpen ? "Active Open Thread" : "Closed Thread"}
            </span>
          </span>
        </div>

        <div className="chat-top-actions">
          {sessionStatus === "ACTIVE" && onKillSession && (
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
          {renderStatusBadge(status)}
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
                    setInputText("Plan a strategy for migrating a legacy Python codebase.")
                  }
                >
                  Plan legacy Python migration &rarr;
                </button>
                <button
                  type="button"
                  className="suggestion-pill"
                  onClick={() =>
                    setInputText("Put the iris dataset in your workspace. Dont use external libraries - either curl for it, or write it from memory.")
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
                onBranch={onBranchMessage}
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
        <div className="chat-error-banner">
          <AlertCircle className="size-4" />
          <span>{streamError}</span>
        </div>
      )}

      {!isOpen && !isSessionTerminal && (
        <div className="closed-thread-notice">
          <Clock className="size-4" />
          <span>This thread is closed. New messages cannot be sent to closed threads. Select the active open thread to continue.</span>
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
                    : isBusy
                      ? "Agent is busy processing... please wait."
                      : "Send a message to Seamus... (Enter to send, Shift+Enter for newline)"
            }
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!isOpen || isBusy || sending}
            rows={2}
            autoFocus
          />

          <button
            type="button"
            className="composer-send-btn"
            onClick={handleSend}
            disabled={!inputText.trim() || !isOpen || isBusy || sending}
            title={isBusy ? "Agent is busy" : "Send message (Enter)"}
          >
            {isBusy || sending ? (
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

