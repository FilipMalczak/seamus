import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import {
  AlertCircle,
  ArrowUp,
  Bot,
  Check,
  CheckCircle2,
  Clock,
  Loader2,
  Sparkles,
  Wrench,
} from "lucide-react";
import type { AgentStatus, ThreadInfo } from "../api/types";
import { useThreadStream } from "../hooks/useThreadStream";
import { MessageItem } from "./MessageItem";

interface ChatAreaProps {
  agentId: string | null;
  agentName: string | null;
  sessionId: string | null;
  sessionName: string | null;
  thread: ThreadInfo | null;
  onAcceptThread?: () => Promise<void>;
  onStatusChange?: (status: AgentStatus) => void;
}

export function ChatArea({
  agentId,
  agentName,
  sessionId,
  sessionName,
  thread,
  onAcceptThread,
  onStatusChange,
}: ChatAreaProps) {
  const [inputText, setInputText] = useState<string>("");
  const [accepting, setAccepting] = useState<boolean>(false);
  const viewportEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { messages, status, streamError, sending, sendMessage } =
    useThreadStream(agentId, sessionId, thread?.id ?? null);

  const isOpen = thread?.is_open ?? false;
  const isBusy = status !== "AWAITING_USER";

  // Notify parent of active thread status changes
  useEffect(() => {
    onStatusChange?.(status);
  }, [status, onStatusChange]);

  // Auto-scroll to bottom as new messages/tokens arrive
  useEffect(() => {
    viewportEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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
          {renderStatusBadge(status)}
          {onAcceptThread && (
            <button
              type="button"
              className={`btn-accept ${
                isOpen && !isBusy && !accepting
                  ? "btn-accept-active"
                  : "btn-accept-disabled"
              }`}
              onClick={async () => {
                if (!isOpen || isBusy || accepting) return;
                setAccepting(true);
                try {
                  await onAcceptThread();
                } finally {
                  setAccepting(false);
                }
              }}
              disabled={!isOpen || isBusy || accepting}
              title={
                !isOpen
                  ? "Thread is closed"
                  : isBusy
                  ? "Agent is currently busy"
                  : "Accept thread and sync to main"
              }
              aria-label="Accept thread"
            >
              {accepting ? (
                <Loader2 className="size-4 animate-spin text-emerald-400" />
              ) : (
                <Check className="size-4 text-emerald-400" />
              )}
            </button>
          )}
        </div>
      </div>

      <div className="chat-viewport">
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
                    setInputText("Explain how DeepAgent checkpointers work in memory.")
                  }
                >
                  DeepAgent in-memory checkpointers &rarr;
                </button>
              </div>
            </div>
          </div>
        ) : (
          messages.map((msg) => <MessageItem key={msg.id} message={msg} />)
        )}
        <div ref={viewportEndRef} />
      </div>

      {streamError && (
        <div className="chat-error-banner">
          <AlertCircle className="size-4" />
          <span>{streamError}</span>
        </div>
      )}

      {!isOpen && (
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
              !isOpen
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

