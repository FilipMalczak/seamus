import { useState, type KeyboardEvent } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Archive,
  Ban,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Flame,
  GitBranch,
  KeyRound,
  Loader2,
  MessageSquare,
  Pencil,
  Plus,
  Settings,
  Sparkles,
  Trash2,
  Wrench,
} from "lucide-react";
import type { AgentConfig, AgentStatus, SystemInfoResponse } from "../api/types";
import type { FullAgentNode } from "../hooks/useAgentsTree";

interface SidebarProps {
  style?: React.CSSProperties;
  agents: FullAgentNode[];
  selectedAgentId: string | null;
  selectedSessionId: string | null;
  selectedThreadId: string | null;
  activeStatus?: AgentStatus;
  systemInfo?: SystemInfoResponse | null;
  onSelectAgent?: (agentId: string) => void;
  onSelectSession?: (agentId: string, sessionId: string) => void;
  onSelectThread: (agentId: string, sessionId: string, threadId: string) => void;
  onCreateAgent: (name?: string | null) => Promise<any>;
  onCreateSession: (agentId: string, name?: string | null) => Promise<any>;
  onUpdateAgentName: (agentId: string, newName: string | null) => Promise<void>;
  onUpdateSessionName: (agentId: string, sessionId: string, newName: string | null) => Promise<void>;
  onUpdateThreadName: (agentId: string, sessionId: string, threadId: string, newName: string | null) => Promise<void>;
  onUpdateAgentConfig?: (agentId: string, config: AgentConfig) => Promise<void>;
  onUpdateSessionConfig?: (agentId: string, sessionId: string, config: AgentConfig) => Promise<void>;
  onEditConfig: (title: string, config: AgentConfig, onSave: (cfg: AgentConfig) => Promise<void>) => void;
  enableDelete?: boolean;
  onArchiveAgent?: (agentId: string) => Promise<void>;
  onDeleteAgent?: (agentId: string) => Promise<void>;
  onArchiveSession?: (agentId: string, sessionId: string) => Promise<void>;
  onDeleteSession?: (agentId: string, sessionId: string) => Promise<void>;
}

