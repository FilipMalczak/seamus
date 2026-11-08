import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  CornerDownLeft,
  Loader2,
  RotateCcw,
  Square,
  Terminal as TerminalIcon,
  XCircle,
} from "lucide-react";
import { getTerminalInfo, streamTerminalCommand } from "../api/client";
import type { TerminalStreamEvent } from "../api/types";

export const TERMINAL_INACTIVITY_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

export interface TerminalViewProps {
  agentId: string | null;
  sessionId: string | null;
  sessionName?: string | null;
  isActive?: boolean;
}

export interface CommandHistoryEntry {
  id: string;
  command: string;
  workingDirectory: string;
  output: Array<{ type: "stdout" | "stderr"; text: string }>;
  exitCode?: number | null;
  isRunning?: boolean;
  error?: string | null;
}

interface SessionTerminalState {
  history: CommandHistoryEntry[];
  cwd: string;
  commandHistoryList: string[];
  lastCommandTimestamp: number;
  isExecuting?: boolean;
}

// Module-level cache storing terminal state per session across tab and session switches
export const sessionTerminalCache = new Map<string, SessionTerminalState>();

const QUICK_COMMANDS = [
  { label: "ls -la", cmd: "ls -la" },
  { label: "git status", cmd: "git status" },
  { label: "pwd", cmd: "pwd" },
  { label: "inspect sandbox", cmd: "cat /etc/seamus-sandbox.json 2>/dev/null || cat /etc/os-release" },
  { label: "which tools", cmd: "which python3 node uv git npm jq 2>&1" },
  { label: "ps aux", cmd: "ps aux" },
];

