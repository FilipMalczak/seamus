import { useCallback, useMemo, useState } from "react";
import {
  AlertCircle,
  Brain,
  ListOrdered,
  Loader2,
  MessageSquare,
  Plus,
  Trash2,
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
  SteerableToolCall,
} from "../api/types";

interface SteerableInspectorProps {
  agentId: string | null;
  sessionId: string | null;
  instances: SteerableInspectInfo[];
  onChanged: () => void;
}

const STRATEGY_LABELS: Record<SteerableEmptyQueueStrategy, string> = {
  error: "Error on empty queue",
  wait: "Wait for a scripted response",
  repeat: "Repeat the default response",
};

interface DraftState {
  text: string;
  reasoning: string;
  toolName: string;
  toolArgs: string;
}

const EMPTY_DRAFT: DraftState = {
  text: "",
  reasoning: "",
  toolName: "",
  toolArgs: "{}",
};

function parseToolCall(toolName: string, rawArgs: string): SteerableToolCall | null {
  const name = toolName.trim();
  if (!name) return null;
  const raw = rawArgs.trim();
  if (!raw) return { name, args: {} };
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    return { name, args: parsed as Record<string, unknown> };
  } catch {
    return null;
  }
}

interface InstanceCardProps {
  agentId: string;
  sessionId: string;
  instance: SteerableInspectInfo;
  busy: boolean;
  onRun: (instanceId: string, action: () => Promise<unknown>) => void;
}

function SteerableInstanceCard({
  agentId,
  sessionId,
  instance,
  busy,
  onRun,
}: InstanceCardProps) {
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const responses = instance.responses ?? [];

  const parsedToolCall = useMemo(
    () => parseToolCall(draft.toolName, draft.toolArgs),
    [draft.toolName, draft.toolArgs]
  );

  const toolArgsInvalid = draft.toolName.trim().length > 0 && parsedToolCall === null;

  const canSubmit =
    draft.text.trim().length > 0 ||
    draft.reasoning.trim().length > 0 ||
    parsedToolCall !== null;

  const handleAppend = () => {
    if (!canSubmit) return;
    const response: SteerableResponse = {
      text: draft.text.trim() || null,
      reasoning: draft.reasoning.trim() || null,
      tool_calls: parsedToolCall ? [parsedToolCall] : [],
    };
    onRun(instance.instance_id, () =>
      appendSteerableResponses(agentId, sessionId, instance.instance_id, [response])
    );
    setDraft((prev) => ({ ...prev, text: "", reasoning: "" }));
  };

  const handleRemove = (index: number) => {
    const next = responses.filter((_, idx) => idx !== index);
    onRun(instance.instance_id, () =>
      replaceSteerableResponses(agentId, sessionId, instance.instance_id, next)
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
          {(Object.keys(STRATEGY_LABELS) as SteerableEmptyQueueStrategy[]).map((strategy) => (
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
            <span>Tool Call</span>
          </label>
          <div className="steerable-tool-call-fields">
            <input
              className="steerable-tool-input"
              value={draft.toolName}
              disabled={busy}
              placeholder="tool name"
              list={toolListId}
              onChange={(e) => setDraft((prev) => ({ ...prev, toolName: e.target.value }))}
            />
            <datalist id={toolListId}>
              {(instance.known_tools ?? []).map((toolName) => (
                <option key={toolName} value={toolName} />
              ))}
            </datalist>
            <input
              className="steerable-tool-args-input"
              value={draft.toolArgs}
              disabled={busy}
              placeholder='{"key": "value"}'
              onChange={(e) => setDraft((prev) => ({ ...prev, toolArgs: e.target.value }))}
            />
          </div>
          {toolArgsInvalid && (
            <span className="steerable-composer-error">Tool arguments must be a JSON object.</span>
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
    (instanceId: string, action: () => Promise<unknown>) => {
      if (!agentId || !sessionId) return;
      setBusyInstance(instanceId);
      setError(null);
      void action()
        .then(() => {
          onChanged();
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
          />
        ))}
      </div>
    </div>
  );
}
