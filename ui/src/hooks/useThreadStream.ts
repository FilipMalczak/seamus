import { useCallback, useEffect, useRef, useState } from "react";
import { getThreadStatus, postUserInput, subscribeToThreadStream } from "../api/client";
import type { AgentStatus, ChatMessage, ToolCallRecord } from "../api/types";

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
        } else if (
          type === "TOOL_CALL_START" ||
          type === "TOOL_CALL_ARGS" ||
          type === "TOOL_CALL_CHUNK"
        ) {
          setStatus("EXECUTING_TOOL");
          const callId = event.tool_call_id || event.toolCallId || "tool-call";
          const callName = event.tool_call_name || event.toolCallName || "tool";
          const args = event.args || {};

          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === "assistant") {
              const existingCalls = last.toolCalls || [];
              const foundIdx = existingCalls.findIndex((c) => c.id === callId);
              let updatedCalls: ToolCallRecord[];
              if (foundIdx >= 0) {
                updatedCalls = [...existingCalls];
                updatedCalls[foundIdx] = {
                  ...updatedCalls[foundIdx],
                  name: callName || updatedCalls[foundIdx].name,
                  args: { ...updatedCalls[foundIdx].args, ...args },
                };
              } else {
                updatedCalls = [
                  ...existingCalls,
                  { id: callId, name: callName, args },
                ];
              }
              return [
                ...prev.slice(0, -1),
                { ...last, toolCalls: updatedCalls },
              ];
            } else {
              return [
                ...prev,
                {
                  id: `msg-${Date.now()}`,
                  role: "assistant",
                  text: "",
                  toolCalls: [{ id: callId, name: callName, args }],
                  timestamp: new Date().toISOString(),
                },
              ];
            }
          });
        } else if (type === "TOOL_CALL_RESULT" || type === "TOOL_CALL_END") {
          setStatus("AWAITING_LLM");
          const callId = event.tool_call_id || event.toolCallId;
          const result = event.result ?? event.output;

          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === "assistant" && last.toolCalls) {
              const updatedCalls = last.toolCalls.map((c) =>
                !callId || c.id === callId ? { ...c, result } : c
              );
              return [
                ...prev.slice(0, -1),
                { ...last, toolCalls: updatedCalls },
              ];
            }
            return prev;
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

