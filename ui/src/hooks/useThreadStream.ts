import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  clickArtifact,
  getArtifact,
  getThreadStatus,
  listArtifacts,
  postUserInput,
  submitArtifact,
  subscribeToSessionStream,
  subscribeToThreadStream,
} from "../api/client";
import type {
  AgentStatus,
  ArtifactInfo,
  ChatMessage,
  MessagePart,
  ToolCallRecord,
} from "../api/types";

function findLastIndex<T>(arr: T[], predicate: (val: T) => boolean): number {
  for (let i = arr.length - 1; i >= 0; i--) {
    if (predicate(arr[i])) return i;
  }
  return -1;
}

function stopStreamingReasoningParts(parts?: MessagePart[]): MessagePart[] {
  if (!parts || parts.length === 0) return [];
  let changed = false;
  const updated = parts.map((p) => {
    if (p.type === "reasoning" && p.isStreaming) {
      changed = true;
      return { ...p, isStreaming: false };
    }
    return p;
  });
  return changed ? updated : parts;
}

export interface StreamErrorDetails {
  message: string;
  errorType?: string;
  traceback?: string;
}

function getToolArg(args: unknown, key: string): string | undefined {
  if (!args || typeof args !== "object") return undefined;
  const val = (args as Record<string, unknown>)[key];
  return typeof val === "string" ? val : undefined;
}

