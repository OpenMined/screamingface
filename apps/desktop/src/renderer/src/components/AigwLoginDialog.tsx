import { useEffect, useState } from 'react';
import type { AigwSessionController } from '@/hooks/use-aigw-session';
import { useToast } from '@/hooks/use-toast';

interface AigwLoginDialogProps {
  open: boolean;
  session: AigwSessionController;
  onClose: () => void;
  onSignedIn?: () => void;
}

export function AigwLoginDialog({ open, session, onClose, onSignedIn }: AigwLoginDialogProps) {
  const [username, setUsername] = useState(session.username ?? '');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [gatewayUrl, setGatewayUrl] = useState(session.gatewayUrl);
  const [showUrl, setShowUrl] = useState(false);
  const [allowPlaintextStorage, setAllowPlaintextStorage] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();
  const plaintextStorageNeedsConsent = remember && !session.secureStorageAvailable;

  useEffect(() => {
    if (!open) return;
    setUsername(session.username ?? '');
    setPassword('');
    setGatewayUrl(session.gatewayUrl);
    setAllowPlaintextStorage(false);
    setError(session.lastError);
  }, [open, session.gatewayUrl, session.lastError, session.username]);

  if (!open) return null;

  const onSubmit = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      if (plaintextStorageNeedsConsent && !allowPlaintextStorage) {
        setError(
          'OS-provided encryption is unavailable. Confirm plaintext storage or turn off saving.',
        );
        return;
      }
      const trimmedGatewayUrl = gatewayUrl.trim();
      if (trimmedGatewayUrl && trimmedGatewayUrl !== session.gatewayUrl) {
        await session.setGatewayUrl(trimmedGatewayUrl);
      }
      const loginOptions = plaintextStorageNeedsConsent
        ? { persist: remember, allowPlaintextStorage }
        : { persist: remember };
      const result = await session.login(username.trim(), password, loginOptions);
      if (!result.ok) {
        setError(result.message);
        return;
      }
      setPassword('');
      onClose();
      toast({ variant: 'success', title: 'Signed in to AIGateway' });
      if (result.warning) {
        toast({
          variant: 'warning',
          title: result.warning.includes('not saved')
            ? 'Password not saved'
            : 'Credentials saved without OS encryption',
          description: result.warning,
        });
      }
      onSignedIn?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 px-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-5 shadow-2xl">
        <div className="mb-4">
          <h2 className="font-heading text-base font-semibold text-foreground">
            Sign in to AIGateway
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Desktop keeps you signed in by refreshing short-lived gateway sessions. Save your
            password only if you want automatic login after restart.
          </p>
        </div>

        <form onSubmit={onSubmit} className="space-y-3">
          <div>
            <label
              className="mb-1 block text-xs font-medium text-foreground"
              htmlFor="aigw-username"
            >
              Username
            </label>
            <input
              id="aigw-username"
              value={username}
              onChange={(event) => {
                setUsername(event.target.value);
                setError(null);
              }}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              autoComplete="username"
              autoFocus
            />
          </div>

          <div>
            <label
              className="mb-1 block text-xs font-medium text-foreground"
              htmlFor="aigw-password"
            >
              Password
            </label>
            <input
              id="aigw-password"
              type="password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
                setError(null);
              }}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              autoComplete="current-password"
            />
          </div>

          <button
            type="button"
            onClick={() => setShowUrl((value) => !value)}
            className="text-xs font-medium text-chart-1 hover:text-chart-1/80"
          >
            {showUrl ? 'Hide AIGateway URL' : 'Configure AIGateway URL'}
          </button>

          {showUrl && (
            <div>
              <label className="mb-1 block text-xs font-medium text-foreground" htmlFor="aigw-url">
                URL
              </label>
              <input
                id="aigw-url"
                value={gatewayUrl}
                onChange={(event) => {
                  setGatewayUrl(event.target.value);
                  setError(null);
                }}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                autoComplete="off"
              />
            </div>
          )}

          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={remember}
              onChange={(event) => {
                setRemember(event.target.checked);
                if (!event.target.checked) setAllowPlaintextStorage(false);
              }}
            />
            Save password on this device for future launches
          </label>

          <p className="text-xs text-muted-foreground">
            {remember
              ? session.secureStorageAvailable
                ? 'Saved with OS-provided encryption. Session tokens are not written to disk.'
                : 'OS-provided encryption is unavailable. Saving will write the password to local plaintext config.'
              : 'Not saved to disk. Desktop keeps credentials in memory for this app session only.'}
          </p>

          {plaintextStorageNeedsConsent && (
            <label className="flex items-start gap-2 rounded-md border border-chart-2/40 bg-chart-2/10 px-3 py-2 text-xs text-foreground">
              <input
                className="mt-0.5"
                type="checkbox"
                checked={allowPlaintextStorage}
                onChange={(event) => setAllowPlaintextStorage(event.target.checked)}
              />
              <span>I understand this will save my AIGateway password in plaintext.</span>
            </label>
          )}

          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted/50 hover:text-foreground"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={
                busy ||
                !username.trim() ||
                !password ||
                (plaintextStorageNeedsConsent && !allowPlaintextStorage)
              }
              className="rounded-md bg-chart-1 px-3 py-1.5 text-xs font-semibold text-background hover:bg-chart-1/90 disabled:opacity-60"
            >
              {busy ? 'Signing in...' : 'Sign in'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
