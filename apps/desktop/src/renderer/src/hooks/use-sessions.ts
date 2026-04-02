import { useState, useEffect, useCallback } from 'react';
import type { SessionInfo, SessionType } from '../../../preload/types';

export function useSessions() {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [logs, setLogs] = useState<Record<string, string[]>>({});

  useEffect(() => {
    window.electronAPI.session.list().then(setSessions);
    const unsub1 = window.electronAPI.session.onSessionsChanged(setSessions);
    const unsub2 = window.electronAPI.session.onLog((id, line) => {
      setLogs((prev) => {
        const lines = prev[id] || [];
        const next = [...lines, line];
        return { ...prev, [id]: next.length > 500 ? next.slice(-500) : next };
      });
    });
    return () => { unsub1(); unsub2(); };
  }, []);

  const createSession = useCallback(
    async (
      type: SessionType,
      workingDir: string,
      pluginConfig?: Record<string, Record<string, unknown>>,
    ) => {
      return window.electronAPI.session.create(type, workingDir, pluginConfig);
    },
    [],
  );

  const terminateSession = useCallback(async (id: string) => {
    await window.electronAPI.session.terminate(id);
  }, []);

  const removeSession = useCallback(async (id: string) => {
    await window.electronAPI.session.remove(id);
    setLogs((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, []);

  const clearLogs = useCallback((id: string) => {
    setLogs((prev) => ({ ...prev, [id]: [] }));
  }, []);

  return { sessions, logs, createSession, terminateSession, removeSession, clearLogs };
}