export function TerminalView({ agentId, sessionId, sessionName, isActive = true }: TerminalViewProps) {
  const [cwd, setCwd] = useState<string>("/workspace");
  const [history, setHistory] = useState<CommandHistoryEntry[]>([]);
  const [inputCommand, setInputCommand] = useState<string>("");
  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const [commandHistoryList, setCommandHistoryList] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const [, setLastCommandTime] = useState<number>(Date.now());

  const terminalBodyRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const abortControllerRef = useRef<(() => void) | null>(null);

  // Focus helper ensuring input gets focus immediately without losing it
  const focusInput = useCallback(() => {
    requestAnimationFrame(() => {
      inputRef.current?.focus();
    });
  }, []);

  // Restore or initialize session state respecting the 5-minute inactivity window
  const syncSessionFromCache = useCallback(
    (targetSessionId: string) => {
      const cached = sessionTerminalCache.get(targetSessionId);
      const now = Date.now();

      if (cached) {
        const elapsed = now - cached.lastCommandTimestamp;
        if (elapsed <= TERMINAL_INACTIVITY_TIMEOUT_MS) {
          // Live session active (< 5m since last command): restore state
          setHistory(cached.history);
          setCwd(cached.cwd);
          setCommandHistoryList(cached.commandHistoryList);
          setIsExecuting(!!cached.isExecuting);
          setLastCommandTime(cached.lastCommandTimestamp);
          return;
        }
        // Inactivity exceeded 5m: invalidate expired session and create a new live session
        sessionTerminalCache.delete(targetSessionId);
      }

      // New live session
      setHistory([]);
      setCwd("/workspace");
      setCommandHistoryList([]);
      setIsExecuting(false);
      setLastCommandTime(now);

      if (agentId) {
        getTerminalInfo(agentId, targetSessionId)
          .then((info) => {
            if (info.operational_dir) {
              setCwd(info.operational_dir);
            }
          })
          .catch(() => {
            // Fall back to /workspace
          });
      }
    },
    [agentId]
  );

  // On session change or tab activation: check 5-minute validity and restore/create
  useEffect(() => {
    if (!sessionId) {
      setHistory([]);
      return;
    }
    syncSessionFromCache(sessionId);
    if (isActive) {
      focusInput();
    }
  }, [sessionId, isActive, syncSessionFromCache, focusInput]);

  // Periodic expiration checker: if 5 minutes elapse without commands, expire live session
  useEffect(() => {
    if (!sessionId) return;
    const interval = setInterval(() => {
      const cached = sessionTerminalCache.get(sessionId);
      if (cached && cached.history.length > 0) {
        const elapsed = Date.now() - cached.lastCommandTimestamp;
        if (elapsed > TERMINAL_INACTIVITY_TIMEOUT_MS) {
          // Expire and create a new clean session
          sessionTerminalCache.delete(sessionId);
          setHistory([]);
          setCommandHistoryList([]);
          setIsExecuting(false);
          setLastCommandTime(Date.now());
        }
      }
    }, 10000);

    return () => clearInterval(interval);
  }, [sessionId]);

  // Scroll to bottom on output updates and keep focus
  useEffect(() => {
    if (terminalBodyRef.current) {
      terminalBodyRef.current.scrollTop = terminalBodyRef.current.scrollHeight;
    }
    if (isActive) {
      focusInput();
    }
  }, [history, isExecuting, isActive, focusInput]);

  const handleInterrupt = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current();
      abortControllerRef.current = null;
    }
    setIsExecuting(false);
    const now = Date.now();
    setLastCommandTime(now);

    setHistory((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      const updated = last.isRunning
        ? [
            ...prev.slice(0, -1),
            {
              ...last,
              isRunning: false,
              error: "Process interrupted by user (SIGINT)",
              exitCode: 130,
            },
          ]
        : prev;

      if (sessionId) {
        sessionTerminalCache.set(sessionId, {
          history: updated,
          cwd,
          commandHistoryList,
          lastCommandTimestamp: now,
          isExecuting: false,
        });
      }
      return updated;
    });

    focusInput();
  }, [sessionId, cwd, commandHistoryList, focusInput]);

  const executeCommand = useCallback(
    (cmdToRun: string) => {
      const trimmed = cmdToRun.trim();
      if (!agentId || !sessionId || !trimmed) {
        focusInput();
        return;
      }

      // If a command is already executing, don't overlap; prompt user
      if (isExecuting) {
        focusInput();
        return;
      }

      const now = Date.now();
      setLastCommandTime(now);

      // Handle local clear command
      if (trimmed === "clear") {
        setHistory([]);
        setInputCommand("");
        if (sessionId) {
          sessionTerminalCache.set(sessionId, {
            history: [],
            cwd,
            commandHistoryList,
            lastCommandTimestamp: now,
            isExecuting: false,
          });
        }
        focusInput();
        return;
      }

      const updatedHistoryList = [trimmed, ...commandHistoryList.filter((c) => c !== trimmed)];
      setCommandHistoryList(updatedHistoryList);
      setHistoryIndex(-1);

      const entryId = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const currentEntry: CommandHistoryEntry = {
        id: entryId,
        command: trimmed,
        workingDirectory: cwd,
        output: [],
        isRunning: true,
      };

      const nextHistory = [...history, currentEntry];
      setHistory(nextHistory);
      setInputCommand("");
      setIsExecuting(true);

      // Keep cache updated with running state and current activity timestamp
      sessionTerminalCache.set(sessionId, {
        history: nextHistory,
        cwd,
        commandHistoryList: updatedHistoryList,
        lastCommandTimestamp: now,
        isExecuting: true,
      });

      // Maintain input focus immediately after dispatch
      focusInput();

      const cancelFn = streamTerminalCommand(
        agentId,
        sessionId,
        {
          command: trimmed,
          working_directory: cwd,
        },
        (event: TerminalStreamEvent) => {
          const eventTime = Date.now();
          setLastCommandTime(eventTime);

          if (event.type === "stdout" || event.type === "stderr") {
            setHistory((prev) => {
              const updated = prev.map((item) =>
                item.id === entryId
                  ? {
                      ...item,
                      output: [...item.output, { type: event.type, text: event.data }],
                    }
                  : item
              );
              sessionTerminalCache.set(sessionId, {
                history: updated,
                cwd,
                commandHistoryList: updatedHistoryList,
                lastCommandTimestamp: eventTime,
                isExecuting: true,
              });
              return updated;
            });
          } else if (event.type === "exit") {
            const nextCwd = event.working_directory || cwd;
            if (event.working_directory) {
              setCwd(event.working_directory);
            }
            setHistory((prev) => {
              const updated = prev.map((item) =>
                item.id === entryId
                  ? {
                      ...item,
                      isRunning: false,
                      exitCode: event.exit_code,
                    }
                  : item
              );
              sessionTerminalCache.set(sessionId, {
                history: updated,
                cwd: nextCwd,
                commandHistoryList: updatedHistoryList,
                lastCommandTimestamp: eventTime,
                isExecuting: false,
              });
              return updated;
            });
            setIsExecuting(false);
            abortControllerRef.current = null;
            focusInput();
          } else if (event.type === "error") {
            setHistory((prev) => {
              const updated = prev.map((item) =>
                item.id === entryId
                  ? {
                      ...item,
                      isRunning: false,
                      error: event.message,
                      exitCode: 1,
                    }
                  : item
              );
              sessionTerminalCache.set(sessionId, {
                history: updated,
                cwd,
                commandHistoryList: updatedHistoryList,
                lastCommandTimestamp: eventTime,
                isExecuting: false,
              });
              return updated;
            });
            setIsExecuting(false);
            abortControllerRef.current = null;
            focusInput();
          }
        },
        (err: Error) => {
          const errTime = Date.now();
          setLastCommandTime(errTime);
          setHistory((prev) => {
            const updated = prev.map((item) =>
              item.id === entryId
                ? {
                    ...item,
                    isRunning: false,
                    error: err.message || "Failed to stream command",
                    exitCode: 1,
                  }
                : item
            );
            sessionTerminalCache.set(sessionId, {
              history: updated,
              cwd,
              commandHistoryList: updatedHistoryList,
              lastCommandTimestamp: errTime,
              isExecuting: false,
            });
            return updated;
          });
          setIsExecuting(false);
          abortControllerRef.current = null;
          focusInput();
        }
      );

      abortControllerRef.current = cancelFn;
    },
    [agentId, sessionId, cwd, history, isExecuting, commandHistoryList, focusInput]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      executeCommand(inputCommand);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (commandHistoryList.length > 0) {
        const nextIndex = Math.min(historyIndex + 1, commandHistoryList.length - 1);
        setHistoryIndex(nextIndex);
        setInputCommand(commandHistoryList[nextIndex] || "");
      }
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (historyIndex > 0) {
        const nextIndex = historyIndex - 1;
        setHistoryIndex(nextIndex);
        setInputCommand(commandHistoryList[nextIndex] || "");
      } else if (historyIndex === 0) {
        setHistoryIndex(-1);
        setInputCommand("");
      }
    } else if ((e.ctrlKey || e.metaKey) && e.key === "c") {
      if (isExecuting) {
        e.preventDefault();
        handleInterrupt();
      }
    } else if ((e.ctrlKey || e.metaKey) && e.key === "l") {
      e.preventDefault();
      setHistory([]);
      if (sessionId) {
        sessionTerminalCache.set(sessionId, {
          history: [],
          cwd,
          commandHistoryList,
          lastCommandTimestamp: Date.now(),
          isExecuting: false,
        });
      }
      focusInput();
    }
  };

  const handleContainerClick = () => {
    // Only auto-focus if the user is not actively selecting text
    const selection = window.getSelection();
    if (!selection || selection.toString().length === 0) {
      focusInput();
    }
  };

  if (!sessionId) {
    return (
      <div className="terminal-empty-state">
        <TerminalIcon className="size-10 text-muted" />
        <h3>No Session Selected</h3>
        <p>Select an agent session from the sidebar to inspect the active sandbox terminal.</p>
      </div>
    );
  }

  return (
    <div className="terminal-container" onClick={handleContainerClick}>
      {/* Terminal Top Control Bar */}
      <div className="terminal-header-bar">
        <div className="terminal-header-left">
          <TerminalIcon className="size-4 text-emerald-400" />
          <span className="terminal-title">Sandbox Shell</span>
          <span className="terminal-cwd-badge" title={`Current working directory: ${cwd}`}>
            {cwd}
          </span>
          {sessionName && <span className="terminal-session-label">{sessionName}</span>}
        </div>

        <div className="terminal-header-right">
          {isExecuting ? (
            <button
              type="button"
              className="terminal-btn terminal-btn-interrupt"
              onClick={(e) => {
                e.stopPropagation();
                handleInterrupt();
              }}
              title="Interrupt running command (Ctrl+C)"
            >
              <Square className="size-3.5 fill-current" />
              <span>Cancel</span>
            </button>
          ) : (
            <button
              type="button"
              className="terminal-btn"
              onClick={(e) => {
                e.stopPropagation();
                setHistory([]);
                if (sessionId) {
                  sessionTerminalCache.set(sessionId, {
                    history: [],
                    cwd,
                    commandHistoryList,
                    lastCommandTimestamp: Date.now(),
                    isExecuting: false,
                  });
                }
                focusInput();
              }}
              title="Clear terminal buffer (Ctrl+L)"
            >
              <RotateCcw className="size-3.5" />
              <span>Clear</span>
            </button>
          )}
        </div>
      </div>

      {/* Quick Action Shortcuts */}
      <div className="terminal-quick-actions">
        <span className="terminal-quick-label">Quick:</span>
        {QUICK_COMMANDS.map((q) => (
          <button
            key={q.label}
            type="button"
            className="terminal-quick-btn"
            disabled={isExecuting}
            onClick={(e) => {
              e.stopPropagation();
              executeCommand(q.cmd);
            }}
          >
            {q.label}
          </button>
        ))}
      </div>

      {/* Terminal Monospace Output Log */}
      <div
        className="terminal-body"
        ref={terminalBodyRef}
        onClick={handleContainerClick}
      >
        <div className="terminal-welcome-banner">
          <div>Seamus Interactive Sandbox Shell & Process Inspector</div>
          <div className="text-muted">
            Live session retained across tab switches (5m inactivity timeout). Output streams in real-time.
          </div>
        </div>

        {history.map((item) => (
          <div key={item.id} className="terminal-entry">
            <div className="terminal-prompt-line">
              <span className="terminal-prompt-user">sandbox</span>
              <span className="terminal-prompt-colon">:</span>
              <span className="terminal-prompt-dir">{item.workingDirectory}</span>
              <span className="terminal-prompt-symbol">$</span>
              <span className="terminal-prompt-cmd">{item.command}</span>
              {item.isRunning && (
                <span className="terminal-executing-tag">
                  <Loader2 className="size-3 animate-spin" />
                  <span>running</span>
                </span>
              )}
              {!item.isRunning && item.exitCode !== undefined && item.exitCode !== null && (
                <span
                  className={`terminal-exit-badge ${item.exitCode === 0 ? "success" : "failure"}`}
                  title={`Exit code: ${item.exitCode}`}
                >
                  {item.exitCode === 0 ? <Check className="size-3" /> : <XCircle className="size-3" />}
                  <span>{item.exitCode}</span>
                </span>
              )}
            </div>

            {item.output.length > 0 && (
              <div className="terminal-output-block">
                {item.output.map((out, idx) => (
                  <div
                    key={`${item.id}-out-${idx}`}
                    className={`terminal-output-line ${out.type === "stderr" ? "terminal-stderr" : ""}`}
                  >
                    {out.text}
                  </div>
                ))}
              </div>
            )}

            {item.error && (
              <div className="terminal-output-line terminal-stderr">
                {item.error}
              </div>
            )}
          </div>
        ))}

        {/* Current Active Command Input Line - NEVER DISABLED */}
        <div className="terminal-input-row" onClick={(e) => e.stopPropagation()}>
          <span className="terminal-prompt-user">sandbox</span>
          <span className="terminal-prompt-colon">:</span>
          <span className="terminal-prompt-dir">{cwd}</span>
          <span className="terminal-prompt-symbol">$</span>
          <input
            ref={inputRef}
            type="text"
            className="terminal-input-field"
            value={inputCommand}
            onChange={(e) => setInputCommand(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={false}
            readOnly={false}
            placeholder={
              isExecuting
                ? "Command executing (Ctrl+C to cancel)..."
                : "Type command and press Enter..."
            }
            autoFocus
            spellCheck={false}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
          />
          {isExecuting ? (
            <Loader2 className="size-4 animate-spin text-muted" />
          ) : (
            <button
              type="button"
              className="terminal-run-btn"
              onClick={() => executeCommand(inputCommand)}
              disabled={!inputCommand.trim()}
              title="Run command (Enter)"
            >
              <CornerDownLeft className="size-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
