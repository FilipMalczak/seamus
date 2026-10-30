import { useCallback, useEffect, useState } from "react";
import {
  createAgent,
  createSession,
  createThread,
  getAgent,
  getSession,
  listAgents,
} from "../api/client";
import type { AgentSummary, SessionDetail } from "../api/types";

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

      // Fetch details for agents to have their sessions
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

      // Auto-select if nothing selected yet
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
      setSelectedAgentId(created.id);
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
    refreshTree,
  };
}
