export type InferenceConfig = {
  format: "openai";
  base_url: string;
  api_key?: string | null;
};

export type AgentConfig = {
  inference: InferenceConfig;
  model_name: string;
};

export type ConfigTemplateResponse = {
  config: AgentConfig;
  is_complete: boolean;
};

export type AgentStatus = "AWAITING_USER" | "AWAITING_LLM" | "EXECUTING_TOOL" | "ERROR";

export type ThreadInfo = {
  id: string;
  name: string | null;
  created_at: string;
  last_touched_at: string;
  is_open: boolean;
  status: AgentStatus;
};

export type SessionSummary = {
  id: string;
  agent_id: string;
  name: string | null;
  created_at: string;
  last_touched_at: string;
  config: AgentConfig;
};

export type SessionDetail = {
  id: string;
  agent_id: string;
  name: string | null;
  created_at: string;
  last_touched_at: string;
  config: AgentConfig;
  threads: ThreadInfo[];
};

export type AgentSummary = {
  id: string;
  name: string | null;
  created_at: string;
  last_touched_at: string;
  config: AgentConfig;
};

export type AgentDetail = {
  id: string;
  name: string | null;
  created_at: string;
  last_touched_at: string;
  config: AgentConfig;
  sessions: SessionSummary[];
};

export type ToolCallRecord = {
  id: string;
  name: string;
  args?: Record<string, unknown>;
  result?: unknown;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  toolCalls?: ToolCallRecord[];
  timestamp: string;
};

export interface SystemLogfireInfo {
  enabled: boolean;
  service_name: string;
  url: string | null;
}

export interface SystemInfoResponse {
  logfire: SystemLogfireInfo;
}


