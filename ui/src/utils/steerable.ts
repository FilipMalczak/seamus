import type {
  SteerableEmptyQueueStrategy,
  SteerableError,
  SteerableResponse,
  SteerableToolCall,
} from "../api/types";

/** Predefined steerable error fixtures for common simulated failure scenarios. */
export interface SteerableErrorPreset {
  id: string;
  label: string;
  description: string;
  error: SteerableError;
}

export const STEERABLE_ERROR_PRESETS: SteerableErrorPreset[] = [
  {
    id: "network_timeout",
    label: "Network Timeout",
    description: "Simulates transient network/API timeout (APITimeoutError 408)",
    error: {
      error_type: "APITimeoutError",
      message: "Request timed out while waiting for response.",
      status_code: 408,
    },
  },
  {
    id: "out_of_cash",
    label: "Out of Cash (Quota Exceeded)",
    description: "Simulates depleted provider balance / billing limit (RateLimitError 429)",
    error: {
      error_type: "RateLimitError",
      message: "You exceeded your current quota, please check your plan and billing details.",
      status_code: 429,
    },
  },
  {
    id: "rate_limit",
    label: "Rate Limit Exceeded",
    description: "Simulates temporary API rate limit spike (RateLimitError 429)",
    error: {
      error_type: "RateLimitError",
      message: "Rate limit reached for requests. Please slow down your requests.",
      status_code: 429,
    },
  },
  {
    id: "auth_failure",
    label: "Authentication Failed",
    description: "Simulates invalid or expired API credentials (AuthenticationError 401)",
    error: {
      error_type: "AuthenticationError",
      message: "Incorrect API key provided or token expired.",
      status_code: 401,
    },
  },
  {
    id: "server_error",
    label: "Internal Server Error",
    description: "Simulates temporary provider 500 error (InternalServerError 500)",
    error: {
      error_type: "InternalServerError",
      message: "The server had an error processing your request. Please try again.",
      status_code: 500,
    },
  },
];

/** The placeholder used for an untouched tool-call argument field. */
export const EMPTY_TOOL_ARGS = "{}";

/** A single in-progress tool call in the Inspector composer. */
export interface ToolCallDraft {
  id: string;
  name: string;
  args: string;
}

/** Outcome of validating the tool-call drafts of a composer. */
export interface ToolCallDraftsResult {
  /** The valid, ready-to-queue tool calls, in draft order. */
  calls: SteerableToolCall[];
  /** True when at least one draft is invalid and the response cannot be queued. */
  invalid: boolean;
  /** A human-readable description of the first problem found, if any. */
  error: string | null;
}

/**
 * Parse a single tool-call draft into a tool call.
 *
 * An untouched draft (no name and the default arguments) yields `null`.
 * A draft with a name but malformed JSON arguments is reported as an error.
 */
export function parseToolCallDraft(
  draft: ToolCallDraft
): { call: SteerableToolCall | null; error: string | null } {
  const name = draft.name.trim();
  const rawArgs = draft.args.trim();
  const filledIn = name.length > 0 || rawArgs !== EMPTY_TOOL_ARGS;

  if (!filledIn) {
    return { call: null, error: null };
  }
  if (!name) {
    return { call: null, error: "Tool name is required." };
  }
  if (!rawArgs) {
    return { call: { name, args: {} }, error: null };
  }
  try {
    const parsed = JSON.parse(rawArgs);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { call: null, error: "Tool arguments must be a JSON object." };
    }
    return { call: { name, args: parsed as Record<string, unknown> }, error: null };
  } catch {
    return { call: null, error: "Tool arguments must be valid JSON." };
  }
}

/**
 * Validate every tool-call draft of a composer at once.
 *
 * Returns the tool calls that can be queued and the first error found, so the
 * composer can block queueing while a draft is malformed.
 */
export function buildToolCallDrafts(
  drafts: ToolCallDraft[]
): ToolCallDraftsResult {
  const calls: SteerableToolCall[] = [];
  for (const draft of drafts) {
    const { call, error } = parseToolCallDraft(draft);
    if (error) {
      return { calls: [], invalid: true, error };
    }
    if (call) {
      calls.push(call);
    }
  }
  return { calls, invalid: false, error: null };
}

/** The on-disk shape of an exported steerable queue. */
export interface SteerableQueueFile {
  instance_id: string;
  exported_at: string;
  strategy: SteerableEmptyQueueStrategy;
  responses: SteerableResponse[];
}

/**
 * Serialize a queue into the exported file format.
 *
 * The envelope carries the originating instance and strategy so an exported
 * queue can be identified later, even though only the responses are replayed.
 */
export function serializeSteerableQueue(
  instanceId: string,
  responses: SteerableResponse[],
  strategy: SteerableEmptyQueueStrategy,
  exportedAt: string = new Date().toISOString()
): string {
  const payload: SteerableQueueFile = {
    instance_id: instanceId,
    exported_at: exportedAt,
    strategy,
    responses,
  };
  return `${JSON.stringify(payload, null, 2)}\n`;
}

