import type {
  AgentConfig,
  AgentDetail,
  AgentSummary,
  AgentStatus,
  ConfigTemplateResponse,
  SessionDetail,
  ThreadInfo,
} from "./types";

const BASE_URL = "/api/v-alpha";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    try {
      const body = await res.json();
      if (body && body.detail) {
        detail = body.detail;
      }
    } catch {
      // Ignore json parse error
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function getConfigTemplate(): Promise<ConfigTemplateResponse> {
  const res = await fetch(`${BASE_URL}/config-template`);
  return handleResponse<ConfigTemplateResponse>(res);
}

export async function updateConfigTemplate(config: AgentConfig): Promise<ConfigTemplateResponse> {
  const res = await fetch(`${BASE_URL}/config-template`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  return handleResponse<ConfigTemplateResponse>(res);
}

export async function listAgents(): Promise<AgentSummary[]> {
  const res = await fetch(`${BASE_URL}/agents`);
  return handleResponse<AgentSummary[]>(res);
}

export async function createAgent(payload: {
  name?: string | null;
  config?: AgentConfig | null;
}): Promise<AgentSummary> {
  const res = await fetch(`${BASE_URL}/agents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<AgentSummary>(res);
}

export async function getAgent(idOrSlug: string): Promise<AgentDetail> {
  const res = await fetch(`${BASE_URL}/agent/${encodeURIComponent(idOrSlug)}`);
  return handleResponse<AgentDetail>(res);
}

export async function updateAgent(
  idOrSlug: string,
  payload: { name?: string | null; config: AgentConfig }
): Promise<AgentDetail> {
  const res = await fetch(`${BASE_URL}/agent/${encodeURIComponent(idOrSlug)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<AgentDetail>(res);
}

export async function createSession(
  agentId: string,
  payload: { name?: string | null; config?: AgentConfig | null }
): Promise<SessionDetail> {
  const res = await fetch(`${BASE_URL}/agent/${encodeURIComponent(agentId)}/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<SessionDetail>(res);
}

export async function getSession(agentId: string, sessionId: string): Promise<SessionDetail> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}`
  );
  return handleResponse<SessionDetail>(res);
}

export async function updateSession(
  agentId: string,
  sessionId: string,
  payload: { name?: string | null; config: AgentConfig }
): Promise<SessionDetail> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  return handleResponse<SessionDetail>(res);
}

export async function createThread(
  agentId: string,
  sessionId: string,
  payload: { name?: string | null }
): Promise<ThreadInfo> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/thread`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  return handleResponse<ThreadInfo>(res);
}

export async function updateThread(
  agentId: string,
  sessionId: string,
  threadId: string,
  payload: { name?: string | null }
): Promise<ThreadInfo> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/thread/${encodeURIComponent(threadId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  return handleResponse<ThreadInfo>(res);
}

export async function getThreadStatus(
  agentId: string,
  sessionId: string,
  threadId: string
): Promise<{ status: AgentStatus }> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/thread/${encodeURIComponent(threadId)}/status`
  );
  return handleResponse<{ status: AgentStatus }>(res);
}

export async function postUserInput(
  agentId: string,
  sessionId: string,
  message: string,
  messageId?: string
): Promise<{ status: string; thread_id: string; message_id?: string }> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/input`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, message_id: messageId }),
    }
  );
  return handleResponse<{ status: string; thread_id: string; message_id?: string }>(res);
}

export function subscribeToThreadStream(
  agentId: string,
  sessionId: string,
  threadId: string,
  onEvent: (event: any) => void,
  onError?: (err: Error) => void
): () => void {
  const controller = new AbortController();
  const url = `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/thread/${encodeURIComponent(threadId)}`;

  (async () => {
    try {
      const res = await fetch(url, {
        signal: controller.signal,
        headers: { Accept: "text/event-stream" },
      });

      if (!res.ok) {
        throw new Error(`SSE stream failed with status ${res.status}`);
      }

      if (!res.body) {
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (!controller.signal.aborted) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() ?? "";

        for (const block of lines) {
          const trimmed = block.trim();
          if (!trimmed) continue;
          for (const line of trimmed.split("\n")) {
            if (line.startsWith("data:")) {
              const jsonStr = line.slice(5).trim();
              if (jsonStr) {
                try {
                  const parsed = JSON.parse(jsonStr);
                  onEvent(parsed);
                } catch {
                  // If raw string event
                  onEvent({ type: "RAW_TEXT", data: jsonStr });
                }
              }
            }
          }
        }
      }
    } catch (err: any) {
      if (!controller.signal.aborted) {
        onError?.(err instanceof Error ? err : new Error(String(err)));
      }
    }
  })();

  return () => {
    controller.abort();
  };
}

