export type ReasoningEffort =
  | "default"
  | "none"
  | "minimal"
  | "low"
  | "medium"
  | "high"
  | "xhigh";

export type InferenceConfig = {
  format: "openai" | "ollama";
  base_url: string;
  api_key?: string | null;
  reasoning_effort?: ReasoningEffort;
};

export type TodoImplementation = "none" | "deepagents" | "seamus";

export type SkillsImplementation = "none" | "deepagents" | "seamus";

export type WebSearchImplementation = "none" | "duckduckgo";

export type OperationalMode = "chat" | "plan";

export type ExternalRepositoryConfig = {
  id?: string;
  url: string;
  branch?: string;
  credentials?: string | null;
};

export type DaemonNamingConfig = {
  enabled?: boolean;
  provider?: InferenceConfig | null;
  model?: string | null;
};

export type DaemonsConfig = {
  naming?: DaemonNamingConfig;
};

export type AgentConfig = {
  inference: InferenceConfig;
  model_name: string;
  mode?: OperationalMode | string;
  system_prompt?: string | null;
  todo_implementation?: TodoImplementation;
  skills_implementation?: SkillsImplementation;
  web_search?: WebSearchImplementation;
  thread_message_overlap?: number;
  repositories?: ExternalRepositoryConfig[];
  sandbox_image?: string | null;
  daemons?: DaemonsConfig;
  rules_patterns?: string[];
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
  mode?: string;
  phase?: string | null;
  mode_label?: string;
};

export type SessionSummary = {
  id: string;
  agent_id: string;
  name: string | null;
  created_at: string;
  last_touched_at: string;
  config: AgentConfig;
  status: SessionStatus;
  active_plan_id?: string | null;
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
  active_plan_id?: string | null;
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
  timestamp?: string;
};

export const SYNTHETIC_MESSAGE_INDICATOR = "<SYNTHETIC MESSAGE INDICATOR>";

/**
 * Minimum number of consecutive messages/bubbles in a streak required before
 * displaying top-left sequence indices (#1, #2, ...).
 */
export const BUBBLE_SEQUENCE_THRESHOLD = 5;

export interface ManifestButton {
  id: string;
  mode: "set" | "append";
  clicks: number | "*";
  unblocking: boolean;
  closing: boolean;
}

export interface ArtifactManifest {
  name: string;
  exposition: "embedded" | "tabbed";
  blocking: boolean;
  commentable: boolean;
  buttons: ManifestButton[];
  title?: string | null;
}

export interface ArtifactState {
  last_event?: Record<string, unknown> | null;
  dataModel?: Record<string, unknown>;
  clicksLeft: Record<string, number | "*">;
}

export interface ClickResult {
  artifact_id: string;
  button_id: string;
  event?: string;
  timestamp: string | number;
  context?: Record<string, unknown>;
  data?: Record<string, unknown>;
  comments?: Array<Record<string, unknown>>;
  raw_context?: Record<string, unknown>;
}

export interface ArtifactInfo {
  family: string;
  uuid: string;
  title?: string | null;
  manifest: ArtifactManifest;
  body: Array<Record<string, unknown>>;
  state: ArtifactState;
  is_closed: boolean;
  // Transitional backward-compatible fields:
  kind: string;
  name: string;
  card?: Record<string, unknown>;
  data?: Record<string, unknown> | null;
}

export type MessagePart =
  | { type: "reasoning"; id: string; content: string; isStreaming?: boolean; timestamp?: string }
  | { type: "tool_call"; id: string; toolCall: ToolCallRecord; timestamp?: string }
  | { type: "artifact"; id: string; artifact: ArtifactInfo; timestamp?: string }
  | { type: "text"; id: string; content: string; timestamp?: string };

export interface ThreadTransitionInfo {
  threadId: string;
  threadName?: string | null;
  mode?: string;
  phase?: string | null;
  modeLabel?: string;
}

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
  reasoning?: string;
  isReasoning?: boolean;
  toolCalls?: ToolCallRecord[];
  parts?: MessagePart[];
  timestamp: string;
  threadTransition?: ThreadTransitionInfo;
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

export interface SystemVaultInfo {
  enabled: boolean;
  url: string | null;
  login_url?: string | null;
}

export interface SystemInfoResponse {
  logfire: SystemLogfireInfo;
  gitea: SystemGiteaInfo;
  vault?: SystemVaultInfo;
}

export interface VaultSecretItem {
  path: string;
  keys: string[];
  version?: number | null;
}

export interface VaultSecretListResponse {
  secrets: VaultSecretItem[];
}

export interface VaultSecretDetailResponse {
  path: string;
  keys: string[];
  current_version: number | null;
  versions: number[];
}

export interface VaultTokenResponse {
  token: string | null;
}

export type SessionDiffResponse = {
  agent_id: string;
  session_id: string;
  pr_number: number | null;
  pr_url: string | null;
  diff: string;
};

export interface ToolLabelInfo {
  title: string;
  color: string;
}

export interface ToolInspectInfo {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  backend: string;
  category?: string;
  labels?: ToolLabelInfo[];
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

export interface TodoInspectItem {
  id?: string | null;
  content: string;
  status: string;
  parent_id?: string | null;
  path?: string | null;
  depth?: number;
}

export interface SkillInspectInfo {
  name: string;
  description: string;
  origin_layer: string;
  sandbox_path: string;
  host_path?: string | null;
  content: string;
  active: boolean;
  loaded?: boolean;
  allowed_tools?: string[];
}

export interface MountedRepoInspectInfo {
  id: string;
  mount_path: string;
  url: string;
  branch: string;
  credentials_configured: boolean;
  project_id?: string;
  gitea_repo_name?: string | null;
  gitea_repo_url?: string | null;
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
  todos?: TodoInspectItem[];
  todo_implementation?: TodoImplementation;
  skills?: SkillInspectInfo[];
  skills_implementation?: SkillsImplementation;
  web_search?: WebSearchImplementation;
  subagents: SubAgentInspectInfo[];
  mounted_repositories?: MountedRepoInspectInfo[];
  history: HistoryInspectInfo;
  workspace: WorkspaceInspectInfo;
}

export interface TerminalStreamRequest {
  command: string;
  working_directory?: string | null;
  timeout?: number | null;
}

export type TerminalStreamEvent =
  | { type: "stdout"; data: string }
  | { type: "stderr"; data: string }
  | { type: "exit"; exit_code: number; working_directory: string }
  | { type: "error"; message: string };

export interface TerminalInfoResponse {
  agent_id: string;
  session_id: string;
  operational_dir: string;
  status: string;
}



