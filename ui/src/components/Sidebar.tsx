import { useState } from "react";
import {
  Bot,
  ChevronDown,
  ChevronRight,
  MessageSquare,
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

  const handlePromptNewAgent = async () => {
    const name = window.prompt("Enter new agent name/slug (optional, e.g. code-reviewer):");
    if (name !== null) {
      await onCreateAgent(name.trim() || null);
    }
  };

  const handlePromptNewSession = async (agentId: string) => {
    const name = window.prompt("Enter new session name/slug (optional, e.g. refactor-auth):");
    if (name !== null) {
      await onCreateSession(agentId, name.trim() || null);
    }
  };

  const handlePromptNewThread = async (agentId: string, sessionId: string) => {
    const name = window.prompt("Enter new thread name/slug (optional, e.g. initial-run):");
    if (name !== null) {
      await onCreateThread(agentId, sessionId, name.trim() || null);
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
          onClick={handlePromptNewAgent}
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
              onClick={handlePromptNewAgent}
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

                  <span className="node-label" title={agent.name || agent.id}>
                    {agent.name || `${agent.id.slice(0, 8)}...`}
                  </span>

                  <div className="node-actions">
                    <button
                      type="button"
                      className="icon-action-btn"
                      onClick={() => handlePromptNewSession(agent.id)}
                      title="New Session"
                    >
                      <Plus className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      className="icon-action-btn"
                      onClick={() =>
                        onEditConfig(
                          `Agent Config (${agent.name || agent.id.slice(0, 8)})`,
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
                          onClick={() => handlePromptNewSession(agent.id)}
                        >
                          + Add session
                        </button>
                      </div>
                    ) : (
                      sessions.map((session) => {
                        const isSessionExpanded = expandedSessions[session.id] ?? true;
                        const isSessionSelected = session.id === selectedSessionId;
                        const threads = session.threads || [];

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
                                title={session.name || session.id}
                              >
                                {session.name || `${session.id.slice(0, 8)}...`}
                              </span>

                              <div className="node-actions">
                                <button
                                  type="button"
                                  className="icon-action-btn"
                                  onClick={() =>
                                    handlePromptNewThread(agent.id, session.id)
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

                                    return (
                                      <button
                                        key={thread.id}
                                        type="button"
                                        className={`tree-node tree-thread-node ${
                                          isThreadSelected
                                            ? "selected-thread"
                                            : ""
                                        }`}
                                        onClick={() =>
                                          onSelectThread(
                                            agent.id,
                                            session.id,
                                            thread.id
                                          )
                                        }
                                        title={`Thread ${thread.name || thread.id} (${
                                          thread.is_open ? "Open" : "Closed"
                                        })`}
                                      >
                                        <div className="thread-left">
                                          <span
                                            className={`thread-dot ${
                                              thread.is_open
                                                ? "dot-open"
                                                : "dot-closed"
                                            }`}
                                            title={
                                              thread.is_open
                                                ? "Open thread"
                                                : "Closed thread"
                                            }
                                          />
                                          <Sparkles className="size-3 text-sky-400" />
                                          <span className="thread-name">
                                            {thread.name ||
                                              `${thread.id.slice(0, 8)}...`}
                                          </span>
                                        </div>

                                        <span
                                          className={`badge-status ${
                                            thread.is_open
                                              ? "badge-open"
                                              : "badge-closed"
                                          }`}
                                        >
                                          {thread.is_open ? "Open" : "Closed"}
                                        </span>
                                      </button>
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

