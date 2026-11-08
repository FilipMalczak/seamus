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

interface TerminalViewProps {
  agentId: string | null;
  sessionId: string | null;
  sessionName?: string | null;
}

interface CommandHistoryEntry {
  id: string;
  command: string;
  workingDirectory: string;
  output: Array<{ type: "stdout" | "stderr"; text: string }>;
  exitCode?: number | null;
  isRunning?: boolean;
  error?: string | null;
}

const QUICK_COMMANDS = [
  { label: "ls -la", cmd: "ls -la" },
  { label: "git status", cmd: "git status" },
  { label: "pwd", cmd: "pwd" },
  { label: "inspect sandbox", cmd: "cat /etc/seamus-sandbox.json 2>/dev/null || cat /etc/os-release" },
  { label: "which tools", cmd: "which python3 node uv git npm jq 2>&1" },
  { label: "ps aux", cmd: "ps aux" },
];

export function TerminalView({ agentId, sessionId, sessionName }: TerminalViewProps) {
  const [cwd, setCwd] = useState<string>("/workspace");
  const [history, setHistory] = useState<CommandHistoryEntry[]>([]);
  const [inputCommand, setInputCommand] = useState<string>("");
  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const [commandHistoryList, setCommandHistoryList] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);

  const terminalBodyRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const abortControllerRef = useRef<(() => void) | null>(null);

  // Load initial working directory info
  useEffect(() => {
    if (!agentId || !sessionId) return;
    let active = true;
    getTerminalInfo(agentId, sessionId)
      .then((info) => {
        if (active && info.operational_dir) {
          setCwd(info.operational_dir);
        }
      })
      .catch(() => {
        // Fall back to /workspace if info endpoint fails
      });
    return () => {
      active = false;
    };
  }, [agentId, sessionId]);

  // Scroll to bottom on updates
  useEffect(() => {
    if (terminalBodyRef.current) {
      terminalBodyRef.current.scrollTop = terminalBodyRef.current.scrollHeight;
    }
  }, [history, isExecuting]);

  // Cleanup active stream on unmount or session switch
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current();
        abortControllerRef.current = null;
      }
    };
  }, [sessionId]);

  const handleInterrupt = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current();
      abortControllerRef.current = null;
    }
    setIsExecuting(false);
    setHistory((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      if (last.isRunning) {
        return [
          ...prev.slice(0, -1),
          {
            ...last,
            isRunning: false,
            error: "Process interrupted by user (SIGINT)",
            exitCode: 130,
          },
        ];
      }
      return prev;
    });
  }, []);

  const executeCommand = useCallback(
    (cmdToRun: string) => {
      const trimmed = cmdToRun.trim();
      if (!agentId || !sessionId || !trimmed) return;

      // Handle local clear command
      if (trimmed === "clear") {
        setHistory([]);
        setInputCommand("");
        return;
      }

      setCommandHistoryList((prev) => [trimmed, ...prev.filter((c) => c !== trimmed)]);
      setHistoryIndex(-1);

      const entryId = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const currentEntry: CommandHistoryEntry = {
        id: entryId,
        command: trimmed,
        workingDirectory: cwd,
        output: [],
        isRunning: true,
      };

      setHistory((prev) => [...prev, currentEntry]);
      setInputCommand("");
      setIsExecuting(true);

      const cancelFn = streamTerminalCommand(
        agentId,
        sessionId,
        {
          command: trimmed,
          working_directory: cwd,
        },
        (event: TerminalStreamEvent) => {
          if (event.type === "stdout" || event.type === "stderr") {
            setHistory((prev) =>
              prev.map((item) =>
                item.id === entryId
                  ? {
                      ...item,
                      output: [...item.output, { type: event.type, text: event.data }],
                    }
                  : item
              )
            );
          } else if (event.type === "exit") {
            if (event.working_directory) {
              setCwd(event.working_directory);
            }
            setHistory((prev) =>
              prev.map((item) =>
                item.id === entryId
                  ? {
                      ...item,
                      isRunning: false,
                      exitCode: event.exit_code,
                    }
                  : item
              )
            );
            setIsExecuting(false);
            abortControllerRef.current = null;
          } else if (event.type === "error") {
            setHistory((prev) =>
              prev.map((item) =>
                item.id === entryId
                  ? {
                      ...item,
                      isRunning: false,
                      error: event.message,
                      exitCode: 1,
                    }
                  : item
              )
            );
            setIsExecuting(false);
            abortControllerRef.current = null;
          }
        },
        (err: Error) => {
          setHistory((prev) =>
            prev.map((item) =>
              item.id === entryId
                ? {
                    ...item,
                    isRunning: false,
                    error: err.message || "Failed to stream command",
                    exitCode: 1,
                  }
                : item
            )
          );
          setIsExecuting(false);
          abortControllerRef.current = null;
        }
      );

      abortControllerRef.current = cancelFn;
    },
    [agentId, sessionId, cwd]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (!isExecuting) {
        executeCommand(inputCommand);
      }
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
    <div className="terminal-container">
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
              onClick={handleInterrupt}
              title="Interrupt running command (Ctrl+C)"
            >
              <Square className="size-3.5 fill-current" />
              <span>Cancel</span>
            </button>
          ) : (
            <button
              type="button"
              className="terminal-btn"
              onClick={() => setHistory([])}
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
            onClick={() => executeCommand(q.cmd)}
          >
            {q.label}
          </button>
        ))}
      </div>

      {/* Terminal Monospace Output Log */}
      <div
        className="terminal-body"
        ref={terminalBodyRef}
        onClick={() => inputRef.current?.focus()}
      >
        <div className="terminal-welcome-banner">
          <div>Seamus Interactive Sandbox Shell & Process Inspector</div>
          <div className="text-muted">Type commands or click quick actions below. Streams in real-time.</div>
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

        {/* Current Active Command Input Line */}
        <div className="terminal-input-row">
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
            disabled={isExecuting}
            placeholder={isExecuting ? "Executing command..." : "Type command and press Enter..."}
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