/** Outcome of parsing an uploaded queue file. */
export type SteerableQueueParseResult =
  | { ok: true; responses: SteerableResponse[] }
  | { ok: false; error: string };

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseToolCalls(value: unknown, index: number): SteerableToolCall[] {
  if (value === undefined || value === null) {
    return [];
  }
  if (!Array.isArray(value)) {
    throw new Error(`Response #${index + 1} has a non-list "tool_calls" field.`);
  }
  return value.map((raw, callIndex) => {
    if (!isPlainObject(raw)) {
      throw new Error(
        `Response #${index + 1} tool call #${callIndex + 1} is not an object.`
      );
    }
    const name = raw.name;
    if (typeof name !== "string" || name.trim().length === 0) {
      throw new Error(
        `Response #${index + 1} tool call #${callIndex + 1} is missing a name.`
      );
    }
    const args = raw.args;
    if (args !== undefined && args !== null && !isPlainObject(args)) {
      throw new Error(
        `Response #${index + 1} tool call #${callIndex + 1} has non-object arguments.`
      );
    }
    return { name: name.trim(), args: (args as Record<string, unknown>) ?? {} };
  });
}

function parseError(value: unknown, index: number): SteerableError | null {
  if (value === undefined || value === null) {
    return null;
  }
  if (!isPlainObject(value)) {
    throw new Error(`Response #${index + 1} has a non-object "error" field.`);
  }
  const errorType = value.error_type;
  if (errorType !== undefined && errorType !== null && typeof errorType !== "string") {
    throw new Error(`Response #${index + 1} has a non-string "error_type" field.`);
  }
  const message = value.message;
  if (message !== undefined && message !== null && typeof message !== "string") {
    throw new Error(`Response #${index + 1} has a non-string error "message" field.`);
  }
  const statusCode = value.status_code;
  if (statusCode !== undefined && statusCode !== null && typeof statusCode !== "number") {
    throw new Error(`Response #${index + 1} has a non-numeric "status_code" field.`);
  }
  return {
    error_type: (errorType as string | undefined)?.trim() || "RuntimeError",
    message: (message as string | undefined)?.trim() || "Simulated steerable error",
    status_code: (statusCode as number | null | undefined) ?? null,
  };
}

function parseResponse(raw: unknown, index: number): SteerableResponse {
  if (!isPlainObject(raw)) {
    throw new Error(`Response #${index + 1} is not an object.`);
  }
  const text = raw.text;
  if (text !== undefined && text !== null && typeof text !== "string") {
    throw new Error(`Response #${index + 1} has a non-string "text" field.`);
  }
  const reasoning = raw.reasoning;
  if (reasoning !== undefined && reasoning !== null && typeof reasoning !== "string") {
    throw new Error(`Response #${index + 1} has a non-string "reasoning" field.`);
  }
  const error = parseError(raw.error, index);
  return {
    text: (text as string | null | undefined) ?? null,
    reasoning: (reasoning as string | null | undefined) ?? null,
    tool_calls: parseToolCalls(raw.tool_calls, index),
    ...(error ? { error } : {}),
  };
}

/**
 * Parse an uploaded queue file.
 *
 * Accepts both the exported envelope (`{"responses": [...]}`) and a bare list
 * of responses, so hand-written scripts work too.
 */
export function parseSteerableQueueFile(text: string): SteerableQueueParseResult {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { ok: false, error: "The file is not valid JSON." };
  }

  let rawResponses: unknown;
  if (Array.isArray(parsed)) {
    rawResponses = parsed;
  } else if (isPlainObject(parsed) && "responses" in parsed) {
    rawResponses = parsed.responses;
  } else {
    return {
      ok: false,
      error: 'The file must contain a "responses" list or a list of responses.',
    };
  }

  if (!Array.isArray(rawResponses)) {
    return { ok: false, error: 'The "responses" field must be a list.' };
  }

  try {
    const responses = rawResponses.map((raw, index) => parseResponse(raw, index));
    return { ok: true, responses };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : "The file is malformed.",
    };
  }
}

/** Build the download filename for an exported queue. */
export function steerableQueueFilename(instanceId: string): string {
  const safe = instanceId.replace(/[^a-zA-Z0-9._-]+/g, "-");
  return `steerable-queue-${safe}.json`;
}

/** How an uploaded queue file changes the queue it is uploaded into. */
export type SteerableUploadMode = "replace" | "extend";

/** The upload modes offered by the Inspector, in display order. */
export const STEERABLE_UPLOAD_MODES: SteerableUploadMode[] = ["replace", "extend"];

/** Human-readable labels for the upload modes. */
export const STEERABLE_UPLOAD_MODE_LABELS: Record<SteerableUploadMode, string> = {
  replace: "Replace",
  extend: "Extend",
};

/** The queue mutation an upload performs. */
export type SteerableUploadPlan =
  | { kind: "replace"; responses: SteerableResponse[] }
  | { kind: "append"; responses: SteerableResponse[] };

/**
 * Plan the queue mutation for an uploaded file.
 *
 * `replace` swaps the whole queue for the uploaded responses, while `extend`
 * keeps the existing responses and appends the uploaded ones after them. The
 * plan names the backend operation so the caller never has to re-derive the
 * meaning of the mode.
 */
export function planSteerableUpload(
  mode: SteerableUploadMode,
  responses: SteerableResponse[]
): SteerableUploadPlan {
  return { kind: mode === "extend" ? "append" : "replace", responses };
}
