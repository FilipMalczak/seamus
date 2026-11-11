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
  TerminalInfoResponse,
  TerminalStreamEvent,
  TerminalStreamRequest,
  ThreadInfo,
  VaultSecretDetailResponse,
  VaultSecretListResponse,
  VaultTokenResponse,
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

export interface BranchSessionOptions {
  position?: "before" | "after";
  itemType?: "user_message" | "system_event" | "bot_message" | "bot_thinking" | "tool_call";
  name?: string | null;
  retryInference?: boolean;
}

export async function branchSession(
  agentId: string,
  sessionId: string,
  targetId: string,
  optionsOrName?: string | null | BranchSessionOptions,
  retryInference?: boolean
): Promise<SessionDetail> {
  let name: string | null = null;
  let position: "before" | "after" = "after";
  let itemType: string | undefined = undefined;
  let retryInf = retryInference ?? false;

  if (optionsOrName && typeof optionsOrName === "object") {
    name = optionsOrName.name ?? null;
    position = optionsOrName.position ?? "after";
    itemType = optionsOrName.itemType;
    retryInf = optionsOrName.retryInference ?? retryInf;
  } else if (typeof optionsOrName === "string") {
    name = optionsOrName;
  }

  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/branch`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_id: targetId,
        message_id: targetId,
        position,
        item_type: itemType,
        name,
        retry_inference: retryInf,
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
        let detail = "";
        try {
          const errData = await res.json();
          detail = errData?.detail ? `: ${errData.detail}` : "";
        } catch {
          // ignore
        }
        throw new Error(`SSE stream failed with status ${res.status}${detail}`);
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
        let detail = "";
        try {
          const errData = await res.json();
          detail = errData?.detail ? `: ${errData.detail}` : "";
        } catch {
          // ignore
        }
        throw new Error(`SSE session stream failed with status ${res.status}${detail}`);
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
  payload: {
    event?: string;
    timestamp?: string;
    context?: Record<string, unknown>;
    data?: Record<string, unknown>;
    comments?: Array<Record<string, unknown>>;
  } = {}
): Promise<ClickResult> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/artifact/${encodeURIComponent(family)}/${encodeURIComponent(uuid)}/click`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        button_id: buttonId,
        event: payload.event || buttonId,
        timestamp: payload.timestamp || new Date().toISOString(),
        context: payload.context || {},
        data: payload.data || {},
        comments: payload.comments || [],
      }),
    }
  );
  return handleResponse<ClickResult>(res);
}

export async function listVaultSecrets(): Promise<VaultSecretListResponse> {
  const res = await fetch(`${BASE_URL}/vault/secrets`);
  return handleResponse<VaultSecretListResponse>(res);
}

export async function createOrUpdateVaultSecret(
  path: string,
  data: Record<string, string>
): Promise<VaultSecretDetailResponse> {
  const res = await fetch(`${BASE_URL}/vault/secrets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, data }),
  });
  return handleResponse<VaultSecretDetailResponse>(res);
}

export async function getVaultToken(): Promise<VaultTokenResponse> {
  const res = await fetch(`${BASE_URL}/vault/token`);
  return handleResponse<VaultTokenResponse>(res);
}

export async function getTerminalInfo(
  agentId: string,
  sessionId: string
): Promise<TerminalInfoResponse> {
  const res = await fetch(
    `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/terminal/info`
  );
  return handleResponse<TerminalInfoResponse>(res);
}

export function streamTerminalCommand(
  agentId: string,
  sessionId: string,
  request: TerminalStreamRequest,
  onEvent: (event: TerminalStreamEvent) => void,
  onError?: (err: Error) => void
): () => void {
  const controller = new AbortController();
  const url = `${BASE_URL}/agent/${encodeURIComponent(agentId)}/session/${encodeURIComponent(sessionId)}/terminal/stream`;

  (async () => {
    try {
      const res = await fetch(url, {
        method: "POST",
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify(request),
      });

      if (!res.ok) {
        throw new Error(`Terminal stream failed with status ${res.status}`);
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
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data:")) continue;
          const dataStr = trimmed.slice(5).trim();
          if (!dataStr) continue;

          try {
            const event: TerminalStreamEvent = JSON.parse(dataStr);
            onEvent(event);
          } catch (e) {
            console.warn("Failed to parse terminal stream event:", dataStr, e);
          }
        }
      }

      if (buffer.trim().startsWith("data:")) {
        try {
          const dataStr = buffer.trim().slice(5).trim();
          if (dataStr) {
            const event: TerminalStreamEvent = JSON.parse(dataStr);
            onEvent(event);
          }
        } catch (e) {
          console.warn("Failed to parse final terminal stream event:", buffer, e);
        }
      }
    } catch (err: any) {
      if (err.name !== "AbortError" && onError) {
        onError(err);
      }
    }
  })();

  return () => {
    controller.abort();
  };
}



