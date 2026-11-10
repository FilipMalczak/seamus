import {
  BUBBLE_SEQUENCE_THRESHOLD,
  SYNTHETIC_MESSAGE_INDICATOR,
  type ChatMessage,
} from "../api/types";

export interface BubbleDescriptor {
  key: string;
  role: "user" | "assistant";
  toolCallId?: string;
}

/**
 * Extracts individual visual bubbles across a conversation.
 * Each user message, assistant reasoning block, tool call card, text bubble, or artifact
 * constitutes a distinct visual bubble in the conversational flow.
 */
export function extractBubblesFromMessages(
  messages: Array<ChatMessage>
): BubbleDescriptor[] {
  const bubbles: BubbleDescriptor[] = [];

  for (let mIdx = 0; mIdx < messages.length; mIdx++) {
    const msg = messages[mIdx];
    if (msg.threadTransition) {
      bubbles.push({ key: `transition-${mIdx}`, role: "boundary" as any });
      continue;
    }

    const isSynthetic = Boolean(
      msg.text?.startsWith(SYNTHETIC_MESSAGE_INDICATOR)
    );
    if (isSynthetic) {
      bubbles.push({ key: `synthetic-${mIdx}`, role: "boundary" as any });
      continue;
    }

    if (msg.role === "user") {
      bubbles.push({ key: msg.id || `user-${mIdx}`, role: "user" });
      continue;
    }

    if (msg.role === "assistant") {
      if (msg.parts && msg.parts.length > 0) {
        for (let pIdx = 0; pIdx < msg.parts.length; pIdx++) {
          const part = msg.parts[pIdx];
          if (part.type === "reasoning") {
            bubbles.push({ key: part.id, role: "assistant" });
          } else if (part.type === "tool_call") {
            bubbles.push({
              key: part.id,
              role: "assistant",
              toolCallId: part.toolCall?.id,
            });
          } else if (part.type === "artifact") {
            bubbles.push({ key: part.id, role: "assistant" });
          } else if (part.type === "text") {
            if (part.content && part.content.trim().length > 0) {
              bubbles.push({ key: part.id, role: "assistant" });
            }
          }
        }
      } else {
        if (msg.reasoning || msg.isReasoning) {
          bubbles.push({ key: `${msg.id}-reasoning`, role: "assistant" });
        }
        if (msg.toolCalls && msg.toolCalls.length > 0) {
          for (const tc of msg.toolCalls) {
            bubbles.push({
              key: tc.id,
              role: "assistant",
              toolCallId: tc.id,
            });
          }
        }
        if (msg.text && msg.text.trim().length > 0) {
          bubbles.push({ key: `${msg.id}-text`, role: "assistant" });
        }
      }
    }
  }

  return bubbles;
}

/**
 * Computes 1-based sequence indices for contiguous runs of bubbles by the same role.
 * If a contiguous run has a length greater than the threshold (default: BUBBLE_SEQUENCE_THRESHOLD),
 * each bubble in that run receives its 1-based index (#1, #2, ..., #N).
 * Thread transitions and synthetic messages act as sequence boundaries.
 */
export function computeBubbleSequenceIndices(
  messages: Array<ChatMessage>,
  threshold: number = BUBBLE_SEQUENCE_THRESHOLD
): Map<string, number> {
  const result = new Map<string, number>();
  const bubbles = extractBubblesFromMessages(messages);

  let currentStreakRole: string | null = null;
  let currentStreak: BubbleDescriptor[] = [];

  const flushStreak = () => {
    if (currentStreak.length > threshold) {
      currentStreak.forEach((bubble, stepIdx) => {
        result.set(bubble.key, stepIdx + 1);
        if (bubble.toolCallId && bubble.toolCallId !== bubble.key) {
          result.set(bubble.toolCallId, stepIdx + 1);
        }
      });
    }
    currentStreak = [];
    currentStreakRole = null;
  };

  for (const b of bubbles) {
    if (b.role !== "user" && b.role !== "assistant") {
      flushStreak();
      continue;
    }

    if (b.role === currentStreakRole) {
      currentStreak.push(b);
    } else {
      flushStreak();
      currentStreakRole = b.role;
      currentStreak.push(b);
    }
  }

  flushStreak();

  // Populate secondary lookup aliases for messages and tool calls
  for (let mIdx = 0; mIdx < messages.length; mIdx++) {
    const msg = messages[mIdx];
    if (msg.role === "assistant" && msg.parts) {
      for (const p of msg.parts) {
        if (p.type === "tool_call" && p.toolCall?.id) {
          const idx = result.get(p.id) ?? result.get(p.toolCall.id);
          if (idx !== undefined) {
            result.set(p.id, idx);
            result.set(p.toolCall.id, idx);
          }
        }
      }
    }
    const msgAlias =
      result.get(`${msg.id}-text`) ??
      result.get(msg.id) ??
      (msg.parts?.length === 1 ? result.get(msg.parts[0].id) : undefined);
    if (msgAlias !== undefined) {
      result.set(msg.id, msgAlias);
    }
  }

  return result;
}

/**
 * Format timestamp into localized HH:MM:SS format with seconds precision.
 */
export function formatBubbleTime(isoString?: string | null): string {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "";
  }
}

/**
 * Format full date and time for accessibility tooltip.
 */
export function formatFullDate(isoString?: string | null): string {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return `${d.toLocaleString()} (${d.toISOString()})`;
  } catch {
    return isoString;
  }
}
