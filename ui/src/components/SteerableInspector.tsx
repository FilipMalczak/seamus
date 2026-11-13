import { useCallback, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Brain,
  Download,
  ListOrdered,
  Loader2,
  MessageSquare,
  Plus,
  Trash2,
  Upload,
  Wrench,
} from "lucide-react";
import {
  appendSteerableResponses,
  replaceSteerableResponses,
  updateSteerableStrategy,
} from "../api/client";
import type {
  SteerableEmptyQueueStrategy,
  SteerableInspectInfo,
  SteerableResponse,
} from "../api/types";
import {
  buildToolCallDrafts,
  EMPTY_TOOL_ARGS,
  parseSteerableQueueFile,
  serializeSteerableQueue,
  steerableQueueFilename,
  type ToolCallDraft,
} from "../utils/steerable";

interface SteerableInspectorProps {
  agentId: string | null;
  sessionId: string | null;
  instances: SteerableInspectInfo[];
  onChanged: () => void;
}

const STRATEGY_LABELS: Record<SteerableEmptyQueueStrategy, string> = {
  wait: "Wait for a scripted response",
  error: "Error on empty queue",
  repeat: "Repeat the default response",
};

const STRATEGY_ORDER: SteerableEmptyQueueStrategy[] = ["wait", "error", "repeat"];

interface DraftState {
  text: string;
  reasoning: string;
  toolCalls: ToolCallDraft[];
}

const EMPTY_DRAFT: DraftState = {
  text: "",
  reasoning: "",
  toolCalls: [],
};

let draftCounter = 0;

function nextDraftId(): string {
  draftCounter += 1;
  return `tc-${draftCounter}`;
}

function newToolCallDraft(): ToolCallDraft {
  return { id: nextDraftId(), name: "", args: EMPTY_TOOL_ARGS };
}

