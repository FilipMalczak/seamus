import type {
  AgentConfig,
  AgentDetail,
  AgentInspectReport,
  AgentSummary,
  AgentStatus,
  ArtifactInfo,
  ClickResult,
  ConfigTemplateResponse,
  SessionDetail,
  SessionDiffResponse,
  SystemInfoResponse,
  SystemSettings,
  SystemSettingsResponse,
  ThreadInfo,
} from "./types";

const BASE_URL = "/api/v-alpha";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    try {
      const body = await res.json();
      if (body && body.detail) {
        if (typeof body.detail === "string") {
          detail = body.detail;
        } else if (Array.isArray(body.detail)) {
          detail = body.detail
            .map((err: any) => {
              const loc = Array.isArray(err.loc) ? err.loc.slice(1).join(".") : "";
              const msg = err.msg || JSON.stringify(err);
              return loc ? `${loc}: ${msg}` : msg;
            })
            .join("; ");
        } else {
          detail = JSON.stringify(body.detail);
        }
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

export async function getSystemInfo(): Promise<SystemInfoResponse> {
  const res = await fetch(`${BASE_URL}/system/info`);
  return handleResponse<SystemInfoResponse>(res);
}

export async function getSystemSettings(): Promise<SystemSettingsResponse> {
  const res = await fetch(`${BASE_URL}/settings`);
  return handleResponse<SystemSettingsResponse>(res);
}

export async function updateSystemSettings(settings: SystemSettings): Promise<SystemSettingsResponse> {
  const res = await fetch(`${BASE_URL}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  return handleResponse<SystemSettingsResponse>(res);
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

export async function killSession(agentId: string, sessionId: string): Promise<SessionDetail> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/kill`,
    {
      method: "POST",
    }
  );
  return handleResponse<SessionDetail>(res);
}

export async function switchSessionMode(
  agentId: string,
  sessionId: string,
  mode: "chat" | "plan"
): Promise<SessionDetail> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/mode`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    }
  );
  return handleResponse<SessionDetail>(res);
}

export async function branchSession(
  agentId: string,
  sessionId: string,
  messageId: string,
  name?: string | null,
  retryInference?: boolean
): Promise<SessionDetail> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/branch`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message_id: messageId,
        name: name ?? null,
        retry_inference: retryInference ?? false,
      }),
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

export async function acceptThread(
  agentId: string,
  sessionId: string,
  threadId: string
): Promise<ThreadInfo> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/thread/${encodeURIComponent(threadId)}/accept`,
    {
      method: "POST",
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

export function subscribeToSessionStream(
  agentId: string,
  sessionId: string,
  onEvent: (event: any) => void,
  onError?: (err: Error) => void
): () => void {
  const controller = new AbortController();
  const url = `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/stream`;

  (async () => {
    try {
      const res = await fetch(url, {
        signal: controller.signal,
        headers: { Accept: "text/event-stream" },
      });

      if (!res.ok) {
        throw new Error(`SSE session stream failed with status ${res.status}`);
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

export async function getAgentInspection(
  agentId: string,
  sessionId: string,
  threadId?: string | null
): Promise<AgentInspectReport> {
  const url = new URL(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/inspect`,
    window.location.origin
  );
  if (threadId) {
    url.searchParams.set("thread_id", threadId);
  }
  const res = await fetch(url.toString());
  return handleResponse<AgentInspectReport>(res);
}

export async function getSessionDiff(
  agentId: string,
  sessionId: string
): Promise<SessionDiffResponse> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/diff`
  );
  return handleResponse<SessionDiffResponse>(res);
}

export async function listArtifacts(
  agentId: string,
  sessionId: string
): Promise<ArtifactInfo[]> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/artifact`
  );
  return handleResponse<ArtifactInfo[]>(res);
}

export async function getArtifact(
  agentId: string,
  sessionId: string,
  kind: string,
  name: string
): Promise<ArtifactInfo> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/artifact/${encodeURIComponent(kind)}/${encodeURIComponent(name)}`
  );
  return handleResponse<ArtifactInfo>(res);
}

export async function submitArtifact(
  agentId: string,
  sessionId: string,
  kind: string,
  name: string,
  data: Record<string, unknown>
): Promise<{ status: string; artifact_id: string; tool_call_id: string }> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/artifact/${encodeURIComponent(kind)}/${encodeURIComponent(name)}/submit`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data }),
    }
  );
  return handleResponse<{ status: string; artifact_id: string; tool_call_id: string }>(res);
}

export async function clickArtifact(
  agentId: string,
  sessionId: string,
  family: string,
  uuid: string,
  buttonId: string,
  context: Record<string, unknown> = {}
): Promise<ClickResult> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/artifact/${encodeURIComponent(family)}/${encodeURIComponent(uuid)}/click`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ button_id: buttonId, context }),
    }
  );
  return handleResponse<ClickResult>(res);
}


