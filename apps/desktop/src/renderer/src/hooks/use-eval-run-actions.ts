// apps/desktop/src/renderer/src/hooks/use-eval-run-actions.ts
//
// Mutations on eval runs: toggle favorite (PATCH) and delete (DELETE). Both go
// through the main-process server fetch and surface failures as error toasts.
// Callers refresh the runs list on success.
import { useCallback } from 'react';
import { useServerStatus } from '@/hooks/use-server-status';
import { useToast } from '@/hooks/use-toast';

function serverBase(info: ReturnType<typeof useServerStatus>['info']): string | null {
  if (!info) return null;
  const host = info.host === '0.0.0.0' ? 'localhost' : info.host;
  return `${info.scheme}://${host}:${info.port}`;
}

export function useEvalRunActions() {
  const { info } = useServerStatus();
  const base = serverBase(info);
  const { toast } = useToast();

  const toggleFavorite = useCallback(
    async (id: string, favorite: boolean): Promise<boolean> => {
      if (!base) return false;
      try {
        const res = await window.electronAPI.server.fetch(`${base}/eval_runs/${id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ favorite }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.body}`);
        return true;
      } catch (e) {
        toast({
          variant: 'error',
          title: 'Could not update favorite',
          description: (e as Error).message,
        });
        return false;
      }
    },
    [base, toast],
  );

  const deleteRun = useCallback(
    async (id: string): Promise<boolean> => {
      if (!base) return false;
      try {
        const res = await window.electronAPI.server.fetch(`${base}/eval_runs/${id}`, {
          method: 'DELETE',
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.body}`);
        return true;
      } catch (e) {
        toast({
          variant: 'error',
          title: 'Could not delete run',
          description: (e as Error).message,
        });
        return false;
      }
    },
    [base, toast],
  );

  const saveExpression = useCallback(
    async (id: string, url4Expression: string): Promise<boolean> => {
      if (!base) return false;
      try {
        const res = await window.electronAPI.server.fetch(`${base}/eval_runs/${id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url4_expression: url4Expression }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.body}`);
        return true;
      } catch (e) {
        toast({
          variant: 'error',
          title: 'Could not save expression',
          description: (e as Error).message,
        });
        return false;
      }
    },
    [base, toast],
  );

  return { toggleFavorite, deleteRun, saveExpression };
}
