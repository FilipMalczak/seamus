import { useEffect, useState } from "react";
import { Eye, MessageSquare } from "lucide-react";
import { getConfigTemplate, getSystemInfo, updateConfigTemplate } from "./api/client";
import type { AgentConfig, AgentStatus, SystemInfoResponse } from "./api/types";
import { AgentInspector } from "./components/AgentInspector";
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
  const [activeMainTab, setActiveMainTab] = useState<"chat" | "inspector">("chat");

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
    createThread,
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

  return (
    <div className="app-layout">
      <Header
        configTemplate={configTemplate}
        onOpenConfigTemplate={handleOpenGlobalConfig}
      />

      <div className="app-body">
        <Sidebar
          agents={agents}
          selectedAgentId={selectedAgentId}
          selectedSessionId={selectedSessionId}
          selectedThreadId={selectedThreadId}
          activeStatus={activeStatus}
          systemInfo={systemInfo}
          onSelectThread={selectThread}
          onCreateAgent={createAgent}
          onCreateSession={createSession}
          onCreateThread={createThread}
          onUpdateAgentName={updateAgentName}
          onUpdateSessionName={updateSessionName}
          onUpdateThreadName={updateThreadName}
          onUpdateAgentConfig={updateAgentConfig}
          onUpdateSessionConfig={updateSessionConfig}
          onEditConfig={handleEditEntityConfig}
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
                thread={activeThread || null}
                onStatusChange={setActiveStatus}
                onNewThread={() => {
                  if (selectedAgentId && selectedSessionId) {
                    createThread(selectedAgentId, selectedSessionId, null);
                  }
                }}
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

