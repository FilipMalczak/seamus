import { useCallback, useEffect, useState } from "react";
import {
  acceptThread,
  branchSession,
  createAgent,
  createSession,
  createThread,
  getAgent,
  getSession,
  killSession,
  listAgents,
  updateAgent,
  updateSession,
  updateThread,
} from "../api/client";
import type { AgentConfig, AgentSummary, SessionDetail } from "../api/types";

export type FullAgentNode = AgentSummary & {
  sessionsMap?: Record<string, SessionDetail>;
  isExpanded?: boolean;
};

export function useAgentsTree() {
  const [agents, setAgents] = useState<FullAgentNode[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);

  const refreshTree = useCallback(async () => {
    try {
      setError(null);
      const agentList = await listAgents();

      // Fetch details for agents to have their sessions and threads
      const fullList: FullAgentNode[] = await Promise.all(
        agentList.map(async (a) => {
          try {
            const detail = await getAgent(a.id);
            const sessionsMap: Record<string, SessionDetail> = {};
            await Promise.all(
              detail.sessions.map(async (s) => {
                try {
                  const sDetail = await getSession(a.id, s.id);
                  sessionsMap[s.id] = sDetail;
                } catch {
                  // ignore session detail load error
                }
              })
            );
            return {
              ...a,
              sessionsMap,
              isExpanded: true,
            };
          } catch {
            return { ...a, isExpanded: false };
          }
        })
      );

      setAgents(fullList);

      // Auto-select first agent, session, and open thread if nothing selected yet
      if (fullList.length > 0 && !selectedAgentId) {
        const firstAgent = fullList[0];
        const sessionKeys = Object.keys(firstAgent.sessionsMap || {});
        setSelectedAgentId(firstAgent.id);
        if (sessionKeys.length > 0) {
          const firstSession = firstAgent.sessionsMap![sessionKeys[0]];
          setSelectedSessionId(firstSession.id);
          const openThread =
            firstSession.threads.find((t) => t.is_open) || firstSession.threads[0];
          if (openThread) {
            setSelectedThreadId(openThread.id);
          }
        }
      }
    } catch (err: any) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [selectedAgentId]);

  useEffect(() => {
    refreshTree();
  }, [refreshTree]);

  const selectThread = useCallback(
    (agentId: string, sessionId: string, threadId: string) => {
      setSelectedAgentId(agentId);
      setSelectedSessionId(sessionId);
      setSelectedThreadId(threadId);
    },
    []
  );

  const handleCreateAgent = useCallback(
    async (name?: string | null) => {
      const created = await createAgent({ name: name || null });
      await refreshTree();
      // The backend creates a default session & thread for the new agent.
      // Auto-select them immediately so user can type right away.
      try {
        const detail = await getAgent(created.id);
        setSelectedAgentId(created.id);
        if (detail.sessions && detail.sessions.length > 0) {
          const defSession = detail.sessions[0];
          setSelectedSessionId(defSession.id);
          const sDetail = await getSession(created.id, defSession.id);
          const openThread =
            sDetail.threads.find((t) => t.is_open) || sDetail.threads[0];
          if (openThread) {
            setSelectedThreadId(openThread.id);
          }
        }
      } catch {
        setSelectedAgentId(created.id);
      }
      return created;
    },
    [refreshTree]
  );

  const handleCreateSession = useCallback(
    async (agentId: string, name?: string | null) => {
      const created = await createSession(agentId, { name: name || null });
      await refreshTree();
      setSelectedAgentId(agentId);
      setSelectedSessionId(created.id);
      const openThread = created.threads.find((t) => t.is_open) || created.threads[0];
      if (openThread) {
        setSelectedThreadId(openThread.id);
      }
      return created;
    },
    [refreshTree]
  );

  const handleCreateThread = useCallback(
    async (agentId: string, sessionId: string, name?: string | null) => {
      const created = await createThread(agentId, sessionId, { name: name || null });
      await refreshTree();
      setSelectedAgentId(agentId);
      setSelectedSessionId(sessionId);
      setSelectedThreadId(created.id);
      return created;
    },
    [refreshTree]
  );

  const handleAcceptThread = useCallback(
    async (agentId: string, sessionId: string, threadId: string) => {
      const newThread = await acceptThread(agentId, sessionId, threadId);
      await refreshTree();
      setSelectedAgentId(agentId);
      setSelectedSessionId(sessionId);
      setSelectedThreadId(newThread.id);
      return newThread;
    },
    [refreshTree]
  );

  const handleUpdateAgentName = useCallback(
    async (agentId: string, newName: string | null) => {
      const agent = agents.find((a) => a.id === agentId);
      if (!agent) return;
      await updateAgent(agentId, { name: newName || null, config: agent.config });
      await refreshTree();
    },
    [agents, refreshTree]
  );

  const handleUpdateSessionName = useCallback(
    async (agentId: string, sessionId: string, newName: string | null) => {
      const agent = agents.find((a) => a.id === agentId);
      const session = agent?.sessionsMap?.[sessionId];
      if (!session) return;
      await updateSession(agentId, sessionId, {
        name: newName || null,
        config: session.config,
      });
      await refreshTree();
    },
    [agents, refreshTree]
  );

  const handleUpdateThreadName = useCallback(
    async (agentId: string, sessionId: string, threadId: string, newName: string | null) => {
      await updateThread(agentId, sessionId, threadId, { name: newName || null });
      await refreshTree();
    },
    [refreshTree]
  );

  const handleUpdateAgentConfig = useCallback(
    async (agentId: string, newConfig: AgentConfig) => {
      const agent = agents.find((a) => a.id === agentId);
      if (!agent) return;
      await updateAgent(agentId, { name: agent.name, config: newConfig });
      await refreshTree();
    },
    [agents, refreshTree]
  );

  const handleUpdateSessionConfig = useCallback(
    async (agentId: string, sessionId: string, newConfig: AgentConfig) => {
      const agent = agents.find((a) => a.id === agentId);
      const session = agent?.sessionsMap?.[sessionId];
      if (!session) return;
      await updateSession(agentId, sessionId, {
        name: session.name,
        config: newConfig,
      });
      await refreshTree();
    },
    [agents, refreshTree]
  );

  const handleKillSession = useCallback(
    async (agentId: string, sessionId: string) => {
      await killSession(agentId, sessionId);
      await refreshTree();
    },
    [refreshTree]
  );

  const handleBranchSession = useCallback(
    async (agentId: string, sessionId: string, messageId: string, name?: string | null) => {
      const newSession = await branchSession(agentId, sessionId, messageId, name);
      await refreshTree();
      setSelectedAgentId(agentId);
      setSelectedSessionId(newSession.id);
      const openThread = newSession.threads.find((t) => t.is_open) || newSession.threads[0];
      if (openThread) {
        setSelectedThreadId(openThread.id);
      }
      return newSession;
    },
    [refreshTree]
  );

  // Helper getters
  const activeAgent = agents.find((a) => a.id === selectedAgentId);
  const activeSession = activeAgent?.sessionsMap?.[selectedSessionId ?? ""];
  const activeThread = activeSession?.threads.find((t) => t.id === selectedThreadId);

  return {
    agents,
    loading,
    error,
    selectedAgentId,
    selectedSessionId,
    selectedThreadId,
    activeAgent,
    activeSession,
    activeThread,
    selectThread,
    createAgent: handleCreateAgent,
    createSession: handleCreateSession,
    createThread: handleCreateThread,
    killSession: handleKillSession,
    branchSession: handleBranchSession,
    acceptThread: handleAcceptThread,
    updateAgentName: handleUpdateAgentName,
    updateSessionName: handleUpdateSessionName,
    updateThreadName: handleUpdateThreadName,
    updateAgentConfig: handleUpdateAgentConfig,
    updateSessionConfig: handleUpdateSessionConfig,
    refreshTree,
  };
}
