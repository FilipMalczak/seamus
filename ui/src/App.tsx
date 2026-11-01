import { useEffect, useRef, useState } from "react";
import { Eye, GitPullRequest, MessageSquare } from "lucide-react";
import { getConfigTemplate, getSystemInfo, updateConfigTemplate } from "./api/client";
import type { AgentConfig, AgentStatus, SystemInfoResponse } from "./api/types";
import { AgentInspector } from "./components/AgentInspector";
import { ChangesViewer } from "./components/ChangesViewer";
import { ChatArea } from "./components/ChatArea";
import { ConfigModal } from "./components/ConfigModal";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { useAgentsTree } from "./hooks/useAgentsTree";
import "./App.css";

export function App() {
  const [configTemplate, setConfigTemplate] = useState<AgentConfig | null>(null);
  const [activeStatus, setActiveStatus] = useState<AgentStatus>("AWAITING_USER");
  const [systemInfo, setSystemInfo] = useState<SystemInfoResponse | null>(null);
  const [activeMainTab, setActiveMainTab] = useState<"chat" | "inspector" | "changes">("chat");

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

  // Split pane state (default 50/50 split)
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
    return 0.5; // Default 50/50 split
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

  useEffect(() => {
    loadTemplate();
    loadSystem();
  }, []);

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
          onDoubleClick={() => setSidebarRatio(0.5)}
          role="separator"
          aria-orientation="vertical"
          aria-valuenow={Math.round(sidebarRatio * 100)}
          title="Drag to resize (Double-click to reset 50/50)"
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
                thread={activeThread || null}
                onStatusChange={setActiveStatus}
                onKillSession={async () => {
                  if (selectedAgentId && selectedSessionId) {
                    await killSession(selectedAgentId, selectedSessionId);
                  }
                }}
                onBranchMessage={async (messageId: string) => {
                  if (selectedAgentId && selectedSessionId) {
                    await branchSession(selectedAgentId, selectedSessionId, messageId);
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
    </div>
  );
}

export default App;

