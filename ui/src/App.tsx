import { useEffect, useRef, useState } from "react";
import { Eye, GitPullRequest, MessageSquare } from "lucide-react";
import {
  getConfigTemplate,
  getSystemInfo,
  getSystemSettings,
  postUserInput,
  updateConfigTemplate,
  updateSystemSettings,
} from "./api/client";
import type { AgentConfig, AgentStatus, SystemInfoResponse, SystemSettings } from "./api/types";
import { AgentInspector } from "./components/AgentInspector";
import { ChangesViewer } from "./components/ChangesViewer";
import { ChatArea } from "./components/ChatArea";
import { ConfigModal } from "./components/ConfigModal";
import { Header } from "./components/Header";
import { SettingsModal } from "./components/SettingsModal";
import { Sidebar } from "./components/Sidebar";
import { useAgentsTree } from "./hooks/useAgentsTree";
import "./App.css";

const DEFAULT_SIDEBAR_RATIO = 1 / 3;

function parseTabFromSearch(search: string): "chat" | "inspector" | "changes" {
  const params = new URLSearchParams(search);
  const tab = params.get("tab");
  if (tab === "inspector" || tab === "changes" || tab === "chat") {
    return tab;
  }
  return "chat";
}

export function App() {
  const [configTemplate, setConfigTemplate] = useState<AgentConfig | null>(null);
  const [activeStatus, setActiveStatus] = useState<AgentStatus>("AWAITING_USER");
  const [systemInfo, setSystemInfo] = useState<SystemInfoResponse | null>(null);
  const [activeMainTab, setActiveMainTab] = useState<"chat" | "inspector" | "changes">(() =>
    typeof window !== "undefined" ? parseTabFromSearch(window.location.search) : "chat"
  );

  // Modal state
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [modalTitle, setModalTitle] = useState<string>("Config Template");
  const [modalConfig, setModalConfig] = useState<AgentConfig>({
    inference: {
      format: "openai",
      base_url: "https://openrouter.ai/api/v1",
      api_key: null,
    },
    model_name: "openai/gpt-oss-120b",
  });
  const [modalSaveFn, setModalSaveFn] = useState<(cfg: AgentConfig) => Promise<void>>(
    () => async () => {}
  );

  // Settings modal state
  const [systemSettings, setSystemSettings] = useState<SystemSettings>({
    skill_directories: ["~/.seamus/skills", "~/.skills"],
  });
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState<boolean>(false);

  // Split pane state (default 1:2 tree-to-chat split)
  const [sidebarRatio, setSidebarRatio] = useState<number>(() => {
    try {
      const saved = localStorage.getItem("seamus_sidebar_ratio");
      if (saved) {
        const parsed = parseFloat(saved);
        if (!isNaN(parsed) && parsed >= 0.15 && parsed <= 0.85) {
          return parsed;
        }
      }
    } catch {}
    return DEFAULT_SIDEBAR_RATIO;
  });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const appBodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      localStorage.setItem("seamus_sidebar_ratio", sidebarRatio.toString());
    } catch {}
  }, [sidebarRatio]);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!appBodyRef.current) return;
      const rect = appBodyRef.current.getBoundingClientRect();
      const minSidebarPx = 280;
      const minMainPx = 300;

      const rawRatio = (e.clientX - rect.left) / rect.width;
      const minRatio = minSidebarPx / rect.width;
      const maxRatio = (rect.width - minMainPx) / rect.width;

      const clampedRatio = Math.max(minRatio, Math.min(maxRatio, rawRatio));
      setSidebarRatio(clampedRatio);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDragging]);

  const {
    agents,
    selectedAgentId,
    selectedSessionId,
    selectedThreadId,
    activeAgent,
    activeSession,
    activeThread,
    selectThread,
    createAgent,
    createSession,
    killSession,
    branchSession,
    acceptThread,
    updateAgentName,
    updateSessionName,
    updateThreadName,
    updateAgentConfig,
    updateSessionConfig,
    refreshTree,
  } = useAgentsTree();

  const loadTemplate = async () => {
    try {
      const res = await getConfigTemplate();
      setConfigTemplate(res.config);
    } catch (err) {
      console.warn("Failed to load config template:", err);
    }
  };

  const loadSystem = async () => {
    try {
      const res = await getSystemInfo();
      setSystemInfo(res);
    } catch (err) {
      console.warn("Failed to load system info:", err);
    }
  };

  const loadSettings = async () => {
    try {
      const res = await getSystemSettings();
      setSystemSettings(res.settings);
    } catch (err) {
      console.warn("Failed to load system settings:", err);
    }
  };

  useEffect(() => {
    loadTemplate();
    loadSystem();
    loadSettings();
  }, []);

  // Synchronize activeMainTab when user navigates browser Back/Forward
  useEffect(() => {
    const handlePopState = () => {
      setActiveMainTab(parseTabFromSearch(window.location.search));
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  // Synchronize URL query parameters (?agent=...&session=...&thread=...&tab=...)
  const hasHydratedUrlRef = useRef<boolean>(false);
  useEffect(() => {
    if (!selectedAgentId) return;
    const params = new URLSearchParams();
    params.set("agent", activeAgent?.name || selectedAgentId);
    if (selectedSessionId) {
      params.set("session", activeSession?.name || selectedSessionId);
    }
    if (selectedThreadId) {
      params.set("thread", activeThread?.name || selectedThreadId);
    }
    params.set("tab", activeMainTab);

    const nextSearch = `?${params.toString()}`;
    if (window.location.search !== nextSearch) {
      const nextUrl = `${window.location.pathname}${nextSearch}${window.location.hash}`;
      if (!hasHydratedUrlRef.current) {
        window.history.replaceState(null, "", nextUrl);
      } else {
        window.history.pushState(null, "", nextUrl);
      }
    }
    hasHydratedUrlRef.current = true;
  }, [
    selectedAgentId,
    selectedSessionId,
    selectedThreadId,
    activeAgent?.name,
    activeSession?.name,
    activeThread?.name,
    activeMainTab,
  ]);

  // Refresh sidebar tree when an active turn completes or errors, and poll while busy
  const prevStatusRef = useRef<AgentStatus>(activeStatus);
  useEffect(() => {
    const prev = prevStatusRef.current;
    prevStatusRef.current = activeStatus;
    if (
      prev !== activeStatus &&
      (activeStatus === "AWAITING_USER" || activeStatus === "ERROR")
    ) {
      void refreshTree();
    }
  }, [activeStatus, refreshTree]);

  useEffect(() => {
    const isTurnActive =
      activeStatus === "AWAITING_LLM" || activeStatus === "EXECUTING_TOOL";
    if (!isTurnActive) return;
    const interval = window.setInterval(() => {
      void refreshTree();
    }, 4000);
    return () => window.clearInterval(interval);
  }, [activeStatus, refreshTree]);

  const handleOpenSystemSettings = () => {
    setIsSettingsModalOpen(true);
  };

  const handleSaveSystemSettings = async (updated: SystemSettings) => {
    const res = await updateSystemSettings(updated);
    setSystemSettings(res.settings);
  };

  const handleOpenGlobalConfig = () => {
    setModalTitle("Edit Global Config Template");
    setModalConfig(
      configTemplate || {
        inference: {
          format: "openai",
          base_url: "https://openrouter.ai/api/v1",
          api_key: null,
        },
        model_name: "openai/gpt-oss-120b",
      }
    );
    setModalSaveFn(() => async (updated: AgentConfig) => {
      const saved = await updateConfigTemplate(updated);
      setConfigTemplate(saved.config);
      await refreshTree();
    });
    setIsModalOpen(true);
  };

  const handleEditEntityConfig = (
    title: string,
    config: AgentConfig,
    saveFn: (cfg: AgentConfig) => Promise<void>
  ) => {
    setModalTitle(title);
    setModalConfig(config);
    setModalSaveFn(() => async (updated: AgentConfig) => {
      await saveFn(updated);
      await refreshTree();
    });
    setIsModalOpen(true);
  };

  const handleNavigateToSession = (targetSessionId: string) => {
    if (!selectedAgentId || !activeAgent) return;
    const targetSession = activeAgent.sessionsMap?.[targetSessionId];
    if (targetSession) {
      const openThread =
        targetSession.threads.find((t) => t.is_open) || targetSession.threads[0];
      if (openThread) {
        selectThread(selectedAgentId, targetSessionId, openThread.id);
      }
    }
  };

  return (
    <div className="app-layout">
      <Header
        configTemplate={configTemplate}
        onOpenConfigTemplate={handleOpenGlobalConfig}
        onOpenSystemSettings={handleOpenSystemSettings}
      />

      <div className="app-body" ref={appBodyRef}>
        <Sidebar
          style={{ width: `${sidebarRatio * 100}%` }}
          agents={agents}
          selectedAgentId={selectedAgentId}
          selectedSessionId={selectedSessionId}
          selectedThreadId={selectedThreadId}
          activeStatus={activeStatus}
          systemInfo={systemInfo}
          onSelectThread={selectThread}
          onCreateAgent={createAgent}
          onCreateSession={createSession}
          onUpdateAgentName={updateAgentName}
          onUpdateSessionName={updateSessionName}
          onUpdateThreadName={updateThreadName}
          onUpdateAgentConfig={updateAgentConfig}
          onUpdateSessionConfig={updateSessionConfig}
          onEditConfig={handleEditEntityConfig}
        />

        <div
          className={`split-resizer ${isDragging ? "dragging" : ""}`}
          onMouseDown={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDoubleClick={() => setSidebarRatio(DEFAULT_SIDEBAR_RATIO)}
          role="separator"
          aria-orientation="vertical"
          aria-valuenow={Math.round(sidebarRatio * 100)}
          title="Drag to resize (Double-click to reset 1:2)"
        />

        <div className="main-panel">
          <div className="main-panel-tabs">
            <button
              type="button"
              className={`main-tab ${activeMainTab === "chat" ? "active" : ""}`}
              onClick={() => setActiveMainTab("chat")}
            >
              <MessageSquare className="size-4" />
              <span>Chat</span>
            </button>
            <button
              type="button"
              className={`main-tab ${activeMainTab === "inspector" ? "active" : ""}`}
              onClick={() => setActiveMainTab("inspector")}
            >
              <Eye className="size-4" />
              <span>Inspector</span>
              {selectedSessionId && <span className="main-tab-badge">Semi-Live</span>}
            </button>
            <button
              type="button"
              className={`main-tab ${activeMainTab === "changes" ? "active" : ""}`}
              onClick={() => setActiveMainTab("changes")}
            >
              <GitPullRequest className="size-4" />
              <span>Changes</span>
            </button>
          </div>

          <div className="main-panel-content">
            <div
              style={{
                display: activeMainTab === "chat" ? "flex" : "none",
                height: "100%",
                width: "100%",
                flexDirection: "column",
              }}
            >
              <ChatArea
                agentId={selectedAgentId}
                agentName={activeAgent?.name || null}
                sessionId={selectedSessionId}
                sessionName={activeSession?.name || null}
                sessionStatus={activeSession?.status || "ACTIVE"}
                sessionProvenance={activeSession?.provenance || null}
                sessionLineage={activeSession?.lineage}
                thread={activeThread || null}
                onStatusChange={setActiveStatus}
                onKillSession={async () => {
                  if (selectedAgentId && selectedSessionId) {
                    await killSession(selectedAgentId, selectedSessionId);
                  }
                }}
                onBranchMessage={async (
                  targetId: string | null,
                  options?: { retryInference?: boolean; promptToSend?: string }
                ) => {
                  if (!selectedAgentId) return;
                  if (targetId && selectedSessionId) {
                    const newSession = await branchSession(
                      selectedAgentId,
                      selectedSessionId,
                      targetId,
                      null,
                      options?.retryInference
                    );
                    if (options?.promptToSend) {
                      await postUserInput(
                        selectedAgentId,
                        newSession.id,
                        options.promptToSend
                      );
                    }
                  } else if (options?.promptToSend) {
                    const newSession = await createSession(selectedAgentId);
                    await postUserInput(
                      selectedAgentId,
                      newSession.id,
                      options.promptToSend
                    );
                  }
                }}
                onNavigateToSession={handleNavigateToSession}
              />
            </div>

            {activeMainTab === "inspector" && (
              <AgentInspector
                agentId={selectedAgentId}
                sessionId={selectedSessionId}
                threadId={selectedThreadId}
                agentName={activeAgent?.name || null}
                sessionName={activeSession?.name || null}
              />
            )}

            {activeMainTab === "changes" && (
              <ChangesViewer
                agentId={selectedAgentId}
                agentName={activeAgent?.name || null}
                sessionId={selectedSessionId}
                sessionName={activeSession?.name || null}
                thread={activeThread || null}
                agentStatus={activeStatus}
                onAcceptThread={async () => {
                  if (selectedAgentId && selectedSessionId && activeThread) {
                    await acceptThread(selectedAgentId, selectedSessionId, activeThread.id);
                  }
                }}
              />
            )}
          </div>
        </div>
      </div>

      <ConfigModal
        isOpen={isModalOpen}
        title={modalTitle}
        initialConfig={modalConfig}
        onClose={() => setIsModalOpen(false)}
        onSave={modalSaveFn}
      />

      <SettingsModal
        isOpen={isSettingsModalOpen}
        initialSettings={systemSettings}
        onClose={() => setIsSettingsModalOpen(false)}
        onSave={handleSaveSystemSettings}
      />
    </div>
  );
}

export default App;

