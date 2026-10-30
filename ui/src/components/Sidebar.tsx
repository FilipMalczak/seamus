import { useState } from "react";
import {
  Bot,
  ChevronDown,
  ChevronRight,
  MessageSquare,
  Pencil,
  Plus,
  Settings,
  Sparkles,
} from "lucide-react";
import type { AgentConfig } from "../api/types";
import type { FullAgentNode } from "../hooks/useAgentsTree";

interface SidebarProps {
  agents: FullAgentNode[];
  selectedAgentId: string | null;
  selectedSessionId: string | null;
  selectedThreadId: string | null;
  onSelectThread: (agentId: string, sessionId: string, threadId: string) => void;
  onCreateAgent: (name?: string | null) => Promise<any>;
  onCreateSession: (agentId: string, name?: string | null) => Promise<any>;
  onCreateThread: (agentId: string, sessionId: string, name?: string | null) => Promise<any>;
  onUpdateAgentName: (agentId: string, newName: string | null) => Promise<void>;
  onUpdateSessionName: (agentId: string, sessionId: string, newName: string | null) => Promise<void>;
  onUpdateThreadName: (agentId: string, sessionId: string, threadId: string, newName: string | null) => Promise<void>;
  onEditConfig: (title: string, config: AgentConfig, onSave: (cfg: AgentConfig) => Promise<void>) => void;
}

export function Sidebar({
  agents,
  selectedAgentId,
  selectedSessionId,
  selectedThreadId,
  onSelectThread,
  onCreateAgent,
  onCreateSession,
  onCreateThread,
  onUpdateAgentName,
  onUpdateSessionName,
  onUpdateThreadName,
  onEditConfig,
}: SidebarProps) {
  const [expandedAgents, setExpandedAgents] = useState<Record<string, boolean>>({});
  const [expandedSessions, setExpandedSessions] = useState<Record<string, boolean>>({});

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

  const handleCreateThread = async (agentId: string, sessionId: string) => {
    await onCreateThread(agentId, sessionId, null);
  };

  const handleEditAgentName = async (agentId: string, currentName: string | null) => {
    const entered = window.prompt(
      "Edit agent name (leave empty to remove name and use UUID):",
      currentName || ""
    );
    if (entered !== null) {
      await onUpdateAgentName(agentId, entered.trim() || null);
    }
  };

  const handleEditSessionName = async (
    agentId: string,
    sessionId: string,
    currentName: string | null
  ) => {
    const entered = window.prompt(
      "Edit session name (leave empty to remove name and use UUID):",
      currentName || ""
    );
    if (entered !== null) {
      await onUpdateSessionName(agentId, sessionId, entered.trim() || null);
    }
  };

  const handleEditThreadName = async (
    agentId: string,
    sessionId: string,
    threadId: string,
    currentName: string | null
  ) => {
    const entered = window.prompt(
      "Edit thread name (leave empty to remove name and use UUID):",
      currentName || ""
    );
    if (entered !== null) {
      await onUpdateThreadName(agentId, sessionId, threadId, entered.trim() || null);
    }
  };

  return (
    <aside className="sidebar-container">
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

                  <span className="node-label" title={`Agent: ${agentDisplay}`}>
                    {agentDisplay}
                  </span>

                  <div className="node-actions">
                    <button
                      type="button"
                      className="icon-action-btn"
                      onClick={() => handleEditAgentName(agent.id, agent.name)}
                      title="Edit Agent Name"
                    >
                      <Pencil className="size-3" />
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
                          async () => {}
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

                              <span
                                className="node-label"
                                title={`Session: ${sessionDisplay}`}
                              >
                                {sessionDisplay}
                              </span>

                              <div className="node-actions">
                                <button
                                  type="button"
                                  className="icon-action-btn"
                                  onClick={() =>
                                    handleEditSessionName(
                                      agent.id,
                                      session.id,
                                      session.name
                                    )
                                  }
                                  title="Edit Session Name"
                                >
                                  <Pencil className="size-3" />
                                </button>
                                <button
                                  type="button"
                                  className="icon-action-btn"
                                  onClick={() =>
                                    handleCreateThread(agent.id, session.id)
                                  }
                                  title="New Thread"
                                >
                                  <Plus className="size-3.5" />
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
                                          onClick={() =>
                                            onSelectThread(
                                              agent.id,
                                              session.id,
                                              thread.id
                                            )
                                          }
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
                                          <span className="thread-name">
                                            {threadDisplay}
                                          </span>
                                        </button>

                                        <div className="thread-right-actions">
                                          <button
                                            type="button"
                                            className="icon-action-btn"
                                            onClick={() =>
                                              handleEditThreadName(
                                                agent.id,
                                                session.id,
                                                thread.id,
                                                thread.name
                                              )
                                            }
                                            title="Edit Thread Name"
                                          >
                                            <Pencil className="size-2.5" />
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
    </aside>
  );
}
