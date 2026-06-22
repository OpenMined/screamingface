// apps/desktop/src/renderer/src/components/eval/LeaderboardLink.tsx
//
// Static "Check the latest leaderboard" affordance for Eval Studio (SF-298).
// Points at the configured public scoreboard (reused via useScoreboardUrl) and
// opens it in the system browser through the main-process shell.openExternal IPC
// — never a raw window.open against the external CORS host. Minimal chrome: a
// plain inline link, no card/banner background.

import { ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useScoreboardUrl } from '@/hooks/use-scoreboard-url';

interface Props {
  className?: string;
}

export function LeaderboardLink({ className }: Props) {
  const scoreboardUrl = useScoreboardUrl();

  const open = (): void => {
    if (scoreboardUrl) void window.electronAPI.publish.openExternal(scoreboardUrl);
  };

  return (
    <button
      type="button"
      onClick={open}
      disabled={!scoreboardUrl}
      className={cn(
        'inline-flex items-center gap-1.5 text-xs text-primary transition-colors hover:underline disabled:opacity-50',
        className,
      )}
    >
      Check the latest leaderboard
      <ExternalLink className="h-3 w-3" />
    </button>
  );
}
