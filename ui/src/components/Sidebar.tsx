import { useState, type KeyboardEvent } from "react";
import {
  AlertCircle,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Flame,
  GitBranch,
  Loader2,
  MessageSquare,
  Pencil,
  Plus,
  Settings,
  Sparkles,
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
  onSelectThread: (agentId: string, sessionId: string, threadId: string) => void;
  onCreateAgent: (name?: string | null) => Promise<any>;
  onCreateSession: (agentId: string, name?: string | null) => Promise<any>;
  onUpdateAgentName: (agentId: string, newName: string | null) => Promise<void>;
  onUpdateSessionName: (agentId: string, sessionId: string, newName: string | null) => Promise<void>;
  onUpdateThreadName: (agentId: string, sessionId: string, threadId: string, newName: string | null) => Promise<void>;
  onUpdateAgentConfig?: (agentId: string, config: AgentConfig) => Promise<void>;
  onUpdateSessionConfig?: (agentId: string, sessionId: string, config: AgentConfig) => Promise<void>;
  onEditConfig: (title: string, config: AgentConfig, onSave: (cfg: AgentConfig) => Promise<void>) => void;
}

export function Sidebar({
  style,
  agents,
  selectedAgentId,
  selectedSessionId,
  selectedThreadId,
  activeStatus,
  systemInfo,
  onSelectThread,
  onCreateAgent,
  onCreateSession,
  onUpdateAgentName,
  onUpdateSessionName,
  onUpdateThreadName,
  onUpdateAgentConfig,
  onUpdateSessionConfig,
  onEditConfig,
}: SidebarProps) {
  const [expandedAgents, setExpandedAgents] = useState<Record<string, boolean>>({});
  const [expandedSessions, setExpandedSessions] = useState<Record<string, boolean>>({});

  // Inline editing state
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState<string>("");

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

  const giteaOwner = systemInfo?.gitea?.owner || "seamus";
  const agentBranchUrl =
    systemInfo?.gitea?.enabled && systemInfo.gitea.url && activeAgentId
      ? `${systemInfo.gitea.url}/${giteaOwner}/agent-${activeAgentId}/src/branch/main`
      : null;

  const sessionBranchUrl =
    systemInfo?.gitea?.enabled &&
    systemInfo.gitea.url &&
    activeAgentId &&
    selectedSessionId
      ? `${systemInfo.gitea.url}/${giteaOwner}/agent-${activeAgentId}/src/branch/session/${selectedSessionId}`
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
                >
                  <button
                    type="button"
                    className="tree-expand-btn"
                    onClick={() => toggleAgent(agent.id)}
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
                      onClick={() => handleCreateSession(agent.id)}
                      title="New Session"
                    >
                      <Plus className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      className="icon-action-btn"
                      onClick={() =>
                        onEditConfig(
                          `Agent Config (${agentDisplay})`,
                          agent.config,
                          async (updated) => {
                            if (onUpdateAgentConfig) {
                              await onUpdateAgentConfig(agent.id, updated);
                            }
                          }
                        )
                      }
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
                        const isSessionSelected = session.id === selectedSessionId;
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
                              }`}
                            >
                              <button
                                type="button"
                                className="tree-expand-btn"
                                onClick={() => toggleSession(session.id)}
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
                                className={`session-status-badge status-${sessionStatus.toLowerCase().replace(/_/g, "-")}`}
                                title={`Session Status: ${formatStatusLabel(sessionStatus)}`}
                              >
                                {renderSessionStatusIcon(sessionStatus)}
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
                                          <Sparkles className="size-3 text-sky-400" />
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

      {(systemInfo?.logfire?.enabled || systemInfo?.gitea?.enabled) && (
        <div className="sidebar-footer">
          <div className="system-links-row">
            {systemInfo?.logfire?.enabled && (
              <a
                href={`https://logfire-eu.pydantic.dev/filip-malczak/${systemInfo.logfire.service_name || "seamus"}`}
                target="_blank"
                rel="noopener noreferrer"
                className="system-link-icon system-link-logfire"
                title={`Open Logfire Dashboard (${systemInfo.logfire.service_name || "seamus"})`}
                aria-label="Open Logfire Dashboard"
              >
                <Flame size={18} />
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
    </aside>
  );
}