export function Sidebar({
  style,
  agents,
  selectedAgentId,
  selectedSessionId,
  selectedThreadId,
  activeStatus,
  systemInfo,
  onSelectAgent,
  onSelectSession,
  onSelectThread,
  onCreateAgent,
  onCreateSession,
  onUpdateAgentName,
  onUpdateSessionName,
  onUpdateThreadName,
  onUpdateAgentConfig,
  onUpdateSessionConfig,
  onEditConfig,
  enableDelete,
  onArchiveAgent,
  onDeleteAgent,
  onArchiveSession,
  onDeleteSession,
}: SidebarProps) {
  const [expandedAgents, setExpandedAgents] = useState<Record<string, boolean>>({});
  const [expandedSessions, setExpandedSessions] = useState<Record<string, boolean>>({});

  // Inline editing state
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState<string>("");

  // Confirmation dialog state
  interface ConfirmDialogState {
    title: string;
    message: string;
    warning?: string;
    confirmLabel: string;
    isDestructive?: boolean;
    onConfirm: () => Promise<void>;
  }
  const [confirmDialog, setConfirmDialog] = useState<ConfirmDialogState | null>(null);
  const [isActionPending, setIsActionPending] = useState(false);

  const promptArchiveAgent = (agent: FullAgentNode) => {
    const agentDisplay = agent.name && agent.name.trim() !== "" ? agent.name : agent.id;
    const hasRunningSession = Object.values(agent.sessionsMap || {}).some((s) =>
      s.threads?.some((t) => t.is_open && t.status !== "AWAITING_USER")
    );
    setConfirmDialog({
      title: "Archive Agent",
      message: `Archive agent "${agentDisplay}"? Its Gitea organization will be renamed to "archived-agent-..." and hidden from the navigation tree.`,
      warning: hasRunningSession
        ? "One or more sessions are currently running and will be terminated before archiving."
        : undefined,
      confirmLabel: "Archive",
      onConfirm: async () => {
        if (onArchiveAgent) await onArchiveAgent(agent.id);
      },
    });
  };

  const promptDeleteAgent = (agent: FullAgentNode) => {
    const agentDisplay = agent.name && agent.name.trim() !== "" ? agent.name : agent.id;
    const hasRunningSession = Object.values(agent.sessionsMap || {}).some((s) =>
      s.threads?.some((t) => t.is_open && t.status !== "AWAITING_USER")
    );
    setConfirmDialog({
      title: "Delete Agent",
      message: `Permanently delete agent "${agentDisplay}"? All repositories in its Gitea organization and local files will be permanently deleted. This cannot be undone.`,
      warning: hasRunningSession
        ? "One or more sessions are currently running and will be terminated."
        : undefined,
      confirmLabel: "Delete Permanently",
      isDestructive: true,
      onConfirm: async () => {
        if (onDeleteAgent) await onDeleteAgent(agent.id);
      },
    });
  };

  const promptArchiveSession = (agentId: string, session: any) => {
    const sessionDisplay =
      session.name && session.name.trim() !== "" ? session.name : session.id;
    const openThread = session.threads?.find((t: any) => t.is_open);
    const isRunning = openThread && openThread.status !== "AWAITING_USER";
    setConfirmDialog({
      title: "Archive Session",
      message: `Archive session "${sessionDisplay}"? Its repository and external mount forks will be archived in Gitea and hidden from the navigation tree.`,
      warning: isRunning
        ? "This session is currently running. Proceeding will terminate the active execution before archiving."
        : undefined,
      confirmLabel: "Archive",
      onConfirm: async () => {
        if (onArchiveSession) await onArchiveSession(agentId, session.id);
      },
    });
  };

  const promptDeleteSession = (agentId: string, session: any) => {
    const sessionDisplay =
      session.name && session.name.trim() !== "" ? session.name : session.id;
    const openThread = session.threads?.find((t: any) => t.is_open);
    const isRunning = openThread && openThread.status !== "AWAITING_USER";
    setConfirmDialog({
      title: "Delete Session",
      message: `Permanently delete session "${sessionDisplay}"? Its repository and external mount forks will be permanently deleted. This cannot be undone.`,
      warning: isRunning
        ? "This session is currently running. Proceeding will terminate the active execution."
        : undefined,
      confirmLabel: "Delete Permanently",
      isDestructive: true,
      onConfirm: async () => {
        if (onDeleteSession) await onDeleteSession(agentId, session.id);
      },
    });
  };

  const toggleAgent = (agentId: string) => {
    setExpandedAgents((prev) => ({
      ...prev,
      [agentId]: prev[agentId] === undefined ? false : !prev[agentId],
    }));
  };

  const toggleSession = (sessionId: string) => {
    setExpandedSessions((prev) => ({
      ...prev,
      [sessionId]: prev[sessionId] === undefined ? false : !prev[sessionId],
    }));
  };

  const handleCreateAgent = async () => {
    await onCreateAgent(null);
  };

  const handleCreateSession = async (agentId: string) => {
    await onCreateSession(agentId, null);
  };

  const startEditing = (key: string, currentName: string | null) => {
    setEditingKey(key);
    setEditingValue(currentName || "");
  };

  const handleSaveAgent = async (agentId: string) => {
    const trimmed = editingValue.trim();
    await onUpdateAgentName(agentId, trimmed || null);
    setEditingKey(null);
  };

  const handleSaveSession = async (agentId: string, sessionId: string) => {
    const trimmed = editingValue.trim();
    await onUpdateSessionName(agentId, sessionId, trimmed || null);
    setEditingKey(null);
  };

  const handleSaveThread = async (
    agentId: string,
    sessionId: string,
    threadId: string
  ) => {
    const trimmed = editingValue.trim();
    await onUpdateThreadName(agentId, sessionId, threadId, trimmed || null);
    setEditingKey(null);
  };

  const handleKeyDown = (
    e: KeyboardEvent<HTMLInputElement>,
    onSave: () => void
  ) => {
    if (e.key === "Enter") {
      e.stopPropagation();
      e.preventDefault();
      onSave();
    } else if (e.key === "Escape") {
      e.stopPropagation();
      e.preventDefault();
      setEditingKey(null);
    }
  };

  const renderSessionStatusIcon = (st: AgentStatus) => {
    switch (st) {
      case "AWAITING_USER":
        return <CheckCircle2 size={13} className="status-icon-ready" />;
      case "AWAITING_LLM":
        return <Loader2 size={13} className="status-icon-thinking animate-spin" />;
      case "EXECUTING_TOOL":
        return <Wrench size={13} className="status-icon-tool animate-pulse" />;
      case "ERROR":
        return <AlertCircle size={13} className="status-icon-error" />;
      default:
        return null;
    }
  };

  const formatStatusLabel = (st: AgentStatus) => {
    switch (st) {
      case "AWAITING_USER":
        return "Ready";
      case "AWAITING_LLM":
        return "Thinking...";
      case "EXECUTING_TOOL":
        return "Executing Tool...";
      case "ERROR":
        return "Error";
      default:
        return st;
    }
  };

  // Active agent and session Gitea branch resolution
  const activeAgentId =
    selectedAgentId ||
    (selectedSessionId
      ? agents.find((a) =>
          Boolean(a.sessionsMap && a.sessionsMap[selectedSessionId])
        )?.id
      : null);

  const activeAgentHex = activeAgentId ? activeAgentId.replace(/-/g, "") : "";

  const agentBranchUrl =
    systemInfo?.gitea?.enabled && systemInfo.gitea.url && activeAgentId
      ? `${systemInfo.gitea.url}/agent-${activeAgentHex}/agent/src/branch/main`
      : null;

  const sessionBranchUrl =
    systemInfo?.gitea?.enabled &&
    systemInfo.gitea.url &&
    activeAgentId &&
    selectedSessionId
      ? `${systemInfo.gitea.url}/agent-${activeAgentHex}/session-${selectedSessionId}/src/branch/main`
      : null;

  return (
    <aside className="sidebar-container" style={style}>
      <div className="sidebar-header">
        <div className="sidebar-title">
          <span>Agent Tree</span>
          <span className="badge-count">{agents.length}</span>
        </div>
        <button
          type="button"
          className="btn-create-agent"
          onClick={handleCreateAgent}
          title="Create a new agent"
        >
          <Plus className="size-4" />
          <span>New Agent</span>
        </button>
      </div>

      <div className="sidebar-tree">
        {agents.length === 0 ? (
          <div className="tree-empty">
            <p>No agents created yet.</p>
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={handleCreateAgent}
            >
              <Plus className="size-3.5" />
              <span>Create First Agent</span>
            </button>
          </div>
        ) : (
          agents.map((agent) => {
            const isAgentExpanded = expandedAgents[agent.id] ?? true;
            const sessions = Object.values(agent.sessionsMap || {});
            const isAgentSelected = agent.id === selectedAgentId;
            const isEditingAgent = editingKey === `agent:${agent.id}`;
            // If name is set and not empty, use it; otherwise display the full UUID
            const agentDisplay =
              agent.name && agent.name.trim() !== "" ? agent.name : agent.id;

            return (
              <div key={agent.id} className="tree-agent-group">
                <div
                  className={`tree-node tree-agent-node ${isAgentSelected ? "selected-agent" : ""}`}
                  onClick={() => {
                    if (!isEditingAgent && onSelectAgent) {
                      onSelectAgent(agent.id);
                    }
                  }}
                >
                  <button
                    type="button"
                    className="tree-expand-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleAgent(agent.id);
                    }}
                    title={isAgentExpanded ? "Collapse" : "Expand"}
                  >
                    {isAgentExpanded ? (
                      <ChevronDown className="size-3.5" />
                    ) : (
                      <ChevronRight className="size-3.5" />
                    )}
                  </button>

                  <Bot className="size-4 text-sky-400 node-icon" />

                  {isEditingAgent ? (
                    <input
                      type="text"
                      className="inline-edit-input"
                      value={editingValue}
                      onChange={(e) => setEditingValue(e.target.value)}
                      onKeyDown={(e) => handleKeyDown(e, () => handleSaveAgent(agent.id))}
                      onClick={(e) => e.stopPropagation()}
                      autoFocus
                      placeholder={agent.id}
                    />
                  ) : (
                    <span className="node-label" title={`Agent: ${agentDisplay}`}>
                      {agentDisplay}
                    </span>
                  )}

                  <div className="node-actions">
                    <button
                      type="button"
                      className="icon-action-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (isEditingAgent) {
                          handleSaveAgent(agent.id);
                        } else {
                          startEditing(`agent:${agent.id}`, agent.name);
                        }
                      }}
                      title={isEditingAgent ? "Accept Name" : "Edit Agent Name"}
                    >
                      {isEditingAgent ? (
                        <Check className="size-3 text-emerald-400" />
                      ) : (
                        <Pencil className="size-3" />
                      )}
                    </button>
                    <button
                      type="button"
                      className="icon-action-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        promptArchiveAgent(agent);
                      }}
                      title="Archive Agent"
                    >
                      <Archive className="size-3" />
                    </button>
                    {enableDelete && (
                      <button
                        type="button"
                        className="icon-action-btn text-rose-400 hover:text-rose-300"
                        onClick={(e) => {
                          e.stopPropagation();
                          promptDeleteAgent(agent);
                        }}
                        title="Delete Agent"
                      >
                        <Trash2 className="size-3" />
                      </button>
                    )}
                    <button
                      type="button"
                      className="icon-action-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCreateSession(agent.id);
                      }}
                      title="New Session"
                    >
                      <Plus className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      className="icon-action-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        onEditConfig(
                          `Agent Config (${agentDisplay})`,
                          agent.config,
                          async (updated) => {
                            if (onUpdateAgentConfig) {
                              await onUpdateAgentConfig(agent.id, updated);
                            }
                          }
                        );
                      }}
                      title="View / Edit Agent Config"
                    >
                      <Settings className="size-3.5" />
                    </button>
                  </div>
                </div>

                {isAgentExpanded && (
                  <div className="tree-sessions-container">
                    {sessions.length === 0 ? (
                      <div className="tree-sub-empty">
                        <span>No sessions yet.</span>
                        <button
                          type="button"
                          className="link-btn"
                          onClick={() => handleCreateSession(agent.id)}
                        >
                          + Add session
                        </button>
                      </div>
                    ) : (
                      sessions.map((session) => {
                        const isSessionExpanded = expandedSessions[session.id] ?? true;
                        const isSessionSelected =
                          session.id === selectedSessionId && selectedThreadId === null;
                        const isSessionParentOfSelectedThread =
                          session.id === selectedSessionId && selectedThreadId !== null;
                        const threads = session.threads || [];
                        const openThread =
                          threads.find((t) => t.is_open) || threads[0];
                        const sessionStatus: AgentStatus =
                          session.id === selectedSessionId && activeStatus
                            ? activeStatus
                            : openThread?.status || "AWAITING_USER";
                        const isEditingSession =
                          editingKey === `session:${session.id}`;
                        // If name is set and not empty, use it; otherwise display the full UUID
                        const sessionDisplay =
                          session.name && session.name.trim() !== ""
                            ? session.name
                            : session.id;

                        return (
                          <div key={session.id} className="tree-session-group">
                            <div
                              className={`tree-node tree-session-node ${
                                isSessionSelected ? "selected-session" : ""
                              } ${isSessionParentOfSelectedThread ? "session-active-parent" : ""}`}
                              onClick={() => {
                                if (!isEditingSession && onSelectSession) {
                                  onSelectSession(agent.id, session.id);
                                }
                              }}
                            >
                              <button
                                type="button"
                                className="tree-expand-btn"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  toggleSession(session.id);
                                }}
                              >
                                {isSessionExpanded ? (
                                  <ChevronDown className="size-3" />
                                ) : (
                                  <ChevronRight className="size-3" />
                                )}
                              </button>

                              <MessageSquare className="size-3.5 text-indigo-400 node-icon" />

                              {isEditingSession ? (
                                <input
                                  type="text"
                                  className="inline-edit-input"
                                  value={editingValue}
                                  onChange={(e) => setEditingValue(e.target.value)}
                                  onKeyDown={(e) =>
                                    handleKeyDown(e, () =>
                                      handleSaveSession(agent.id, session.id)
                                    )
                                  }
                                  onClick={(e) => e.stopPropagation()}
                                  autoFocus
                                  placeholder={session.id}
                                />
                              ) : (
                                <span
                                  className="node-label"
                                  title={`Session: ${sessionDisplay}`}
                                >
                                  {sessionDisplay}
                                </span>
                              )}

                              <span
                                className={`session-status-badge status-${session.status === "KILLED" ? "killed" : session.status === "FAILED" ? "failed" : sessionStatus.toLowerCase().replace(/_/g, "-")}`}
                                title={`Session Status: ${session.status === "KILLED" ? "Killed" : session.status === "FAILED" ? "Failed" : formatStatusLabel(sessionStatus)}`}
                              >
                                {session.status === "KILLED" ? (
                                  <Ban size={13} className="text-zinc-400" />
                                ) : session.status === "FAILED" ? (
                                  <AlertTriangle size={13} className="text-rose-400" />
                                ) : (
                                  renderSessionStatusIcon(sessionStatus)
                                )}
                              </span>

                              <div className="node-actions">
                                <button
                                  type="button"
                                  className="icon-action-btn"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (isEditingSession) {
                                      handleSaveSession(agent.id, session.id);
                                    } else {
                                      startEditing(`session:${session.id}`, session.name);
                                    }
                                  }}
                                  title={isEditingSession ? "Accept Name" : "Edit Session Name"}
                                >
                                  {isEditingSession ? (
                                    <Check className="size-3 text-emerald-400" />
                                  ) : (
                                    <Pencil className="size-3" />
                                  )}
                                </button>
                                <button
                                  type="button"
                                  className="icon-action-btn"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    promptArchiveSession(agent.id, session);
                                  }}
                                  title="Archive Session"
                                >
                                  <Archive className="size-3" />
                                </button>
                                {enableDelete && (
                                  <button
                                    type="button"
                                    className="icon-action-btn text-rose-400 hover:text-rose-300"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      promptDeleteSession(agent.id, session);
                                    }}
                                    title="Delete Session"
                                  >
                                    <Trash2 className="size-3" />
                                  </button>
                                )}
                                <button
                                  type="button"
                                  className="icon-action-btn"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onEditConfig(
                                      `Session Config (${sessionDisplay})`,
                                      session.config,
                                      async (updated) => {
                                        if (onUpdateSessionConfig) {
                                          await onUpdateSessionConfig(agent.id, session.id, updated);
                                        }
                                      }
                                    );
                                  }}
                                  title="View / Edit Session Config"
                                >
                                  <Settings className="size-3.5" />
                                </button>
                              </div>
                            </div>

                            {isSessionExpanded && (
                              <div className="tree-threads-container">
                                {threads.length === 0 ? (
                                  <div className="tree-sub-empty">No threads.</div>
                                ) : (
                                  threads.map((thread) => {
                                    const isThreadSelected =
                                      thread.id === selectedThreadId;
                                    const isEditingThread =
                                      editingKey === `thread:${thread.id}`;
                                    // If name is set and not empty, use it; otherwise display the full UUID
                                    const threadDisplay =
                                      thread.name && thread.name.trim() !== ""
                                        ? thread.name
                                        : thread.id;
                                    const modeLabel =
                                      thread.mode_label ||
                                      (thread.phase
                                        ? `${thread.mode || "chat"}/${thread.phase}`
                                        : thread.mode || "chat");

                                    return (
                                      <div
                                        key={thread.id}
                                        className={`tree-node tree-thread-node ${
                                          isThreadSelected
                                            ? "selected-thread"
                                            : ""
                                        }`}
                                      >
                                        <button
                                          type="button"
                                          className="thread-left-btn"
                                          onClick={() => {
                                            if (!isEditingThread) {
                                              onSelectThread(
                                                agent.id,
                                                session.id,
                                                thread.id
                                              );
                                            }
                                          }}
                                          title={`Thread: ${threadDisplay} (${
                                            thread.is_open ? "Open" : "Closed"
                                          })`}
                                        >
                                          <span
                                            className={`thread-dot ${
                                              thread.is_open
                                                ? "dot-open"
                                                : "dot-closed"
                                            }`}
                                          />
                                          <Sparkles className="size-3 text-sky-400 shrink-0" />
                                          <span
                                            className={`badge-mode badge-mode-${thread.mode || "chat"}`}
                                            title={`Thread Mode: ${modeLabel}`}
                                          >
                                            {modeLabel}
                                          </span>
                                          {isEditingThread ? (
                                            <input
                                              type="text"
                                              className="inline-edit-input"
                                              value={editingValue}
                                              onChange={(e) =>
                                                setEditingValue(e.target.value)
                                              }
                                              onKeyDown={(e) =>
                                                handleKeyDown(e, () =>
                                                  handleSaveThread(
                                                    agent.id,
                                                    session.id,
                                                    thread.id
                                                  )
                                                )
                                              }
                                              onClick={(e) => e.stopPropagation()}
                                              autoFocus
                                              placeholder={thread.id}
                                            />
                                          ) : (
                                            <span className="thread-name">
                                              {threadDisplay}
                                            </span>
                                          )}
                                        </button>

                                        <div className="thread-right-actions">
                                          <button
                                            type="button"
                                            className="icon-action-btn"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              if (isEditingThread) {
                                                handleSaveThread(
                                                  agent.id,
                                                  session.id,
                                                  thread.id
                                                );
                                              } else {
                                                startEditing(
                                                  `thread:${thread.id}`,
                                                  thread.name
                                                );
                                              }
                                            }}
                                            title={isEditingThread ? "Accept Name" : "Edit Thread Name"}
                                          >
                                            {isEditingThread ? (
                                              <Check className="size-2.5 text-emerald-400" />
                                            ) : (
                                              <Pencil className="size-2.5" />
                                            )}
                                          </button>
                                          <span
                                            className={`badge-status ${
                                              thread.is_open
                                                ? "badge-open"
                                                : "badge-closed"
                                            }`}
                                          >
                                            {thread.is_open ? "Open" : "Closed"}
                                          </span>
                                        </div>
                                      </div>
                                    );
                                  })
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {(systemInfo?.logfire?.enabled ||
        systemInfo?.gitea?.enabled ||
        systemInfo?.vault?.enabled) && (
        <div className="sidebar-footer">
          <div className="system-links-row">
            {systemInfo?.logfire?.enabled && (
              <a
                href={
                  systemInfo.logfire.url ||
                  (systemInfo.logfire.service_name
                    ? `https://logfire.pydantic.dev`
                    : "#")
                }
                target="_blank"
                rel="noopener noreferrer"
                className="system-link-icon system-link-logfire"
                title={`Open Logfire Dashboard (${systemInfo.logfire.service_name || "seamus"})`}
                aria-label="Open Logfire Dashboard"
              >
                <Flame size={18} />
              </a>
            )}
            {systemInfo?.vault?.enabled &&
              (systemInfo.vault.login_url || systemInfo.vault.url) && (
                <a
                  href={
                    systemInfo.vault.login_url ||
                    `${systemInfo.vault.url?.replace(/\/$/, "")}/ui/vault/auth?with=token`
                  }
                  target="_blank"
                  rel="noopener noreferrer"
                  className="system-link-icon system-link-vault"
                  title={`Open OpenBao Login via Token (${
                    systemInfo.vault.login_url || systemInfo.vault.url
                  })`}
                  aria-label="Open OpenBao Login via Token"
                >
                  <KeyRound size={18} />
                </a>
              )}
            {systemInfo?.gitea?.enabled && systemInfo.gitea.url && (
              <>
                <a
                  href={systemInfo.gitea.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="system-link-icon system-link-gitea"
                  title={`Open Gitea (${systemInfo.gitea.url})`}
                  aria-label="Open Gitea"
                >
                  <GitBranch size={18} />
                </a>

                {agentBranchUrl ? (
                  <a
                    href={agentBranchUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="system-link-icon system-link-gitea-agent"
                    title={`Open Agent Git Branch (main) on Gitea (${activeAgentId})`}
                    aria-label="Open Agent Git Branch on Gitea"
                  >
                    <span className="composite-icon-wrapper">
                      <Bot size={15} className="composite-base-icon text-sky-400" />
                      <span className="composite-badge">
                        <GitBranch size={8} />
                      </span>
                    </span>
                  </a>
                ) : (
                  <span
                    className="system-link-icon system-link-disabled"
                    title="Select an agent to open its Git branch"
                    aria-label="Agent Git Branch disabled (none selected)"
                  >
                    <span className="composite-icon-wrapper">
                      <Bot size={15} className="composite-base-icon text-sky-400" />
                      <span className="composite-badge">
                        <GitBranch size={8} />
                      </span>
                    </span>
                  </span>
                )}

                {sessionBranchUrl ? (
                  <a
                    href={sessionBranchUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="system-link-icon system-link-gitea-session"
                    title={`Open Session Git Branch on Gitea (${selectedSessionId})`}
                    aria-label="Open Session Git Branch on Gitea"
                  >
                    <span className="composite-icon-wrapper">
                      <MessageSquare size={14} className="composite-base-icon text-indigo-400" />
                      <span className="composite-badge">
                        <GitBranch size={8} />
                      </span>
                    </span>
                  </a>
                ) : (
                  <span
                    className="system-link-icon system-link-disabled"
                    title="Select a session to open its Git branch"
                    aria-label="Session Git Branch disabled (none selected)"
                  >
                    <span className="composite-icon-wrapper">
                      <MessageSquare size={14} className="composite-base-icon text-indigo-400" />
                      <span className="composite-badge">
                        <GitBranch size={8} />
                      </span>
                    </span>
                  </span>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {confirmDialog && (
        <div
          className="modal-backdrop"
          style={{ zIndex: 9999 }}
          onClick={() => !isActionPending && setConfirmDialog(null)}
        >
          <div
            className="modal-panel"
            style={{ maxWidth: "440px", padding: "16px 20px" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header" style={{ marginBottom: "12px", borderBottom: "none" }}>
              <div className="modal-title flex items-center gap-2">
                <AlertTriangle
                  className={`size-5 ${confirmDialog.isDestructive ? "text-rose-400" : "text-amber-400"}`}
                />
                <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>
                  {confirmDialog.title}
                </h3>
              </div>
            </div>
            <div className="modal-body" style={{ padding: 0, marginBottom: "16px" }}>
              <p style={{ margin: 0, fontSize: "13px", color: "var(--text-secondary, #aaa)", lineHeight: 1.5 }}>
                {confirmDialog.message}
              </p>
              {confirmDialog.warning && (
                <div
                  style={{
                    marginTop: "12px",
                    padding: "8px 12px",
                    borderRadius: "6px",
                    background: "rgba(245, 158, 11, 0.1)",
                    border: "1px solid rgba(245, 158, 11, 0.25)",
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "8px",
                    color: "#fbbf24",
                    fontSize: "12px",
                    lineHeight: 1.4,
                  }}
                >
                  <AlertCircle className="size-4 shrink-0 mt-0.5" />
                  <span>{confirmDialog.warning}</span>
                </div>
              )}
            </div>
            <div className="modal-footer" style={{ borderTop: "none", padding: 0, display: "flex", justifyContent: "flex-end", gap: "8px" }}>
              <button
                type="button"
                className="btn-secondary btn-sm"
                disabled={isActionPending}
                onClick={() => setConfirmDialog(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className={`btn-sm ${confirmDialog.isDestructive ? "btn-danger" : "btn-primary"}`}
                style={
                  confirmDialog.isDestructive
                    ? { background: "#dc2626", color: "#fff", borderColor: "#b91c1c" }
                    : undefined
                }
                disabled={isActionPending}
                onClick={async () => {
                  setIsActionPending(true);
                  try {
                    await confirmDialog.onConfirm();
                    setConfirmDialog(null);
                  } finally {
                    setIsActionPending(false);
                  }
                }}
              >
                {isActionPending ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  confirmDialog.confirmLabel
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
