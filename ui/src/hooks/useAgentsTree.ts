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
  switchSessionMode,
  updateAgent,
  updateSession,
  updateThread,
} from "../api/client";
import type { AgentConfig, AgentSummary, SessionDetail } from "../api/types";

export type FullAgentNode = AgentSummary & {
  sessionsMap?: Record<string, SessionDetail>;
  isExpanded?: boolean;
};

function resolveSelectionFromUrl(
  fullList: FullAgentNode[],
  search: string
): {
  agentId: string | null;
  sessionId: string | null;
  threadId: string | null;
} {
  if (fullList.length === 0) {
    return { agentId: null, sessionId: null, threadId: null };
  }
  const params = new URLSearchParams(search);
  const agentParam = params.get("agent");
  const sessionParam = params.get("session");
  const threadParam = params.get("thread");

  const targetAgent =
    (agentParam
      ? fullList.find((a) => a.id === agentParam || a.name === agentParam)
      : undefined) || fullList[0];

  const sessions = Object.values(targetAgent.sessionsMap || {});
  if (sessions.length === 0) {
    return { agentId: targetAgent.id, sessionId: null, threadId: null };
  }

  const sortedSessions = [...sessions].sort(
    (a, b) =>
      new Date(b.last_touched_at || b.created_at).getTime() -
      new Date(a.last_touched_at || a.created_at).getTime()
  );

  const targetSession = sessionParam
    ? sessions.find((s) => s.id === sessionParam || s.name === sessionParam) || sortedSessions[0]
    : sortedSessions[0];

  const targetThread = threadParam
    ? targetSession?.threads.find(
        (t) => t.id === threadParam || t.name === threadParam
      )
    : undefined;

  return {
    agentId: targetAgent.id,
    sessionId: targetSession ? targetSession.id : null,
    threadId: targetThread ? targetThread.id : null,
  };
}

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

      // Hydrate selection from URL query params (or fallback to first entity) if nothing selected yet
      if (fullList.length > 0 && !selectedAgentId) {
        const resolved = resolveSelectionFromUrl(
          fullList,
          typeof window !== "undefined" ? window.location.search : ""
        );
        if (resolved.agentId) setSelectedAgentId(resolved.agentId);
        if (resolved.sessionId) setSelectedSessionId(resolved.sessionId);
        if (resolved.threadId) setSelectedThreadId(resolved.threadId);
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

  // Synchronize entity selection when user navigates browser Back/Forward
  useEffect(() => {
    const handlePopState = () => {
      if (agents.length === 0) return;
      const resolved = resolveSelectionFromUrl(agents, window.location.search);
      if (resolved.agentId) setSelectedAgentId(resolved.agentId);
      if (resolved.sessionId) setSelectedSessionId(resolved.sessionId);
      if (resolved.threadId) setSelectedThreadId(resolved.threadId);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [agents]);

  const selectThread = useCallback(
    (agentId: string, sessionId: string, threadId: string) => {
      setSelectedAgentId(agentId);
      setSelectedSessionId(sessionId);
      setSelectedThreadId(threadId);
    },
    []
  );

  const selectSession = useCallback(
    (agentId: string, sessionId: string) => {
      setSelectedAgentId(agentId);
      setSelectedSessionId(sessionId);
      setSelectedThreadId(null);
    },
    []
  );

  const selectAgent = useCallback(
    (agentId: string) => {
      setSelectedAgentId(agentId);
      const targetAgent = agents.find((a) => a.id === agentId);
      const sessions = Object.values(targetAgent?.sessionsMap || {});
      if (sessions.length > 0) {
        const sortedSessions = [...sessions].sort(
          (a, b) =>
            new Date(b.last_touched_at || b.created_at).getTime() -
            new Date(a.last_touched_at || a.created_at).getTime()
        );
        setSelectedSessionId(sortedSessions[0].id);
      } else {
        setSelectedSessionId(null);
      }
      setSelectedThreadId(null);
    },
    [agents]
  );

  const handleCreateAgent = useCallback(
    async (name?: string | null) => {
      const created = await createAgent({ name: name || null });
      await refreshTree();
      // The backend creates a default session & thread for the new agent.
      // Auto-select session view immediately so user can type right away.
      try {
        const detail = await getAgent(created.id);
        setSelectedAgentId(created.id);
        if (detail.sessions && detail.sessions.length > 0) {
          const defSession = detail.sessions[0];
          setSelectedSessionId(defSession.id);
          setSelectedThreadId(null);
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
      setSelectedThreadId(null);
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

  const handleSwitchSessionMode = useCallback(
    async (agentId: string, sessionId: string, mode: "chat" | "plan") => {
      const updatedSession = await switchSessionMode(agentId, sessionId, mode);
      await refreshTree();
      setSelectedAgentId(agentId);
      setSelectedSessionId(sessionId);
      if (selectedThreadId) {
        const openThread =
          updatedSession.threads.find((t) => t.is_open) ||
          updatedSession.threads[updatedSession.threads.length - 1];
        if (openThread) {
          setSelectedThreadId(openThread.id);
        }
      }
      return updatedSession;
    },
    [refreshTree, selectedThreadId]
  );

  const handleBranchSession = useCallback(
    async (
      agentId: string,
      sessionId: string,
      messageId: string,
      name?: string | null,
      retryInference?: boolean
    ) => {
      const newSession = await branchSession(
        agentId,
        sessionId,
        messageId,
        name,
        retryInference
      );
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
  const openThread =
    activeSession?.threads.find((t) => t.is_open) ||
    (activeSession?.threads && activeSession.threads.length > 0
      ? activeSession.threads[activeSession.threads.length - 1]
      : undefined);
  const activeThread = selectedThreadId
    ? activeSession?.threads.find((t) => t.id === selectedThreadId) || openThread
    : openThread;

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
    selectAgent,
    selectSession,
    selectThread,
    createAgent: handleCreateAgent,
    createSession: handleCreateSession,
    createThread: handleCreateThread,
    killSession: handleKillSession,
    switchSessionMode: handleSwitchSessionMode,
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
