import { useCallback, useEffect, useRef, useState } from "react";
import { getThreadStatus, postUserInput, subscribeToThreadStream } from "../api/client";
import type { AgentStatus, ChatMessage, ToolCallRecord } from "../api/types";

function findLastIndex<T>(arr: T[], predicate: (val: T) => boolean): number {
  for (let i = arr.length - 1; i >= 0; i--) {
    if (predicate(arr[i])) return i;
  }
  return -1;
}

export function useThreadStream(
  agentId: string | null,
  sessionId: string | null,
  threadId: string | null
) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<AgentStatus>("AWAITING_USER");
  const [streamError, setStreamError] = useState<string | null>(null);
  const [sending, setSending] = useState<boolean>(false);

  // Keep ref of messages for mutable updates during streaming chunks
  const messagesRef = useRef<ChatMessage[]>([]);
  messagesRef.current = messages;

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

  // Connect to SSE stream
  useEffect(() => {
    if (!agentId || !sessionId || !threadId) {
      setMessages([]);
      return;
    }

    setMessages([]);
    setStreamError(null);

    const unsubscribe = subscribeToThreadStream(
      agentId,
      sessionId,
      threadId,
      (event: any) => {
        const type = event.type || event.event;

        if (type === "RUN_STARTED") {
          setStatus("AWAITING_LLM");
        } else if (type === "RUN_FINISHED") {
          setStatus("AWAITING_USER");
        } else if (type === "RUN_ERROR") {
          setStatus("ERROR");
          setStreamError(event.message || "Execution encountered an error.");
        } else if (type === "TOOL_CALL_START") {
          setStatus("EXECUTING_TOOL");
          const callId = event.tool_call_id || event.toolCallId || "tool-call";
          const callName = event.tool_call_name || event.toolCallName || "tool";

          setMessages((prev) => {
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
              const copy = [...prev];
              copy[msgIdx] = { ...target, toolCalls: updatedCalls };
              return copy;
            }

            const last = prev[prev.length - 1];
            const newCall: ToolCallRecord = {
              id: callId,
              name: callName,
              status: "pending",
              rawArgs: "",
              args: {},
            };

            if (last && last.role === "assistant") {
              return [
                ...prev.slice(0, -1),
                { ...last, toolCalls: [...(last.toolCalls || []), newCall] },
              ];
            } else {
              return [
                ...prev,
                {
                  id: `msg-${Date.now()}`,
                  role: "assistant",
                  text: "",
                  toolCalls: [newCall],
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

              updatedCalls = [...existingCalls];
              updatedCalls[callIdx] = {
                ...existing,
                name: callName || existing.name,
                rawArgs: accumulatedRaw,
                args: parsed,
                status:
                  existing.status === "wip" || existing.status === "done"
                    ? existing.status
                    : "pending",
              };
            } else {
              let parsed: any = explicitArgs || {};
              if (delta) {
                try {
                  parsed = JSON.parse(delta);
                } catch {
                  // Partial JSON
                }
              }
              updatedCalls = [
                ...existingCalls,
                {
                  id: callId,
                  name: callName || "tool",
                  rawArgs: delta,
                  args: parsed,
                  status: "pending",
                },
              ];
            }

            const copy = [...prev];
            copy[msgIdx] = { ...target, toolCalls: updatedCalls };
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

            const copy = [...prev];
            copy[msgIdx] = { ...target, toolCalls: updatedCalls };
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

            const copy = [...prev];
            copy[msgIdx] = { ...target, toolCalls: updatedCalls };
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
            if (last && last.role === "assistant" && !last.text) {
              return [
                ...prev.slice(0, -1),
                { ...last, isReasoning: true },
              ];
            }
            return [
              ...prev,
              {
                id: msgId,
                role: "assistant",
                text: "",
                reasoning: "",
                isReasoning: true,
                timestamp: new Date().toISOString(),
              },
            ];
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
              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  reasoning: currentReasoning + delta,
                  isReasoning: true,
                },
              ];
            }
            return [
              ...prev,
              {
                id: msgId || `reasoning-${Date.now()}`,
                role: "assistant",
                text: "",
                reasoning: delta,
                isReasoning: true,
                timestamp: new Date().toISOString(),
              },
            ];
          });
        } else if (
          type === "REASONING_MESSAGE_END" ||
          type === "REASONING_END"
        ) {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === "assistant" && last.isReasoning) {
              return [
                ...prev.slice(0, -1),
                { ...last, isReasoning: false },
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
            if (role === "assistant" && last && last.role === "assistant" && !last.text) {
              return [
                ...prev.slice(0, -1),
                { ...last, id: msgId, isReasoning: false },
              ];
            }
            return [
              ...prev,
              {
                id: msgId,
                role,
                text: "",
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
                const updated = {
                  ...target,
                  text: target.text ? target.text + delta : delta,
                };
                const copy = [...prev];
                copy[idx] = updated;
                return copy;
              }
            }

            // Fallback: append to last assistant message if one exists
            const last = prev[prev.length - 1];
            if (last && last.role === "assistant") {
              return [
                ...prev.slice(0, -1),
                { ...last, text: last.text + delta },
              ];
            } else {
              setStatus("AWAITING_LLM");
              return [
                ...prev,
                {
                  id: msgId || `msg-${Date.now()}`,
                  role: "assistant",
                  text: delta,
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
                    return {
                      id,
                      name,
                      status: res !== undefined ? ("done" as const) : ("wip" as const),
                      rawArgs,
                      args: parsedArgs,
                      result: res,
                    };
                  });

                  rebuilt.push({
                    id: m.id || `asst-${rebuilt.length}`,
                    role: "assistant",
                    text,
                    toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
                    timestamp: new Date().toISOString(),
                  });
                }
              }
              return rebuilt;
            }

            return prev.map((msg) => {
              if (msg.role !== "assistant" || !msg.toolCalls) return msg;
              const updated = msg.toolCalls.map((c) => {
                const snapRes = toolResults.get(c.id);
                if (snapRes !== undefined) {
                  return {
                    ...c,
                    result: c.result !== undefined ? c.result : snapRes,
                    status: "done" as const,
                  };
                }
                return c;
              });
              return { ...msg, toolCalls: updated };
            });
          });
        }
      },
      (err) => {
        setStreamError(err.message);
      }
    );

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
        setStreamError(err instanceof Error ? err.message : String(err));
        throw err;
      } finally {
        setSending(false);
      }
    },
    [agentId, sessionId, status]
  );

  return {
    messages,
    status,
    streamError,
    sending,
    sendMessage,
  };
}