export function useThreadStream(
  agentId: string | null,
  sessionId: string | null,
  threadId: string | null,
  sessionStatus?: string,
  onThreadTransition?: (toThreadId: string, mode?: string, phase?: string | null) => void,
  onNamed?: (event: any) => void
) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<AgentStatus>("AWAITING_USER");
  const [streamError, setStreamError] = useState<string | null>(null);
  const [streamErrorDetails, setStreamErrorDetails] = useState<StreamErrorDetails | null>(
    null
  );
  const [sending, setSending] = useState<boolean>(false);
  const [artifacts, setArtifacts] = useState<ArtifactInfo[]>([]);

  const onThreadTransitionRef = useRef(onThreadTransition);
  onThreadTransitionRef.current = onThreadTransition;
  const onNamedRef = useRef(onNamed);
  onNamedRef.current = onNamed;

  // Keep ref of messages for mutable updates during streaming chunks
  const messagesRef = useRef<ChatMessage[]>([]);
  messagesRef.current = messages;

  const statusRef = useRef<AgentStatus>("AWAITING_USER");
  const pendingArtifactsRef = useRef<Map<string, ArtifactInfo>>(new Map());
  const artifactsRef = useRef<ArtifactInfo[]>([]);
  artifactsRef.current = artifacts;

  const attachArtifactToMessages = useCallback((art: ArtifactInfo) => {
    if (art.manifest?.exposition === "tabbed") {
      return;
    }
    const artId = art.uuid || art.name;
    setMessages((prev) => {
      const artPart: MessagePart = {
        type: "artifact",
        id: `artifact-${artId}`,
        artifact: art,
      };

      // 1. If artifact is already in a message, update it in place
      const msgWithArtIdx = findLastIndex(prev, (m) =>
        Boolean(
          m.parts?.some(
            (p) =>
              p.type === "artifact" &&
              (p.artifact?.uuid === artId ||
                p.artifact?.name === artId ||
                p.id === `artifact-${artId}`)
          )
        )
      );
      if (msgWithArtIdx >= 0) {
        const target = prev[msgWithArtIdx];
        const updatedParts = (target.parts || []).map((p) =>
          p.type === "artifact" &&
          (p.artifact?.uuid === artId ||
            p.artifact?.name === artId ||
            p.id === `artifact-${artId}`)
            ? artPart
            : p
        );
        const copy = [...prev];
        copy[msgWithArtIdx] = { ...target, parts: updatedParts };
        return copy;
      }

      // 2. Find the assistant message with the tool call that created this artifact
      const toolCallMsgIdx = findLastIndex(
        prev,
        (m) =>
          m.role === "assistant" &&
          Boolean(
            m.toolCalls?.some(
              (c) =>
                (c.name === "make_questionnaire" ||
                  c.name === "make_form" ||
                  c.name === "make_artifact") &&
                (c.result === artId ||
                  String(c.result).includes(artId) ||
                  getToolArg(c.args, "id") === artId ||
                  getToolArg(c.args, "artifact_id") === artId)
            )
          )
      );

      // 3. Fallback: find any assistant message waiting for this artifact, or with artifact tool calls
      const fallbackMsgIdx = findLastIndex(
        prev,
        (m) =>
          m.role === "assistant" &&
          Boolean(
            m.toolCalls?.some(
              (c) =>
                (c.name === "wait_for_click" &&
                  (getToolArg(c.args, "artifact_id") === artId || !getToolArg(c.args, "artifact_id"))) ||
                c.name === "make_questionnaire" ||
                c.name === "make_form" ||
                c.name === "make_artifact" ||
                c.name === "ask"
            )
          )
      );

      const targetIdx = toolCallMsgIdx >= 0 ? toolCallMsgIdx : fallbackMsgIdx;

      // If messages haven't loaded yet, do NOT create a fake message at the top!
      if (targetIdx < 0 || !prev[targetIdx] || prev[targetIdx].role !== "assistant") {
        return prev;
      }

      const target = prev[targetIdx];
      const parts = target.parts || [];
      // Insert right after make_questionnaire if present
      const tcPartIdx = parts.findIndex(
        (p) =>
          p.type === "tool_call" &&
          (p.toolCall?.name === "make_questionnaire" ||
            p.toolCall?.name === "make_form" ||
            p.toolCall?.name === "make_artifact") &&
          (p.toolCall?.result === artId ||
            String(p.toolCall?.result).includes(artId) ||
            getToolArg(p.toolCall?.args, "id") === artId ||
            getToolArg(p.toolCall?.args, "artifact_id") === artId)
      );

      const newParts = [...parts];
      if (tcPartIdx >= 0) {
        newParts.splice(tcPartIdx + 1, 0, artPart);
      } else {
        newParts.push(artPart);
      }

      const copy = [...prev];
      copy[targetIdx] = { ...target, parts: newParts };
      return copy;
    });
  }, []);

  const flushPendingArtifacts = useCallback(() => {
    if (pendingArtifactsRef.current.size === 0) return;
    const pending = Array.from(pendingArtifactsRef.current.values());
    pendingArtifactsRef.current.clear();
    for (const art of pending) {
      attachArtifactToMessages(art);
    }
  }, [attachArtifactToMessages]);

  useEffect(() => {
    statusRef.current = status;
    if (status === "AWAITING_USER") {
      flushPendingArtifacts();
    }
  }, [status, flushPendingArtifacts]);

  const refreshArtifacts = useCallback(async () => {
    if (!agentId || !sessionId) return [];
    try {
      const list = await listArtifacts(agentId, sessionId);
      setArtifacts(list);
      for (const art of list) {
        if (art.manifest?.exposition !== "tabbed") {
          attachArtifactToMessages(art);
        }
      }
      return list;
    } catch {
      return [];
    }
  }, [agentId, sessionId, attachArtifactToMessages]);

  useEffect(() => {
    if (!agentId || !sessionId) {
      setArtifacts([]);
      return;
    }
    refreshArtifacts();
  }, [agentId, sessionId, threadId, refreshArtifacts]);

  // Poll status occasionally or fetch initial status
  useEffect(() => {
    if (!agentId || !sessionId || !threadId) return;

    let mounted = true;
    getThreadStatus(agentId, sessionId, threadId)
      .then((res) => {
        if (mounted) setStatus(res.status);
      })
      .catch(() => {});

    return () => {
      mounted = false;
    };
  }, [agentId, sessionId, threadId]);

  // Synchronize terminal session states
  useEffect(() => {
    if (sessionStatus && sessionStatus !== "ACTIVE") {
      setStatus((prev) =>
        prev === "AWAITING_LLM" || prev === "EXECUTING_TOOL" ? "ERROR" : prev
      );
      setMessages((prev) =>
        prev.map((m) => {
          if (m.role !== "assistant") return m;
          return {
            ...m,
            isReasoning: false,
            parts: stopStreamingReasoningParts(m.parts),
          };
        })
      );
    }
  }, [sessionStatus]);

  // Connect to SSE stream
  useEffect(() => {
    if (!agentId || !sessionId) {
      setMessages([]);
      return;
    }

    setMessages([]);
    setStreamError(null);
    setStreamErrorDetails(null);

    const onEventHandler = (event: any) => {
      const type = event.type || event.event;

        if (type === "ARTIFACT_CREATED") {
          const artId = event.artifact_id || event.artifactId;
          const kind = event.kind || "questionnaires";
          if (artId && agentId && sessionId) {
            getArtifact(agentId, sessionId, kind, artId)
              .then((art) => {
                setArtifacts((prev) => {
                  const idx = prev.findIndex((a) => (a.uuid === artId || a.name === artId));
                  if (idx >= 0) {
                    const next = [...prev];
                    next[idx] = art;
                    return next;
                  }
                  return [...prev, art];
                });

                if (art.manifest?.exposition !== "tabbed") {
                  attachArtifactToMessages(art);
                }
              })
              .catch(() => {});
          }
        } else if (type === "ARTIFACT_UPDATED") {
          const artId = event.artifact_id || event.artifactId || event.name;
          const kind = event.kind || "plans";
          if (artId && agentId && sessionId) {
            getArtifact(agentId, sessionId, kind, artId)
              .then((art) => {
                setArtifacts((prev) => {
                  const idx = prev.findIndex((a) => a.kind === kind && a.name === artId);
                  if (idx >= 0) {
                    const next = [...prev];
                    next[idx] = art;
                    return next;
                  }
                  return [...prev, art];
                });
                setMessages((prev) =>
                  prev.map((m) => {
                    if (!m.parts) return m;
                    const updatedParts = m.parts.map((p) =>
                      p.type === "artifact" &&
                      (p.artifact.name === artId || p.id === `artifact-${artId}`)
                        ? { ...p, artifact: art }
                        : p
                    );
                    return { ...m, parts: updatedParts };
                  })
                );
              })
              .catch(() => {});
          }
        } else if (type === "ARTIFACT_CLOSED") {
          const artId = event.artifact_id || event.artifactId || event.name;
          const kind = event.kind || "plans";
          if (artId && agentId && sessionId) {
            setArtifacts((prev) =>
              prev.map((a) =>
                a.kind === kind && a.name === artId ? { ...a, is_closed: true } : a
              )
            );
            getArtifact(agentId, sessionId, kind, artId)
              .then((art) => {
                setArtifacts((prev) =>
                  prev.map((a) => (a.kind === kind && a.name === artId ? art : a))
                );
              })
              .catch(() => {});
          }
        } else if (type === "ARTIFACT_SUBMITTED") {
          const artId = event.artifact_id || event.artifactId || event.name;
          const kind = event.kind || "questionnaires";
          if (artId && agentId && sessionId) {
            getArtifact(agentId, sessionId, kind, artId)
              .then((art) => {
                setArtifacts((prev) =>
                  prev.map((a) => (a.kind === kind && a.name === artId ? art : a))
                );
                setMessages((prev) =>
                  prev.map((m) => {
                    if (!m.parts) return m;
                    const updatedParts = m.parts.map((p) =>
                      p.type === "artifact" &&
                      (p.artifact.name === artId || p.id === `artifact-${artId}`)
                        ? { ...p, artifact: art }
                        : p
                    );
                    return { ...m, parts: updatedParts };
                  })
                );
              })
              .catch(() => {});
          }
        } else if (type === "THREAD_TRANSITION") {
          const toThreadId =
            event.to_thread_id ||
            event.toThreadId ||
            event.thread_id ||
            event.threadId;
          if (toThreadId) {
            if (!event.is_first) {
              setMessages((prev) => {
                const alreadyPresent = prev.some(
                  (m) => m.threadTransition?.threadId === toThreadId
                );
                if (alreadyPresent) return prev;
                return [
                  ...prev,
                  {
                    id: `transition-${toThreadId}`,
                    role: "system",
                    text: "",
                    timestamp: new Date().toISOString(),
                    threadTransition: {
                      threadId: toThreadId,
                      threadName: event.thread_name || event.name || null,
                      mode: event.mode,
                      phase: event.phase,
                      modeLabel:
                        event.mode_label ||
                        (event.phase ? `${event.mode}/${event.phase}` : event.mode),
                    },
                  },
                ];
              });
            }
            onThreadTransitionRef.current?.(toThreadId, event.mode, event.phase);
          }
        } else if (type === "THREAD_NAMED" || type === "SESSION_NAMED") {
          onNamedRef.current?.(event);
        } else if (type === "STATUS_CHANGED") {
          const nextStatus = event.status as AgentStatus;
          if (nextStatus) {
            statusRef.current = nextStatus;
            setStatus(nextStatus);
            if (nextStatus === "AWAITING_USER") {
              flushPendingArtifacts();
            }
          }
        } else if (type === "RUN_STARTED") {
          statusRef.current = "AWAITING_LLM";
          setStatus("AWAITING_LLM");
        } else if (type === "RUN_FINISHED") {
          statusRef.current = "AWAITING_USER";
          setStatus("AWAITING_USER");
          flushPendingArtifacts();
        } else if (type === "RUN_ERROR") {
          statusRef.current = "ERROR";
          setStatus("ERROR");
          flushPendingArtifacts();
          const errMsg = event.message || "Execution encountered an error.";
          setStreamError(errMsg);
          setStreamErrorDetails({
            message: errMsg,
            errorType: event.error_type || event.errorType || undefined,
            traceback: event.traceback || undefined,
          });
          setMessages((prev) =>
            prev.map((m) => {
              if (m.role !== "assistant") return m;
              const stoppedParts = stopStreamingReasoningParts(m.parts);
              const updatedCalls = (m.toolCalls || []).map((c) =>
                c.status === "wip" || c.status === "pending"
                  ? {
                      ...c,
                      status: "error" as const,
                      result: c.result || "Execution interrupted or errored.",
                    }
                  : c
              );
              const finalParts = (stoppedParts || []).map((p) => {
                if (p.type !== "tool_call") return p;
                if (
                  p.toolCall.status === "wip" ||
                  p.toolCall.status === "pending"
                ) {
                  return {
                    ...p,
                    toolCall: {
                      ...p.toolCall,
                      status: "error" as const,
                      result:
                        p.toolCall.result || "Execution interrupted or errored.",
                    },
                  };
                }
                return p;
              });
              return {
                ...m,
                isReasoning: false,
                toolCalls: updatedCalls.length > 0 ? updatedCalls : m.toolCalls,
                parts: finalParts.length > 0 ? finalParts : m.parts,
              };
            })
          );
        } else if (type === "TOOL_CALL_START") {
          setStatus("EXECUTING_TOOL");
          const callId = event.tool_call_id || event.toolCallId || "tool-call";
          const callName = event.tool_call_name || event.toolCallName || "tool";

          setMessages((prev) => {
            const newCall: ToolCallRecord = {
              id: callId,
              name: callName,
              status: "pending",
              rawArgs: "",
              args: {},
            };
            const toolPart: MessagePart = {
              type: "tool_call",
              id: callId,
              toolCall: newCall,
            };

            const msgIdx = findLastIndex(prev, (m) =>
              Boolean(m.toolCalls?.some((c) => c.id === callId))
            );

            if (msgIdx >= 0) {
              const target = prev[msgIdx];
              const updatedCalls = (target.toolCalls || []).map((c) =>
                c.id === callId
                  ? {
                      ...c,
                      name: callName || c.name,
                      status: "pending" as const,
                    }
                  : c
              );
              const updatedParts = (target.parts || []).map((p) =>
                p.type === "tool_call" && p.toolCall.id === callId
                  ? {
                      ...p,
                      toolCall: {
                        ...p.toolCall,
                        name: callName || p.toolCall.name,
                        status: "pending" as const,
                      },
                    }
                  : p
              );
              const copy = [...prev];
              copy[msgIdx] = {
                ...target,
                toolCalls: updatedCalls,
                parts: updatedParts,
              };
              return copy;
            }

            const last = prev[prev.length - 1];
            if (last && last.role === "assistant") {
              // Auto-collapse any active reasoning bubble because a new tool bubble started emitting!
              const stoppedParts = stopStreamingReasoningParts(last.parts);
              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  isReasoning: false,
                  toolCalls: [...(last.toolCalls || []), newCall],
                  parts: [...stoppedParts, toolPart],
                },
              ];
            } else {
              const asstId =
                event.parent_message_id ||
                event.parentMessageId ||
                event.message_id ||
                event.messageId ||
                `asst-${Date.now()}`;
              return [
                ...prev,
                {
                  id: asstId,
                  role: "assistant",
                  text: "",
                  toolCalls: [newCall],
                  parts: [toolPart],
                  timestamp: new Date().toISOString(),
                },
              ];
            }
          });
        } else if (
          type === "TOOL_CALL_ARGS" ||
          type === "TOOL_CALL_CHUNK"
        ) {
          setStatus("EXECUTING_TOOL");
          const callId = event.tool_call_id || event.toolCallId || "tool-call";
          const delta =
            event.delta || (typeof event.args === "string" ? event.args : "") || "";
          const explicitArgs =
            typeof event.args === "object" && event.args !== null ? event.args : null;
          const callName = event.tool_call_name || event.toolCallName;

          setMessages((prev) => {
            let msgIdx = findLastIndex(prev, (m) =>
              Boolean(m.toolCalls?.some((c) => c.id === callId))
            );
            if (msgIdx < 0 && prev.length > 0 && prev[prev.length - 1].role === "assistant") {
              msgIdx = prev.length - 1;
            }
            if (msgIdx < 0) return prev;

            const target = prev[msgIdx];
            const existingCalls = target.toolCalls || [];
            const callIdx = existingCalls.findIndex((c) => c.id === callId);

            let updatedCall: ToolCallRecord;
            let updatedCalls: ToolCallRecord[];

            if (callIdx >= 0) {
              const existing = existingCalls[callIdx];
              const accumulatedRaw = (existing.rawArgs || "") + delta;
              let parsed = existing.args;
              if (explicitArgs) {
                parsed = {
                  ...(typeof parsed === "object" && parsed !== null ? parsed : {}),
                  ...explicitArgs,
                };
              } else if (accumulatedRaw) {
                try {
                  parsed = JSON.parse(accumulatedRaw);
                } catch {
                  // Partial JSON chunk, keep accumulating
                }
              }

              updatedCall = {
                ...existing,
                name: callName || existing.name,
                rawArgs: accumulatedRaw,
                args: parsed,
                status:
                  existing.status === "wip" || existing.status === "done"
                    ? existing.status
                    : "pending",
              };
              updatedCalls = [...existingCalls];
              updatedCalls[callIdx] = updatedCall;
            } else {
              let parsed: any = explicitArgs || {};
              if (delta) {
                try {
                  parsed = JSON.parse(delta);
                } catch {
                  // Partial JSON
                }
              }
              updatedCall = {
                id: callId,
                name: callName || "tool",
                rawArgs: delta,
                args: parsed,
                status: "pending",
              };
              updatedCalls = [...existingCalls, updatedCall];
            }

            // Sync into chronological parts
            const currentParts = target.parts || [];
            const partIdx = currentParts.findIndex(
              (p) => p.type === "tool_call" && p.toolCall.id === callId
            );
            let updatedParts: MessagePart[];
            if (partIdx >= 0) {
              updatedParts = [...currentParts];
              updatedParts[partIdx] = {
                type: "tool_call",
                id: callId,
                toolCall: updatedCall,
              };
            } else {
              updatedParts = [
                ...currentParts,
                { type: "tool_call", id: callId, toolCall: updatedCall },
              ];
            }

            const copy = [...prev];
            copy[msgIdx] = {
              ...target,
              toolCalls: updatedCalls,
              parts: updatedParts,
            };
            return copy;
          });
        } else if (type === "TOOL_CALL_END") {
          setStatus("EXECUTING_TOOL");
          const callId = event.tool_call_id || event.toolCallId;

          setMessages((prev) => {
            const msgIdx = findLastIndex(prev, (m) =>
              Boolean(m.toolCalls?.some((c) => !callId || c.id === callId))
            );
            if (msgIdx < 0) return prev;

            const target = prev[msgIdx];
            const updatedCalls = (target.toolCalls || []).map((c) => {
              if (callId && c.id !== callId) return c;
              let parsed = c.args;
              if ((!parsed || Object.keys(parsed).length === 0) && c.rawArgs) {
                try {
                  parsed = JSON.parse(c.rawArgs);
                } catch {
                  // Not valid JSON
                }
              }
              return {
                ...c,
                args: parsed,
                status: c.status === "done" ? ("done" as const) : ("wip" as const),
              };
            });

            const updatedParts = (target.parts || []).map((p) => {
              if (p.type !== "tool_call") return p;
              if (callId && p.toolCall.id !== callId) return p;
              const matched = updatedCalls.find((c) => c.id === p.toolCall.id);
              return matched
                ? { ...p, toolCall: matched }
                : {
                    ...p,
                    toolCall: {
                      ...p.toolCall,
                      status: p.toolCall.status === "done" ? ("done" as const) : ("wip" as const),
                    },
                  };
            });

            const copy = [...prev];
            copy[msgIdx] = {
              ...target,
              toolCalls: updatedCalls,
              parts: updatedParts,
            };
            return copy;
          });
        } else if (type === "TOOL_CALL_RESULT") {
          setStatus("AWAITING_LLM");
          const callId = event.tool_call_id || event.toolCallId;
          const result = event.content ?? event.result ?? event.output;
          const isError = Boolean(
            event.is_error || event.isError || event.status === "error"
          );

          setMessages((prev) => {
            let msgIdx = findLastIndex(prev, (m) =>
              Boolean(m.toolCalls?.some((c) => !callId || c.id === callId))
            );
            if (msgIdx < 0 && prev.length > 0 && prev[prev.length - 1].role === "assistant") {
              msgIdx = prev.length - 1;
            }
            if (msgIdx < 0) return prev;

            const target = prev[msgIdx];
            const updatedCalls = (target.toolCalls || []).map((c) =>
              !callId || c.id === callId
                ? {
                    ...c,
                    result,
                    status: isError ? ("error" as const) : ("done" as const),
                  }
                : c
            );

            const updatedParts = (target.parts || []).map((p) => {
              if (p.type !== "tool_call") return p;
              if (callId && p.toolCall.id !== callId) return p;
              const matched = updatedCalls.find((c) => c.id === p.toolCall.id);
              return matched
                ? { ...p, toolCall: matched }
                : {
                    ...p,
                    toolCall: {
                      ...p.toolCall,
                      result,
                      status: isError ? ("error" as const) : ("done" as const),
                    },
                  };
            });

            const copy = [...prev];
            copy[msgIdx] = {
              ...target,
              toolCalls: updatedCalls,
              parts: updatedParts,
            };
            return copy;
          });
        } else if (
          type === "REASONING_START" ||
          type === "REASONING_MESSAGE_START"
        ) {
          setStatus("AWAITING_LLM");
          const msgId = event.message_id || event.messageId || `reasoning-${Date.now()}`;

          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === "assistant") {
              const currentParts = last.parts || [];
              const lastPart = currentParts[currentParts.length - 1];
              let updatedParts = currentParts;
              if (lastPart && lastPart.type === "reasoning" && lastPart.isStreaming) {
                // Already streaming this reasoning part
              } else {
                updatedParts = [
                  ...stopStreamingReasoningParts(currentParts),
                  { type: "reasoning", id: msgId, content: "", isStreaming: true },
                ];
              }
              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  isReasoning: true,
                  parts: updatedParts,
                },
              ];
            } else {
              const asstId =
                event.message_id ||
                event.messageId ||
                `asst-${Date.now()}`;
              return [
                ...prev,
                {
                  id: asstId,
                  role: "assistant",
                  text: "",
                  reasoning: "",
                  isReasoning: true,
                  parts: [{ type: "reasoning", id: msgId, content: "", isStreaming: true }],
                  timestamp: new Date().toISOString(),
                },
              ];
            }
          });
        } else if (
          type === "REASONING_MESSAGE_CONTENT" ||
          type === "REASONING_MESSAGE_CHUNK"
        ) {
          setStatus("AWAITING_LLM");
          const msgId = event.message_id || event.messageId;
          const delta = event.delta || event.content || event.text || "";
          if (!delta) return;

          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === "assistant") {
              const currentReasoning = last.reasoning || "";
              const currentParts = last.parts || [];
              const lastPart = currentParts[currentParts.length - 1];
              let updatedParts: MessagePart[];

              if (lastPart && lastPart.type === "reasoning" && lastPart.isStreaming) {
                updatedParts = [
                  ...currentParts.slice(0, -1),
                  { ...lastPart, content: lastPart.content + delta, isStreaming: true },
                ];
              } else {
                updatedParts = [
                  ...stopStreamingReasoningParts(currentParts),
                  {
                    type: "reasoning",
                    id: msgId || `reasoning-${Date.now()}`,
                    content: delta,
                    isStreaming: true,
                  },
                ];
              }

              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  reasoning: currentReasoning + delta,
                  isReasoning: true,
                  parts: updatedParts,
                },
              ];
            } else {
              const newMsgId = msgId || `reasoning-${Date.now()}`;
              const asstId =
                event.message_id ||
                event.messageId ||
                `asst-${Date.now()}`;
              return [
                ...prev,
                {
                  id: asstId,
                  role: "assistant",
                  text: "",
                  reasoning: delta,
                  isReasoning: true,
                  parts: [
                    { type: "reasoning", id: newMsgId, content: delta, isStreaming: true },
                  ],
                  timestamp: new Date().toISOString(),
                },
              ];
            }
          });
        } else if (
          type === "REASONING_MESSAGE_END" ||
          type === "REASONING_END"
        ) {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === "assistant") {
              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  isReasoning: false,
                  parts: stopStreamingReasoningParts(last.parts),
                },
              ];
            }
            return prev;
          });
        } else if (type === "TEXT_MESSAGE_START") {
          const msgId = event.message_id || event.messageId || `msg-${Date.now()}`;
          const role = event.role === "user" ? "user" : "assistant";
          if (role === "assistant") {
            setStatus("AWAITING_LLM");
          }

          setMessages((prev) => {
            const existingIdx = prev.findIndex((m) => m.id === msgId);
            if (existingIdx >= 0) {
              return prev;
            }
            const last = prev[prev.length - 1];
            if (role === "assistant" && last && last.role === "assistant") {
              // Another bubble started emitting (text)! Auto-collapse any active reasoning bubble
              const stoppedParts = stopStreamingReasoningParts(last.parts);
              const textPart: MessagePart = {
                type: "text",
                id: msgId,
                content: "",
              };
              const updatedId =
                !last.id || last.id.startsWith("asst-") ? msgId : last.id;
              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  id: updatedId,
                  isReasoning: false,
                  parts: [...stoppedParts, textPart],
                },
              ];
            }
            return [
              ...prev,
              {
                id: msgId,
                role,
                text: "",
                parts:
                  role === "assistant"
                    ? [{ type: "text", id: msgId, content: "" }]
                    : undefined,
                timestamp: new Date().toISOString(),
              },
            ];
          });
        } else if (
          type === "TEXT_MESSAGE_CHUNK" ||
          type === "TEXT_MESSAGE_CONTENT"
        ) {
          const msgId = event.message_id || event.messageId;
          const delta = event.delta || event.content || event.text || "";

          setMessages((prev) => {
            // If msgId matches an existing message, update it
            if (msgId) {
              const idx = prev.findIndex((m) => m.id === msgId);
              if (idx >= 0) {
                const target = prev[idx];
                // If this is an optimistic user message that already has the exact text, don't duplicate
                if (target.role === "user" && target.text === delta) {
                  return prev;
                }
                const currentParts = target.parts || [];
                const stopped = stopStreamingReasoningParts(currentParts);
                const lastPart = stopped[stopped.length - 1];
                let updatedParts: MessagePart[];
                if (lastPart && lastPart.type === "text") {
                  updatedParts = [
                    ...stopped.slice(0, -1),
                    { ...lastPart, content: lastPart.content + delta },
                  ];
                } else {
                  updatedParts = [
                    ...stopped,
                    { type: "text", id: msgId, content: delta },
                  ];
                }

                const updated = {
                  ...target,
                  text: target.text ? target.text + delta : delta,
                  parts: updatedParts,
                  isReasoning: false,
                };
                const copy = [...prev];
                copy[idx] = updated;
                return copy;
              }
            }

            // Fallback: append to last assistant message if one exists
            const last = prev[prev.length - 1];
            if (last && last.role === "assistant") {
              const currentParts = last.parts || [];
              const stopped = stopStreamingReasoningParts(currentParts);
              const lastPart = stopped[stopped.length - 1];
              let updatedParts: MessagePart[];
              if (lastPart && lastPart.type === "text") {
                updatedParts = [
                  ...stopped.slice(0, -1),
                  { ...lastPart, content: lastPart.content + delta },
                ];
              } else {
                updatedParts = [
                  ...stopped,
                  {
                    type: "text",
                    id: msgId || `text-${Date.now()}`,
                    content: delta,
                  },
                ];
              }

              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  text: last.text + delta,
                  parts: updatedParts,
                  isReasoning: false,
                },
              ];
            } else {
              setStatus("AWAITING_LLM");
              const newMsgId = msgId || `msg-${Date.now()}`;
              return [
                ...prev,
                {
                  id: newMsgId,
                  role: "assistant",
                  text: delta,
                  parts: [{ type: "text", id: newMsgId, content: delta }],
                  timestamp: new Date().toISOString(),
                },
              ];
            }
          });
        } else if (type === "TEXT_MESSAGE_END") {
          // Message complete event
        } else if (type === "USER_MESSAGE") {
          // Replayed user message
          const text = event.content?.[0]?.text || event.text || "";
          const msgId = event.id || `user-${Date.now()}`;
          setMessages((prev) => {
            if (prev.some((m) => m.id === msgId)) return prev;
            return [
              ...prev,
              {
                id: msgId,
                role: "user",
                text,
                timestamp: new Date().toISOString(),
              },
            ];
          });
        } else if (type === "MESSAGES_SNAPSHOT") {
          const snapshotMsgs = event.messages || [];
          if (!Array.isArray(snapshotMsgs) || snapshotMsgs.length === 0) return;

          const toolResults = new Map<string, unknown>();
          for (const m of snapshotMsgs) {
            const role = m.role || m.type;
            const callRef = m.toolCallId || m.tool_call_id;
            if (role === "tool" && callRef) {
              toolResults.set(callRef, m.content);
            }
          }

          setMessages((prev) => {
            if (prev.length === 0) {
              const rebuilt: ChatMessage[] = [];
              for (const m of snapshotMsgs) {
                const role = m.role || m.type;
                if (role === "user") {
                  const text =
                    typeof m.content === "string"
                      ? m.content
                      : m.content?.[0]?.text || "";
                  rebuilt.push({
                    id: m.id || `user-${rebuilt.length}`,
                    role: "user",
                    text,
                    timestamp: new Date().toISOString(),
                  });
                } else if (role === "assistant") {
                  const text = typeof m.content === "string" ? m.content : "";
                  const rawCalls = m.toolCalls || m.tool_calls || [];
                  const toolCalls: ToolCallRecord[] = rawCalls.map((tc: any) => {
                    const id = tc.id;
                    const name = tc.function?.name || tc.name || "tool";
                    const rawArgs =
                      tc.function?.arguments ||
                      (typeof tc.args === "string"
                        ? tc.args
                        : JSON.stringify(tc.args || {}));
                    let parsedArgs: any = undefined;
                    try {
                      parsedArgs = JSON.parse(rawArgs);
                    } catch {
                      parsedArgs = rawArgs;
                    }
                    const res = toolResults.get(id);
                    const isTerminal = Boolean(sessionStatus && sessionStatus !== "ACTIVE");
                    const toolStatus =
                      res !== undefined
                        ? ("done" as const)
                        : isTerminal
                          ? ("error" as const)
                          : ("wip" as const);
                    return {
                      id,
                      name,
                      status: toolStatus,
                      rawArgs,
                      args: parsedArgs,
                      result: res !== undefined ? res : isTerminal ? "Execution interrupted." : undefined,
                    };
                  });

                  // Build chronological parts
                  const parts: MessagePart[] = [];
                  const reasoningText = m.reasoning || m.reasoning_content;
                  if (reasoningText) {
                    parts.push({
                      type: "reasoning",
                      id: `reasoning-${m.id || rebuilt.length}`,
                      content: reasoningText,
                      isStreaming: false,
                    });
                  }
                  for (const tc of toolCalls) {
                    parts.push({
                      type: "tool_call",
                      id: tc.id,
                      toolCall: tc,
                    });

                    // Insert matching artifact immediately following its creation tool call
                    const matchedArt = artifactsRef.current.find(
                      (a) =>
                        a.manifest?.exposition !== "tabbed" &&
                        (a.uuid === tc.result ||
                          a.name === tc.result ||
                          String(tc.result).includes(a.uuid) ||
                          a.uuid === getToolArg(tc.args, "artifact_id") ||
                          a.name === getToolArg(tc.args, "artifact_id") ||
                          a.uuid === getToolArg(tc.args, "id") ||
                          a.name === getToolArg(tc.args, "id"))
                    );
                    if (matchedArt) {
                      const matchedId = matchedArt.uuid || matchedArt.name;
                      parts.push({
                        type: "artifact",
                        id: `artifact-${matchedId}`,
                        artifact: matchedArt,
                      });
                    }
                  }
                  if (text) {
                    parts.push({
                      type: "text",
                      id: `text-${m.id || rebuilt.length}`,
                      content: text,
                    });
                  }

                  rebuilt.push({
                    id: m.id || `asst-${rebuilt.length}`,
                    role: "assistant",
                    text,
                    reasoning: reasoningText || undefined,
                    isReasoning: false,
                    toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
                    parts: parts.length > 0 ? parts : undefined,
                    timestamp: new Date().toISOString(),
                  });
                }
              }

              return rebuilt;
            }

            const isTerminal = Boolean(sessionStatus && sessionStatus !== "ACTIVE");
            return prev.map((msg) => {
              if (msg.role !== "assistant") return msg;
              const updatedCalls = (msg.toolCalls || []).map((c) => {
                const snapRes = toolResults.get(c.id);
                if (snapRes !== undefined) {
                  return {
                    ...c,
                    result: c.result !== undefined ? c.result : snapRes,
                    status: "done" as const,
                  };
                }
                if (isTerminal && (c.status === "wip" || c.status === "pending")) {
                  return {
                    ...c,
                    result: c.result || "Execution interrupted.",
                    status: "error" as const,
                  };
                }
                return c;
              });

              const updatedParts = (msg.parts || []).map((p) => {
                if (p.type === "reasoning") {
                  return { ...p, isStreaming: false };
                }
                if (p.type === "tool_call") {
                  const snapRes = toolResults.get(p.toolCall.id);
                  if (snapRes !== undefined) {
                    return {
                      ...p,
                      toolCall: {
                        ...p.toolCall,
                        result:
                          p.toolCall.result !== undefined ? p.toolCall.result : snapRes,
                        status: "done" as const,
                      },
                    };
                  }
                  if (isTerminal && (p.toolCall.status === "wip" || p.toolCall.status === "pending")) {
                    return {
                      ...p,
                      toolCall: {
                        ...p.toolCall,
                        result: p.toolCall.result || "Execution interrupted.",
                        status: "error" as const,
                      },
                    };
                  }
                }
                return p;
              });

              return {
                ...msg,
                isReasoning: false,
                toolCalls: updatedCalls,
                parts: updatedParts,
              };
            });
          });
        }
      };

    const onErrorHandler = (err: any) => {
      setStreamError(err.message);
      setStreamErrorDetails({
        message: err.message,
        errorType: "StreamConnectionError",
      });
    };

    const unsubscribe = threadId
      ? subscribeToThreadStream(agentId, sessionId, threadId, onEventHandler, onErrorHandler)
      : subscribeToSessionStream(agentId, sessionId, onEventHandler, onErrorHandler);

    return () => {
      unsubscribe();
    };
  }, [agentId, sessionId, threadId]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!agentId || !sessionId || !text.trim()) return;

      if (status !== "AWAITING_USER") {
        throw new Error(
          `Cannot send message: agent is currently busy (status: ${status}).`
        );
      }

      setSending(true);
      setStreamError(null);
      setStreamErrorDetails(null);

      // Optimistically append user message to chat UI with deterministic messageId
      const userMsgId = `user-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const userMsg: ChatMessage = {
        id: userMsgId,
        role: "user",
        text: text.trim(),
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setStatus("AWAITING_LLM");

      try {
        await postUserInput(agentId, sessionId, text.trim(), userMsgId);
      } catch (err: any) {
        setStatus("AWAITING_USER");
        const errMsg = err instanceof Error ? err.message : String(err);
        setStreamError(errMsg);
        setStreamErrorDetails({
          message: errMsg,
          errorType: "DispatchError",
        });
        throw err;
      } finally {
        setSending(false);
      }
    },
    [agentId, sessionId, status]
  );

  const hasOpenBlockingArtifact = useMemo(() => {
    return artifacts.some(
      (a) => !a.is_closed && Boolean(a.manifest?.blocking)
    );
  }, [artifacts]);

  const submitArtifactHandler = useCallback(
    async (artifact: ArtifactInfo, data: Record<string, unknown>) => {
      if (!agentId || !sessionId) return;
      const { button_id, buttonId, action, ...contextData } = data;
      const effectiveButtonId =
        (button_id as string) ||
        (buttonId as string) ||
        (action as string) ||
        "submit-btn";
      const family = artifact.family || artifact.kind;
      const uuid = artifact.uuid || artifact.name;

      try {
        await clickArtifact(agentId, sessionId, family, uuid, effectiveButtonId, contextData);
      } catch (err) {
        console.warn("clickArtifact failed, attempting fallback to submitArtifact:", err);
        await submitArtifact(agentId, sessionId, family, uuid, contextData);
      }

      try {
        const updated = await getArtifact(agentId, sessionId, family, uuid);
        setArtifacts((prev) =>
          prev.map((a) =>
            (a.family === family && a.uuid === uuid) || (a.kind === family && a.name === uuid)
              ? updated
              : a
          )
        );
        setMessages((prev) =>
          prev.map((m) => {
            if (!m.parts) return m;
            const updatedParts = m.parts.map((p) =>
              p.type === "artifact" &&
              (p.artifact.uuid === uuid || p.artifact.name === uuid)
                ? { ...p, artifact: updated }
                : p
            );
            return { ...m, parts: updatedParts };
          })
        );
      } catch (err) {
        console.error("Failed to refresh artifact after interaction:", err);
      }
    },
    [agentId, sessionId]
  );

  return {
    messages,
    status,
    streamError,
    streamErrorDetails,
    sending,
    sendMessage,
    artifacts,
    hasOpenBlockingArtifact,
    refreshArtifacts,
    submitArtifact: submitArtifactHandler,
  };
}

