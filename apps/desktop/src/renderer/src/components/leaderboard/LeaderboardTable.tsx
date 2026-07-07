// apps/desktop/src/renderer/src/components/leaderboard/LeaderboardTable.tsx
//
// Pure presentational table for one benchmark's ranked entries. Modeled on
// EvalQuestionsTable.tsx's markup (plain <table> + Tailwind — this app has no
// shared Table primitive). `verified_by_openmined` is rendered as plain text
// for this first pass; a designed badge treatment is deferred.

import type { LeaderboardEntry } from '../../../../preload/types';

const TRUNC = 80;

function truncate(s: string): string {
  return s.length > TRUNC ? s.slice(0, TRUNC) + '…' : s;
}

function formatAccuracy(accuracy: number): string {
  return `${(accuracy * 100).toFixed(1)}%`;
}

function formatSubmittedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString()}`;
}

export function LeaderboardTable({ entries }: { entries: LeaderboardEntry[] }) {
  if (entries.length === 0) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        No submissions yet for this benchmark.
      </div>
    );
  }
  return (
    <table className="w-full text-sm">
      <thead className="bg-muted/30 text-xs text-muted-foreground">
        <tr className="border-b border-border">
          <th className="w-10 px-3 py-2 text-right font-medium">#</th>
          <th className="px-3 py-2 text-left font-medium">Spec</th>
          <th className="px-3 py-2 text-right font-medium">Accuracy</th>
          <th className="px-3 py-2 text-right font-medium">Questions</th>
          <th className="px-3 py-2 text-left font-medium">Providers</th>
          <th className="px-3 py-2 text-left font-medium">Submitted</th>
          <th className="px-3 py-2 text-left font-medium">Submitted by</th>
          <th className="px-3 py-2 text-left font-medium">Verified</th>
          <th className="px-3 py-2 text-left font-medium">url4</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((entry) => (
          <tr key={entry.specId} className="border-b border-border/50">
            <td className="px-3 py-2 text-right tabular-nums text-xs text-muted-foreground">
              {entry.rank}
            </td>
            <td className="px-3 py-2 font-mono text-xs">{entry.specId}</td>
            <td className="px-3 py-2 text-right tabular-nums">{formatAccuracy(entry.accuracy)}</td>
            <td className="px-3 py-2 text-right tabular-nums">{entry.totalQuestions}</td>
            <td className="px-3 py-2">{entry.ranWithProviders.join(', ')}</td>
            <td className="px-3 py-2 text-xs text-muted-foreground">
              {formatSubmittedAt(entry.submittedAt)}
            </td>
            <td className="px-3 py-2">
              {entry.submittedBy ?? <span className="text-muted-foreground">—</span>}
            </td>
            <td className="px-3 py-2 text-xs">{entry.verifiedByOpenmined ? '✓ verified' : ''}</td>
            <td className="px-3 py-2 font-mono text-xs" title={entry.url4Expression}>
              {truncate(entry.url4Expression)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
