// apps/desktop/src/renderer/src/hooks/use-publish-logs.ts
//
// Streams the main-process publish/scoreboard diagnostic lines (SF-277) for the
// Eval Studio "Publish logs" panel: loads the backlog on mount, then appends
// live lines, ring-buffered to the most recent 500.

import { useCallback, useEffect, useState } from 'react';

const MAX_LINES = 500;

export function usePublishLogs() {
  const [logs, setLogs] = useState<string[]>([]);

  useEffect(() => {
    let active = true;
    // Seed with the backlog, but don't clobber any live lines that raced ahead.
    void window.electronAPI.publish.getLogs().then((backlog) => {
      if (active) setLogs((prev) => (prev.length === 0 ? backlog : prev));
    });
    const unsub = window.electronAPI.publish.onLog((line) => {
      setLogs((prev) => {
        const next = [...prev, line];
        return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next;
      });
    });
    return () => {
      active = false;
      unsub();
    };
  }, []);

  const clearLogs = useCallback(() => setLogs([]), []);

  return { logs, clearLogs };
}
