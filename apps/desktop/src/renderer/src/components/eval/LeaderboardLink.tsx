// apps/desktop/src/renderer/src/components/eval/LeaderboardLink.tsx
//
// "Check the latest leaderboard" CTA for Eval Studio (SF-298 / SF-311). Points at
// the configured public scoreboard (reused via useScoreboardUrl) and opens it in
// the system browser through the main-process shell.openExternal IPC — never a
// raw window.open against the external CORS host. Styled as the primary amber CTA
// (square, hairline, no shadow): the leaderboard is the thing to look at, so it
// earns the one --mark spark instead of a faint inline link.

import { ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
    <Button
      type="button"
      variant="default"
      size="sm"
      onClick={open}
      disabled={!scoreboardUrl}
      className={className}
    >
      <ExternalLink className="h-3.5 w-3.5" />
      Check the latest leaderboard
    </Button>
  );
}
