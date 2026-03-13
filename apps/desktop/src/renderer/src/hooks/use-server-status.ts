import { useState, useEffect, useCallback, useRef } from 'react';
import type { ServerStatus, ServerInfo } from '../../../preload/types';

export function useServerStatus() {
  const [status, setStatus] = useState<ServerStatus>('stopped');
  const [info, setInfo] = useState<ServerInfo | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const logsRef = useRef(logs);
  logsRef.current = logs;

  useEffect(() => {
    window.electronAPI.server.getStatus().then((s) => {
      setStatus(s.status);
      setInfo(s.info);
    });

    const unsub1 = window.electronAPI.server.onStatusChanged((s) => {
      setStatus(s);
      if (s === 'starting') {
        setLogs([]);
      } else if (s === 'ready') {
        // Re-fetch to get the updated info (host/port/scheme)
        window.electronAPI.server.getStatus().then((full) => setInfo(full.info));
      } else if (s === 'stopped' || s === 'error') {
        setInfo(null);
      }
    });
    const unsub2 = window.electronAPI.server.onLog((line) => {
      setLogs((prev) => {
        const next = [...prev, line];
        return next.length > 500 ? next.slice(-500) : next;
      });
    });

    return () => {
      unsub1();
      unsub2();
    };
  }, []);

  const start = useCallback(() => window.electronAPI.server.start(), []);
  const stop = useCallback(() => window.electronAPI.server.stop(), []);
  const restart = useCallback(() => window.electronAPI.server.restart(), []);
  const clearLogs = useCallback(() => setLogs([]), []);

  return { status, info, logs, start, stop, restart, clearLogs };
}