function downloadTextFile(filename: string, text: string): void {
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

interface InstanceCardProps {
  agentId: string;
  sessionId: string;
  instance: SteerableInspectInfo;
  busy: boolean;
  onRun: (
    instanceId: string,
    action: () => Promise<unknown>,
    onSuccess?: () => void
  ) => void;
  onError: (message: string) => void;
}

function SteerableInstanceCard({
  agentId,
  sessionId,
  instance,
  busy,
  onRun,
  onError,
}: InstanceCardProps) {
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const responses = instance.responses ?? [];

  const toolDrafts = useMemo(
    () => buildToolCallDrafts(draft.toolCalls),
    [draft.toolCalls]
  );

  const canSubmit =
    !toolDrafts.invalid &&
    (draft.text.trim().length > 0 ||
      draft.reasoning.trim().length > 0 ||
      toolDrafts.calls.length > 0);

  const handleAppend = () => {
    if (!canSubmit) return;
    const response: SteerableResponse = {
      text: draft.text.trim() || null,
      reasoning: draft.reasoning.trim() || null,
      tool_calls: toolDrafts.calls,
    };
    onRun(
      instance.instance_id,
      () =>
        appendSteerableResponses(agentId, sessionId, instance.instance_id, [response]),
      // Reset the whole composer, including the tool-call fields, so the next
      // queued response does not repeat the tool calls just submitted. Only
      // after the append succeeded, so a failed request keeps the draft.
      () => setDraft(EMPTY_DRAFT)
    );
  };

  const handleRemove = (index: number) => {
    const next = responses.filter((_, idx) => idx !== index);
    onRun(instance.instance_id, () =>
      replaceSteerableResponses(agentId, sessionId, instance.instance_id, next)
    );
  };

  const handleAddToolCall = () => {
    setDraft((prev) => ({
      ...prev,
      toolCalls: [...prev.toolCalls, newToolCallDraft()],
    }));
  };

  const handleUpdateToolCall = (
    id: string,
    patch: Partial<Omit<ToolCallDraft, "id">>
  ) => {
    setDraft((prev) => ({
      ...prev,
      toolCalls: prev.toolCalls.map((call) =>
        call.id === id ? { ...call, ...patch } : call
      ),
    }));
  };

  const handleRemoveToolCall = (id: string) => {
    setDraft((prev) => ({
      ...prev,
      toolCalls: prev.toolCalls.filter((call) => call.id !== id),
    }));
  };

  const handleDownload = () => {
    const content = serializeSteerableQueue(
      instance.instance_id,
      responses,
      instance.strategy
    );
    downloadTextFile(steerableQueueFilename(instance.instance_id), content);
  };

  const handleUpload = async (file: File) => {
    let text: string;
    try {
      text = await file.text();
    } catch {
      onError("Could not read the selected file.");
      return;
    }
    const parsed = parseSteerableQueueFile(text);
    if (!parsed.ok) {
      onError(parsed.error);
      return;
    }
    onRun(instance.instance_id, () =>
      replaceSteerableResponses(
        agentId,
        sessionId,
        instance.instance_id,
        parsed.responses
      )
    );
  };

  const toolListId = `steerable-known-tools-${instance.instance_id}`;

  return (
    <div className="steerable-instance-card">
      <div className="tool-card-header">
        <div className="tool-card-title-group">
          {instance.role === "daemon" ? (
            <Brain className="size-4 text-violet-400" />
          ) : (
            <MessageSquare className="size-4 text-sky-400" />
          )}
          <h4 className="tool-name">{instance.instance_id}</h4>
          <span className="tool-backend-badge backend-harness">{instance.role}</span>
          <span className="todo-impl-badge impl-deepagents">{responses.length} queued</span>
        </div>
        <div className="steerable-header-actions">
          <button
            type="button"
            className="btn-secondary btn-sm"
            disabled={busy || responses.length === 0}
            onClick={handleDownload}
            title="Download this queue as a JSON file"
          >
            <Download className="size-3.5" />
            <span>Download</span>
          </button>
          <button
            type="button"
            className="btn-secondary btn-sm"
            disabled={busy}
            onClick={() => fileInputRef.current?.click()}
            title="Upload a JSON queue file, replacing the current queue"
          >
            <Upload className="size-3.5" />
            <span>Upload</span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            className="steerable-file-input"
            onChange={(e) => {
              const file = e.target.files?.[0];
              // Reset the input so re-picking the same file still fires a change.
              e.target.value = "";
              if (file) {
                void handleUpload(file);
              }
            }}
          />
          <button
            type="button"
            className="btn-secondary btn-sm"
            disabled={busy || responses.length === 0}
            onClick={() =>
              onRun(instance.instance_id, () =>
                replaceSteerableResponses(agentId, sessionId, instance.instance_id, [])
              )
            }
          >
            <Trash2 className="size-3.5" />
            <span>Clear Queue</span>
          </button>
        </div>
      </div>

      <div className="steerable-strategy-row">
        <span className="text-xs text-neutral-400 font-medium">Empty Queue Strategy:</span>
        <select
          className="steerable-strategy-select"
          value={instance.strategy}
          disabled={busy}
          onChange={(e) =>
            onRun(instance.instance_id, () =>
              updateSteerableStrategy(
                agentId,
                sessionId,
                instance.instance_id,
                e.target.value as SteerableEmptyQueueStrategy
              )
            )
          }
        >
          {STRATEGY_ORDER.map((strategy) => (
            <option key={strategy} value={strategy}>
              {STRATEGY_LABELS[strategy]}
            </option>
          ))}
        </select>
      </div>

      {instance.strategy === "repeat" && (
        <div className="steerable-strategy-row">
          <span className="text-xs text-neutral-400 font-medium">Default Response:</span>
          <input
            className="steerable-default-input"
            defaultValue={instance.default_response}
            disabled={busy}
            onBlur={(e) =>
              onRun(instance.instance_id, () =>
                updateSteerableStrategy(
                  agentId,
                  sessionId,
                  instance.instance_id,
                  instance.strategy,
                  e.target.value
                )
              )
            }
          />
        </div>
      )}

      {responses.length === 0 ? (
        <div className="steerable-empty-queue">
          Queue is empty. The next model turn will use the{" "}
          <strong>{STRATEGY_LABELS[instance.strategy]}</strong> behaviour.
        </div>
      ) : (
        <ol className="steerable-queue-list">
          {responses.map((response, index) => (
            <li key={index} className="steerable-queue-item">
              <div className="steerable-queue-index">#{index + 1}</div>
              <div className="steerable-queue-body">
                {response.reasoning && (
                  <div className="steerable-queue-reasoning">
                    <Brain className="size-3.5" />
                    <span>{response.reasoning}</span>
                  </div>
                )}
                {response.text && <div className="steerable-queue-text">{response.text}</div>}
                {(response.tool_calls ?? []).map((call, callIdx) => (
                  <div key={callIdx} className="steerable-queue-tool">
                    <Wrench className="size-3.5" />
                    <span className="steerable-queue-tool-name">{call.name}</span>
                    <code>{JSON.stringify(call.args)}</code>
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="btn-tool-toggle"
                disabled={busy}
                onClick={() => handleRemove(index)}
                title="Remove this scripted response"
              >
                <Trash2 className="size-3.5" />
              </button>
            </li>
          ))}
        </ol>
      )}

      <div className="steerable-composer">
        <div className="steerable-composer-row">
          <label className="steerable-composer-label">
            <MessageSquare className="size-3.5" />
            <span>Assistant Text</span>
          </label>
          <textarea
            className="steerable-composer-textarea"
            value={draft.text}
            disabled={busy}
            placeholder="Text the model should reply with..."
            onChange={(e) => setDraft((prev) => ({ ...prev, text: e.target.value }))}
          />
        </div>

        <div className="steerable-composer-row">
          <label className="steerable-composer-label">
            <Brain className="size-3.5" />
            <span>Reasoning</span>
          </label>
          <textarea
            className="steerable-composer-textarea"
            value={draft.reasoning}
            disabled={busy}
            placeholder="Reasoning the model should emit before replying..."
            onChange={(e) => setDraft((prev) => ({ ...prev, reasoning: e.target.value }))}
          />
        </div>

        <div className="steerable-composer-row">
          <label className="steerable-composer-label">
            <Wrench className="size-3.5" />
            <span>Tool Calls</span>
          </label>
          {draft.toolCalls.length === 0 ? (
            <span className="text-xs text-neutral-500">
              No tool calls in this response.
            </span>
          ) : (
            <div className="steerable-tool-call-list">
              {draft.toolCalls.map((call, callIdx) => (
                <div key={call.id} className="steerable-tool-call-fields">
                  <span className="steerable-tool-call-index">#{callIdx + 1}</span>
                  <input
                    className="steerable-tool-input"
                    value={call.name}
                    disabled={busy}
                    placeholder="tool name"
                    list={toolListId}
                    onChange={(e) =>
                      handleUpdateToolCall(call.id, { name: e.target.value })
                    }
                  />
                  <datalist id={toolListId}>
                    {(instance.known_tools ?? []).map((toolName) => (
                      <option key={toolName} value={toolName} />
                    ))}
                  </datalist>
                  <input
                    className="steerable-tool-args-input"
                    value={call.args}
                    disabled={busy}
                    placeholder='{"key": "value"}'
                    onChange={(e) =>
                      handleUpdateToolCall(call.id, { args: e.target.value })
                    }
                  />
                  <button
                    type="button"
                    className="btn-tool-toggle"
                    disabled={busy}
                    onClick={() => handleRemoveToolCall(call.id)}
                    title="Remove this tool call"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="steerable-composer-actions">
            <button
              type="button"
              className="btn-secondary btn-sm"
              disabled={busy}
              onClick={handleAddToolCall}
            >
              <Plus className="size-3.5" />
              <span>Add tool call</span>
            </button>
          </div>
          {toolDrafts.error && (
            <span className="steerable-composer-error">{toolDrafts.error}</span>
          )}
        </div>

        <div className="steerable-composer-actions">
          <button
            type="button"
            className="btn-primary btn-sm"
            disabled={busy || !canSubmit}
            onClick={handleAppend}
          >
            {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Plus className="size-3.5" />}
            <span>Queue Response</span>
          </button>
        </div>
      </div>
    </div>
  );
}

export function SteerableInspector({
  agentId,
  sessionId,
  instances,
  onChanged,
}: SteerableInspectorProps) {
  const [busyInstance, setBusyInstance] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    (
      instanceId: string,
      action: () => Promise<unknown>,
      onSuccess?: () => void
    ) => {
      if (!agentId || !sessionId) return;
      setBusyInstance(instanceId);
      setError(null);
      void action()
        .then(() => {
          onChanged();
          onSuccess?.();
        })
        .catch((err: any) => {
          setError(err?.message || "Failed to update the steerable model");
        })
        .finally(() => {
          setBusyInstance(null);
        });
    },
    [agentId, sessionId, onChanged]
  );

  if (!agentId || !sessionId) {
    return (
      <div className="inspector-empty-state">
        <ListOrdered className="size-8 text-neutral-500 mb-2" />
        <p>No session selected.</p>
      </div>
    );
  }

  if (instances.length === 0) {
    return (
      <div className="inspector-empty-state">
        <ListOrdered className="size-8 text-neutral-500 mb-2" />
        <p>No steerable models are registered for this session.</p>
        <span className="text-xs text-neutral-400">
          Set the session's inference format to <code>steerable</code> to script model
          responses manually.
        </span>
      </div>
    );
  }

  return (
    <div className="inspector-steerable-panel">
      <div className="todos-panel-header">
        <div className="todos-setting-info">
          <span className="text-xs text-neutral-400 font-medium">Steerable Models:</span>
          <span className="todo-impl-badge impl-deepagents">{instances.length}</span>
        </div>
        <span className="text-xs text-neutral-400">
          Scripted responses are consumed in order, one per model turn.
        </span>
      </div>

      {error && (
        <div className="steerable-error">
          <AlertCircle className="size-4 text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      <div className="steerable-instance-list">
        {instances.map((instance) => (
          <SteerableInstanceCard
            key={instance.instance_id}
            agentId={agentId}
            sessionId={sessionId}
            instance={instance}
            busy={busyInstance === instance.instance_id}
            onRun={run}
            onError={setError}
          />
        ))}
      </div>
    </div>
  );
}
