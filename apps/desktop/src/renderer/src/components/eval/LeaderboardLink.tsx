// apps/desktop/src/renderer/src/components/eval/LeaderboardLink.tsx
//
// "Check the latest leaderboard" CTA for Eval Studio (SF-298 / SF-311 / SF-314).
// Points at the configured public scoreboard (reused via useScoreboardUrl) and
// opens it in the system browser through the main-process shell.openExternal IPC
// — never a raw window.open against the external CORS host.
//
// NOTE: this button is a DELIBERATE, user-approved brand override (SF-314): a
// glossy, rounded, animated amber pill so the leaderboard "pops". It intentionally
// breaks the square/flat/no-motion design rules — but ONLY here; the rest of the
// app keeps the brand. The sheen/glow keyframes live in globals.css (sf-cta-*) and
// respect prefers-reduced-motion.

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
        'sf-cta-glow group relative inline-flex items-center gap-1.5 overflow-hidden rounded-full',
        'bg-gradient-to-b from-[#f4c264] via-[#e0a23c] to-[#c9821f]',
        'px-4 py-1.5 text-sm font-semibold text-[#241803]',
        'transition-transform duration-200 ease-out [animation:sf-cta-glow_3s_ease-in-out_infinite]',
        'hover:scale-[1.04] hover:brightness-110 active:scale-100',
        'disabled:cursor-default disabled:opacity-50 disabled:[animation:none] disabled:hover:scale-100',
        className,
      )}
    >
      {/* Top gloss highlight */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-1/2 bg-gradient-to-b from-white/35 to-transparent"
      />
      {/* Animated sheen sweep */}
      <span
        aria-hidden
        className="sf-cta-sheen pointer-events-none absolute inset-y-0 left-0 w-1/4 bg-white/45 blur-[2px] [animation:sf-cta-sheen_3s_ease-in-out_infinite] group-disabled:[animation:none]"
      />
      <ExternalLink className="relative h-4 w-4" />
      <span className="relative">Check the latest leaderboard</span>
    </button>
  );
}
