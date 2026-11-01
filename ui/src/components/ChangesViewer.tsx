import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  Copy,
  ExternalLink,
  Folder,
  FolderOpen,
  FolderTree,
  GitPullRequest,
  List,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Search,
  Split,
  Square,
  X,
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

interface FileTreeNode {
  name: string;
  path: string;
  isDirectory: boolean;
  fileDiffIndex?: number;
  fileDiff?: FileDiffMetadata;
  children: FileTreeNode[];
}

function getFileStats(fileDiff: FileDiffMetadata): { additions: number; deletions: number } {
  let additions = 0;
  let deletions = 0;
  if (fileDiff.hunks && Array.isArray(fileDiff.hunks)) {
    for (const hunk of fileDiff.hunks) {
      additions += hunk.additionLines || 0;
      deletions += hunk.deletionLines || 0;
    }
  } else {
    additions = fileDiff.additionLines?.length || 0;
    deletions = fileDiff.deletionLines?.length || 0;
  }
  return { additions, deletions };
}

function getChangeStatus(type: string): { label: string; text: string; className: string } {
  switch (type) {
    case "new":
      return { label: "Added", text: "A", className: "status-added" };
    case "deleted":
      return { label: "Deleted", text: "D", className: "status-deleted" };
    case "rename-pure":
    case "rename-changed":
      return { label: "Renamed", text: "R", className: "status-renamed" };
    case "change":
    default:
      return { label: "Modified", text: "M", className: "status-modified" };
  }
}

interface IndexedFileDiff {
  fileDiff: FileDiffMetadata;
  originalIndex: number;
}

