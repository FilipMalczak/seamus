import { useEffect, useState } from "react";
import {
  AlertCircle,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Code2,
  Copy,
  Cpu,
  ExternalLink,
  FileCode,
  FolderGit2,
  FolderOpen,
  Layers,
  Loader2,
  MessageSquare,
  RefreshCw,
  ShieldCheck,
  Terminal,
  Wrench,
  Zap,
} from "lucide-react";
import { getAgentInspection } from "../api/client";
import type { AgentInspectReport, AgentStatus, ToolInspectInfo } from "../api/types";
import { MarkdownRenderer } from "./MarkdownRenderer";

interface AgentInspectorProps {
  agentId: string | null;
  sessionId: string | null;
  threadId?: string | null;
  agentName?: string | null;
  sessionName?: string | null;
}

type SubTab = "prompt" | "tools" | "inference" | "messages" | "workspace";
type PromptLayer = "composite" | "scaffold" | "custom";

export function AgentInspector({
  agentId,
  sessionId,
  threadId,
  agentName,
  sessionName,
}: AgentInspectorProps) {
  const [report, setReport] = useState<AgentInspectReport | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [subTab, setSubTab] = useState<SubTab>("prompt");
  const [promptLayer, setPromptLayer] = useState<PromptLayer>("composite");
  const [copiedPrompt, setCopiedPrompt] = useState<boolean>(false);
  const [expandedTools, setExpandedTools] = useState<Record<string, boolean>>({});

  const fetchReport = async (isManualRefresh = false) => {
    if (!agentId || !sessionId) {
      setReport(null);
      return;
    }

    if (isManualRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const data = await getAgentInspection(agentId, sessionId, threadId);
      setReport(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load agent inspection report");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchReport();
  }, [agentId, sessionId, threadId]);

  const toggleToolExpand = (toolName: string) => {
    setExpandedTools((prev) => ({
      ...prev,
      [toolName]: !prev[toolName],
    }));
  };

  const handleCopyPrompt = async (text: string) => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setCopiedPrompt(true);
      setTimeout(() => setCopiedPrompt(false), 2000);
    } catch (err) {
      console.error("Failed to copy prompt to clipboard", err);
    }
  };

  const renderStatusPill = (st: AgentStatus) => {
    switch (st) {
      case "AWAITING_USER":
        return (
          <span className="status-pill status-ready">
            <CheckCircle2 className="size-3.5" />
            <span>Ready (Awaiting User)</span>
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

  if (!agentId || !sessionId) {
    return (
      <div className="inspector-empty-state">
        <Bot className="size-12 text-sky-400" />
        <h2>No Active Session Selected</h2>
        <p>Select an agent and session from the sidebar to inspect its prompt, tools, and runtime state.</p>
      </div>
    );
  }

  if (loading && !report) {
    return (
      <div className="inspector-loading-state">
        <Loader2 className="size-8 animate-spin text-sky-400" />
        <p>Inspecting DeepAgent runtime and Git state...</p>
      </div>
    );
  }

  if (error && !report) {
    return (
      <div className="inspector-error-state">
        <AlertCircle className="size-8 text-rose-400" />
        <h3>Failed to Inspect Agent</h3>
        <p>{error}</p>
        <button
          type="button"
          className="btn-secondary btn-sm"
          onClick={() => fetchReport(true)}
        >
          <RefreshCw className="size-3.5" />
          <span>Retry</span>
        </button>
      </div>
    );
  }

  if (!report) return null;

  const currentPromptText =
    promptLayer === "composite"
      ? report.prompts.composite
      : promptLayer === "scaffold"
      ? report.prompts.scaffold
      : report.prompts.custom || "*(No custom instructions specified)*";

  return (
    <div className="inspector-container">
      {/* Inspector Hero Header */}
      <div className="inspector-hero">
        <div className="inspector-hero-left">
          <div className="inspector-title-row">
            <h2 className="inspector-title">DeepAgent Inspector</h2>
            <span className="badge-semi-live">Latest Inference State</span>
            {renderStatusPill(report.status)}
          </div>

          <div className="inspector-meta-row">
            <span className="meta-item" title="Target Entity">
              <Bot className="size-3.5 text-sky-400" />
              <span className="meta-text">
                {report.agent_name || agentName || report.agent_id} /{" "}
                {report.session_name || sessionName || report.session_id}
              </span>
            </span>

            <span className="meta-sep">&bull;</span>

            <span className="meta-item" title="Model">
              <Zap className="size-3.5 text-amber-400" />
              <span className="meta-text">{report.inference.model_name}</span>
            </span>

            <span className="meta-sep">&bull;</span>

            <span className="meta-item" title="Git Branch">
              <FolderGit2 className="size-3.5 text-sky-400" />
              {report.git.gitea_url ? (
                <a
                  href={report.git.gitea_url}
                  target="_blank"
                  rel="noreferrer"
                  className="meta-link"
                  title="View branch on Gitea"
                >
                  <span>{report.git.branch}</span>
                  <ExternalLink className="size-3" />
                </a>
              ) : (
                <span className="meta-text">{report.git.branch}</span>
              )}
            </span>

            {report.git.commit_sha && (
              <>
                <span className="meta-sep">&bull;</span>
                <span
                  className="meta-item chip-commit"
                  title={`Latest Commit: ${report.git.commit_sha} - ${report.git.commit_message || ""}`}
                >
                  <Code2 className="size-3.5 text-emerald-400" />
                  <code>{report.git.commit_sha.slice(0, 7)}</code>
                </span>
              </>
            )}
          </div>
        </div>

        <div className="inspector-hero-right">
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={() => fetchReport(true)}
            disabled={refreshing}
            title="Refresh inspector report"
          >
            <RefreshCw className={`size-3.5 ${refreshing ? "animate-spin" : ""}`} />
            <span>{refreshing ? "Refreshing..." : "Refresh"}</span>
          </button>
        </div>
      </div>

      {/* Sub-Tabs Bar */}
      <div className="inspector-tabs-bar">
        <button
          type="button"
          className={`inspector-tab-btn ${subTab === "prompt" ? "active" : ""}`}
          onClick={() => setSubTab("prompt")}
        >
          <Layers className="size-4" />
          <span>System Prompt</span>
        </button>

        <button
          type="button"
          className={`inspector-tab-btn ${subTab === "tools" ? "active" : ""}`}
          onClick={() => setSubTab("tools")}
        >
          <Wrench className="size-4" />
          <span>Tools</span>
          <span className="tab-counter">{report.tools.length}</span>
        </button>

        <button
          type="button"
          className={`inspector-tab-btn ${subTab === "inference" ? "active" : ""}`}
          onClick={() => setSubTab("inference")}
        >
          <Cpu className="size-4" />
          <span>Inference & Runtime</span>
        </button>

        <button
          type="button"
          className={`inspector-tab-btn ${subTab === "messages" ? "active" : ""}`}
          onClick={() => setSubTab("messages")}
        >
          <MessageSquare className="size-4" />
          <span>Trajectory</span>
          <span className="tab-counter">{report.history.message_count}</span>
        </button>

        <button
          type="button"
          className={`inspector-tab-btn ${subTab === "workspace" ? "active" : ""}`}
          onClick={() => setSubTab("workspace")}
        >
          <FolderOpen className="size-4" />
          <span>Workspace Files</span>
          <span className="tab-counter">{report.workspace.files.length}</span>
        </button>
      </div>

      {/* Tab Contents */}
      <div className="inspector-tab-content">
        {/* TAB 1: SYSTEM PROMPT */}
        {subTab === "prompt" && (
          <div className="inspector-prompt-panel">
            <div className="prompt-toolbar">
              <div className="prompt-layer-pills">
                <button
                  type="button"
                  className={`layer-pill ${promptLayer === "composite" ? "active" : ""}`}
                  onClick={() => setPromptLayer("composite")}
                >
                  Composite (Effective Prompt)
                </button>
                <button
                  type="button"
                  className={`layer-pill ${promptLayer === "scaffold" ? "active" : ""}`}
                  onClick={() => setPromptLayer("scaffold")}
                >
                  Scaffold (OpenSandbox)
                </button>
                <button
                  type="button"
                  className={`layer-pill ${promptLayer === "custom" ? "active" : ""}`}
                  onClick={() => setPromptLayer("custom")}
                >
                  Custom Instructions
                </button>
              </div>

              <div className="prompt-actions">
                <span className="prompt-char-count">
                  {currentPromptText.length.toLocaleString()} characters
                </span>
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  onClick={() => handleCopyPrompt(currentPromptText)}
                >
                  {copiedPrompt ? (
                    <>
                      <Check className="size-3.5 text-emerald-400" />
                      <span>Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy className="size-3.5" />
                      <span>Copy Prompt</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            <div className="prompt-content-box">
              <MarkdownRenderer content={currentPromptText} variant="assistant" />
            </div>
          </div>
        )}

        {/* TAB 2: AVAILABLE TOOLS */}
        {subTab === "tools" && (
          <div className="inspector-tools-panel">
            <div className="tools-panel-header">
              <p className="tools-lead">
                The agent has access to <strong>{report.tools.length} active tools</strong> registered
                with the model. Operations targeting the filesystem or shell execute inside the
                isolated OpenSandbox container.
              </p>
            </div>

            <div className="tools-grid">
              {report.tools.map((tool: ToolInspectInfo) => {
                const isExpanded = !!expandedTools[tool.name];
                const paramKeys = Object.keys(tool.parameters?.properties || {});
                return (
                  <div key={tool.name} className="tool-inspect-card">
                    <div className="tool-card-header">
                      <div className="tool-card-title-group">
                        <Terminal className="size-4 text-sky-400" />
                        <h4 className="tool-name">{tool.name}</h4>
                        <span
                          className={`tool-backend-badge ${
                            tool.backend === "opensandbox" ? "backend-sandbox" : "backend-harness"
                          }`}
                        >
                          {tool.backend === "opensandbox" ? "OpenSandbox" : "Harness"}
                        </span>
                      </div>

                      <button
                        type="button"
                        className="btn-tool-toggle"
                        onClick={() => toggleToolExpand(tool.name)}
                      >
                        <span>{isExpanded ? "Hide Schema" : "View Schema"}</span>
                        {isExpanded ? (
                          <ChevronDown className="size-3.5" />
                        ) : (
                          <ChevronRight className="size-3.5" />
                        )}
                      </button>
                    </div>

                    <p className="tool-description">{tool.description}</p>

                    {paramKeys.length > 0 && (
                      <div className="tool-params-preview">
                        <span className="param-label">Arguments:</span>
                        <div className="param-pills">
                          {paramKeys.map((k) => {
                            const isReq = (tool.parameters.required as string[] | undefined)?.includes(k);
                            return (
                              <span key={k} className={`param-pill ${isReq ? "req" : ""}`}>
                                {k}
                                {isReq && <span className="req-star">*</span>}
                              </span>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {isExpanded && (
                      <div className="tool-schema-expanded">
                        <div className="schema-title-bar">
                          <span>JSON Parameter Schema</span>
                          <button
                            type="button"
                            className="btn-copy-small"
                            onClick={() =>
                              handleCopyPrompt(JSON.stringify(tool.parameters, null, 2))
                            }
                            title="Copy schema JSON"
                          >
                            <Copy className="size-3" />
                            <span>Copy</span>
                          </button>
                        </div>
                        <pre className="schema-code">
                          <code>{JSON.stringify(tool.parameters, null, 2)}</code>
                        </pre>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* TAB 3: INFERENCE & RUNTIME */}
        {subTab === "inference" && (
          <div className="inspector-inference-panel">
            <div className="inference-grid">
              <div className="inference-card">
                <div className="card-header">
                  <Zap className="size-4 text-amber-400" />
                  <h4>Language Model</h4>
                </div>
                <div className="card-body">
                  <div className="property-row">
                    <span className="prop-name">Model Identifier</span>
                    <span className="prop-val highlight">{report.inference.model_name}</span>
                  </div>
                  <div className="property-row">
                    <span className="prop-name">Provider Format</span>
                    <span className="prop-val">{report.inference.format}</span>
                  </div>
                  <div className="property-row">
                    <span className="prop-name">Base URL</span>
                    <span className="prop-val truncate" title={report.inference.base_url}>
                      {report.inference.base_url}
                    </span>
                  </div>
                  <div className="property-row">
                    <span className="prop-name">API Key Status</span>
                    <span className="prop-val">
                      {report.inference.api_key_configured ? (
                        <span className="badge-ok">
                          <ShieldCheck className="size-3.5 text-emerald-400" />
                          <span>Configured</span>
                        </span>
                      ) : (
                        <span className="badge-warn">
                          <AlertCircle className="size-3.5 text-amber-400" />
                          <span>Not Configured</span>
                        </span>
                      )}
                    </span>
                  </div>
                </div>
              </div>

              <div className="inference-card">
                <div className="card-header">
                  <FolderGit2 className="size-4 text-sky-400" />
                  <h4>Git & Storage Boundaries</h4>
                </div>
                <div className="card-body">
                  <div className="property-row">
                    <span className="prop-name">Gitea Repository</span>
                    <span className="prop-val">{report.git.repo_name}</span>
                  </div>
                  <div className="property-row">
                    <span className="prop-name">Active Session Branch</span>
                    <span className="prop-val highlight">{report.git.branch}</span>
                  </div>
                  <div className="property-row">
                    <span className="prop-name">Operational Directory</span>
                    <span className="prop-val code-pill">{report.workspace.operational_dir}</span>
                  </div>
                  <div className="property-row">
                    <span className="prop-name">Total Checkpoints</span>
                    <span className="prop-val">{report.history.checkpoint_step}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: MESSAGE TRAJECTORY */}
        {subTab === "messages" && (
          <div className="inspector-messages-panel">
            <div className="messages-panel-header">
              <p>
                Showing <strong>{report.history.messages.length} conversation turns</strong> in this
                session's active thread.
              </p>
            </div>

            {report.history.messages.length === 0 ? (
              <div className="messages-empty">
                <MessageSquare className="size-8 text-slate-500" />
                <p>No messages recorded for this thread yet.</p>
              </div>
            ) : (
              <div className="messages-list">
                {report.history.messages.map((msg, idx) => (
                  <div key={msg.id || idx} className={`message-inspect-item role-${msg.role}`}>
                    <div className="msg-header">
                      <span className={`role-badge role-${msg.role}`}>{msg.role}</span>
                      {msg.id && <code className="msg-id">{msg.id.slice(0, 8)}</code>}
                    </div>

                    {msg.content && (
                      <div className="msg-content">
                        <MarkdownRenderer content={msg.content} variant="assistant" />
                      </div>
                    )}

                    {msg.tool_calls && msg.tool_calls.length > 0 && (
                      <div className="msg-tool-calls">
                        <span className="tool-calls-title">Tool Invocations:</span>
                        {msg.tool_calls.map((tc, tcIdx) => (
                          <div key={tcIdx} className="msg-tool-call-box">
                            <div className="call-header">
                              <Wrench className="size-3.5 text-amber-400" />
                              <span className="call-name">{String(tc.name || "Tool Call")}</span>
                            </div>
                            <pre className="call-args">
                              <code>{JSON.stringify(tc.args || {}, null, 2)}</code>
                            </pre>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 5: WORKSPACE FILES */}
        {subTab === "workspace" && (
          <div className="inspector-workspace-panel">
            <div className="workspace-panel-header">
              <p>
                Files tracked under <code>{report.workspace.operational_dir}</code> (backed by Git{" "}
                <code>data/</code> on branch <code>{report.git.branch}</code>):
              </p>
            </div>

            {report.workspace.files.length === 0 ? (
              <div className="workspace-empty">
                <FolderOpen className="size-8 text-slate-500" />
                <p>No project files created in {report.workspace.operational_dir} yet.</p>
              </div>
            ) : (
              <ul className="workspace-files-list">
                {report.workspace.files.map((file) => (
                  <li key={file} className="workspace-file-item">
                    <FileCode className="size-4 text-sky-400" />
                    <span className="file-path">{file}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
