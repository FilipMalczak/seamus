import { useEffect, useState } from "react";
import { getConfigTemplate, updateConfigTemplate } from "./api/client";
import type { AgentConfig } from "./api/types";
import { ChatArea } from "./components/ChatArea";
import { ConfigModal } from "./components/ConfigModal";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { useAgentsTree } from "./hooks/useAgentsTree";
import "./App.css";

export function App() {
  const [configTemplate, setConfigTemplate] = useState<AgentConfig | null>(null);

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

  useEffect(() => {
    loadTemplate();
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
          onSelectThread={selectThread}
          onCreateAgent={createAgent}
          onCreateSession={createSession}
          onCreateThread={createThread}
          onUpdateAgentName={updateAgentName}
          onUpdateSessionName={updateSessionName}
          onUpdateThreadName={updateThreadName}
          onEditConfig={handleEditEntityConfig}
        />

        <ChatArea
          agentId={selectedAgentId}
          agentName={activeAgent?.name || null}
          sessionId={selectedSessionId}
          sessionName={activeSession?.name || null}
          thread={activeThread || null}
          onNewThread={() => {
            if (selectedAgentId && selectedSessionId) {
              createThread(selectedAgentId, selectedSessionId, null);
            }
          }}
        />
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

