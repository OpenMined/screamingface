// apps/desktop/src/renderer/src/components/Url4Field.tsx
//
// Public url4 field used everywhere a url4 expression is shown or edited
// (SF-249). Lazy-loads the Monaco editor so its ~7MB chunk only loads when a
// url4 first appears; until then (and as a graceful fallback) it renders the
// raw expression as wrapped monospace text. Read-only unless given onChange.
import { Suspense, lazy } from 'react';
import { CopyButton } from '@/components/CopyButton';

const Url4MonacoEditor = lazy(() => import('@/components/Url4MonacoEditor'));

interface Url4FieldProps {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  serverUrl: string;
  className?: string;
  /** Upper bound for the editor's auto-grow height; null = grow to full content (no inner scrollbar). Defaults to 360. */
  maxContentHeight?: number | null;
}

export function Url4Field(props: Url4FieldProps) {
  return (
    <div className="relative">
      {props.value.length > 0 && (
        <CopyButton value={props.value} className="absolute right-1 top-1 z-10 bg-card/70" />
      )}
      <Suspense
        fallback={
          <code className="block whitespace-pre-wrap break-words font-mono text-xs text-muted-foreground">
            {props.value}
          </code>
        }
      >
        <Url4MonacoEditor {...props} />
      </Suspense>
    </div>
  );
}
