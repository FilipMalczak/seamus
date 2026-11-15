import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentStatus } from "../api/types";

export interface UseInteractionNotificationsOptions {
  status: AgentStatus;
  hasOpenBlockingArtifact: boolean;
  sessionName?: string | null;
}

const DEFAULT_TITLE = "Seamus";

/**
 * Fires Web Notifications and updates document.title when a hidden tab
 * transitions into a state awaiting user interaction or encounters an error.
 */
export function useInteractionNotifications({
  status,
  hasOpenBlockingArtifact,
  sessionName,
}: UseInteractionNotificationsOptions) {
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">(() => {
    if (typeof window === "undefined" || typeof Notification === "undefined") {
      return "unsupported";
    }
    return Notification.permission;
  });

  const prevStatusRef = useRef<AgentStatus>(status);
  const prevBlockingRef = useRef<boolean>(hasOpenBlockingArtifact);

  const requestPermission = useCallback(async () => {
    if (typeof window === "undefined" || typeof Notification === "undefined") {
      setPermission("unsupported");
      return "unsupported" as const;
    }
    const result = await Notification.requestPermission();
    setPermission(result);
    return result;
  }, []);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (typeof document !== "undefined" && !document.hidden) {
        document.title = DEFAULT_TITLE;
      }
    };
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", handleVisibilityChange);
      return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
    }
    return undefined;
  }, []);

  useEffect(() => {
    const prevStatus = prevStatusRef.current;
    const prevBlocking = prevBlockingRef.current;
    prevStatusRef.current = status;
    prevBlockingRef.current = hasOpenBlockingArtifact;

    const becameBlocking = !prevBlocking && hasOpenBlockingArtifact;
    const becameAwaitingUser = prevStatus === "AWAITING_LLM" && status === "AWAITING_USER";
    const becameError = prevStatus !== "ERROR" && status === "ERROR";

    if (!becameBlocking && !becameAwaitingUser && !becameError) {
      return;
    }
    if (typeof document === "undefined" || !document.hidden) {
      return;
    }

    const label = sessionName ? ` (${sessionName})` : "";
    const title = becameError
      ? `(Error) ${DEFAULT_TITLE}${label}`
      : `(Action Needed) ${DEFAULT_TITLE}${label}`;
    document.title = title;

    if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      const body = becameError
        ? `Session${label} encountered an error.`
        : becameBlocking
          ? `Session${label} is waiting for your artifact response.`
          : `Session${label} is ready for your input.`;
      const notif = new Notification(`Seamus${label}`, { body });
      notif.onclick = () => {
        if (typeof window !== "undefined") {
          window.focus();
        }
        notif.close();
      };
    }
  }, [status, hasOpenBlockingArtifact, sessionName]);

  return { permission, requestPermission };
}
