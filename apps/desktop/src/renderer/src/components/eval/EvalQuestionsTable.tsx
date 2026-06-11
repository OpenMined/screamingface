// apps/desktop/src/renderer/src/components/eval/EvalQuestionsTable.tsx
import { Check, X } from 'lucide-react';
import type { EvalQuestion } from './types';

const TRUNC = 80;

function truncate(s: string): string {
  return s.length > TRUNC ? s.slice(0, TRUNC) + '…' : s;
}

function CorrectIcon({ correct }: { correct: boolean | null }) {
  if (correct === null) return <span className="text-muted-foreground">—</span>;
  return correct ? <Check className="h-4 w-4 text-gain" /> : <X className="h-4 w-4 text-red-400" />;
}

export function EvalQuestionsTable({ questions }: { questions: EvalQuestion[] }) {
  if (questions.length === 0) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        No questions recorded for this run yet.
      </div>
    );
  }
  return (
    <table className="w-full text-sm">
      <thead className="bg-muted/30 text-xs text-muted-foreground">
        <tr className="border-b border-border">
          <th className="w-10 px-3 py-2 text-right font-medium">#</th>
          <th className="px-3 py-2 text-left font-medium">Question</th>
          <th className="px-3 py-2 text-left font-medium">Expected</th>
          <th className="px-3 py-2 text-left font-medium">Predicted</th>
          <th className="w-12 px-3 py-2 text-center font-medium">✓</th>
        </tr>
      </thead>
      <tbody>
        {questions.map((q) => (
          <tr key={q.id} className="border-b border-border/50">
            <td className="px-3 py-2 text-right tabular-nums text-xs text-muted-foreground">
              {q.idx}
            </td>
            <td className="px-3 py-2" title={q.question}>
              {truncate(q.question)}
            </td>
            <td className="px-3 py-2 font-mono text-xs">{q.expected}</td>
            <td className="px-3 py-2 font-mono text-xs">
              {q.error ? (
                <span className="text-destructive" title={q.error}>
                  error
                </span>
              ) : (
                (q.predicted ?? <span className="text-muted-foreground">—</span>)
              )}
            </td>
            <td className="px-3 py-2 text-center">
              <div className="inline-flex">
                <CorrectIcon correct={q.correct} />
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
