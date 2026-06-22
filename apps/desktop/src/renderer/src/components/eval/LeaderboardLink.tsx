// apps/desktop/src/renderer/src/components/eval/LeaderboardLink.tsx
//
// "Check the latest leaderboard" affordance for Eval Studio (SF-298). Points at
// the configured public scoreboard (reused via useScoreboardUrl) and opens it in
// the system browser through the main-process shell.openExternal IPC — never a
// raw window.open against the external CORS host.
//
// Two variants:
//   - 'link'   : plain inline link (minimal chrome) — used in the empty state.
//   - 'banner' : amber "mark"-gradient pill with a periodic light sweep + hover
//                glow, for the Eval Studio header. Motion respects
//                prefers-reduced-motion.

import { ExternalLink, Trophy } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useScoreboardUrl } from '@/hooks/use-scoreboard-url';

interface Props {
  className?: string;
  variant?: 'link' | 'banner';
}

const LABEL = 'Check the latest leaderboard';

export function LeaderboardLink({ className, variant = 'link' }: Props) {
  const scoreboardUrl = useScoreboardUrl();

  const open = (): void => {
    if (scoreboardUrl) void window.electronAPI.publish.openExternal(scoreboardUrl);
  };

  if (variant === 'banner') {
    return (
      <button
        type="button"
        onClick={open}
        disabled={!scoreboardUrl}
        title={LABEL}
        className={cn(
          'group relative isolate inline-flex items-center gap-2 overflow-hidden rounded-full',
          'px-3.5 py-1.5 text-xs font-medium text-primary-foreground',
          'bg-gradient-to-r from-primary via-[#f3cd7d] to-primary',
          'ring-1 ring-primary/60 transition-all duration-300',
          'hover:scale-[1.03] hover:ring-primary hover:shadow-[0_0_18px_-3px_var(--primary)]',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          'disabled:opacity-50 disabled:hover:scale-100 disabled:hover:shadow-none',
          className,
        )}
      >
        {/* Periodic light sweep; paused for users who prefer reduced motion. */}
        <span
          aria-hidden
          className={cn(
            'pointer-events-none absolute inset-y-0 -left-1/3 w-1/3 -skew-x-12',
            'bg-gradient-to-r from-transparent via-white/40 to-transparent',
            'animate-[leaderboard-shimmer_3s_ease-in-out_infinite] motion-reduce:hidden',
          )}
        />
        <Trophy className="relative h-3.5 w-3.5" />
        <span className="relative">{LABEL}</span>
        <ExternalLink className="relative h-3 w-3 opacity-80" />
      </button>
    );
  }

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
      {LABEL}
      <ExternalLink className="h-3 w-3" />
    </button>
  );
}
