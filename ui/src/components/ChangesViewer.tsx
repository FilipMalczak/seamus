import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  GitPullRequest,
  Loader2,
  RefreshCw,
  Split,
  Square,
} from "lucide-react";
import { parsePatchFiles, type FileDiffMetadata } from "@pierre/diffs";
import { FileDiff } from "@pierre/diffs/react";
import { getSessionDiff } from "../api/client";
import type { AgentStatus, SessionDiffResponse, ThreadInfo } from "../api/types";

interface ChangesViewerProps {
  agentId: string | null;
  agentName: string | null;
  sessionId: string | null;
  sessionName: string | null;
  thread: ThreadInfo | null;
  agentStatus?: AgentStatus;
  onAcceptThread?: () => Promise<void>;
}

export function ChangesViewer({
  agentId,
  agentName,
  sessionId,
  sessionName,
  thread,
  agentStatus,
  onAcceptThread,
}: ChangesViewerProps) {
  const [diffData, setDiffData] = useState<SessionDiffResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [accepting, setAccepting] = useState<boolean>(false);
  const [diffStyle, setDiffStyle] = useState<"unified" | "split">("unified");
  const [expandedFiles, setExpandedFiles] = useState<Record<string, boolean>>({});

  const toggleFile = (fileName: string) => {
    setExpandedFiles((prev) => ({
      ...prev,
      [fileName]: !prev[fileName],
    }));
  };

  const isOpen = thread?.is_open ?? false;
  // Consider agent busy if status is provided and not AWAITING_USER, or thread status is not AWAITING_USER
  const currentStatus = agentStatus ?? thread?.status ?? "AWAITING_USER";
  const isBusy = currentStatus !== "AWAITING_USER";

  const fetchDiff = useCallback(async () => {
    if (!agentId || !sessionId) {
      setDiffData(null);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await getSessionDiff(agentId, sessionId);
      setDiffData(data);
    } catch (err: any) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [agentId, sessionId]);

  useEffect(() => {
    void fetchDiff();
  }, [fetchDiff]);

  const handleAccept = async () => {
    if (!isOpen || isBusy || accepting || !onAcceptThread) return;
    setAccepting(true);
    try {
      await onAcceptThread();
      await fetchDiff();
    } catch (err: any) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAccepting(false);
    }
  };

  const fileDiffs = useMemo<FileDiffMetadata[]>(() => {
    if (!diffData?.diff || diffData.diff.trim().length === 0) return [];
    try {
      const patches = parsePatchFiles(diffData.diff);
      return patches.flatMap((p) => p.files);
    } catch (err) {
      console.error("Failed to parse diff patch:", err);
      return [];
    }
  }, [diffData?.diff]);

  const hasDiffContent = fileDiffs.length > 0;

  return (
    <div className="changes-viewer">
      {/* Changes Header */}
      <div className="changes-header">
        <div className="changes-header-left">
          <div className="changes-title-row">
            <GitPullRequest className="size-4 text-emerald-400" />
            <span className="changes-title">Changes</span>
            {diffData?.pr_number ? (
              diffData.pr_url ? (
                <a
                  href={diffData.pr_url}
                  target="_blank"
                  rel="noreferrer"
                  className="changes-pr-badge"
                  title="Open Sync PR in Gitea"
                >
                  <span>Sync PR #{diffData.pr_number}</span>
                  <ExternalLink className="size-3" />
                </a>
              ) : (
                <span className="changes-pr-badge">Sync PR #{diffData.pr_number}</span>
              )
            ) : (
              <span className="changes-pr-badge changes-pr-none">No active Sync PR</span>
            )}
          </div>
          {(agentName || sessionName) && (
            <div className="changes-subtitle">
              {agentName || agentId} / {sessionName || sessionId}
            </div>
          )}
        </div>

        <div className="changes-header-actions">
          {/* Style toggle */}
          <div className="changes-style-toggle">
            <button
              type="button"
              className={`changes-toggle-btn ${diffStyle === "unified" ? "active" : ""}`}
              onClick={() => setDiffStyle("unified")}
              title="Unified diff"
            >
              <Square className="size-3.5" />
              <span>Unified</span>
            </button>
            <button
              type="button"
              className={`changes-toggle-btn ${diffStyle === "split" ? "active" : ""}`}
              onClick={() => setDiffStyle("split")}
              title="Split (side-by-side) diff"
            >
              <Split className="size-3.5" />
              <span>Split</span>
            </button>
          </div>

          {/* Refresh button */}
          <button
            type="button"
            className="changes-action-btn"
            onClick={() => void fetchDiff()}
            disabled={loading}
            title="Refresh diff"
            aria-label="Refresh diff"
          >
            <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>

          {/* Accept Button */}
          {onAcceptThread && (
            <button
              type="button"
              className={`btn-accept ${
                isOpen && !isBusy && !accepting
                  ? "btn-accept-active"
                  : "btn-accept-disabled"
              }`}
              onClick={() => void handleAccept()}
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
              <span className="btn-accept-label">Accept</span>
            </button>
          )}
        </div>
      </div>

      {/* Changes Content Area */}
      <div className="changes-content">
        {!agentId || !sessionId ? (
          <div className="changes-empty-state">
            <p>Select a session to view sync PR changes.</p>
          </div>
        ) : loading && !diffData ? (
          <div className="changes-loading-state">
            <Loader2 className="size-6 animate-spin text-emerald-400" />
            <p>Fetching session changes from Sync PR...</p>
          </div>
        ) : error ? (
          <div className="changes-error-state">
            <AlertCircle className="size-6 text-rose-400" />
            <p className="changes-error-message">{error}</p>
            <button
              type="button"
              className="changes-retry-btn"
              onClick={() => void fetchDiff()}
            >
              Retry
            </button>
          </div>
        ) : !hasDiffContent ? (
          <div className="changes-empty-state">
            <GitPullRequest className="size-8 text-neutral-500 mb-2" />
            <h3>No Changes</h3>
            <p>The current session branch is up-to-date with main.</p>
          </div>
        ) : (
          <div className="changes-diff-viewport">
            <div className="changes-diff-summary">
              Showing {fileDiffs.length} changed file{fileDiffs.length === 1 ? "" : "s"}
            </div>
            {fileDiffs.map((fileDiff, idx) => {
              const fileName = fileDiff.name || `file-${idx}`;
              const lineCount =
                fileDiff.unifiedLineCount ??
                (fileDiff.additionLines?.length || 0) + (fileDiff.deletionLines?.length || 0);
              const isLarge = lineCount > 1000;
              const isExpanded = expandedFiles[fileName] ?? !isLarge;

              return (
                <div
                  key={`${fileName}-${idx}`}
                  className="changes-file-diff-item"
                >
                  {isLarge && (
                    <div className="changes-file-large-bar">
                      <div className="changes-file-large-info">
                        <span className="changes-file-large-name">{fileName}</span>
                        <span className="changes-file-large-badge">
                          Large diff ({lineCount.toLocaleString()} lines)
                        </span>
                      </div>
                      <button
                        type="button"
                        className="changes-file-toggle-btn"
                        onClick={() => toggleFile(fileName)}
                      >
                        {isExpanded ? (
                          <>
                            <ChevronDown className="size-3.5" />
                            <span>Collapse</span>
                          </>
                        ) : (
                          <>
                            <ChevronRight className="size-3.5" />
                            <span>Show diff</span>
                          </>
                        )}
                      </button>
                    </div>
                  )}
                  {isExpanded && (
                    <FileDiff
                      fileDiff={fileDiff}
                      options={{
                        diffStyle,
                        theme: "github-dark",
                      }}
                    />
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

