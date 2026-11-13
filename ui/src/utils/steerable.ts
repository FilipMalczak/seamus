import type {
  SteerableEmptyQueueStrategy,
  SteerableResponse,
  SteerableToolCall,
} from "../api/types";

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
  return {
    text: (text as string | null | undefined) ?? null,
    reasoning: (reasoning as string | null | undefined) ?? null,
    tool_calls: parseToolCalls(raw.tool_calls, index),
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
