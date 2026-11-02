export type InferenceConfig = {
  format: "openai";
  base_url: string;
  api_key?: string | null;
};

export type AgentConfig = {
  inference: InferenceConfig;
  model_name: string;
  system_prompt?: string | null;
};

export type ConfigTemplateResponse = {
  config: AgentConfig;
  is_complete: boolean;
};

export type SystemSettings = {
  skill_directories: string[];
};

export type SystemSettingsResponse = {
  settings: SystemSettings;
};

export type AgentStatus = "AWAITING_USER" | "AWAITING_LLM" | "EXECUTING_TOOL" | "ERROR";

export type SessionStatus = "ACTIVE" | "KILLED" | "FAILED";

export type SessionBranchProvenance = {
  parent_session_id: string;
  parent_message_id: string;
  parent_session_name: string | null;
  branched_at: string;
};

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
  status: SessionStatus;
  provenance?: SessionBranchProvenance | null;
  lineage?: SessionBranchProvenance[];
};

export type SessionDetail = {
  id: string;
  agent_id: string;
  name: string | null;
  created_at: string;
  last_touched_at: string;
  config: AgentConfig;
  status: SessionStatus;
  provenance?: SessionBranchProvenance | null;
  lineage?: SessionBranchProvenance[];
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

export type ToolCallStatus = "pending" | "wip" | "done" | "error";

export type ToolCallRecord = {
  id: string;
  name: string;
  status?: ToolCallStatus;
  args?: Record<string, unknown> | string;
  rawArgs?: string;
  result?: unknown;
};

export type MessagePart =
  | { type: "reasoning"; id: string; content: string; isStreaming?: boolean }
  | { type: "tool_call"; id: string; toolCall: ToolCallRecord }
  | { type: "text"; id: string; content: string };

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  reasoning?: string;
  isReasoning?: boolean;
  toolCalls?: ToolCallRecord[];
  parts?: MessagePart[];
  timestamp: string;
};

export interface SystemLogfireInfo {
  enabled: boolean;
  service_name: string;
  url: string | null;
}

export interface SystemGiteaInfo {
  enabled: boolean;
  url: string | null;
  owner: string | null;
}

export interface SystemInfoResponse {
  logfire: SystemLogfireInfo;
  gitea: SystemGiteaInfo;
}

export type SessionDiffResponse = {
  agent_id: string;
  session_id: string;
  pr_number: number | null;
  pr_url: string | null;
  diff: string;
};

export interface ToolInspectInfo {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  backend: string;
}

export interface SubAgentInspectInfo {
  name: string;
  description: string;
  subagent_type?: string | null;
  model?: string | null;
}

export interface GitInspectInfo {
  branch: string;
  commit_sha: string | null;
  commit_message: string | null;
  commit_time: string | null;
  repo_name: string;
  gitea_url: string | null;
}

export interface InferenceInspectInfo {
  model_name: string;
  format: string;
  base_url: string;
  api_key_configured: boolean;
}

export interface PromptInspectInfo {
  composite: string;
  scaffold: string;
  custom: string;
}

export interface MessageHistoryItem {
  id: string | null;
  role: string;
  content: string | null;
  reasoning?: string | null;
  tool_calls?: Array<Record<string, unknown>> | null;
  tool_call_id?: string | null;
}

export interface HistoryInspectInfo {
  message_count: number;
  checkpoint_step: number;
  messages: MessageHistoryItem[];
}

export interface WorkspaceInspectInfo {
  operational_dir: string;
  files: string[];
}

export interface AgentInspectReport {
  agent_id: string;
  agent_name: string | null;
  session_id: string;
  session_name: string | null;
  thread_id: string;
  thread_name: string | null;
  status: AgentStatus;
  git: GitInspectInfo;
  inference: InferenceInspectInfo;
  prompts: PromptInspectInfo;
  tools: ToolInspectInfo[];
  subagents: SubAgentInspectInfo[];
  history: HistoryInspectInfo;
  workspace: WorkspaceInspectInfo;
}