function buildFileTree(files: IndexedFileDiff[]): FileTreeNode {
  const root: FileTreeNode = {
    name: "root",
    path: "",
    isDirectory: true,
    children: [],
  };

  files.forEach(({ fileDiff, originalIndex }) => {
    const rawPath = fileDiff.name || `file-${originalIndex}`;
    const parts = rawPath.split("/").filter(Boolean);
    let current = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isFile = i === parts.length - 1;
      const currentPath = parts.slice(0, i + 1).join("/");

      let existing = current.children.find((child) => child.name === part);
      if (!existing) {
        existing = {
          name: part,
          path: currentPath,
          isDirectory: !isFile,
          fileDiffIndex: isFile ? originalIndex : undefined,
          fileDiff: isFile ? fileDiff : undefined,
          children: [],
        };
        current.children.push(existing);
      }
      current = existing;
    }
  });

  function sortNode(node: FileTreeNode) {
    node.children.sort((a, b) => {
      if (a.isDirectory && !b.isDirectory) return -1;
      if (!a.isDirectory && b.isDirectory) return 1;
      return a.name.localeCompare(b.name);
    });
    node.children.forEach(sortNode);
  }

  sortNode(root);
  return root;
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
  const [viewMode, setViewMode] = useState<"tree" | "list">("tree");
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(true);
  const [filterQuery, setFilterQuery] = useState<string>("");
  const [activeFileIndex, setActiveFileIndex] = useState<number | null>(null);
  const [expandedFiles, setExpandedFiles] = useState<Record<string, boolean>>({});
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({});
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  const isOpen = thread?.is_open ?? false;
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

  const indexedFileDiffs = useMemo<IndexedFileDiff[]>(() => {
    return fileDiffs.map((fileDiff, originalIndex) => ({
      fileDiff,
      originalIndex,
    }));
  }, [fileDiffs]);

  const filteredIndexedDiffs = useMemo(() => {
    if (!filterQuery.trim()) return indexedFileDiffs;
    const q = filterQuery.trim().toLowerCase();
    return indexedFileDiffs.filter((item) =>
      (item.fileDiff.name || "").toLowerCase().includes(q)
    );
  }, [indexedFileDiffs, filterQuery]);

  const fileTree = useMemo(
    () => buildFileTree(filteredIndexedDiffs),
    [filteredIndexedDiffs]
  );

  const totalStats = useMemo(() => {
    let additions = 0;
    let deletions = 0;
    for (const file of fileDiffs) {
      const stats = getFileStats(file);
      additions += stats.additions;
      deletions += stats.deletions;
    }
    return { additions, deletions };
  }, [fileDiffs]);

  const toggleFile = (fileName: string) => {
    setExpandedFiles((prev) => ({
      ...prev,
      [fileName]: !(prev[fileName] ?? true),
    }));
  };

  const toggleFolder = (folderPath: string) => {
    setExpandedFolders((prev) => ({
      ...prev,
      [folderPath]: !(prev[folderPath] ?? true),
    }));
  };

  const allFilesExpanded = useMemo(() => {
    if (fileDiffs.length === 0) return true;
    return fileDiffs.every((file, idx) => {
      const name = file.name || `file-${idx}`;
      return expandedFiles[name] ?? true;
    });
  }, [fileDiffs, expandedFiles]);

  const toggleAllFiles = () => {
    const nextState = !allFilesExpanded;
    const updated: Record<string, boolean> = {};
    fileDiffs.forEach((file, idx) => {
      const name = file.name || `file-${idx}`;
      updated[name] = nextState;
    });
    setExpandedFiles(updated);
  };

  const handleSelectFile = (index: number, fileName: string) => {
    setActiveFileIndex(index);
    // Ensure the selected file is expanded in the diff viewport
    setExpandedFiles((prev) => ({
      ...prev,
      [fileName]: true,
    }));
    const element = document.getElementById(`diff-file-${index}`);
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const handleCopyPath = async (path: string) => {
    try {
      await navigator.clipboard.writeText(path);
      setCopiedPath(path);
      setTimeout(() => setCopiedPath(null), 2000);
    } catch (err) {
      console.error("Failed to copy path:", err);
    }
  };

  const hasDiffContent = fileDiffs.length > 0;

  // Render recursive tree node
  const renderTreeNode = (node: FileTreeNode, level: number = 0): React.ReactNode => {
    if (node.isDirectory) {
      if (node.path === "") {
        // Root node
        return node.children.map((child) => renderTreeNode(child, level));
      }
      const isFolderOpen = expandedFolders[node.path] ?? true;
      return (
        <div key={node.path} className="changes-tree-dir-group">
          <div
            className="changes-tree-dir-row"
            style={{ paddingLeft: `${level * 14 + 10}px` }}
            onClick={() => toggleFolder(node.path)}
            role="button"
            tabIndex={0}
          >
            <span className="changes-tree-chevron">
              {isFolderOpen ? (
                <ChevronDown className="size-3 text-neutral-400" />
              ) : (
                <ChevronRight className="size-3 text-neutral-400" />
              )}
            </span>
            {isFolderOpen ? (
              <FolderOpen className="size-3.5 text-amber-400/90 shrink-0" />
            ) : (
              <Folder className="size-3.5 text-amber-400/90 shrink-0" />
            )}
            <span className="changes-tree-dir-name">{node.name}</span>
          </div>
          {isFolderOpen && (
            <div className="changes-tree-dir-children">
              {node.children.map((child) => renderTreeNode(child, level + 1))}
            </div>
          )}
        </div>
      );
    }

    // File node
    const fileDiff = node.fileDiff;
    const fileIdx = node.fileDiffIndex ?? 0;
    const status = getChangeStatus(fileDiff?.type || "change");
    const stats = fileDiff ? getFileStats(fileDiff) : { additions: 0, deletions: 0 };
    const isActive = activeFileIndex === fileIdx;

    return (
      <div
        key={node.path}
        className={`changes-tree-file-row ${isActive ? "active" : ""}`}
        style={{ paddingLeft: `${level * 14 + 10}px` }}
        onClick={() => handleSelectFile(fileIdx, node.path)}
        role="button"
        tabIndex={0}
      >
        <span className={`changes-status-badge-sm ${status.className}`} title={status.label}>
          {status.text}
        </span>
        <span className="changes-tree-file-name" title={node.path}>
          {node.name}
        </span>
        <span className="changes-tree-file-stats">
          {stats.additions > 0 && <span className="stat-add">+{stats.additions}</span>}
          {stats.deletions > 0 && <span className="stat-del">-{stats.deletions}</span>}
        </span>
      </div>
    );
  };

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
          {/* Sidebar toggle button (only when diff is present) */}
          {hasDiffContent && (
            <button
              type="button"
              className={`changes-action-btn ${sidebarOpen ? "active" : ""}`}
              onClick={() => setSidebarOpen((prev) => !prev)}
              title={sidebarOpen ? "Hide changed files sidebar" : "Show changed files sidebar"}
              aria-label="Toggle changed files sidebar"
            >
              {sidebarOpen ? (
                <PanelLeftClose className="size-3.5" />
              ) : (
                <PanelLeftOpen className="size-3.5" />
              )}
            </button>
          )}

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
          <div className="changes-layout-container">
            {/* Left Files Sidebar */}
            {sidebarOpen && (
              <aside className="changes-files-sidebar">
                <div className="changes-sidebar-header">
                  <div className="changes-sidebar-title-group">
                    <span className="changes-sidebar-title">Files Changed</span>
                    <span className="changes-sidebar-count-badge">
                      {filterQuery.trim()
                        ? `${filteredIndexedDiffs.length} / ${fileDiffs.length}`
                        : fileDiffs.length}
                    </span>
                  </div>
                  <div className="changes-sidebar-view-toggle">
                    <button
                      type="button"
                      className={`changes-view-btn ${viewMode === "tree" ? "active" : ""}`}
                      onClick={() => setViewMode("tree")}
                      title="Tree view"
                      aria-label="Tree view"
                    >
                      <FolderTree className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      className={`changes-view-btn ${viewMode === "list" ? "active" : ""}`}
                      onClick={() => setViewMode("list")}
                      title="List view"
                      aria-label="List view"
                    >
                      <List className="size-3.5" />
                    </button>
                  </div>
                </div>

                <div className="changes-sidebar-search-container">
                  <div className="changes-search-box">
                    <Search className="size-3.5 text-neutral-400" />
                    <input
                      type="text"
                      className="changes-search-input"
                      placeholder="Filter by file path..."
                      value={filterQuery}
                      onChange={(e) => setFilterQuery(e.target.value)}
                    />
                    {filterQuery && (
                      <button
                        type="button"
                        className="changes-search-clear-btn"
                        onClick={() => setFilterQuery("")}
                        title="Clear filter"
                        aria-label="Clear filter"
                      >
                        <X className="size-3 text-neutral-400" />
                      </button>
                    )}
                  </div>
                </div>

                <div className="changes-sidebar-content">
                  {filteredIndexedDiffs.length === 0 ? (
                    <div className="changes-no-filter-match">
                      <p>No files match "{filterQuery}"</p>
                    </div>
                  ) : viewMode === "tree" ? (
                    <div className="changes-tree-view">
                      {renderTreeNode(fileTree)}
                    </div>
                  ) : (
                    <div className="changes-list-view">
                      {filteredIndexedDiffs.map(({ fileDiff, originalIndex }) => {
                        const rawName = fileDiff.name || `file-${originalIndex}`;
                        const status = getChangeStatus(fileDiff.type || "change");
                        const stats = getFileStats(fileDiff);
                        const parts = rawName.split("/");
                        const baseName = parts[parts.length - 1];
                        const dirPath = parts.slice(0, parts.length - 1).join("/");
                        const isActive = activeFileIndex === originalIndex;

                        return (
                          <div
                            key={`${rawName}-${originalIndex}`}
                            className={`changes-list-file-row ${isActive ? "active" : ""}`}
                            onClick={() => handleSelectFile(originalIndex, rawName)}
                            role="button"
                            tabIndex={0}
                          >
                            <span
                              className={`changes-status-badge-sm ${status.className}`}
                              title={status.label}
                            >
                              {status.text}
                            </span>
                            <div className="changes-list-file-info" title={rawName}>
                              {dirPath && (
                                <span className="changes-list-file-dir">
                                  {dirPath}/
                                </span>
                              )}
                              <span className="changes-list-file-base">
                                {baseName}
                              </span>
                            </div>
                            <span className="changes-list-file-stats">
                              {stats.additions > 0 && (
                                <span className="stat-add">+{stats.additions}</span>
                              )}
                              {stats.deletions > 0 && (
                                <span className="stat-del">-{stats.deletions}</span>
                              )}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </aside>
            )}

            {/* Right Diff Viewport */}
            <main className="changes-diff-viewport">
              <div className="changes-diff-summary-bar">
                <div className="changes-diff-summary-text">
                  <span className="changes-diff-summary-count">
                    {fileDiffs.length} changed file{fileDiffs.length === 1 ? "" : "s"}
                  </span>
                  <span className="changes-diff-summary-stats">
                    {totalStats.additions > 0 && (
                      <span className="stat-add">+{totalStats.additions.toLocaleString()}</span>
                    )}
                    {totalStats.deletions > 0 && (
                      <span className="stat-del">-{totalStats.deletions.toLocaleString()}</span>
                    )}
                  </span>
                </div>
                <button
                  type="button"
                  className="changes-collapse-all-btn"
                  onClick={toggleAllFiles}
                  title={allFilesExpanded ? "Collapse all file diffs" : "Expand all file diffs"}
                >
                  {allFilesExpanded ? (
                    <>
                      <ChevronsDownUp className="size-3.5" />
                      <span>Collapse All</span>
                    </>
                  ) : (
                    <>
                      <ChevronsUpDown className="size-3.5" />
                      <span>Expand All</span>
                    </>
                  )}
                </button>
              </div>

              <div className="changes-diff-cards">
                {filteredIndexedDiffs.length === 0 ? (
                  <div className="changes-empty-state">
                    <p>No changed files match "{filterQuery}".</p>
                    <button
                      type="button"
                      className="changes-retry-btn"
                      onClick={() => setFilterQuery("")}
                    >
                      Clear filter
                    </button>
                  </div>
                ) : (
                  filteredIndexedDiffs.map(({ fileDiff, originalIndex }) => {
                    const fileName = fileDiff.name || `file-${originalIndex}`;
                    const isExpanded = expandedFiles[fileName] ?? true;
                    const status = getChangeStatus(fileDiff.type || "change");
                    const stats = getFileStats(fileDiff);
                    const isCopied = copiedPath === fileName;

                    return (
                      <article
                        key={`${fileName}-${originalIndex}`}
                        id={`diff-file-${originalIndex}`}
                        className={`changes-file-diff-item ${isExpanded ? "expanded" : "collapsed"}`}
                      >
                      {/* Clickable Collapsible Header */}
                      <header
                        className="changes-file-card-header"
                        onClick={() => toggleFile(fileName)}
                        role="button"
                        tabIndex={0}
                        aria-expanded={isExpanded}
                      >
                        <div className="changes-file-card-left">
                          <button
                            type="button"
                            className="changes-file-chevron-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleFile(fileName);
                            }}
                            aria-label={isExpanded ? "Collapse file" : "Expand file"}
                          >
                            {isExpanded ? (
                              <ChevronDown className="size-4 text-neutral-400" />
                            ) : (
                              <ChevronRight className="size-4 text-neutral-400" />
                            )}
                          </button>
                          <span
                            className={`changes-status-badge ${status.className}`}
                            title={status.label}
                          >
                            {status.text}
                          </span>
                          <span className="changes-file-name" title={fileName}>
                            {fileDiff.prevName ? (
                              <>
                                <span className="changes-file-prevname">
                                  {fileDiff.prevName}
                                </span>
                                <span className="changes-file-arrow">→</span>
                                <span>{fileName}</span>
                              </>
                            ) : (
                              fileName
                            )}
                          </span>
                        </div>

                        <div className="changes-file-card-right">
                          <div className="changes-file-stats">
                            {stats.additions > 0 && (
                              <span className="stat-add">+{stats.additions}</span>
                            )}
                            {stats.deletions > 0 && (
                              <span className="stat-del">-{stats.deletions}</span>
                            )}
                          </div>
                          <button
                            type="button"
                            className="changes-file-action-icon-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              void handleCopyPath(fileName);
                            }}
                            title="Copy file path"
                            aria-label="Copy file path"
                          >
                            {isCopied ? (
                              <Check className="size-3.5 text-emerald-400" />
                            ) : (
                              <Copy className="size-3.5 text-neutral-400" />
                            )}
                          </button>
                        </div>
                      </header>

                      {/* Diff Body (Hidden when collapsed) */}
                      {isExpanded && (
                        <div className="changes-file-diff-body">
                          <FileDiff
                            fileDiff={fileDiff}
                            options={{
                              diffStyle,
                              theme: "github-dark",
                              disableFileHeader: true,
                            }}
                          />
                        </div>
                      )}
                    </article>
                  );
                }))}
              </div>
            </main>
          </div>
        )}
      </div>
    </div>
  );
}
