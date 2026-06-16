// React state wrapper over private-data-api. Resolves the local-server base from
// useServerStatus (same helper Code Studio uses), surfaces errors as toasts, and
// refetches the list after mutations (no optimistic state — demo simplicity).
import { useCallback, useEffect, useState } from 'react';
import { useServerStatus } from '@/hooks/use-server-status';
import { useToast } from '@/hooks/use-toast';
import {
  createPrivate,
  deletePrivate,
  getPrivateContent,
  listPrivate,
  updatePrivate,
  type PrivateItem,
} from '@/lib/private-data-api';

function serverBase(info: ReturnType<typeof useServerStatus>['info']): string | null {
  if (!info) return null;
  const host = info.host === '0.0.0.0' ? 'localhost' : info.host;
  return `${info.scheme}://${host}:${info.port}`;
}

export function usePrivateData() {
  const { info } = useServerStatus();
  const base = serverBase(info);
  const { toast } = useToast();
  const [items, setItems] = useState<PrivateItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refresh = useCallback(async () => {
    if (!base) return;
    try {
      setItems(await listPrivate(base));
      setError(null);
    } catch (e) {
      setError(e as Error);
    } finally {
      setLoading(false);
    }
  }, [base]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = useCallback(
    async (label?: string): Promise<string | null> => {
      if (!base) return null;
      try {
        const res = await createPrivate(base, { label: label || null, content: '' });
        await refresh();
        return res.uuid;
      } catch (e) {
        toast({ variant: 'error', title: 'Create failed', description: (e as Error).message });
        return null;
      }
    },
    [base, refresh, toast],
  );

  const update = useCallback(
    async (
      uuid: string,
      payload: { label?: string | null; content?: string },
    ): Promise<boolean> => {
      if (!base) return false;
      try {
        await updatePrivate(base, uuid, payload);
        await refresh();
        return true;
      } catch (e) {
        toast({ variant: 'error', title: 'Save failed', description: (e as Error).message });
        return false;
      }
    },
    [base, refresh, toast],
  );

  const remove = useCallback(
    async (uuid: string): Promise<boolean> => {
      if (!base) return false;
      try {
        await deletePrivate(base, uuid);
        await refresh();
        return true;
      } catch (e) {
        toast({ variant: 'error', title: 'Delete failed', description: (e as Error).message });
        return false;
      }
    },
    [base, refresh, toast],
  );

  const getContent = useCallback(
    async (uuid: string): Promise<string> => (base ? getPrivateContent(base, uuid) : ''),
    [base],
  );

  return {
    items,
    loading,
    error,
    ready: base !== null,
    create,
    update,
    remove,
    getContent,
    refresh,
  };
}
